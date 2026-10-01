#include <QtWidgets>
#include "version.h"
#include <functional>

struct Row {
    quint32 id;
    QString name;
    quint64 size;
    bool directory, encrypted, link;
    quint64 resourceSize;
    bool resourceFork;
};
static QString visibleName(const QString &name) {
    QStringList parts;
    for (const auto &part : name.split('/')) {
        QString text;
        bool whitespaceOnly = part.trimmed().isEmpty();
        for (QChar c : part) {
            if (c == '\t')
                text += "\\t";
            else if (c == '\n')
                text += "\\n";
            else if (c == '\r')
                text += "\\r";
            else if (c == '\\')
                text += "\\\\";
            else if (c.unicode() < 32 || c.unicode() == 127 || c.category() == QChar::Other_Format)
                text += QString("\\u%1").arg(uint(c.unicode()), 4, 16, QChar('0'));
            else if (whitespaceOnly && c == ' ')
                text += "\\x20";
            else
                text += c;
        }
        parts.append(text);
    }
    return parts.join('/');
}
class Entries final : public QAbstractTableModel {
  public:
    QVector<Row> rows;
    int rowCount(const QModelIndex &parent = {}) const override {
        return parent.isValid() ? 0 : rows.size();
    }
    int columnCount(const QModelIndex &parent = {}) const override {
        return parent.isValid() ? 0 : 5;
    }
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override {
        if (orientation == Qt::Horizontal && role == Qt::DisplayRole)
            return QStringList{"Name", "Data size", "Resource fork", "Type", "Protection"}.value(
                section);
        return QAbstractTableModel::headerData(section, orientation, role);
    }
    QVariant data(const QModelIndex &index, int role) const override {
        if (!index.isValid())
            return {};
        const auto &r = rows[index.row()];
        if (role == Qt::UserRole)
            return r.id;
        if (role == Qt::UserRole + 1) {
            if (index.column() == 1)
                return QVariant::fromValue(r.size);
            if (index.column() == 2)
                return QVariant::fromValue(r.resourceSize);
            if (index.column() == 3)
                return r.link ? "Link" : r.directory ? "Folder" : "File";
            if (index.column() == 4)
                return r.encrypted ? "Encrypted" : "";
            return r.name;
        }
        if (role == Qt::TextAlignmentRole && (index.column() == 1 || index.column() == 2))
            return int(Qt::AlignRight | Qt::AlignVCenter);
        if (role == Qt::ToolTipRole)
            return QString("Entry %1\n%2").arg(r.id).arg(visibleName(r.name));
        if (role != Qt::DisplayRole)
            return {};
        switch (index.column()) {
        case 0:
            return visibleName(r.name);
        case 1:
            return r.directory ? QString() : QLocale().formattedDataSize(r.size);
        case 2:
            return r.resourceFork ? QLocale().formattedDataSize(r.resourceSize) : QString();
        case 3:
            return r.link ? "Link" : r.directory ? "Folder" : "File";
        case 4:
            return r.encrypted ? "Encrypted" : "";
        }
        return {};
    }
    void clear() {
        beginResetModel();
        rows.clear();
        endResetModel();
    }
    void append(const QJsonArray &items) {
        if (items.isEmpty())
            return;
        beginInsertRows({}, rows.size(), rows.size() + items.size() - 1);
        for (auto v : items) {
            auto r = v.toObject();
            rows.append({quint32(r["id"].toInteger()), r["path"].toString(),
                         r["size"].toString().toULongLong(), r["directory"].toBool(),
                         r["encrypted"].toBool(), r["link"].toBool(),
                         r["resource_size"].toString().toULongLong(), r["has_resource"].toBool()});
        }
        endInsertRows();
    }
};

class Window final : public QMainWindow {
    Entries model;
    QSortFilterProxyModel proxy;
    QTableView *table;
    QLineEdit *search;
    QLabel *heading, *subtitle, *status;
    QProgressBar *progress;
    QPushButton *cancel;
    QList<QAction *> operations;
    QList<QAction *> edits;
    QProcess process;
    QProcess recovery;
    QJsonObject stagingRecord;
    QString stagingJournal;
    QList<QPair<QJsonObject, QString>> pendingRecovery;
    QByteArray recoveryOutput;
    bool recoveryRequired = false;
    QByteArray incoming;
    QString archive, password, operation, staging, fingerprint, filenameEncoding;
    QAction *encodingAction = nullptr;
    bool passwordDefined = false, terminal = false, busy = false, listingValid = false,
         readOnly = false;
    QJsonObject request;
    QElapsedTimer jobClock, heartbeatClock;
    qint64 maxEventGap = 0;
    QTimer heartbeat, killTimer;
    QString smokeReport, smokeDestination;
    QJsonObject smoke;
    int smokePhase = 0;

