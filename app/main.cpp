#include <QtWidgets>
#include "version.h"
#include <functional>

#include "archive_model.h"
#include "job_controller.h"
#include "archive_opening.h"

class Window final : public QMainWindow {
    friend struct GuiChecks;
    Entries model;
    QSortFilterProxyModel proxy;
    QTableView *table;
    QLineEdit *search;
    QLabel *heading, *subtitle, *status;
    QProgressBar *progress;
    QPushButton *cancel;
    QList<QAction *> operations;
    QList<QAction *> edits;
    JobController jobs;
    QProcess &process = jobs.process;
    QPlainTextEdit *resultText;
    QGroupBox *resultBox;
    QWidget *resultDetails;
    QLabel *resultSummary;
    QPushButton *outputButton, *mappingButton, *backButton, *upButton;
    QHBoxLayout *breadcrumbs;
    QAction *extractAction = nullptr, *extractAllAction = nullptr;
    QAction *classicAction = nullptr, *classicAllAction = nullptr;
    bool passwordRetry = false;
    QProcess recovery;
    QJsonObject stagingRecord;
    QString stagingJournal;
    QList<QPair<QJsonObject, QString>> pendingRecovery;
    QByteArray recoveryOutput;
    bool recoveryRequired = false;
    QString archive, password, operation, staging, fingerprint, filenameEncoding;
    QAction *encodingAction = nullptr;
    QAction *legacyOptionsAction = nullptr;
    QString extractionFilenamePolicy = "readable", extractionForkStyle = "rsrc";
    RecentArchives recent;
    QMenu *recentMenu = nullptr;
    QAction *rememberAction = nullptr;
    QPushButton *resultToggle = nullptr;
    QPointer<QDialog> activeReview;
    QSet<QString> announcedPhases;
    bool announcedOutcome = false;
    bool passwordDefined = false, terminal = false, busy = false, listingValid = false,
         readOnly = false;
    QJsonObject request;
    QElapsedTimer jobClock, heartbeatClock;
    qint64 maxEventGap = 0;
    QTimer heartbeat, killTimer;
    QString smokeReport, smokeDestination, lastOutput, lastMapping;
    QHash<quint32, QJsonObject> extractedEntries;
    QJsonObject smoke;
    QJsonArray lastClassicMapping;
    bool lastResultClassic = false;
    int smokePhase = 0;

