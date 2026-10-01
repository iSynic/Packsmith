#pragma once
#include "classic_format.h"
#include "version.h"

struct InternalJob {
    std::function<void(const QJsonObject &)> previous = internalEvents;
    QString previousOutput = committedOutput, previousBackend = backend;
    QJsonObject terminal;
    QJsonArray rows;
    InternalJob() {
        internalEvents = [this](const QJsonObject &event) {
            const auto kind = event["event"].toString();
            if (kind == "complete") terminal = event;
            else if (kind == "entries") for (auto row : event["items"].toArray()) rows.append(row);
            else if (kind == "progress" || kind == "warning" || kind == "cleanup_failed") {
                auto sink = internalEvents; internalEvents = previous; emitEvent(event); internalEvents = sink;
            }
        };
    }
    ~InternalJob() { internalEvents = previous; committedOutput = previousOutput; backend = previousBackend; }
};

static QSet<int> classicSelection(const QJsonArray &rows, const QJsonObject &request) {
    QSet<int> selected;
    const auto scope = request["selection_scope"].toString();
    require(scope == "all" || scope == "entries", "Classic export requires explicit selection scope", "invalid_selection");
    const auto ids = request["ids"].toArray();
    require(scope != "entries" || !ids.isEmpty(), "Select at least one entry", "empty_selection");
    require(scope != "all" || ids.isEmpty(), "Export All cannot contain IDs", "invalid_selection");
    for (auto id : ids) {
        auto n=id.toInteger(-1); require(n>=0 && n<rows.size(), "Invalid classic export ID", "invalid_id"); selected.insert(int(n));
    }
    if (scope=="all") for (int i=0;i<rows.size();++i) selected.insert(i);
    const auto initial = selected;
    for (int id : initial) if (rows[id].toObject()["directory"].toBool()) {
        const auto prefix=rows[id].toObject()["components"].toArray();
        for (int i=0;i<rows.size();++i) {
            const auto parts=rows[i].toObject()["components"].toArray(); bool match=parts.size()>prefix.size();
            for(int j=0;match && j<prefix.size();++j) match=parts[j]==prefix[j];
            if(match) selected.insert(i);
        }
    }
    require(!selected.isEmpty(), "The archive has no exportable entries", "empty_selection");
    return selected;
}

static bool classicValid(const QByteArray &name, bool folder) {
    if (name.isEmpty() || name.size()>31 || name=="." || name=="..") return false;
    for (uchar c : name) if (c<32 || c==127 || c==':' || (folder && (c>=128 || QByteArray("/\\<>\"|?*").contains(char(c))))) return false;
    if (folder && (name.endsWith('.') || name.endsWith(' ') || QRegularExpression("^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\\.|$)",QRegularExpression::CaseInsensitiveOption).match(QString::fromLatin1(name)).hasMatch())) return false;
    return true;
}
static QString classicComponent(const QString &original, bool folder, qint64 id, QSet<QByteArray> &used) {
    auto bytes=romanName(original);
    if (classicValid(bytes,folder) && !used.contains(hfsKey(bytes))) { used.insert(hfsKey(bytes)); return original; }
    QString base;
    for (QChar c : original) {
        auto encoded=romanName(QString(c));
        base += classicValid(encoded,folder) ? c : QChar('_');
    }
    if (base.isEmpty() || base=="." || base=="..") base="Entry";
    QString candidate; int attempt=0;
    do { auto suffix=QString("~%1").arg(id); if(attempt) suffix+=QString("-%1").arg(attempt);
        candidate=base.left(31-suffix.size())+suffix; ++attempt;
    } while(used.contains(hfsKey(romanName(candidate))));
    used.insert(hfsKey(romanName(candidate))); return candidate;
}
static QString componentKey(const QJsonArray &parts) { return QString::fromLatin1(QJsonDocument(parts).toJson(QJsonDocument::Compact).toBase64()); }