  public:
    Window() {
        setWindowTitle("Packsmith " PACKSMITH_VERSION " · Windows beta");
        resize(1100, 760);
        setMinimumSize(760, 480);
        setWindowIcon(QApplication::windowIcon());
        auto body = new QWidget;
        setCentralWidget(body);
        auto layout = new QVBoxLayout(body);
        layout->setContentsMargins(28, 24, 28, 20);
        layout->setSpacing(14);
        auto brand = new QHBoxLayout;
        auto brandIcon = new QLabel;
        brandIcon->setPixmap(windowIcon().pixmap(QSize(32, 32), devicePixelRatioF()));
        brand->addWidget(brandIcon);
        auto brandName = new QLabel("Packsmith");
        brandName->setObjectName("product");
        brand->addWidget(brandName);
        brand->addStretch();
        layout->addLayout(brand);
        heading = new QLabel("Your archives, organized.");
        heading->setObjectName("heading");
        subtitle = new QLabel("Open ZIP, 7z, StuffIt or BinHex. Classic Mac forks stay together.");
        subtitle->setWordWrap(true);
        layout->addWidget(heading);
        layout->addWidget(subtitle);
        auto toolbar = addToolBar("Archive actions");
        toolbar->setMovable(false);
        toolbar->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);
        toolbar->setIconSize({20, 20});
        auto action = [&](QString label, QStyle::StandardPixmap icon, QKeySequence shortcut,
                          std::function<void()> fn, bool needsArchive = false) {
            auto a = toolbar->addAction(style()->standardIcon(icon), label);
            a->setShortcut(shortcut);
            connect(a, &QAction::triggered, this, fn);
            if (needsArchive)
                operations.append(a);
            return a;
        };
        auto openAction = action("Open…", QStyle::SP_DialogOpenButton, QKeySequence::Open,
                                 [this] { chooseArchive(); });
        openAction->setToolTip("Open ZIP, 7z, StuffIt or BinHex (Ctrl+O)");
        openAction->setIcon(QIcon(":/brand/packsmith-archive.ico"));
        action("Create…", QStyle::SP_FileIcon, QKeySequence::New, [this] { createArchive(); });
        toolbar->addSeparator();
        action(
            "Extract…", QStyle::SP_DialogSaveButton, QKeySequence("Ctrl+E"), [this] { extract(); },
            true);
        action(
            "Test", QStyle::SP_DialogApplyButton, QKeySequence("Ctrl+T"),
            [this] { run({{"operation", "test"}}); }, true);
        toolbar->addSeparator();
        action(
            "Add…", QStyle::SP_FileDialogNewFolder, QKeySequence("Ctrl+Shift+A"), [this] { add(); },
            true);
        action("Replace…", QStyle::SP_BrowserReload, {}, [this] { replace(); }, true);
        action(
            "Rename…", QStyle::SP_FileDialogDetailedView, QKeySequence("F2"), [this] { rename(); },
            true);
        action("Remove", QStyle::SP_TrashIcon, QKeySequence::Delete, [this] { remove(); }, true);
        edits = operations.mid(2);
        action(
            "Password…", QStyle::SP_MessageBoxQuestion, {},
            [this] {
                if (!idle())
                    return;
                bool ok = false;
                auto p = QInputDialog::getText(
                    this, "Archive password", "Password for the next extraction or integrity check",
                    QLineEdit::Password, {}, &ok);
                if (ok) {
                    password = p;
                    passwordDefined = true;
                    status->setText("Password set for this archive session.");
                }
            },
            true);
        encodingAction = action(
            "Filename encoding…", QStyle::SP_FileDialogInfoView, {},
            [this] {
                if (!idle())
                    return;
                bool ok = false;
                QStringList labels{"Mac Roman", "Mac Japanese",         "Mac Cyrillic",
                                   "Mac Greek", "Mac Central European", "UTF-8"};
                QStringList encodings{"macintosh",   "x-mac-japanese",        "x-mac-cyrillic",
                                      "x-mac-greek", "x-mac-centraleurroman", "UTF-8"};
                auto label = QInputDialog::getItem(this, "Filename encoding", "Reopen using",
                                                   labels, 0, false, &ok);
                if (ok) {
                    filenameEncoding = encodings[labels.indexOf(label)];
                    listingValid = false;
                    fingerprint.clear();
                    model.clear();
                    search->clear();
                    run({{"operation", "list"}});
                }
            },
            true);
        auto searchRow = new QHBoxLayout;
        search = new QLineEdit;
        search->setPlaceholderText("Search archive contents");
        search->setClearButtonEnabled(true);
        search->setAccessibleName("Search archive contents");
        auto find = new QShortcut(QKeySequence::Find, this);
        connect(find, &QShortcut::activated, search, qOverload<>(&QWidget::setFocus));
        searchRow->addWidget(search);
        layout->addLayout(searchRow);
        proxy.setSourceModel(&model);
        proxy.setFilterKeyColumn(0);
        proxy.setFilterCaseSensitivity(Qt::CaseInsensitive);
        proxy.setSortRole(Qt::UserRole + 1);
        proxy.setDynamicSortFilter(false);
        table = new QTableView;
        table->setModel(&proxy);
        table->setSelectionBehavior(QAbstractItemView::SelectRows);
        table->setSelectionMode(QAbstractItemView::ExtendedSelection);
        table->setAlternatingRowColors(true);
        table->setShowGrid(false);
        table->setSortingEnabled(true);
        table->sortByColumn(0, Qt::AscendingOrder);
        table->verticalHeader()->hide();
        table->verticalHeader()->setDefaultSectionSize(30);
        table->horizontalHeader()->setStretchLastSection(true);
        table->horizontalHeader()->setSectionResizeMode(0, QHeaderView::Stretch);
        table->setColumnWidth(1, 130);
        table->setColumnWidth(2, 125);
        table->setColumnWidth(3, 85);
        table->setColumnWidth(4, 110);
        table->setAccessibleName("Archive entries");
        layout->addWidget(table, 1);
        auto footer = new QHBoxLayout;
        status = new QLabel("Ready");
        status->setWordWrap(true);
        status->setTextInteractionFlags(Qt::TextSelectableByMouse);
        footer->addWidget(status, 1);
        progress = new QProgressBar;
        progress->setFixedWidth(180);
        progress->hide();
        footer->addWidget(progress);
        cancel = new QPushButton("Cancel");
        cancel->hide();
        footer->addWidget(cancel);
        layout->addLayout(footer);
        auto note = new QLabel("Extraction keeps all colliding names in a new folder. Edits keep a "
                               "backup of the original.");
        note->setObjectName("note");
        note->setWordWrap(true);
        layout->addWidget(note);
        setStyleSheet(
            "QLabel#heading {font-size:26px;font-weight:600;} QLabel#note {font-size:12px;} "
            "QLabel#product {font-size:15px;font-weight:600;} "
            "QToolBar {spacing:8px;padding:12px 20px;border:0;} QLineEdit {padding:9px;} "
            "QTableView {border:1px solid palette(mid);border-radius:4px;} QHeaderView::section "
            "{padding:8px;border:0;border-bottom:1px solid palette(mid);font-weight:600;} "
            "QPushButton {padding:6px 14px;}");
        connect(search, &QLineEdit::textChanged, &proxy,
                &QSortFilterProxyModel::setFilterFixedString);
        connect(cancel, &QPushButton::clicked, this, [this] { cancelJob(); });
        connect(&process, &QProcess::readyReadStandardOutput, this, [this] { readOutput(); });
        connect(&process, &QProcess::started, this, [this] {
            process.write(QJsonDocument(request).toJson(QJsonDocument::Compact) + "\n");
        });
        connect(&process, &QProcess::readyReadStandardError, this,
                [this] { process.readAllStandardError(); });
        connect(&process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
                [this](int code, QProcess::ExitStatus exit) {
                    readOutput();
                    killTimer.stop();
                    if (!terminal) {
                        status->setText(
                            QString("Worker stopped (%1). Partial output is quarantined at %2")
                                .arg(code)
                                .arg(staging.isEmpty() ? "no staging folder" : staging));
                        if (!smokeReport.isEmpty() && smokePhase != 3)
                            finishSmoke(false, "Worker stopped before completion");
                    }
                    setBusy(false);
                    if (!stagingJournal.isEmpty()) {
                        if (!QFileInfo::exists(staging)) {
                            QFile::remove(stagingJournal);
                        } else if (!recoveryRequired) {
                            pendingRecovery.append({stagingRecord, stagingJournal});
                            beginRecovery();
                        }
                    }
                    if (terminal && exit == QProcess::NormalExit && code == 0 &&
                        (operation == "create" || operation == "update"))
                        QTimer::singleShot(0, this, [this] { openArchive(archive); });
                    if (smokePhase == 4 && terminal) {
                        smoke["stage_removed"] = !QFileInfo::exists(staging);
                        finishSmoke(code != 0 && smoke["error_dialog_visible"].toBool() &&
                                        !QFileInfo::exists(staging),
                                    "Expected extraction failure and visible warning");
                    }
                });
        connect(&process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError e) {
            if (e == QProcess::FailedToStart) {
                status->setText("Cannot start the packaged worker: " + process.errorString());
                setBusy(false);
                if (!smokeReport.isEmpty())
                    finishSmoke(false, "Worker failed to start");
            }
        });
        killTimer.setSingleShot(true);
        killTimer.setInterval(3000);
        connect(&killTimer, &QTimer::timeout, this, [this] { process.kill(); });
        connect(&recovery, &QProcess::started, this, [this] {
            auto r = pendingRecovery.first().first;
            r["operation"] = "cleanup";
            recovery.write(QJsonDocument(r).toJson(QJsonDocument::Compact) + "\n");
            recovery.closeWriteChannel();
        });
        connect(&recovery, &QProcess::readyReadStandardOutput, this,
                [this] { recoveryOutput += recovery.readAllStandardOutput(); });
        connect(&recovery, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
                [this](int code, QProcess::ExitStatus) {
                    recoveryOutput += recovery.readAllStandardOutput();
                    auto item = pendingRecovery.takeFirst();
                    if (code == 0) {
                        QFile::remove(item.second);
                        status->setText(
                            "Interrupted staging cleaned. Original archives were retained.");
                    } else
                        status->setText("Recovery needs review: " + item.second);
                    setBusy(false);
                    beginRecovery();
                    if (smokePhase == 3) {
                        smoke["recovery_ms"] = jobClock.elapsed();
                        smoke["stage_removed"] = !QFileInfo::exists(staging);
                        finishSmoke(code == 0 && !QFileInfo::exists(staging),
                                    code == 0 ? QString() : "Interrupted-job recovery failed");
                    }
                });
        connect(&recovery, &QProcess::errorOccurred, this, [this](QProcess::ProcessError e) {
            if (e == QProcess::FailedToStart) {
                status->setText("Recovery worker could not start; keep the recovery journal.");
                pendingRecovery.clear();
                setBusy(false);
            }
        });
        heartbeatClock.start();
        heartbeat.setInterval(16);
        connect(&heartbeat, &QTimer::timeout, this, [this] {
            if (busy || smokePhase)
                maxEventGap = qMax(maxEventGap, heartbeatClock.elapsed());
            heartbeatClock.restart();
        });
        heartbeat.start();
        setBusy(false);
        QTimer::singleShot(0, this, [this] {
            const QStringList folders{journalFolder(),
                                      QDir::cleanPath(QStandardPaths::writableLocation(
                                                          QStandardPaths::AppLocalDataLocation) +
                                                      "/../../Unarchiver/Unarchiver/jobs")};
            for (const auto &folder : folders)
                for (const auto &name : QDir(folder).entryList({"*.json"}, QDir::Files)) {
                    QFile f(QDir(folder).filePath(name));
                    if (!f.open(QIODevice::ReadOnly))
                        continue;
                    auto r = QJsonDocument::fromJson(f.read(8192)).object();
                    if (r["manual_review"].toBool()) {
                        status->setText("An archive commit needs recovery review: " + f.fileName());
                        continue;
                    }
                    if (!r.isEmpty())
                        pendingRecovery.append({r, f.fileName()});
                }
            beginRecovery();
        });
    }
    ~Window() {
        for (auto p : {&process, &recovery})
            if (p->state() != QProcess::NotRunning) {
                p->kill();
                p->waitForFinished(3000);
            }
    }
    void openArchive(const QString &path) {
        archive = path;
        listingValid = false;
        fingerprint.clear();
        password.clear();
        passwordDefined = false;
        filenameEncoding.clear();
        model.clear();
        search->clear();
        heading->setText(QFileInfo(path).fileName());
        subtitle->setText(QDir::toNativeSeparators(path));
        run({{"operation", "list"}});
    }
    void startSmoke(QString source, QString destination, QString report) {
        smokeDestination = destination;
        smokeReport = report;
        smokePhase = 1;
        QTimer::singleShot(0, this, [this, source] { openArchive(source); });
    }
    void startRecoverySmoke(QString source, QString destination, QString report) {
        archive = source;
        smokeDestination = destination;
        smokeReport = report;
        smokePhase = 3;
        QTimer::singleShot(0, this, [this] {
            run({{"operation", "extract"}, {"destination", smokeDestination}});
        });
    }
    void startErrorSmoke(QString source, QString destination, QString report) {
        archive = source;
        smokeDestination = destination;
        smokeReport = report;
        smokePhase = 4;
        QTimer::singleShot(0, this, [this] {
            run({{"operation", "extract"}, {"destination", smokeDestination}});
        });
    }
    void startStartupRecoverySmoke(QString stage, QString report) {
        staging = stage;
        smokeReport = report;
        smokePhase = 3;
        jobClock.start();
    }

  protected:
    void closeEvent(QCloseEvent *event) override {
        if (busy) {
            cancelJob();
            status->setText("Cancelling. Close the window after the job stops.");
            event->ignore();
        } else
            event->accept();
    }

  private:
    void setBusy(bool value) {
        busy = value;
        for (auto a : operations)
            a->setEnabled(!busy && listingValid && (!readOnly || !edits.contains(a)));
        encodingAction->setEnabled(!busy && !archive.isEmpty() && readOnly);
        search->setEnabled(!busy);
        cancel->setVisible(busy);
        progress->setVisible(busy);
        table->setSortingEnabled(!busy);
    }
    bool idle() {
        if (!busy)
            return true;
        status->setText("Wait for the current job or cancel it.");
        return false;
    }
    QString journalFolder() {
        QString p =
            QStandardPaths::writableLocation(QStandardPaths::AppLocalDataLocation) + "/jobs";
        QDir().mkpath(p);
        return p;
    }
    void beginRecovery() {
        if (pendingRecovery.isEmpty() || recovery.state() != QProcess::NotRunning)
            return;
        setBusy(true);
        cancel->setEnabled(false);
        status->setText("Cleaning interrupted staging…");
        recoveryOutput.clear();
        recovery.setProgram(QCoreApplication::applicationDirPath() +
                            "/workers/packsmith-worker.exe");
        recovery.start();
    }
    QJsonArray selected() {
        QJsonArray ids;
        for (auto index : table->selectionModel()->selectedRows())
            ids.append(qint64(model.rows[proxy.mapToSource(index).row()].id));
        return ids;
    }
    bool one(QJsonArray &ids) {
        ids = selected();
        if (ids.size() == 1)
            return true;
        status->setText("Select exactly one archive entry.");
        return false;
    }
    void chooseArchive() {
        if (!idle())
            return;
        auto path = QFileDialog::getOpenFileName(
            this, "Open archive", {},
            "Archives (*.zip *.7z *.sit *.hqx *.sitx *.bin);;All files (*)");
        if (!path.isEmpty())
            openArchive(path);
    }
    void run(QJsonObject r) {
        if (!idle())
            return;
        r["archive"] = archive;
        if (passwordDefined)
            r["password"] = password;
        if (!filenameEncoding.isEmpty())
            r["filename_encoding"] = filenameEncoding;
        if (r["operation"].toString() != "list" && !fingerprint.isEmpty())
            r["fingerprint"] = fingerprint;
        request = r;
        operation = r["operation"].toString();
        terminal = false;
        staging.clear();
        stagingRecord = {};
        stagingJournal.clear();
        recoveryRequired = false;
        incoming.clear();
        jobClock.start();
        maxEventGap = 0;
        heartbeatClock.restart();
        setBusy(true);
        cancel->setEnabled(true);
        progress->setRange(0, 0);
        status->setText(operation == "list" ? "Reading archive…" : "Working…");
        process.setProgram(QCoreApplication::applicationDirPath() +
                           "/workers/packsmith-worker.exe");
        process.setArguments({});
        process.start();
    }
    void cancelJob() {
        if (!busy)
            return;
        process.write("{\"cancel\":true}\n");
        status->setText("Cancelling…");
        cancel->setEnabled(false);
        killTimer.start();
    }
    void readOutput() {
        incoming += process.readAllStandardOutput();
        qsizetype pos;
        while ((pos = incoming.indexOf('\n')) >= 0) {
            auto line = incoming.left(pos);
            incoming.remove(0, pos + 1);
            QJsonParseError error;
            auto doc = QJsonDocument::fromJson(line, &error);
            if (error.error != QJsonParseError::NoError || !doc.isObject())
                continue;
            event(doc.object());
        }
    }
    void event(const QJsonObject &e) {
        auto kind = e["event"].toString();
        if (kind == "entries") {
            model.append(e["items"].toArray());
            status->setText(QString("%1 entries loaded…").arg(model.rows.size()));
        }
        if (kind == "staging") {
            staging = e["path"].toString();
            stagingRecord = e;
            stagingJournal = QDir(journalFolder()).filePath(e["token"].toString() + ".json");
            QSaveFile f(stagingJournal);
            if (!f.open(QIODevice::WriteOnly) || f.write(QJsonDocument(e).toJson()) < 0 ||
                !f.commit()) {
                cancelJob();
                status->setText("Cannot save recovery journal; cancelling the job.");
            }
            if (smokePhase == 3)
                QTimer::singleShot(0, this, [this] { process.kill(); });
        }
        if (kind == "recovery_required") {
            recoveryRequired = true;
            stagingRecord["manual_review"] = true;
            stagingRecord["archive"] = e["archive"];
            stagingRecord["backup"] = e["backup"];
            QSaveFile f(stagingJournal);
            if (f.open(QIODevice::WriteOnly)) {
                f.write(QJsonDocument(stagingRecord).toJson());
                f.commit();
            }
        }
        if (kind == "progress") {
            quint64 total = e["total"].toString().toULongLong(),
                    done = e["completed"].toString().toULongLong();
            if (total) {
                progress->setRange(0, 1000);
                progress->setValue(int(qMin(1.0, double(done) / double(total)) * 1000));
            }
        }
        if (kind == "complete") {
            if (operation == "list") {
                fingerprint = e["fingerprint"].toString();
                listingValid = true;
                readOnly = e["read_only"].toBool();
            }
            terminal = true;
            cancel->setEnabled(true);
            status->setText(operation == "list"
                                ? QString("%1 entries · %2 · %3 s")
                                          .arg(model.rows.size())
                                          .arg(e["format"].toString())
                                          .arg(jobClock.elapsed() / 1000.0, 0, 'f', 2) +
                                      (readOnly
                                           ? " · Legacy read-only · Forks preserved as AppleDouble"
                                           : QString())
                            : e.contains("output")
                                ? "Saved to " + QDir::toNativeSeparators(e["output"].toString()) +
                                      (e.contains("backup") ? " · Backup: " + e["backup"].toString()
                                                            : QString())
                                : e["message"].toString());
            if (!smokeReport.isEmpty()) {
                if (smokePhase == 1) {
                    smoke["read_only"] = readOnly;
                    smoke["columns"] = model.columnCount();
                    smoke["entries"] = model.rows.size();
                    QJsonArray names;
                    for (int i = 0; i < model.rows.size(); ++i)
                        names.append(model.data(model.index(i, 0), Qt::DisplayRole).toString());
                    smoke["display_names"] = names;
                    smoke["listing_ms"] = jobClock.elapsed();
                    smoke["max_event_gap_ms"] = maxEventGap;
                    smokePhase = 2;
                    QTimer::singleShot(100, this, [this] {
                        bool editsDisabled = true;
                        for (auto a : edits)
                            editsDisabled &= !a->isEnabled();
                        smoke["edit_actions_disabled"] = editsDisabled;
                        grab().save(QFileInfo(smokeReport).absolutePath() + "/gui.png");
                        if (process.state() != QProcess::NotRunning) {
                            QTimer::singleShot(100, this, [this] { smokeExtract(); });
                        } else
                            smokeExtract();
                    });
                } else {
                    if (smokePhase == 4) {
                        finishSmoke(false, "Corrupt archive unexpectedly extracted");
                        return;
                    }
                    smoke["output"] = e["output"];
                    smoke["extract_ms"] = jobClock.elapsed();
                    finishSmoke(true, {});
                }
            }
        }
        if (kind == "error" || kind == "cancelled") {
            terminal = true;
            cancel->setEnabled(true);
            QString message = e["message"].toString();
            QString summary = operation == "extract"
                                  ? "Extraction failed. No completed output was exported."
                                  : "Archive operation failed.";
            status->setText(kind == "cancelled" ? message : summary + " " + message);
            if (kind == "error" && message != "Password required") {
                auto dialog = new QMessageBox(QMessageBox::Critical, "Packsmith — Archive error",
                                              summary, QMessageBox::Ok, this);
                dialog->setAttribute(Qt::WA_DeleteOnClose);
                dialog->setTextFormat(Qt::PlainText);
                dialog->setInformativeText(message);
                dialog->setDetailedText("Archive: " + QDir::toNativeSeparators(archive));
                dialog->open();
                if (smokePhase == 4) {
                    smoke["error_dialog_visible"] = dialog->isVisible();
                    smoke["error_dialog_text"] = dialog->text();
                    smoke["error_dialog_detail"] = dialog->informativeText();
                    dialog->grab().save(QFileInfo(smokeReport).absolutePath() + "/error.png");
                    dialog->close();
                }
            }
            if (!smokeReport.isEmpty() && smokePhase != 4) {
                finishSmoke(false, message);
                return;
            }
            if (message == "Password required")
                QTimer::singleShot(100, this, [this] {
                    bool ok = false;
                    auto p = QInputDialog::getText(this, "Archive password", "Password",
                                                   QLineEdit::Password, {}, &ok);
                    if (ok) {
                        password = p;
                        passwordDefined = true;
                        if (operation == "list")
                            model.clear();
                        auto retry = request;
                        retry["password"] = p;
                        run(retry);
                    }
                });
        }
    }
    void smokeExtract() {
        if (busy) {
            QTimer::singleShot(100, this, [this] { smokeExtract(); });
            return;
        }
        smoke["max_event_gap_ms"] = qMax(smoke["max_event_gap_ms"].toInteger(), maxEventGap);
        int sourceRow = -1;
        for (int i = model.rows.size() - 1; i >= 0; --i)
            if (!model.rows[i].directory) {
                sourceRow = i;
                break;
            }
        if (sourceRow < 0) {
            finishSmoke(false, "No file for selection smoke test");
            return;
        }
        search->setText(visibleName(model.rows[sourceRow].name));
        table->selectRow(proxy.mapFromSource(model.index(sourceRow, 0)).row());
        auto ids = selected();
        if (ids.size() != 1 || ids[0].toInteger() != model.rows[sourceRow].id) {
            finishSmoke(false, "Search/selection ID mismatch");
            return;
        }
        smoke["selected_id"] = ids[0];
        smoke["selected_path"] = model.rows[sourceRow].name;
        run({{"operation", "extract"}, {"destination", smokeDestination}, {"ids", ids}});
    }
    void finishSmoke(bool ok, QString reason) {
        smoke["journal_directory"] = journalFolder();
        smoke["application_name"] = QApplication::applicationName();
        smoke["window_title"] = windowTitle();
        smoke["application_icon_loaded"] =
            !windowIcon().isNull() && !windowIcon().pixmap(32, 32).isNull();
        smoke["archive_icon_loaded"] =
            !QIcon(":/brand/packsmith-archive.ico").pixmap(32, 32).isNull();
        smoke["passed"] = ok;
        smoke["error"] = reason;
        QSaveFile f(smokeReport);
        if (f.open(QIODevice::WriteOnly)) {
            f.write(QJsonDocument(smoke).toJson());
            f.commit();
        }
        QTimer::singleShot(0, qApp, [ok] { qApp->exit(ok ? 0 : 1); });
    }
    void extract() {
        if (!idle())
            return;
        auto destination =
            QFileDialog::getExistingDirectory(this, "Extract into a new folder inside…");
        if (!destination.isEmpty())
            run({{"operation", "extract"}, {"destination", destination}, {"ids", selected()}});
    }
    void createArchive() {
        if (!idle())
            return;
        auto files = QFileDialog::getOpenFileNames(this, "Choose files for the new archive");
        if (files.isEmpty())
            return;
        QString filter;
        auto path =
            QFileDialog::getSaveFileName(this, "Create archive", {}, "ZIP (*.zip);;7z (*.7z)",
                                         &filter, QFileDialog::DontConfirmOverwrite);
        if (path.isEmpty())
            return;
        if (QFileInfo(path).suffix().isEmpty())
            path += filter.startsWith("7z") ? ".7z" : ".zip";
        if (QFileInfo::exists(path)) {
            status->setText("Choose a new archive filename.");
            return;
        }
        archive = path;
        fingerprint.clear();
        listingValid = false;
        model.clear();
        password.clear();
        passwordDefined = false;
        auto r = QJsonObject{{"operation", "create"},
                             {"format", path.endsWith(".7z", Qt::CaseInsensitive) ? "7z" : "zip"},
                             {"files", QJsonArray::fromStringList(files)}};
        run(r);
    }
    void add() {
        if (!idle())
            return;
        auto files = QFileDialog::getOpenFileNames(this, "Add files (existing names are kept)");
        if (!files.isEmpty())
            run({{"operation", "update"}, {"files", QJsonArray::fromStringList(files)}});
    }
    void replace() {
        if (!idle())
            return;
        QJsonArray ids;
        if (!one(ids))
            return;
        auto file = QFileDialog::getOpenFileName(this, "Replacement file");
        if (!file.isEmpty())
            run({{"operation", "update"},
                 {"replace", QJsonArray{QJsonObject{{"id", ids[0]}, {"source", file}}}}});
    }
    void rename() {
        if (!idle())
            return;
        QJsonArray ids;
        if (!one(ids))
            return;
        auto index = table->selectionModel()->selectedRows().first();
        bool ok = false;
        auto path = QInputDialog::getText(this, "Rename entry", "Archive path", QLineEdit::Normal,
                                          model.rows[proxy.mapToSource(index).row()].name, &ok);
        if (ok && !path.isEmpty())
            run({{"operation", "update"},
                 {"rename", QJsonArray{QJsonObject{{"id", ids[0]}, {"path", path}}}}});
    }
    void remove() {
        if (!idle())
            return;
        auto ids = selected();
        if (ids.isEmpty()) {
            status->setText("Select entries to remove.");
            return;
        }
        run({{"operation", "update"}, {"remove", ids}});
    }
};

