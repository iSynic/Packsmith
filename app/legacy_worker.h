// Internal adapter compiled inside the filesystem-owning worker.
// The Objective-C helper only sends bounded decoded stream frames.
struct LegacyChild {
    QProcess process;
    HANDLE job = nullptr;
    QByteArray pending;
    bool sentCancel = false, complete = false;
    QElapsedTimer cancelClock;
    explicit LegacyChild(QJsonObject request) {
        job = CreateJobObjectW(nullptr, nullptr);
        require(job, "Cannot create legacy decoder job");
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        require(SetInformationJobObject(job, JobObjectExtendedLimitInformation, &limits,
                                        sizeof(limits)),
                winError("Protect legacy decoder lifetime"));
        process.setProgram(QCoreApplication::applicationDirPath() + "/legacy/xad-stream.exe");
        process.start();
        require(process.waitForStarted(5000), "Cannot start the packaged legacy decoder");
        HANDLE handle =
            OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, FALSE, DWORD(process.processId()));
        bool assigned = handle && AssignProcessToJobObject(job, handle);
        if (handle)
            CloseHandle(handle);
        require(assigned, winError("Cannot protect legacy decoder process"));
        request["protocol"] = 1;
        process.write(QJsonDocument(request).toJson(QJsonDocument::Compact) + "\n");
    }
    ~LegacyChild() {
        if (job)
            CloseHandle(job);
        if (process.state() != QProcess::NotRunning) {
            process.kill();
            process.waitForFinished(1000);
        }
    }
    bool next(QJsonObject &obj) {
        for (;;) {
            if (cancelled && !sentCancel) {
                sentCancel = true;
                cancelClock.start();
                process.write("{\"cancel\":true}\n");
            }
            if (sentCancel && cancelClock.elapsed() > 2500) {
                process.kill();
                require(false, "Cancelled");
            }
            auto newline = pending.indexOf('\n');
            if (newline >= 0) {
                auto line = pending.left(newline);
                pending.remove(0, newline + 1);
                QJsonParseError error;
                auto document = QJsonDocument::fromJson(line, &error);
                require(error.error == QJsonParseError::NoError && document.isObject(),
                        "Invalid legacy decoder frame");
                obj = document.object();
                return true;
            }
            require(pending.size() < 256 * 1024, "Legacy decoder frame exceeds limit");
            if (process.state() != QProcess::NotRunning)
                process.waitForReadyRead(30);
            pending += process.readAllStandardOutput();
            process.readAllStandardError();
            if (process.state() == QProcess::NotRunning && pending.isEmpty()) {
                require(!cancelled, "Cancelled");
                require(process.exitStatus() == QProcess::NormalExit && process.exitCode() == 0 && complete,
                        "Legacy decoder stopped before verification");
                return false;
            }
        }
    }
};
static bool usesLegacy(const QJsonObject &request) {
    QString path = request["archive"].toString().toLower();
    return request["engine"].toString() == "xad" || path.endsWith(".sit") ||
           path.endsWith(".hqx") || path.endsWith(".sitx") || path.endsWith(".bin") ||
           path.endsWith(".cpt") || path.endsWith(".lha") || path.endsWith(".lzh") || path.endsWith(".lzx");
}
static QByteArray appleDouble(quint32 resourceSize, const QByteArray &finder, bool resource) {
    require(finder.isEmpty() || finder.size() == 32, "Unsupported Finder metadata length");
    int count = (!finder.isEmpty() ? 1 : 0) + (resource ? 1 : 0);
    QByteArray bytes(26 + 12 * count, 0);
    qToBigEndian<quint32>(0x00051607, bytes.data());
    qToBigEndian<quint32>(0x00020000, bytes.data() + 4);
    qToBigEndian<quint16>(count, bytes.data() + 24);
    int descriptor = 26, offset = bytes.size();
    if (!finder.isEmpty()) {
        qToBigEndian<quint32>(9, bytes.data() + descriptor);
        qToBigEndian<quint32>(offset, bytes.data() + descriptor + 4);
        qToBigEndian<quint32>(32, bytes.data() + descriptor + 8);
        descriptor += 12;
        offset += 32;
    }
    if (resource) {
        qToBigEndian<quint32>(2, bytes.data() + descriptor);
        qToBigEndian<quint32>(offset, bytes.data() + descriptor + 4);
        qToBigEndian<quint32>(resourceSize, bytes.data() + descriptor + 8);
    }
    bytes += finder;
    return bytes;
}
static void writeBytes(Output *out, const QByteArray &bytes) {
    UInt32 done = 0;
    check(out->Write(bytes.constData(), bytes.size(), &done), "Write decoded legacy stream");
    require(done == UInt32(bytes.size()), "Incomplete legacy output write");
}
static void setLegacyTime(HANDLE handle, const QJsonObject &row) {
    if (!row.contains("modified_ms"))
        return;
    qint64 ms = row["modified_ms"].toInteger();
    require(ms >= -11644473600000LL && ms <= 1833029933770955LL,
            "Unsupported legacy modification time");
    quint64 ticks = quint64(ms + 11644473600000LL) * 10000;
    FILETIME time{DWORD(ticks), DWORD(ticks >> 32)};
    require(SetFileTime(handle, nullptr, nullptr, &time),
            winError("Preserve legacy timestamp"));
}
static void setLegacyTime(Output *out, const QJsonObject &row) { setLegacyTime(out->handle, row); }
static QString legacySafePath(const QJsonObject &row) {
    require(!row["absolute"].toBool(), "Absolute legacy entry path is unsafe");
    QStringList parts;
    for (auto value : row["components"].toArray()) {
        QString part = value.toString();
        require(!part.isEmpty() && part != "." && part != ".." && !part.contains(QChar(0)),
                "Unsafe legacy path component");
        // A slash or colon inside a classic Mac filename is a character, not a separator/ADS.
        part.replace("/", "~002f");
        part.replace("\\", "~005c");
        part.replace(":", "~003a");
        parts.append(part);
    }
    require(!parts.isEmpty(), "Missing legacy filename components");
    return parts.join('/');
}
static void legacyJob(const QJsonObject &request) {
    QString operation = request["operation"].toString();
    const QString filenamePolicy = request["filename_policy"].toString("escaped");
    const QString forkStyle = request["resource_fork_style"].toString("appledouble");
    require(filenamePolicy == "escaped" || filenamePolicy == "readable", "Unknown filename policy", "invalid_request");
    require(forkStyle == "appledouble" || forkStyle == "rsrc", "Unknown resource fork style", "invalid_request");
    const bool readable = filenamePolicy == "readable", visible = forkStyle == "rsrc";
    const QString preservation = visible
        ? "Resource forks and file FinderInfo are in .rsrc AppleDouble files. Resource-only files have no empty data placeholder; folder FinderInfo remains in the mapping report. Available file/folder modification times are applied; classic timezone/DST limitations remain."
        : "Data and resource forks and FinderInfo are preserved with ._ AppleDouble sidecars and empty data placeholders for resource-only files. Available file/folder modification times are applied; classic timezone/DST limitations remain.";
    phase("listing");
    require(operation == "list" || operation == "extract" || operation == "test",
            "Legacy formats support reading, extraction and integrity checks; creation/editing is "
            "unavailable");
    ComPtr<Input> original;
    original.p = new Input(request["archive"].toString());
    QString fingerprint = QString::fromLatin1(fileHash(request["archive"].toString()).toHex());
    if (request.contains("fingerprint"))
        require(fingerprint == request["fingerprint"].toString(),
                "Archive changed; reopen it before using the selected entry IDs");
    QJsonObject decoder = request;
    if (!decoder.value("ids").isArray()) decoder["ids"] = QJsonArray{};
    decoder["operation"] = operation == "extract" ? "stream" : operation;
    LegacyChild child(decoder);
    QVector<QJsonObject> rows;
    QSet<UInt32> selected;
    std::unique_ptr<SafeTree> parent, tree;
    std::unique_ptr<Staging> stage;
    QMap<UInt32, QString> names;
    QSet<UInt32> verified;
    QString format;
    ComPtr<Output> output;
    QCryptographicHash hash(QCryptographicHash::Sha256);
    quint64 count = 0, total = 0, completed = 0;
    QMap<UInt32, QByteArray> dataHashes, resourceHashes;
    QMap<UInt32, bool> dataChecksums, resourceChecksums;
    QJsonObject coverage;
    UInt32 currentId = 0;
    QString currentPart;
    QJsonObject frame;
    bool ready = false, reading = false;
    while (child.next(frame)) {
        QString event = frame["event"].toString();
        if (event == "error" || event == "cancelled") {
            for (const auto &key : {"format", "method", "method_id"}) if (frame.contains(key)) errorContext[key] = frame[key];
            throw WorkerError(frame["code"].toString("decode_failed"), frame["message"].toString(), frame["id"].toInteger(-1), frame["part"].toString());
        }
        if (event == "progress") {
            emitEvent(frame);
        } else if (event == "entries") {
            require(!ready, "Unexpected legacy listing batch");
            for (auto v : frame["items"].toArray()) {
                auto row = v.toObject();
                require(row["id"].toInteger(-1) == rows.size(), "Unexpected legacy entry identity");
                rows.append(row);
            }
            if (operation == "list")
                emitEvent(frame);
        } else if (event == "ready") {
            require(!ready && frame["count"].toInteger(-1) == rows.size(),
                    "Invalid legacy listing count");
            ready = true;
            format = frame["format"].toString();
            coverage["outer_format"] = frame["outer_format"];
            coverage["wrapper_chain"] = frame["wrapper_chain"];
            if (operation == "extract") {
                for (auto id : request["ids"].toArray()) {
                    auto n = id.toInteger(-1);
                    require(n >= 0 && n < rows.size(), "Invalid legacy entry ID", "invalid_id");
                    selected.insert(UInt32(n));
                }
                if (selected.isEmpty())
                    for (int i = 0; i < rows.size(); ++i)
                        selected.insert(i);
                QList<QJsonArray> folders;
                for (auto id : selected)
                    if (rows[id]["directory"].toBool())
                        folders.append(rows[id]["components"].toArray());
                for (int i = 0; i < rows.size(); ++i)
                    for (const auto &folder : folders) {
                        auto components = rows[i]["components"].toArray();
                        bool descendant = components.size() > folder.size();
                        for (int j = 0; descendant && j < folder.size(); ++j)
                            descendant = components[j] == folder[j];
                        if (descendant)
                            selected.insert(i);
                    }
                QVector<Entry> entries;
                QSet<UInt32> sidecars;
                for (int i = 0; i < rows.size(); ++i)
                    if (selected.contains(i)) {
                        auto row = rows[i];
                        QString safe = legacySafePath(row);
                        require(!row["link"].toBool(),
                                "Legacy links or special files are not supported for extraction");
                        auto finder =
                            QByteArray::fromBase64(row["finder_info"].toString().toLatin1());
                        require(finder.isEmpty() || finder.size() == 32, "Invalid Finder metadata");
                        entries.append({UInt32(i),
                                        safe,
                                        row["size"].toString().toULongLong(),
                                        row["directory"].toBool(),
                                        row["encrypted"].toBool(),
                                        false,
                                        {}, {}});
                        for (const auto &component : row["components"].toArray()) entries.last().components.append(component.toString());
                        if (row["has_resource"].toBool() || (!visible && !finder.isEmpty()) || (visible && !row["directory"].toBool() && !finder.isEmpty()))
                            sidecars.insert(i);
                        total += row["size"].toString().toULongLong() +
                                 row["resource_size"].toString().toULongLong();
                    }
                names = planNames(entries, sidecars, visible, readable);
                QString destination = request["destination"].toString();
                require(!destination.isEmpty(), "Destination is required");
                parent = std::make_unique<SafeTree>(destination);
                stage = std::make_unique<Staging>(parent->root);
                tree = std::make_unique<SafeTree>(stage->temp.path());
                for (const auto &e : entries) {
                    QString name = names[e.id];
                    int slash = name.lastIndexOf('/');
                    if (slash >= 0)
                        tree->directory(name.left(slash));
                    if (e.dir)
                        tree->directory(name);
                    if (!e.dir && !rows[e.id]["has_data"].toBool() && (!visible || !rows[e.id]["has_resource"].toBool())) {
                        Output empty(QDir(tree->root).filePath(name));
                        require(empty.flush(), "Flush empty data fork");
                        setLegacyTime(&empty, rows[e.id]);
                    }
                    if (sidecars.contains(e.id) && !rows[e.id]["has_resource"].toBool()) {
                        Output sidecar(QDir(tree->root).filePath(sidecarName(name, visible)));
                        writeBytes(&sidecar,
                                   appleDouble(0,
                                               QByteArray::fromBase64(
                                                   rows[e.id]["finder_info"].toString().toLatin1()),
                                               false));
                        require(sidecar.flush(), "Flush Finder metadata");
                        setLegacyTime(&sidecar, rows[e.id]);
                    }
                }
            }
        } else if (event == "begin") {
            require(ready && operation == "extract" && !reading, "Unexpected legacy fork start");
            currentId = UInt32(frame["id"].toInteger(-1));
            currentPart = frame["part"].toString();
            phase("decoding", currentId, currentPart);
            require(selected.contains(currentId) &&
                        (currentPart == "data" || currentPart == "resource"),
                    "Unexpected decoded legacy fork");
            QString path = QDir(tree->root)
                               .filePath(currentPart == "data" ? names[currentId]
                                                               : sidecarName(names[currentId], visible));
            if (currentPart == "data")
                output.p = new Output(path);
            else {
                output.p = new Output(path);
                writeBytes(output.p,
                           appleDouble(0,
                                       QByteArray::fromBase64(
                                           rows[currentId]["finder_info"].toString().toLatin1()),
                                       true));
            }
            count = 0;
            hash.reset();
            reading = true;
        } else if (event == "chunk") {
            require(reading && frame["id"].toInteger(-1) == currentId &&
                        frame["part"].toString() == currentPart,
                    "Unexpected legacy chunk identity");
            auto decoded = QByteArray::fromBase64Encoding(frame["data"].toString().toLatin1(),
                                                          QByteArray::AbortOnBase64DecodingErrors);
            require(bool(decoded) && decoded.decoded.size() <= 65536, "Invalid legacy chunk");
            writeBytes(output.p, decoded.decoded);
            hash.addData(decoded.decoded);
            count += decoded.decoded.size();
            completed += decoded.decoded.size();
            if (currentPart == "resource")
                require(count <= UINT32_MAX,
                        "Resource fork exceeds AppleDouble's 32-bit size limit");
            UInt64 value = completed;
            check(progress(total, &value), "Cancelled");
        } else if (event == "end") {
            phase("verifying", currentId, currentPart);
            require(reading && frame["id"].toInteger(-1) == currentId &&
                        frame["part"].toString() == currentPart &&
                        frame["bytes"].toString().toULongLong() == count &&
                        rows[currentId][currentPart == "resource" ? "resource_size" : "size"]
                                .toString()
                                .toULongLong() == count,
                    "Legacy stream extent differs");
            if (currentPart == "resource") {
                resourceHashes[currentId] = hash.result();
                resourceChecksums[currentId] = frame["checksum_checked"].toBool();
                UInt64 position = 0;
                check(output->Seek(0, STREAM_SEEK_SET, &position),
                      "Rewrite AppleDouble descriptor");
                writeBytes(output.p,
                           appleDouble(quint32(count),
                                       QByteArray::fromBase64(
                                           rows[currentId]["finder_info"].toString().toLatin1()),
                                       true));
            } else {
                dataHashes[currentId] = hash.result();
                dataChecksums[currentId] = frame["checksum_checked"].toBool();
            }
            setLegacyTime(output.p, rows[currentId]);
            require(output->flush(), "Flush legacy output");
            output.put();
            reading = false;
        } else if (event == "verified") {
            require(ready && !reading, "Unfinished legacy stream");
            auto id = frame["id"].toInteger(-1);
            require(id >= 0 && id < rows.size(), "Invalid verified legacy entry");
            if (operation == "extract") {
                require(selected.contains(id) && !verified.contains(id),
                        "Unexpected legacy verification");
                require(dataHashes.contains(id) == (rows[id]["has_data"].toBool() &&
                                                    !rows[id]["directory"].toBool()) &&
                            resourceHashes.contains(id) == rows[id]["has_resource"].toBool(),
                        "Missing verified legacy fork");
            }
            verified.insert(UInt32(id));
        } else if (event == "complete") {
            require(ready && !reading, "Incomplete legacy decoder result");
            child.complete = true;
            coverage = {{"outer_format", coverage["outer_format"]}, {"wrapper_chain", coverage["wrapper_chain"]}, {"checked_forks", frame["checked_forks"]},
                        {"unchecked_forks", frame["unchecked_forks"]},
                        {"expanded_wrappers", frame["expanded_wrappers"]}, {"shared_checksums", frame["shared_checksums"]}};
        } else
            require(false, "Unknown legacy decoder event");
    }
    require(!cancelled, "Cancelled");
    if (operation == "extract") {
        phase("verifying");
        require(verified == selected, "Selected legacy entries did not all verify");
        QJsonArray mappings;
        for (int i = 0; i < rows.size(); ++i)
            if (selected.contains(i)) {
                auto row = rows[i];
                QJsonObject map{{"id", i},
                                {"original", row["path"]},
                                {"components", row["components"]},
                                {"raw_name", row["raw_name"]},
                                {"encoding", row["encoding"]},
                                {"finder_info", row["finder_info"]},
                                {"output", names[i]},
                                {"output_written", row["directory"].toBool() || row["has_data"].toBool() || !visible || !row["has_resource"].toBool()}};
                if (row.contains("modified_ms"))
                    map["modified_ms"] = row["modified_ms"];
                for (const auto &key : {"raw_components", "created_1904", "modified_1904", "has_data", "has_resource", "resource_size", "size", "directory"})
                    if (row.contains(key)) map[key] = row[key];
                if (dataHashes.contains(i)) {
                    map["data_sha256"] = QString::fromLatin1(dataHashes[i].toHex());
                    map["data_checksum_checked"] = dataChecksums[i];
                }
                if (resourceHashes.contains(i)) {
                    map["resource_sha256"] = QString::fromLatin1(resourceHashes[i].toHex());
                    map["resource_checksum_checked"] = resourceChecksums[i];
                }
                if (row["has_resource"].toBool() || (!visible && !row["finder_info"].toString().isEmpty()) || (visible && !row["directory"].toBool() && !row["finder_info"].toString().isEmpty()))
                    map["sidecar"] = sidecarName(names[i], visible);
                mappings.append(map);
            }
        QString mapping = "packsmith-mapping.json";
        while (QFileInfo::exists(QDir(tree->root).filePath(mapping)))
            mapping.prepend('_');
        {
            Output out(QDir(tree->root).filePath(mapping));
            writeBytes(
                &out,
                QJsonDocument(
                    QJsonObject{{"entries", mappings},
                                {"checksum_coverage", coverage},
                                {"filename_policy", filenamePolicy}, {"resource_fork_style", forkStyle},
                                {"preservation", preservation}})
                    .toJson());
            require(out.flush(), "Flush legacy mapping");
        }
        for (auto id : selected) if (rows[id]["directory"].toBool() && rows[id].contains("modified_ms")) {
            auto path = winPath(QDir(tree->root).filePath(names[id]));
            HANDLE handle = CreateFileW(path.c_str(), FILE_WRITE_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE,
                nullptr, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
            require(handle != INVALID_HANDLE_VALUE, winError("Open folder timestamp"));
            try { setLegacyTime(handle, rows[id]); } catch (...) { CloseHandle(handle); throw; }
            CloseHandle(handle);
        }
        QString destination = parent->root;
        tree.reset();
        QString label = safeName(QFileInfo(request["archive"].toString()).completeBaseName());
        label.replace('/', '_');
        QString target = QDir(destination).filePath(label);
        int suffix = 2;
        while (QFileInfo::exists(target))
            target = QDir(destination).filePath(label + QString(" (%1)").arg(suffix++));
        auto from = winPath(stage->temp.path()), to = winPath(target);
        phase("committing");
        moveFreshDirectory(from, to);
        committedOutput = target;
        stage->temp.setAutoRemove(false);
        {
            SafeTree committed(target);
            auto marker = winPath(QDir(target).filePath(".unarchiver-job.json"));
            if (!DeleteFileW(marker.c_str()))
                emitEvent({{"event", "warning"},
                           {"message", "Verified output committed; job marker remains"}});
        }
        int fileCount = 0, dataCount = 0, resourceCount = 0, mappedNames = 0;
        for (auto id : selected) {
            const auto row = rows[id]; fileCount += !row["directory"].toBool();
            dataCount += !row["directory"].toBool() && row["has_data"].toBool();
            resourceCount += row["has_resource"].toBool(); mappedNames += names[id] != row["path"].toString();
        }
        emitEvent({{"event", "complete"},
                   {"output_committed", true}, {"file_count", fileCount}, {"data_forks", dataCount},
                   {"resource_forks", resourceCount}, {"mapped_names", mappedNames},
                   {"filename_policy", filenamePolicy}, {"resource_fork_style", forkStyle}, {"preservation", preservation},
                   {"output", target},
                   {"mapping", mapping},
                   {"count", selected.size()},
                   {"checksum_coverage", coverage},
                   {"engine", "xad"}});
    } else
        emitEvent({{"event", "complete"},
                   {"count", rows.size()},
                   {"format", format},
                   {"engine", "xad"},
                   {"read_only", true},
                   {"fingerprint", fingerprint},
                   {"checksum_coverage", coverage},
                   {"message",
                    operation != "test" ? QString()
                    : coverage["unchecked_forks"].toInteger()
                        ? QString("Decoded successfully; %1 fork streams have no source checksum")
                              .arg(coverage["unchecked_forks"].toInteger())
                        : QString("Legacy integrity check passed")}});
}