static QJsonObject classicPlan(const QJsonArray &rows, const QSet<int> &selected, const QString &fingerprint) {
    QHash<QString,QString> folderPaths;
    QHash<QString,QSet<QByteArray>> used;
    QSet<QString> explicitFolders;
    QJsonArray entries,changes,folders;
    quint64 total=0;
    int fileCount=0,dataCount=0,resourceCount=0;
    auto ids=selected.values();std::sort(ids.begin(),ids.end());
    for(int id:ids) {
        require(!cancelled,"Cancelled","cancelled");
        auto row=rows[id].toObject();auto parts=row["components"].toArray();
        require(!row["absolute"].toBool() && !row["link"].toBool() && !parts.isEmpty(),"Unsafe or missing classic entry components","unsafe_entry");
        QStringList restored; QJsonArray prefix;
        for(int depth=0;depth<parts.size();++depth) {
            auto original=parts[depth].toString();
            require(!original.isEmpty() && original!="." && original!=".." && !original.contains(QChar(0)),"Unsafe classic component","unsafe_entry");
            bool isFolder=depth<parts.size()-1 || row["directory"].toBool();
            QString parent=restored.join('/');prefix.append(original);auto key=componentKey(prefix);
            bool duplicate=isFolder && depth==parts.size()-1 && row["directory"].toBool() && explicitFolders.contains(key);
            QString name;
            if(isFolder && folderPaths.contains(key) && !duplicate) name=folderPaths[key].section('/',-1);
            else {
                name=classicComponent(original,isFolder,id,used[parent]);
                if(isFolder) {
                    auto path=parent.isEmpty()?name:parent+'/'+name;
                    folderPaths.insert(key,path);
                    folders.append(path);
                }
                if(name!=original) changes.append(QJsonObject{{"id",id},{"component",depth},{"components",parts},{"original",original},{"restored",name},{"reason",duplicate?"duplicate directory":"classic HFS name, encoding or collision"}});
            }
            restored.append(name);
            if(isFolder && depth==parts.size()-1 && row["directory"].toBool()) explicitFolders.insert(key);
        }
        auto path=restored.join('/');row["restored_components"]=QJsonArray::fromStringList(restored);row["restored_path"]=path;
        const auto finder=QByteArray::fromBase64(row["finder_info"].toString().toLatin1());
        if(finder.size()==32) { const auto flags=qFromBigEndian<quint16>(finder.constData()+8);row["finder_exported_flags"]=flags & 0xfc0e;row["finder_report_only_flags"]=flags & 0x03f1; }
        if(!row["directory"].toBool()) {
            ++fileCount;dataCount+=row["has_data"].toBool();resourceCount+=row["has_resource"].toBool();
            const quint64 data=row["size"].toString().toULongLong(),resource=row["resource_size"].toString().toULongLong();
            require(data<0x80000000ULL && resource<0x80000000ULL,"Classic package fork exceeds compatibility limits","classic_limit");
            total+=128+((data+127)&~127ULL)+((resource+127)&~127ULL);
            require(total<0x80000000ULL,"Classic package exceeds 2 GiB","classic_limit");
            auto parent=restored.mid(0,restored.size()-1).join('/');
            auto transport=QString("F%1.bin").arg(id,8,10,QChar('0'));
            int suffix=0;
            while(used[parent].contains(hfsKey(transport.toLatin1()))) transport=QString("F%1-%2.bin").arg(id,8,10,QChar('0')).arg(++suffix);
            used[parent].insert(hfsKey(transport.toLatin1()));
            row["transport_path"]=parent.isEmpty()?transport:parent+'/'+transport;
        }
        entries.append(row);
    }
    // Reserve report names independently of the restored payload tree.
    require(entries.size()+folders.size()+3<65535,"Classic ZIP record limit exceeded","classic_limit");
    QJsonObject plan{{"schema",1},{"profile","classic-hfs-macroman-macbinary2"},{"fingerprint",fingerprint},{"entries",entries},{"folders",folders},{"changes",changes},{"strict_allowed",changes.isEmpty()},{"file_count",fileCount},{"data_forks",dataCount},{"resource_forks",resourceCount},{"fork_container_bytes",QString::number(total)},
        {"limitations","MacBinary II restores both forks, type/creator and available classic file dates. Finder may change reserved resource-header bytes and managed flags. Directory metadata, comments and extended Finder fields are recorded, not restored. Renames can break application references. Missing dates use zero."}};
    plan["exporter_version"]=PACKSMITH_VERSION;
    plan["engine_revision"]="7cb9ee0abbb163f261e4cb74501e15067032319c";
    plan["metadata_profile"]="Finder flags mask 0xfc0e; full available FinderInfo retained in report. Icon position, containing-folder ID, Finder-managed state and lock/protection fields are not restored.";
    plan["plan_digest"]=QString::fromLatin1(QCryptographicHash::hash(QJsonDocument(plan).toJson(QJsonDocument::Compact),QCryptographicHash::Sha256).toHex());
    return plan;
}