int main(int argc, char **argv) {
    QApplication app(argc, argv);
    app.setApplicationName("Packsmith");
    app.setApplicationDisplayName("Packsmith");
    app.setApplicationVersion(PACKSMITH_VERSION);
    app.setOrganizationName("Packsmith");
    app.setWindowIcon(QIcon(":/brand/packsmith.ico"));
    QFontDatabase::addApplicationFont("C:/Windows/Fonts/segoeui.ttf");
    app.setFont(QFont("Segoe UI", 10));
    auto args = app.arguments();
    if (args.size() > 1 && args[1].startsWith("--smoke"))
        QStandardPaths::setTestModeEnabled(true);
    Window window;
    window.show();
    if (args.size() == 5 && args[1] == "--smoke")
        window.startSmoke(args[2], args[3], args[4]);
    else if (args.size() == 5 && args[1] == "--smoke-recovery")
        window.startRecoverySmoke(args[2], args[3], args[4]);
    else if (args.size() == 5 && args[1] == "--smoke-error")
        window.startErrorSmoke(args[2], args[3], args[4]);
    else if (args.size() == 5 && args[1] == "--smoke-startup-recovery")
        window.startStartupRecoverySmoke(args[2], args[4]);
    else if (args.size() > 1)
        window.openArchive(args[1]);
    return app.exec();
}