  public:
    explicit Window(QString settingsPath = {}) : recent(settingsPath) {
        setAcceptDrops(true);
        setWindowTitle("Packsmith " PACKSMITH_VERSION " · Windows beta");
        resize(1100, 760);
        setMinimumSize(760, 480);
        setWindowIcon(QApplication::windowIcon());
        auto body = new QWidget;
        setCentralWidget(body);
        auto layout = new QVBoxLayout(body);
        layout->setContentsMargins(28, 24, 28, 20);
        layout->setSpacing(14);
        heading = new QLabel("Your archives, organized.");
        heading->setObjectName("heading");
        auto headingFont = font(); headingFont.setPointSizeF(headingFont.pointSizeF() + 8); headingFont.setBold(true); heading->setFont(headingFont);
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
        auto createAction = action("Create…", QStyle::SP_FileIcon, QKeySequence::New, [this] { createArchive(); });
        auto fileMenu = menuBar()->addMenu("&File");
        fileMenu->addAction(openAction); fileMenu->addAction(createAction);
        recentMenu = fileMenu->addMenu("Recent Archives");
        rememberAction = fileMenu->addAction("Remember recent archives");
        rememberAction->setCheckable(true); rememberAction->setChecked(recent.enabled());
        rememberAction->setToolTip("Off by default. Stores only successfully opened paths for this Windows user.");
        connect(rememberAction, &QAction::toggled, this, [this](bool enabled) { recent.enable(enabled); refreshRecent(); });
        fileMenu->addAction("Clear recent history", this, [this] { recent.clear(); refreshRecent(); });
        toolbar->addSeparator();
        extractAction = action(
            "Extract…", QStyle::SP_DialogSaveButton, QKeySequence("Ctrl+E"), [this] { extract(); },
            true);
        extractAllAction = action("Extract All…", QStyle::SP_DialogSaveButton, QKeySequence("Ctrl+Shift+E"), [this] { extract(true); }, true);
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
        edits = operations.mid(3);
        auto archiveMenu = menuBar()->addMenu("&Archive");
        for (auto a : operations) archiveMenu->addAction(a);
        auto classicMenu = menuBar()->addMenu("&Classic Mac");
        classicAction = classicMenu->addAction("Export for Classic Mac…", this, [this] { exportClassic(); }, QKeySequence("Ctrl+M"));
        classicAllAction = classicMenu->addAction("Export All for Classic Mac…", this, [this] { exportClassic(true); }, QKeySequence("Ctrl+Shift+M"));
        operations.append(classicAction); operations.append(classicAllAction);
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
                    extractedEntries.clear();
                    listingValid = false;
                    fingerprint.clear();
                    model.clear();
                    search->clear();
                    run({{"operation", "list"}});
                }
            },
            true);
        archiveMenu->addAction(operations[operations.size()-2]);
        archiveMenu->addAction(encodingAction);
        legacyOptionsAction = archiveMenu->addAction("Legacy extraction options…", this, [this] { legacyExtractionOptions(); });
        legacyOptionsAction->setEnabled(false);
        refreshRecent();
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
        proxy.setFilterRole(Entries::SearchRole);
        proxy.setFilterCaseSensitivity(Qt::CaseInsensitive);
        proxy.setSortRole(Qt::UserRole + 1);
        proxy.setDynamicSortFilter(false);
        auto navigation = new QHBoxLayout;
        backButton = new QPushButton("Back"); upButton = new QPushButton("Up");
        backButton->setShortcut(QKeySequence("Alt+Left")); upButton->setShortcut(QKeySequence("Alt+Up"));
        navigation->addWidget(backButton); navigation->addWidget(upButton);
        breadcrumbs = new QHBoxLayout; navigation->addLayout(breadcrumbs, 1);
        layout->addLayout(navigation);
        connect(backButton, &QPushButton::clicked, this, [this] { model.back(); navigated(); });
        connect(upButton, &QPushButton::clicked, this, [this] { model.up(); navigated(); });
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
        table->setColumnWidth(5, 200);
        const QFontMetrics headerMetrics(table->horizontalHeader()->font());
        for (int column = 1; column < 5; ++column)
            table->setColumnWidth(column, qMax(table->columnWidth(column), headerMetrics.horizontalAdvance(model.headerData(column, Qt::Horizontal, Qt::DisplayRole).toString()) + 32));
        layout->addWidget(table, 3);
        resultBox = new QGroupBox("Last job result");
        auto resultLayout = new QVBoxLayout(resultBox);
        auto resultHeader = new QHBoxLayout;
        resultSummary = new QLabel;
        resultSummary->setTextFormat(Qt::PlainText); resultSummary->setWordWrap(true);
        resultSummary->setAccessibleName("Last job outcome"); resultHeader->addWidget(resultSummary, 1);
        outputButton = new QPushButton("Open output folder"); resultHeader->addWidget(outputButton);
        resultToggle = new QPushButton("Show details"); resultToggle->setCheckable(true);
        resultToggle->setAccessibleName("Show or hide last job details"); resultHeader->addWidget(resultToggle);
        resultLayout->addLayout(resultHeader);
        resultDetails = new QWidget;
        auto detailsLayout = new QVBoxLayout(resultDetails); detailsLayout->setContentsMargins(0, 0, 0, 0);
        resultText = new QPlainTextEdit; resultText->setReadOnly(true); resultText->setMinimumHeight(0);
        resultText->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Ignored);
        connect(resultToggle, &QPushButton::toggled, this, [this, layout](bool expanded) {
            if (!expanded && resultDetails->isAncestorOf(QApplication::focusWidget())) resultToggle->setFocus();
            resultDetails->setVisible(expanded);
            layout->setStretch(layout->indexOf(resultBox), expanded ? 2 : 0);
            resultToggle->setText(expanded ? "Hide details" : "Show details");
        });
        resultText->setAccessibleName("Last job result"); detailsLayout->addWidget(resultText, 1);
        auto resultActions = new QHBoxLayout;
        mappingButton = new QPushButton("View mapping");
        auto copyButton = new QPushButton("Copy diagnostic details");
        resultActions->addWidget(mappingButton); resultActions->addWidget(copyButton); resultActions->addStretch();
        detailsLayout->addLayout(resultActions); resultLayout->addWidget(resultDetails, 1);
        resultDetails->hide(); layout->addWidget(resultBox); resultBox->hide();
        outputButton->setEnabled(false); mappingButton->setEnabled(false);
        connect(outputButton, &QPushButton::clicked, this, [this] { QDesktopServices::openUrl(QUrl::fromLocalFile(QFileInfo(lastOutput).isFile() ? QFileInfo(lastOutput).absolutePath() : lastOutput)); });
        connect(mappingButton, &QPushButton::clicked, this, [this] {
            if (lastResultClassic) {
                auto dialog = new QDialog(this); dialog->setWindowTitle("Classic export name mapping"); dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->resize(800,450);
                auto layout = new QVBoxLayout(dialog);
                auto note = new QLabel("The full preservation report and raw details are in Report.json inside the ZIP."); note->setWordWrap(true); layout->addWidget(note);
                layout->addWidget(mappingTable(lastClassicMapping, dialog));
                auto buttons = new QDialogButtonBox(QDialogButtonBox::Close); layout->addWidget(buttons);
                connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject); restoreDialogFocus(dialog); dialog->open();
            } else QDesktopServices::openUrl(QUrl::fromLocalFile(lastMapping));
        });
        connect(copyButton, &QPushButton::clicked, this, [this] { QApplication::clipboard()->setText(resultText->toPlainText()); });
        connect(table, &QTableView::activated, this, [this](const QModelIndex &index) { activate(index); });
        connect(table->selectionModel(), &QItemSelectionModel::selectionChanged, this, [this] { updateActions(); });
        auto detailsShortcut = new QShortcut(QKeySequence("Alt+Return"), table);
        connect(detailsShortcut, &QShortcut::activated, this, [this] { activate(table->currentIndex()); });
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
        cancel->setAccessibleName("Cancel current archive job");
        progress->setAccessibleName("Archive job progress");
        progress->setAccessibleDescription("Indeterminate when the worker cannot provide a total.");
        status->setAccessibleName("Archive job status");
        cancel->hide();
        footer->addWidget(cancel);
        layout->addLayout(footer);
        auto note = new QLabel("Extraction keeps all colliding names in a new folder. Edits keep a "
                               "backup of the original.");
        note->setObjectName("note");
        note->setWordWrap(true);
        layout->addWidget(note);
        setStyleSheet(
            "QToolBar {spacing:8px;padding:12px 20px;border:0;} QLineEdit {padding:9px;} "
            "QTableView {border:1px solid palette(mid);border-radius:4px;} QHeaderView::section "
            "{padding:8px;border:0;border-bottom:1px solid palette(mid);font-weight:600;} "
            "QPushButton {padding:6px 14px;}");
        for (auto label : {heading, subtitle, status, note}) label->setTextFormat(Qt::PlainText);
        QWidget::setTabOrder(backButton, upButton); QWidget::setTabOrder(upButton, search);
        QWidget::setTabOrder(search, table); QWidget::setTabOrder(table, cancel);
        QWidget::setTabOrder(cancel, outputButton); QWidget::setTabOrder(outputButton, resultToggle);
        QWidget::setTabOrder(resultToggle, resultText); QWidget::setTabOrder(resultText, mappingButton);
        QWidget::setTabOrder(mappingButton, copyButton);
        connect(search, &QLineEdit::textChanged, this, [this](const QString &text) {
            table->clearSelection(); model.searchMode(!text.isEmpty());
            proxy.setFilterFixedString(text); proxy.sort(table->horizontalHeader()->sortIndicatorSection(), table->horizontalHeader()->sortIndicatorOrder());
            updateNavigation(); updateActions();
        });
        connect(cancel, &QPushButton::clicked, this, [this] { cancelJob(); });
        jobs.onEvent = [this](const QJsonObject &e) { event(e); };
        connect(&process, &QProcess::started, this, [this] {
            process.write(QJsonDocument(request).toJson(QJsonDocument::Compact) + "\n");
        });
        jobs.onFinished = [this](int code, QProcess::ExitStatus exit) {
            killTimer.stop();
            terminal = !jobs.result.terminal.isEmpty();
            if (exit != QProcess::NormalExit) passwordRetry = false;
            if (jobs.result.success) completed(jobs.result.terminal);
            else if (jobs.result.terminal["event"] != "error" && jobs.result.terminal["event"] != "cancelled") showFailure(jobs.result.failure);
            if (!jobs.result.success && operation == "list") { listingValid = false; model.clear(); }
            if (operation != "list" || !jobs.result.success) showResult();
            setBusy(false);
            if (!announcedOutcome) {
                announcedOutcome = true;
                announce(jobs.result.success ? (operation == "list" ? "Archive ready. " + QString::number(model.rows.size()) + " entries." : "Archive job completed. Review the last job result.") : jobs.result.terminal["event"] == "cancelled" ? "Archive job cancelled. Review the last job result." : "Archive job failed. " + jobs.result.redact(jobs.result.failure));
            }
            if (!stagingJournal.isEmpty()) {
                if (!QFileInfo::exists(staging)) QFile::remove(stagingJournal);
                else if (!recoveryRequired) { pendingRecovery.append({stagingRecord, stagingJournal}); beginRecovery(); }
            }
            if (jobs.result.success && (operation == "create" || operation == "update"))
                QTimer::singleShot(0, this, [this] { openArchive(archive); });
            if (smokePhase == 4 && terminal) {
                smoke["stage_removed"] = !QFileInfo::exists(staging);
                finishSmoke(code != 0 && smoke["error_dialog_visible"].toBool() && !QFileInfo::exists(staging), "Expected extraction failure and visible warning");
            } else if (!smokeReport.isEmpty() && !jobs.result.success && smokePhase != 3) finishSmoke(false, jobs.result.failure);
            maybeRetryPassword();
            if (jobs.result.success && operation == "export_classic" && jobs.result.terminal["preflight"].toBool()) {
                const auto plan = jobs.result.terminal["plan"].toObject();
                const auto reviewedRequest = request;
                QTimer::singleShot(0, this, [this, plan, reviewedRequest] { reviewClassic(plan, reviewedRequest); });
            }
            Q_UNUSED(exit);
        };
        jobs.onStartFailure = [this] {
            showFailure(jobs.result.failure); showResult(); setBusy(false);
            if (!announcedOutcome) { announcedOutcome = true; announce("Archive job failed. " + jobs.result.redact(jobs.result.failure)); }
            if (!smokeReport.isEmpty()) finishSmoke(false, jobs.result.failure);
        };
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
                [this](int code, QProcess::ExitStatus exit) {
                    recoveryOutput += recovery.readAllStandardOutput();
                    auto item = pendingRecovery.takeFirst();
                    QJsonObject recoveryTerminal;
                    int terminals = 0;
                    for (const auto &line : recoveryOutput.split('\n')) {
                        auto e = QJsonDocument::fromJson(line).object();
                        if (e["event"] == "complete" || e["event"] == "error" || e["event"] == "cancelled") { recoveryTerminal = e; ++terminals; }
                    }
                    const bool recovered = code == 0 && exit == QProcess::NormalExit && terminals == 1 && recoveryTerminal["event"] == "complete" && !QFileInfo::exists(item.first["path"].toString());
                    if (recovered) {
                        QFile::remove(item.second);
                        jobs.result.cleanup = "Interrupted staging cleaned. Original archives were retained.";
                    } else { jobs.result.cleanup = "Recovery needs review: " + item.second + " " + recoveryTerminal["message"].toString(); passwordRetry = false; }
                    showResult();
                    setBusy(false);
                    beginRecovery();
                    maybeRetryPassword();
                    if (smokePhase == 3) {
                        smoke["recovery_ms"] = jobClock.elapsed();
                        smoke["stage_removed"] = !QFileInfo::exists(staging);
                        finishSmoke(recovered && !QFileInfo::exists(staging),
                                    recovered ? QString() : "Interrupted-job recovery failed");
                    }
                });
        connect(&recovery, &QProcess::errorOccurred, this, [this](QProcess::ProcessError e) {
            if (e == QProcess::FailedToStart) {
                jobs.result.cleanup = "Recovery worker could not start; keep the recovery journal: " + pendingRecovery.first().second;
                showResult();
                passwordRetry = false;
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
                        jobs.result.cleanup = "An archive commit needs recovery review: " + f.fileName();
                        showResult();
                        continue;
                    }
                    if (!r.isEmpty())
                        pendingRecovery.append({r, f.fileName()});
                }
            beginRecovery();
        });
    }
    ~Window() {
        table->selectionModel()->disconnect(this);
        recovery.disconnect(this);
        jobs.onEvent = {}; jobs.onFinished = {}; jobs.onStartFailure = {};
        for (auto p : {&process, &recovery})
            if (p->state() != QProcess::NotRunning) {
                p->kill();
                p->waitForFinished(3000);
            }
    }
    void openArchive(const QString &path) {
        if (!idle()) return;
        if (!QFileInfo(path).isFile()) {
            recent.remove(path); refreshRecent();
            status->setText("Archive file is missing or is not a regular file: " + visibleName(path));
            announce(status->text()); return;
        }
        extractedEntries.clear();
        archive = normalizedArchivePath(path);
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
    void dragEnterEvent(QDragEnterEvent *event) override {
        QString error;
        if (!busy && !recoveryRequired && !activeReview && !archiveDropPath(event->mimeData()->urls(), error).isEmpty()) event->acceptProposedAction();
        else { status->setText(busy || recoveryRequired || activeReview ? "Wait for the current job or review to finish before opening another archive." : error); event->ignore(); }
    }
    void dropEvent(QDropEvent *event) override {
        QString error; const auto path = archiveDropPath(event->mimeData()->urls(), error);
        if (path.isEmpty()) { status->setText(error); announce(error); event->ignore(); return; }
        if (!idle()) { event->ignore(); return; }
        openArchive(path); event->acceptProposedAction();
    }
    void closeEvent(QCloseEvent *event) override {
        if (busy) {
            cancelJob();
            status->setText("Cancelling. Close the window after the job stops.");
            event->ignore();
        } else
            event->accept();
    }

  private:
    void announce(const QString &message) {
        QAccessibleAnnouncementEvent event(status, jobs.result.redact(message));
        QAccessible::updateAccessibility(&event);
    }
    void refreshRecent() {
        if (!recentMenu) return;
        recentMenu->clear();
        for (const auto &path : recent.paths()) {
            auto label = visibleName(QFileInfo(path).fileName()).replace("&", "&&");
            auto a = recentMenu->addAction(label, this, [this, path] { openArchive(path); });
            a->setToolTip(QDir::toNativeSeparators(path));
        }
        recentMenu->setEnabled(!recent.paths().isEmpty());
    }
    void restoreDialogFocus(QDialog *dialog) {
        QPointer<QWidget> prior = focusWidget();
        connect(dialog, &QDialog::finished, this, [this, prior] {
            if (prior && prior->isEnabled()) prior->setFocus(); else if (!busy) table->setFocus();
        });
    }
    QTableWidget *mappingTable(const QJsonArray &changes, QWidget *parent) {
        auto table = new QTableWidget(changes.size(), 4, parent);
        table->setAccessibleName("Classic Mac filename mapping");
        table->setHorizontalHeaderLabels({"Original location / name", "Restored name", "Reason", "Entry ID"});
        table->setEditTriggers(QAbstractItemView::NoEditTriggers); table->setSelectionBehavior(QAbstractItemView::SelectRows);
        table->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch); table->verticalHeader()->hide();
        for (int i = 0; i < changes.size(); ++i) {
            const auto change = changes[i].toObject();
            QString original = change["original"].toString();
            if (change["components"].isArray()) { QStringList parts; for (auto part : change["components"].toArray()) parts.append(part.toString()); original = displayPath(parts); }
            const QStringList cells{visibleName(original), visibleName(change["restored"].toString()), change["reason"].toString(), QString::number(change["id"].toInteger())};
            for (int col = 0; col < cells.size(); ++col) { auto item = new QTableWidgetItem(cells[col]); item->setToolTip(cells[col]); table->setItem(i, col, item); }
        }
        return table;
    }
    void updateActions() {
        if (!extractAction) return;
        extractAction->setEnabled(!busy && listingValid &&
            (!model.searching() || !table->selectionModel()->selectedRows().isEmpty()));
        if (classicAction) {
            classicAction->setEnabled(readOnly && extractAction->isEnabled());
            classicAllAction->setEnabled(!busy && listingValid && readOnly);
        }
        bool editable = false;
        bool replaceable = false;
        const auto selection = table->selectionModel()->selectedRows();
        if (selection.size() == 1) {
            const auto entry = model.editableAt(proxy.mapToSource(selection.first()).row());
            editable = entry; replaceable = entry && !entry->directory;
        }
        if (edits.size() == 4) {
            edits[1]->setEnabled(!busy && listingValid && !readOnly && replaceable);
            edits[2]->setEnabled(!busy && listingValid && !readOnly && editable);
            edits[3]->setEnabled(!busy && listingValid && !readOnly && !selection.isEmpty());
        }
    }
    void updateNavigation() {
        if (!backButton) return;
        backButton->setEnabled(!busy && model.canBack()); upButton->setEnabled(!busy && model.canUp());
        while (auto item = breadcrumbs->takeAt(0)) { if (auto widget = item->widget()) { widget->hide(); widget->deleteLater(); } delete item; }
        const auto parts = model.currentParts();
        for (int depth = 0; depth <= parts.size(); ++depth) {
            auto button = new QPushButton(depth == 0 ? "Archive" : visibleName(parts[depth - 1]));
            button->setEnabled(!busy && !model.searching());
            button->setAccessibleName("Open archive folder " + displayPath(parts.mid(0, depth)));
            connect(button, &QPushButton::clicked, this, [this, parts, depth] { model.navigate(parts.mid(0, depth)); navigated(); });
            breadcrumbs->addWidget(button);
        }
        if (model.searching()) { auto label = new QLabel("Global search"); label->setTextFormat(Qt::PlainText); breadcrumbs->addWidget(label); }
        breadcrumbs->addStretch();
        table->setColumnHidden(5, !model.searching());
    }
    void navigated() {
        table->clearSelection();
        proxy.sort(table->horizontalHeader()->sortIndicatorSection(), table->horizontalHeader()->sortIndicatorOrder());
        updateNavigation(); updateActions(); table->setFocus();
    }
    void activate(const QModelIndex &index) {
        if (busy || !index.isValid()) return;
        const int row = proxy.mapToSource(index).row();
        if (model.folderAt(row)) {
            const auto parts = model.partsAt(row);
            search->clear(); model.navigate(parts); navigated(); return;
        }
        const auto entry = model.editableAt(row);
        if (!entry) return;
        QStringList detail{"Original filename (escaped): " + visibleName(entry->components.last()), "Original archive path: " + displayPath(entry->components), QString("Entry ID: %1").arg(entry->id)};
        detail.append("Original components: " + QString::fromUtf8(QJsonDocument(QJsonArray::fromStringList(entry->components)).toJson(QJsonDocument::Compact)));
        if (!entry->metadata["format"].toString().isEmpty()) detail.append("Detected format: " + entry->metadata["format"].toString());
        for (const auto &part : {QString("data"), QString("resource")})
            if (entry->metadata["has_" + part].toBool()) detail.append(part + " compression: " + entry->metadata[part + "_method"].toString("unknown") + (entry->metadata.contains(part + "_method_id") ? QString(" (method %1)").arg(entry->metadata[part + "_method_id"].toInteger()) : QString()));
        detail.append(QString("Data fork: %1 · %2 bytes").arg(entry->metadata.contains("has_data") ? entry->metadata["has_data"].toBool() ? "present" : "absent (an empty data file is exported)" : "present").arg(entry->size));
        detail.append(QString("Resource fork: %1 · %2 bytes").arg(entry->resourceFork ? "present" : "absent").arg(entry->resourceSize));
        if (!entry->metadata["encoding"].toString().isEmpty()) detail.append("Filename encoding: " + entry->metadata["encoding"].toString());
        const auto finder = QByteArray::fromBase64(entry->metadata["finder_info"].toString().toLatin1());
        if (finder.size() == 32) {
            detail.append("Finder type: " + visibleName(QString::fromLatin1(finder.left(4))) + " · Creator: " + visibleName(QString::fromLatin1(finder.mid(4, 4))));
            detail.append("Finder flags: 0x" + QString::number(qFromBigEndian<quint16>(finder.constData() + 8), 16).rightJustified(4, '0'));
        }
        if (entry->metadata.contains("modified_ms")) {
            detail.append("Interpreted modification time: " + QDateTime::fromMSecsSinceEpoch(entry->metadata["modified_ms"].toVariant().toLongLong()).toString(Qt::ISODate));
            if (readOnly) detail.append("Classic dates have no timezone; this decoder uses the current local UTC offset. Historical daylight-saving dates may shift by an hour.");
        }
        for (const auto &key : {QString("created_1904"), QString("modified_1904")}) {
            const auto label = key.startsWith("created") ? "creation" : "modification";
            if (entry->metadata.contains(key)) {
                const auto raw = entry->metadata[key].toInteger();
                const auto date = raw ? QDateTime(QDate(1904,1,1), QTime(0,0), QTimeZone::UTC).addSecs(raw).toString("yyyy-MM-dd HH:mm:ss") : QString("unknown");
                detail.append(QString("Raw classic %1: %2 (%3; wall-clock value, no timezone)").arg(label).arg(raw).arg(date));
            } else if (readOnly) detail.append(QString("Raw classic %1: unavailable").arg(label));
        }
        const auto mapping = extractedEntries.value(entry->id);
        if (mapping.isEmpty()) detail.append("Source checksum status: not yet verified in this session.");
        else {
            detail.append(mapping["output_written"].toBool(true)
                ? "Exported path: " + QDir(lastOutput).filePath(mapping["output"].toString())
                : "Data output: none (resource-only file; no empty placeholder).");
            if (mapping.contains("sidecar")) detail.append("Resource/metadata file: " + QDir(lastOutput).filePath(mapping["sidecar"].toString()));
            for (const auto &part : {QString("data"), QString("resource")})
                if (mapping.contains(part + "_sha256")) detail.append(part + " fork SHA-256: " + mapping[part + "_sha256"].toString() + "\nSource checksum: " + (mapping[part + "_checksum_checked"].toBool() ? "checked" : "not available"));
        }
        auto dialog = new QMessageBox(QMessageBox::Information, "Entry details", entry->displayName, QMessageBox::Ok, this);
        dialog->setTextFormat(Qt::PlainText); dialog->setInformativeText(detail.join('\n')); dialog->setAttribute(Qt::WA_DeleteOnClose); restoreDialogFocus(dialog); dialog->open();
    }
    void showResult() {
        const auto &r = jobs.result;
        lastResultClassic = r.success && r.operation == "export_classic" && r.terminal["output_committed"].toBool();
        lastClassicMapping = lastResultClassic ? r.terminal["name_mapping"].toArray() : QJsonArray{};
        resultText->setPlainText(r.report());
        QString summary = !r.finished ? "Recovery details available"
            : r.success ? "Completed" : r.terminal["event"] == "cancelled" ? "Cancelled" : "Failed";
        if (r.operation == "extract" || r.operation == "export_classic" || r.operation == "create" || r.operation == "update")
            summary += r.terminal["output_committed"].toBool() ? " · Output committed" : " · No output committed";
        if (r.success && r.terminal["checksum_coverage"].toObject()["unchecked_forks"].toInteger()) summary += " · Verification limits";
        resultSummary->setText(summary); resultBox->show();
        if (r.terminal["output_committed"].toBool()) {
            lastOutput = r.terminal["output"].toString();
            lastMapping = r.terminal["mapping"].toString().isEmpty() ? QString() : QDir(lastOutput).filePath(r.terminal["mapping"].toString());
            extractedEntries.clear(); QFile file(lastMapping);
            if (file.open(QIODevice::ReadOnly)) for (auto value : QJsonDocument::fromJson(file.readAll()).object()["entries"].toArray()) {
                auto entry = value.toObject(); extractedEntries.insert(quint32(entry["id"].toInteger()), entry);
            }
        } else { lastOutput.clear(); lastMapping.clear(); extractedEntries.clear(); }
        outputButton->setEnabled(!lastOutput.isEmpty()); mappingButton->setEnabled(!lastMapping.isEmpty() || (r.success && r.operation == "export_classic" && r.terminal["output_committed"].toBool()));
        if (!r.success && r.finished) status->setText(r.redact(r.failure));
        else if (!r.cleanup.isEmpty()) status->setText(r.redact(r.cleanup));
    }
    void showFailure(const QString &message) {
        const QString summary = jobs.result.terminal["output_committed"].toBool()
            ? "Archive operation failed after output was committed. Review the job result."
            : operation == "extract" ? "Extraction failed. No completed output was exported." : "Archive operation failed.";
        status->setText(summary + " " + jobs.result.redact(message));
        auto dialog = new QMessageBox(QMessageBox::Critical, "Packsmith — Archive error", summary, QMessageBox::Ok, this);
        dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->setTextFormat(Qt::PlainText);
        dialog->setInformativeText(jobs.result.redact(message)); dialog->setDetailedText(jobs.result.redact("Archive: " + archive)); restoreDialogFocus(dialog); dialog->open();
        if (smokePhase == 4) {
            smoke["error_dialog_visible"] = dialog->isVisible(); smoke["error_dialog_text"] = dialog->text(); smoke["error_dialog_detail"] = dialog->informativeText();
            dialog->grab().save(QFileInfo(smokeReport).absolutePath() + "/error.png"); dialog->close();
        }
    }
    void maybeRetryPassword() {
        if (!passwordRetry || busy || !pendingRecovery.isEmpty() || recoveryRequired) return;
        passwordRetry = false;
        QTimer::singleShot(0, this, [this] {
            if (busy || process.state() != QProcess::NotRunning) return;
            bool ok = false;
            const auto p = QInputDialog::getText(this, "Archive password", "Password", QLineEdit::Password, {}, &ok);
            if (ok) {
                password = p; passwordDefined = true; auto retry = request; retry["password"] = p;
                if (operation == "list") model.clear();
                run(retry);
            }
        });
    }
    void setBusy(bool value) {
        busy = value;
        for (auto a : operations)
            a->setEnabled(!busy && listingValid && (!readOnly || !edits.contains(a)));
        encodingAction->setEnabled(!busy && !archive.isEmpty() && readOnly);
        if (legacyOptionsAction) legacyOptionsAction->setEnabled(!busy && listingValid && readOnly);
        search->setEnabled(!busy);
        cancel->setVisible(busy);
        progress->setVisible(busy);
        table->setSortingEnabled(!busy);
        updateNavigation(); updateActions();
    }
    bool idle() {
        if (!busy && !recoveryRequired && pendingRecovery.isEmpty() && recovery.state() == QProcess::NotRunning && !activeReview)
            return true;
        status->setText("Wait for the current job, recovery, or review to finish.");
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
        QSet<qint64> unique;
        for (auto index : table->selectionModel()->selectedRows())
            for (auto id : model.idsAt(proxy.mapToSource(index).row())) unique.insert(id.toInteger());
        auto values = unique.values(); std::sort(values.begin(), values.end());
        QJsonArray ids; for (auto id : values) ids.append(id); return ids;
    }
    bool one(QJsonArray &ids) {
        const auto selectedRows = table->selectionModel()->selectedRows();
        if (selectedRows.size() == 1) {
            const auto r = model.editableAt(proxy.mapToSource(selectedRows.first()).row());
            if (r) { ids = {qint64(r->id)}; return true; }
        }
        status->setText("Select exactly one real entry. Grouped folders cannot be renamed."); return false;
    }
    void chooseArchive() {
        if (!idle())
            return;
        auto path = QFileDialog::getOpenFileName(
            this, "Open archive", {},
            "Archives (*.zip *.7z *.sit *.hqx *.sitx *.bin *.cpt *.lha *.lzh *.lzx);;All files (*)");
        if (!path.isEmpty())
            openArchive(path);
    }
    void run(QJsonObject r) {
        if (!idle())
            return;
        r["archive"] = archive;
        if (r["operation"] == "extract" && readOnly) {
            if (!r.contains("filename_policy")) r["filename_policy"] = extractionFilenamePolicy;
            if (!r.contains("resource_fork_style")) r["resource_fork_style"] = extractionForkStyle;
        }
        if (passwordDefined)
            r["password"] = password;
        if (!filenameEncoding.isEmpty())
            r["filename_encoding"] = filenameEncoding;
        if (r["operation"].toString() != "list" && !fingerprint.isEmpty())
            r["fingerprint"] = fingerprint;
        request = r;
        operation = r["operation"].toString();
        announcedPhases.clear(); announcedOutcome = false;
        terminal = false;
        staging.clear();
        stagingRecord = {};
        stagingJournal.clear();
        recoveryRequired = false;

        jobClock.start();
        maxEventGap = 0;
        heartbeatClock.restart();
        setBusy(true);
        cancel->setEnabled(true);
        progress->setRange(0, 0);
        status->setText(operation == "list" ? "Reading archive…" : "Working…");
        if (operation == "extract" && !request.contains("selection_scope")) request["selection_scope"] = request["ids"].toArray().isEmpty() ? "all" : "entries";
        jobs.start(request, QCoreApplication::applicationDirPath() + "/workers/packsmith-worker.exe");
    }
    void cancelJob() {
        if (!busy)
            return;
        status->setText("Cancelling…");
        cancel->setEnabled(false);
        killTimer.start();
        jobs.cancel();
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
            if (!e["phase"].toString().isEmpty()) {
                QString text = e["phase"].toString();
                if (!announcedPhases.contains(text)) { announcedPhases.insert(text); announce("Archive job: " + text); }
                if (e["id"].toInteger(-1) >= 0) text += QString(" · Entry %1 · %2").arg(e["id"].toInteger()).arg(e["part"].toString());
                status->setText(text);
            }
            quint64 total = e["total"].toString().toULongLong(),
                    done = e["completed"].toString().toULongLong();
            if (total) {
                progress->setRange(0, 1000);
                progress->setValue(int(qMin(1.0, double(done) / double(total)) * 1000));
            } else progress->setRange(0, 0);
        }
        if (kind == "error" || kind == "cancelled") {
            terminal = true;
            if (e["code"] == "password_required") passwordRetry = true;
            else if (kind == "error") showFailure(jobs.result.redact(e["message"].toString()));
            else status->setText(e["message"].toString());
        }
    }
    void completed(const QJsonObject &e) {
        if (operation == "list") { recent.opened(archive); refreshRecent(); }
            if (operation == "list") {
                QElapsedTimer modelClock; modelClock.start(); model.finish(); navigated();
                smoke["model_build_ms"] = modelClock.elapsed();
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
                    for (int i = 0; i < model.rowCount(); ++i) if (model.folderAt(i)) {
                        const auto parts = model.partsAt(i); QElapsedTimer navClock; navClock.start();
                        model.navigate(parts); navigated(); smoke["folder_navigation_ms"] = navClock.elapsed();
                        smoke["folder_entries"] = model.rowCount(); model.up(); navigated(); break;
                    }
                    QJsonArray names;
                    for (int i = 0; i < model.rows.size(); ++i)
                        names.append(displayPath(model.rows[i].components));
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
                    QTimer::singleShot(0, this, [this] { finishSmoke(true, {}); });
                }
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
        search->setText(displayPath(model.rows[sourceRow].components));
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
        smoke["result_panel"] = resultText->toPlainText();
        smoke["worker_exit_verified"] = jobs.result.finished && process.state() == QProcess::NotRunning;
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
    void extract(bool all = false) {
        if (!idle()) return;
        auto ids = selected();
        if (!all && ids.isEmpty()) {
            if (model.searching()) { status->setText("Select search results to extract, or use Extract All."); return; }
            ids = model.currentIds();
        }
        if (!all && ids.isEmpty()) { status->setText("This folder has no extractable entries."); return; }
        auto destination = QFileDialog::getExistingDirectory(this, "Extract into a new folder inside…");
        if (!destination.isEmpty()) run({{"operation", "extract"}, {"destination", destination}, {"selection_scope", all ? "all" : "entries"}, {"ids", all ? QJsonArray{} : ids}});
    }
    void legacyExtractionOptions() {
        if (!idle() || !readOnly) return;
        QDialog dialog(this); dialog.setWindowTitle("Legacy extraction options");
        auto layout = new QVBoxLayout(&dialog);
        auto form = new QFormLayout; layout->addLayout(form);
        auto names = new QComboBox(&dialog); names->setObjectName("extractionFilenamePolicy");
        names->addItem("Readable Windows names (replace invalid characters with _)", "readable");
        names->addItem("Escaped Windows names (for example, ~0009)", "escaped");
        names->setCurrentIndex(names->findData(extractionFilenamePolicy));
        names->setAccessibleName("Extracted filenames"); form->addRow("&Filenames:", names);
        auto forks = new QComboBox(&dialog); forks->setObjectName("extractionForkStyle");
        forks->addItem("Visible .rsrc files, without empty resource-only placeholders", "rsrc");
        forks->addItem("Preservation mode: ._ sidecars and resource-only placeholders", "appledouble");
        forks->setCurrentIndex(forks->findData(extractionForkStyle));
        forks->setAccessibleName("Resource fork output"); form->addRow("&Resource forks:", forks);
        auto explanation = new QLabel("Both modes keep the original names and available Finder metadata in the mapping report. .rsrc mode keeps file metadata in AppleDouble files and folder Finder metadata in the report. These choices apply to extraction only; Classic Mac export is unchanged.", &dialog);
        explanation->setTextFormat(Qt::PlainText); explanation->setWordWrap(true); layout->addWidget(explanation);
        auto buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &dialog); layout->addWidget(buttons);
        connect(buttons, &QDialogButtonBox::accepted, &dialog, &QDialog::accept);
        connect(buttons, &QDialogButtonBox::rejected, &dialog, &QDialog::reject);
        dialog.resize(680, 240);
        if (dialog.exec() == QDialog::Accepted) {
            extractionFilenamePolicy = names->currentData().toString(); extractionForkStyle = forks->currentData().toString();
            status->setText("Legacy extraction options updated for this app session.");
        }
        table->setFocus();
    }
    QJsonObject classicRequest(bool all) {
        auto ids = selected();
        if (!all && ids.isEmpty()) {
            if (model.searching()) return {};
            ids = model.currentIds();
        }
        if (!all && ids.isEmpty()) return {};
        return {{"operation", "export_classic"}, {"mode", "preflight"}, {"name_policy", "strict"},
                {"selection_scope", all ? "all" : "entries"}, {"ids", all ? QJsonArray{} : ids}};
    }
    void exportClassic(bool all = false) {
        if (!idle() || !readOnly || !listingValid) return;
        auto r = classicRequest(all);
        if (r.isEmpty()) { status->setText(model.searching() ? "Select search results for classic export." : "This folder has no exportable entries."); return; }
        auto path = QFileDialog::getSaveFileName(this, "Export a new Classic Mac transfer ZIP", QFileInfo(archive).completeBaseName()+"-classic.zip", "ZIP (*.zip)", nullptr, QFileDialog::DontConfirmOverwrite);
        if (path.isEmpty()) return;
        if (QFileInfo::exists(path)) { status->setText("Choose a new ZIP filename. Existing files are preserved."); return; }
        r["destination"] = path; run(r);
    }
    void reviewClassic(const QJsonObject &plan, const QJsonObject &reviewedRequest) {
        auto dialog = new QDialog(this);
        dialog->setObjectName("classicPreflight"); dialog->setWindowTitle("Review Classic Mac export");
        dialog->setWindowModality(Qt::WindowModal); dialog->setAttribute(Qt::WA_DeleteOnClose); dialog->resize(720,500);
        activeReview = dialog;
        connect(dialog, &QDialog::finished, this, [this] { activeReview = nullptr; });
        restoreDialogFocus(dialog);
        auto layout = new QVBoxLayout(dialog);
        auto summary = new QLabel(QString("%1 files · %2 data forks · %3 resource forks\nStrict naming is the default. Review every proposed substitution before exporting.").arg(plan["file_count"].toInteger()).arg(plan["data_forks"].toInteger()).arg(plan["resource_forks"].toInteger()));
        summary->setTextFormat(Qt::PlainText); summary->setWordWrap(true); layout->addWidget(summary);
        QStringList lines;
        for (auto value : plan["changes"].toArray()) {
            auto change = value.toObject(); lines.append(QString("Entry %1, component %2: %3 → %4 (%5)").arg(change["id"].toInteger()).arg(change["component"].toInteger()).arg(change["original"].toString(),change["restored"].toString(),change["reason"].toString()));
        }
        if (lines.isEmpty()) lines.append("All selected names fit the strict classic HFS profile.");
        lines.append("\n"+plan["limitations"].toString());
        lines.append("\nTested restoration: StuffIt Expander 5.5 on System 7.6 and Mac OS 9. Expander 7.0.3 is unqualified in the tested emulator.");
        auto text = new QPlainTextEdit(lines.join('\n')); text->setReadOnly(true); text->setAccessibleName("Classic export name changes and preservation limits"); layout->addWidget(text);
        if (!plan["changes"].toArray().isEmpty()) layout->addWidget(mappingTable(plan["changes"].toArray(), dialog));
        auto buttons = new QDialogButtonBox(QDialogButtonBox::Cancel);
        auto strict = buttons->addButton("Export", QDialogButtonBox::AcceptRole); strict->setEnabled(plan["strict_allowed"].toBool());
        auto mapped = buttons->addButton("Export with mapped names", QDialogButtonBox::ActionRole); mapped->setEnabled(!plan["changes"].toArray().isEmpty());
        auto execute = [this, dialog, reviewedRequest, plan](QString policy) { auto r = reviewedRequest; r["mode"] = "execute"; r["name_policy"] = policy; r["plan_digest"] = plan["plan_digest"]; dialog->accept(); run(r); };
        connect(strict, &QPushButton::clicked, this, [execute] { execute("strict"); });
        connect(mapped, &QPushButton::clicked, this, [execute] { execute("mapped"); });
        connect(buttons, &QDialogButtonBox::rejected, dialog, &QDialog::reject); layout->addWidget(buttons);
        if (strict->isEnabled()) strict->setDefault(true); else buttons->button(QDialogButtonBox::Cancel)->setDefault(true);
        dialog->open();
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
        const auto index = table->selectionModel()->selectedRows().first();
        if (model.editableAt(proxy.mapToSource(index).row())->directory) {
            status->setText("Select a file entry for replacement."); return;
        }
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
                                          model.editableAt(proxy.mapToSource(index).row())->name, &ok);
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
    auto args = app.arguments();
    if (args.size() > 1 && args[1].startsWith("--smoke"))
        QStandardPaths::setTestModeEnabled(true);
    QTemporaryDir smokeSettings;
    Window window(args.size() > 1 && args[1].startsWith("--smoke") ? smokeSettings.filePath("preferences.ini") : QString());
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