struct ClassicFork { quint64 offset=0,size=0; };
static ClassicFork resourceExtent(const QString &path) {
    QFile file(path);require(file.open(QIODevice::ReadOnly),"Cannot open AppleDouble resource source");
    auto header=file.read(26);require(header.size()==26 && qFromBigEndian<quint32>(header.constData())==0x00051607 && qFromBigEndian<quint32>(header.constData()+4)==0x00020000,"Invalid internal AppleDouble header");
    int count=qFromBigEndian<quint16>(header.constData()+24);require(count<=16,"Invalid AppleDouble count");
    ClassicFork resource;bool found=false;
    for(int i=0;i<count;++i) {
        auto descriptor=file.read(12);require(descriptor.size()==12,"Incomplete AppleDouble descriptor");
        auto kind=qFromBigEndian<quint32>(descriptor.constData());quint64 offset=qFromBigEndian<quint32>(descriptor.constData()+4),size=qFromBigEndian<quint32>(descriptor.constData()+8);
        require(offset>=quint64(26+12*count) && offset+size<=quint64(file.size()),"Invalid AppleDouble extent");
        if(kind==2) { require(!found,"Duplicate resource fork");found=true;resource={offset,size}; }
    }
    require(found,"Missing resource fork");return resource;
}
static QByteArray classicCopy(QFile &source, quint64 offset, quint64 size, Output *destination=nullptr) {
    require(source.seek(offset),"Cannot seek classic fork");QCryptographicHash hash(QCryptographicHash::Sha256);
    while(size) {
        require(!cancelled,"Cancelled","cancelled");auto bytes=source.read(qMin<quint64>(size,1024*1024));
        require(!bytes.isEmpty(),"Truncated classic fork");if(destination) writeBytes(destination,bytes);hash.addData(bytes);size-=bytes.size();
    }
    return hash.result().toHex();
}

static void exportClassic(const QJsonObject &request) {
    require(usesLegacy(request),"Classic export requires a legacy archive","unsupported_operation");
    const auto mode=request["mode"].toString();require(mode=="preflight" || mode=="execute","Invalid classic export mode","invalid_request");
    require(request["name_policy"]=="strict" || request["name_policy"]=="mapped","Invalid name policy","invalid_request");
    ComPtr<Input> guard;guard.p=new Input(request["archive"].toString());
    auto fingerprint=QString::fromLatin1(fileHash(request["archive"].toString()).toHex());
    require(request["fingerprint"].toString()==fingerprint,"Archive changed; reopen it before exporting","stale_archive");
    QJsonArray rows;
    { InternalJob capture;auto listing=request;listing["operation"]="list";legacyJob(listing);rows=capture.rows; }
    auto selection=classicSelection(rows,request);auto plan=classicPlan(rows,selection,fingerprint);
    if(mode=="preflight") { emitEvent({{"event","complete"},{"preflight",true},{"plan",plan},{"count",selection.size()},{"message","Classic export preflight complete; no payload checks performed"}});return; }
    require(request["plan_digest"]==plan["plan_digest"],"Export plan changed; review it again","stale_plan");
    require(request["name_policy"]=="mapped" || plan["strict_allowed"].toBool(),"Classic names require reviewed mapping","classic_name_conflict");
    const auto target=QFileInfo(request["destination"].toString()).absoluteFilePath();
    require(!request["destination"].toString().isEmpty() && !QFileInfo::exists(target),"Choose a new ZIP filename","destination_conflict");
    SafeTree parent(QFileInfo(target).absolutePath());Staging stage(parent.root);
    QJsonObject decoded;auto decodeRoot=stage.temp.filePath("decode");require(QDir().mkdir(decodeRoot),"Cannot create decode stage");
    { InternalJob capture;auto extraction=request;extraction["operation"]="extract";extraction["destination"]=decodeRoot;legacyJob(extraction);decoded=capture.terminal; }
    committedOutput.clear();
    auto root=decoded["output"].toString();QFile mapping(QDir(root).filePath(decoded["mapping"].toString()));require(mapping.open(QIODevice::ReadOnly),"Cannot read verified fork mapping");
    auto mapped=QJsonDocument::fromJson(mapping.readAll()).object()["entries"].toArray();mapping.close();QMap<int,QJsonObject> payloads;
    for(auto value:mapped) payloads.insert(value.toObject()["id"].toInt(),value.toObject());
    auto packageRoot=stage.temp.filePath("package");require(QDir().mkdir(packageRoot),"Cannot create package stage");
    QJsonArray manifestEntries;QMap<QString,QJsonObject> expected;
    {
        SafeTree tree(packageRoot);tree.directory("Files");
        for(auto folder:plan["folders"].toArray()) tree.directory("Files/"+folder.toString());
        for(auto value:plan["entries"].toArray()) {
            auto row=value.toObject();int id=row["id"].toInt();auto payload=payloads.value(id);require(!payload.isEmpty(),"Missing selected entry");
            for(const auto &key:{"data_sha256","resource_sha256","data_checksum_checked","resource_checksum_checked"}) if(payload.contains(key)) row[key]=payload[key];
            if(row["directory"].toBool()) { manifestEntries.append(row);continue; }
            phase("encoding",id);
            const auto transport="Files/"+row["transport_path"].toString();auto dataPath=QDir(root).filePath(payload["output"].toString());
            QFile data(dataPath);require(data.open(QIODevice::ReadOnly),"Cannot open verified data fork");ClassicFork resource;
            QFile fork;
            if(row["has_resource"].toBool()) { fork.setFileName(QDir(root).filePath(payload["sidecar"].toString()));resource=resourceExtent(fork.fileName());require(fork.open(QIODevice::ReadOnly),"Cannot open verified resource fork"); }
            require(quint64(data.size())==row["size"].toString().toULongLong() && resource.size==row["resource_size"].toString().toULongLong(),"Verified fork sizes differ");
            auto components=row["restored_components"].toArray();auto header=classicHeader(romanName(components.last().toString()),data.size(),resource.size,QByteArray::fromBase64(row["finder_info"].toString().toLatin1()),quint32(row["created_1904"].toInteger()),quint32(row["modified_1904"].toInteger()));
            Output output(QDir(packageRoot).filePath(transport));writeBytes(&output,header);
            auto dh=classicCopy(data,0,data.size(),&output);writeBytes(&output,QByteArray((128-data.size()%128)%128,0));
            auto rh=row["has_resource"].toBool()?classicCopy(fork,resource.offset,resource.size,&output):QCryptographicHash::hash({},QCryptographicHash::Sha256).toHex();
            writeBytes(&output,QByteArray((128-resource.size%128)%128,0));require(output.flush(),"Flush MacBinary output");
            require(!payload.contains("data_sha256") || dh==payload["data_sha256"].toString().toLatin1(),"Data fork changed during export");
            require(!payload.contains("resource_sha256") || rh==payload["resource_sha256"].toString().toLatin1(),"Resource fork changed during export");
            row["data_sha256"]=QString::fromLatin1(dh);row["resource_sha256"]=QString::fromLatin1(rh);manifestEntries.append(row);
            expected.insert(transport,QJsonObject{{"header",QString::fromLatin1(header.toBase64())},{"data_sha256",QString::fromLatin1(dh)},{"resource_sha256",QString::fromLatin1(rh)}});
        }
        plan["entries"]=manifestEntries;plan["checksum_coverage"]=decoded["checksum_coverage"];
        Output report(QDir(packageRoot).filePath("Report.json"));writeBytes(&report,QJsonDocument(plan).toJson());require(report.flush(),"Flush preservation report");
        Output guide(QDir(packageRoot).filePath("Read Me.txt"));writeBytes(&guide,QByteArray("Packsmith Classic Mac Transfer\r\n\r\nTested with StuffIt Expander 5.5 on System 7.6 and Mac OS 9.\r\nExpander 7.0.3 is unqualified in the tested SheepShaver environment.\r\nUse File > Expand to expand this ZIP into a fresh folder on a writable HFS disk.\r\nIf .bin files remain, expand each with StuffIt Expander in its existing folder.\r\nKeep the Files folder hierarchy. Never merge into an existing application folder.\r\nReport.json records original names, mappings, both fork hashes and metadata limits.\r\nClassic tools may change reserved resource-fork header bytes 16-255 and Finder-managed flags.\r\nThe MacBinary files contain the exact original fork bytes. Missing dates use zero.\r\nRenamed files may require application-specific repair. Directory metadata is not restored.\r\n"));require(guide.flush(),"Flush restoration guide");
    }
    auto zip=stage.temp.filePath("Transfer.zip");
    { InternalJob capture;backend="7zip";QJsonObject create{{"operation","create"},{"archive",zip},{"format","zip"},{"files",QJsonArray{QDir(packageRoot).filePath("Files"),QDir(packageRoot).filePath("Report.json"),QDir(packageRoot).filePath("Read Me.txt")}}};Engine engine(create);mutateArchive(engine,create,false); }
    committedOutput.clear();require(QFileInfo(zip).size()<0x80000000LL,"Classic ZIP exceeds 2 GiB","classic_limit");
    // Independently inspect the writer's ZIP framing; no encryption, descriptors or ZIP64.
    QFile zipped(zip);require(zipped.open(QIODevice::ReadOnly),"Cannot inspect ZIP");auto tailSize=qMin<qint64>(zipped.size(),65557);require(zipped.seek(zipped.size()-tailSize),"Seek ZIP footer");auto tail=zipped.read(tailSize);int end=tail.lastIndexOf(QByteArray("PK\5\6",4));require(end>=0 && end+22<=tail.size(),"Missing ZIP footer");
    auto footer=tail.constData()+end;quint16 records=qFromLittleEndian<quint16>(footer+10);quint32 offset=qFromLittleEndian<quint32>(footer+16);require(records<65535 && qFromLittleEndian<quint16>(footer+8)==records && offset!=0xffffffff && qFromLittleEndian<quint32>(footer+12)!=0xffffffff,"ZIP64 or multipart transfer is unsupported","classic_limit");
    require(zipped.seek(offset),"Seek ZIP directory");quint64 uncompressed=0;
    for(int i=0;i<records;++i) { auto fixed=zipped.read(46);require(fixed.size()==46 && fixed.left(4)==QByteArray("PK\1\2",4),"Invalid ZIP central directory");auto p=fixed.constData();auto flags=qFromLittleEndian<quint16>(p+8),method=qFromLittleEndian<quint16>(p+10);require(!(flags&1) && !(flags&0x800) && (method==0 || method==8) && qFromLittleEndian<quint32>(p+20)!=0xffffffff && qFromLittleEndian<quint32>(p+24)!=0xffffffff,"Unsupported classic ZIP feature");uncompressed+=qFromLittleEndian<quint32>(p+24);auto skip=quint64(qFromLittleEndian<quint16>(p+28))+qFromLittleEndian<quint16>(p+30)+qFromLittleEndian<quint16>(p+32);require(zipped.seek(zipped.pos()+skip),"Seek ZIP record"); }
    require(uncompressed<0x80000000ULL,"Classic ZIP uncompressed size exceeds 2 GiB","classic_limit");zipped.close();
    auto verificationRoot=stage.temp.filePath("verify");require(QDir().mkdir(verificationRoot),"Cannot create verification stage");QJsonObject verified;
    phase("verifying");
    { InternalJob capture;backend="7zip";QJsonObject extract{{"operation","extract"},{"archive",zip},{"destination",verificationRoot},{"selection_scope","all"}};Engine engine(extract);engine.open(zip);extractArchive(engine,extract);verified=capture.terminal; }
    committedOutput.clear();
    for(auto it=expected.begin();it!=expected.end();++it) {
        QFile file(QDir(verified["output"].toString()).filePath(it.key()));require(file.open(QIODevice::ReadOnly),"Missing verified MacBinary file");auto header=file.read(128);auto metadata=it.value();
        require(header==QByteArray::fromBase64(metadata["header"].toString().toLatin1()) && classicCrc(header.left(124))==qFromBigEndian<quint16>(header.constData()+124),"MacBinary header differs");
        quint64 d=qFromBigEndian<quint32>(header.constData()+83),r=qFromBigEndian<quint32>(header.constData()+87),resourceOffset=128+((d+127)&~127ULL);
        require(quint64(file.size())==resourceOffset+((r+127)&~127ULL),"Invalid MacBinary extent");
        require(classicCopy(file,128,d)==metadata["data_sha256"].toString().toLatin1() && classicCopy(file,resourceOffset,r)==metadata["resource_sha256"].toString().toLatin1(),"MacBinary fork verification failed");
        require(file.seek(128+d) && file.read(resourceOffset-128-d)==QByteArray(resourceOffset-128-d,0),"Invalid data padding");require(file.seek(resourceOffset+r) && file.readAll()==QByteArray((128-r%128)%128,0),"Invalid resource padding");
    }
    require(fileHash(QDir(verified["output"].toString()).filePath("Report.json"))==fileHash(QDir(packageRoot).filePath("Report.json")),"Preservation report changed");
    require(!cancelled,"Cancelled","cancelled");phase("committing");auto from=winPath(zip),to=winPath(target);moveFreshDirectory(from,to);committedOutput=target;stage.clean();
    emitEvent({{"event","complete"},{"output_committed",true},{"output",target},{"count",selection.size()},{"file_count",plan["file_count"]},{"data_forks",plan["data_forks"]},{"resource_forks",plan["resource_forks"]},{"mapped_names",plan["changes"].toArray().size()},{"name_mapping",plan["changes"]},{"checksum_coverage",decoded["checksum_coverage"]},{"message","Classic transfer ZIP verified and committed. Report.json and Read Me.txt are inside the ZIP."},{"preservation",plan["limitations"]}});
}
