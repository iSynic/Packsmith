#include <QtTest>
#include <iostream>
#define main packsmith_main
#include "../app/main.cpp"
#undef main

static QStringList announcements;
static void accessibilityEvent(QAccessibleEvent *event) {
    if (event->type()==QAccessible::Announcement) announcements.append(static_cast<QAccessibleAnnouncementEvent *>(event)->message());
}

struct GuiChecks {
    static void expect(bool value, const char *message) { if (!value) { std::cerr << message << std::endl; std::exit(1); } }
    static void run(Window &w, const QString &fixture) {
        QTemporaryDir settings;
        RecentArchives history(settings.filePath("history.ini"));
        expect(!history.enabled() && history.paths().isEmpty(), "History is opt in");
        history.opened("private.sit"); expect(history.paths().isEmpty(), "Disabled history records nothing");
        history.enable(true);
        for (int i=0;i<12;++i) history.opened(settings.filePath(QString("caf\u00e9-%1.sit").arg(i)));
        expect(history.paths().size()==10,"History is bounded to ten paths");
        auto latest=history.paths().first(); history.opened(latest.toUpper()); expect(history.paths().size()==10,"Windows paths deduplicate case insensitively");
        RecentArchives reopened(settings.filePath("history.ini")); expect(reopened.paths()==history.paths(),"Opted-in history persists");
        history.clear(); expect(history.paths().isEmpty(),"Clear history takes effect immediately");
        history.opened(latest); history.enable(false); history.enable(true); expect(history.paths().isEmpty(),"Disabling history clears stored paths");
        QSettings stored(settings.filePath("history.ini"),QSettings::IniFormat);
        expect(stored.allKeys()==QStringList{"recent/enabled"},"History stores no unrelated or sensitive settings");
        QString error;
        expect(archiveDropPath({QUrl("https://example.com/archive.sit")},error).isEmpty(),"Remote drops rejected");
        expect(archiveDropPath({QUrl("file://server/share/archive.sit")},error).isEmpty(),"Network file URLs rejected");
        expect(archiveDropPath({QUrl::fromLocalFile(settings.path())},error).isEmpty(),"Directory drops rejected");
        expect(archiveDropPath({QUrl::fromLocalFile(fixture),QUrl::fromLocalFile(fixture)},error).isEmpty(),"Multiple drops rejected");
        w.archive="unchanged.sit";w.password="secret";w.fingerprint="stable";w.setBusy(true);
        w.openArchive(fixture);expect(w.archive=="unchanged.sit" && w.password=="secret" && w.fingerprint=="stable","Busy opening preserves archive identity and credentials");
        w.setBusy(false);w.recoveryRequired=true;w.openArchive(fixture);expect(w.archive=="unchanged.sit","Recovery blocks archive replacement");w.recoveryRequired=false;
        w.recent.enable(true);w.recent.opened(settings.filePath("missing.sit"));w.openArchive(settings.filePath("missing.sit"));expect(w.recent.paths().isEmpty() && w.archive=="unchanged.sit","Missing recent file is removed without disturbing current archive");
        w.password.clear();
        auto accessible=QAccessible::queryAccessibleInterface(w.table);
        expect(accessible && accessible->role()==QAccessible::Table && accessible->text(QAccessible::Name)=="Archive entries","Entries expose a named accessible table");
        expect(w.resultBox->isHidden() && w.resultDetails->isHidden(), "No empty result panel before a job completes");
        expect(!w.findChild<QLabel *>("product"), "Archive heading has no redundant branding row");
        w.model.append({QJsonObject{{"id", 0}, {"path", "dir/a"}, {"components", QJsonArray{"dir", "a"}}, {"size", "2"}},
                        QJsonObject{{"id", 1}, {"path", "dir/a"}, {"components", QJsonArray{"dir", "a"}}, {"size", "3"}},
                        QJsonObject{{"id", 2}, {"path", "empty"}, {"components", QJsonArray{"empty"}}, {"directory", true}},
                        QJsonObject{{"id", 3}, {"path", "<b>literal/slash</b>"}, {"components", QJsonArray{"<b>literal/slash</b>"}}}});
        w.model.finish(); w.listingValid = true; w.readOnly = true; w.setBusy(false); w.navigated();
        expect(w.extractionFilenamePolicy == "readable" && w.extractionForkStyle == "rsrc", "GUI defaults to readable visible forks");
        expect(w.legacyOptionsAction->isEnabled(), "Legacy options accessible through Archive menu");
        QTimer::singleShot(0, &w, [&] {
            auto dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
            expect(dialog, "Native extraction options dialog opens");
            auto names = dialog->findChild<QComboBox *>("extractionFilenamePolicy");
            auto forks = dialog->findChild<QComboBox *>("extractionForkStyle");
            expect(names && forks && !names->accessibleName().isEmpty() && !forks->accessibleName().isEmpty(), "Extraction choices have accessible names");
            names->setCurrentIndex(names->findData("escaped")); forks->setCurrentIndex(forks->findData("appledouble")); dialog->reject();
        });
        w.legacyExtractionOptions();
        expect(w.extractionFilenamePolicy == "readable" && w.extractionForkStyle == "rsrc", "Cancel preserves extraction settings");
        QTimer::singleShot(0, &w, [&] {
            auto dialog = qobject_cast<QDialog *>(QApplication::activeModalWidget());
            dialog->findChild<QComboBox *>("extractionFilenamePolicy")->setCurrentIndex(1);
            dialog->findChild<QComboBox *>("extractionForkStyle")->setCurrentIndex(1); dialog->accept();
        });
        w.legacyExtractionOptions();
        expect(w.extractionFilenamePolicy == "escaped" && w.extractionForkStyle == "appledouble", "Accept keeps preservation mode available");
        expect(w.table->hasFocus(), "Extraction settings restore entry focus");
        w.extractionFilenamePolicy = "readable"; w.extractionForkStyle = "rsrc";
        w.heading->setText("<b>untrusted.sit</b>");
        expect(w.heading->textFormat() == Qt::PlainText && w.status->textFormat() == Qt::PlainText, "Untrusted labels must remain plain text");
        int folderRow = -1;
        for (int i = 0; i < w.proxy.rowCount(); ++i) if (w.model.partsAt(w.proxy.mapToSource(w.proxy.index(i, 0)).row()) == QStringList{"dir"}) folderRow = i;
        expect(folderRow >= 0, "Folder visible at root");
        w.table->selectRow(folderRow); w.activate(w.proxy.index(folderRow, 0));
        expect(w.model.currentParts() == QStringList{"dir"}, "Activating folder enters it");
        expect(w.selected().isEmpty(), "Navigation clears selection");
        expect(w.model.currentIds() == QJsonArray({0, 1}), "Current-folder scope includes duplicate IDs");
        expect(w.classicRequest(false)["ids"].toArray() == QJsonArray({0,1}), "Classic export uses current-folder IDs");
        expect(w.classicRequest(true)["selection_scope"] == "all", "Classic Export All has explicit scope");
        expect(w.table->hasFocus(), "Navigation restores keyboard focus");
        expect(!w.model.data(w.proxy.mapToSource(w.proxy.index(0,0)),Qt::AccessibleTextRole).toString().isEmpty(),"Entry paths have accessible text");
        w.table->selectRow(0); const auto before = w.selected();
        w.table->sortByColumn(1, Qt::DescendingOrder); expect(w.selected() == before, "Sorting preserves selected ID");
        w.search->setText("dir/a"); expect(w.model.searching() && w.proxy.rowCount() == 2, "Search is global");
        expect(!w.extractAction->isEnabled() && w.extractAllAction->isEnabled(), "Search requires explicit selected extraction");
        expect(w.classicRequest(false).isEmpty() && !w.classicAction->isEnabled(), "Classic search requires selection");
        w.table->selectRow(1); expect(w.extractAction->isEnabled(), "Selected search result enables extraction");
        expect(w.classicAction->isEnabled() && w.classicRequest(false)["ids"].toArray().size()==1, "Classic search uses selected IDs");
        w.search->clear(); expect(w.model.currentParts() == QStringList{"dir"} && w.selected().isEmpty(), "Clearing search restores folder and clears hidden selection");
        w.activateWindow();expect(QTest::qWaitForWindowActive(&w),"Keyboard navigation requires the active test window");w.table->setFocus();
        QTest::keyClick(w.table, Qt::Key_Up, Qt::AltModifier); QTest::qWait(150);
        expect(w.model.currentParts().isEmpty(), "Alt+Up navigates to parent");
        QTest::keyClick(w.table, Qt::Key_Left, Qt::AltModifier); QTest::qWait(150);
        expect(w.model.currentParts() == QStringList{"dir"}, "Alt+Left navigates back");
        w.model.navigate({"empty"}); w.navigated(); expect(w.model.currentIds() == QJsonArray({2}), "Empty directory does not request all entries");
        w.search->setText("literal"); w.table->setCurrentIndex(w.proxy.index(0,0)); w.table->setFocus();
        QTest::keyClick(w.table, Qt::Key_Return); QTest::qWait(20);
        auto details = w.findChild<QMessageBox *>();
        expect(details && details->isVisible() && details->textFormat() == Qt::PlainText, "Enter on a file opens plain-text details");
        details->close(); w.search->clear();
        QTest::qWait(25);expect(w.table->hasFocus(),"Details dismissal restores entry focus");
        auto updateHandler=QAccessible::installUpdateHandler(accessibilityEvent); QAccessible::setActive(true);
        w.jobs.result.begin({{"password","hidden-password"}});w.announcedPhases.clear();announcements.clear();
        w.event({{"event","progress"},{"phase","decoding"}});w.event({{"event","progress"},{"phase","decoding"}});
        w.event({{"event","progress"},{"phase","verifying"}});w.announce("Error hidden-password");
        expect(announcements.size()==3 && !announcements.last().contains("hidden-password"),"Phase announcements are deduplicated and secrets redacted");
        QAccessible::installUpdateHandler(updateHandler);
        QJsonObject change{{"id",1},{"component",0},{"original","<b>name</b>"},{"restored","name~1"}};
        w.reviewClassic(QJsonObject{{"strict_allowed",false},{"changes",QJsonArray{change}}},{});
        QTest::qWait(25);auto review=w.findChild<QDialog *>("classicPreflight");expect(review && review->isVisible(), "Classic preflight opens a keyboard-accessible native dialog");
        expect(review->findChild<QPlainTextEdit *>()->toPlainText().contains("<b>name</b>"), "Preflight names remain plain text");
        bool strictDisabled=false,mappedEnabled=false;
        for(auto button:review->findChildren<QPushButton *>()) { if(button->text()=="Export")strictDisabled=!button->isEnabled();if(button->text()=="Export with mapped names")mappedEnabled=button->isEnabled(); }
        expect(strictDisabled && mappedEnabled,"Names requiring mapping cannot use strict Export");QTest::keyClick(review,Qt::Key_Escape);QTest::qWait(25);
        for (auto action : w.edits) expect(!action->isEnabled(), "Legacy edit actions remain disabled");
        w.readOnly = false; w.search->setText("empty"); w.table->selectRow(0); w.setBusy(false);
        expect(w.edits[2]->isEnabled() && !w.edits[1]->isEnabled(), "A unique real directory can be renamed, but cannot be replaced with a file");
        w.search->setText("dir");
        // The implicit parent has no real entry to mutate.
        w.search->clear(); w.model.navigate({}); w.navigated();
        for (int i = 0; i < w.proxy.rowCount(); ++i) if (w.model.partsAt(w.proxy.mapToSource(w.proxy.index(i,0)).row()) == QStringList{"dir"}) w.table->selectRow(i);
        expect(!w.edits[2]->isEnabled(), "Implicit folders cannot be renamed as one real entry");
        w.jobs.result.begin({{"operation", "extract"}, {"password", "hidden-password"}});
        w.jobs.result.accept({{"event", "error"}, {"message", "Checksum failed hidden-password"}});
        w.jobs.result.finish(1, QProcess::NormalExit); w.jobs.result.cleanup = "Staging cleaned"; w.showResult();
        QTest::qWait(25);
        expect(w.resultBox->isVisible() && !w.resultDetails->isVisible(), "A completed job shows a compact summary by default");
        expect(w.resultSummary->text() == "Failed · No output committed", "Collapsed failure identifies outcome and commitment");
        expect(w.resultSummary->textFormat() == Qt::PlainText && !w.resultSummary->text().contains("hidden-password"), "Summary stays plain text and excludes private diagnostics");
        if (qEnvironmentVariableIsSet("PACKSMITH_TEST_LARGE_TEXT"))
            expect(w.table->height() > w.resultBox->height(), "Enlarged text keeps the list larger than the collapsed result");
        else
            expect(w.resultBox->height() < 100 && w.table->height() > 3 * w.resultBox->height(), "At standard size the entry list dominates the collapsed result");
        const auto collapsedTableHeight = w.table->height();
        w.resultToggle->setFocus(); QTest::keyClick(w.resultToggle, Qt::Key_Space); QTest::qWait(25);
        expect(w.resultDetails->isVisible() && w.resultText->isVisible() && w.mappingButton->isVisible(), "Keyboard expansion reveals full diagnostics and report controls");
        if (qEnvironmentVariableIsSet("PACKSMITH_TEST_LARGE_TEXT"))
            expect(w.table->viewport()->height() >= w.table->verticalHeader()->defaultSectionSize(), "Enlarged-text details leave visible archive rows");
        else
            expect(w.table->height() >= w.resultBox->height(), "Expanded details retain the larger share of standard-size list space");
        w.resultText->setFocus(); w.resultToggle->click(); QTest::qWait(25);
        expect(!w.resultDetails->isVisible() && w.resultToggle->hasFocus() && w.table->height() == collapsedTableHeight, "Collapsing restores list space and keyboard focus");
        w.grab().save("compact-result.png");
        expect(w.resultText->toPlainText().contains("Checksum failed") && w.resultText->toPlainText().contains("Staging cleaned"), "Durable panel retains failure and cleanup");
        expect(!w.resultText->toPlainText().contains("hidden-password"), "Visible diagnostics exclude passwords");
        bool promptAfterExit = false;
        QTimer dialogCloser;
        QObject::connect(&dialogCloser, &QTimer::timeout, &w, [&] {
            for (auto dialog : w.findChildren<QInputDialog *>()) if (dialog->isVisible()) {
                promptAfterExit = w.process.state() == QProcess::NotRunning && w.jobs.result.finished && !w.busy && w.pendingRecovery.isEmpty();
                dialog->reject();
            }
        });
        dialogCloser.start(10);
        w.operation = "list"; w.request = {{"operation", "list"}, {"mode", "password"}, {"password", "hidden-password"}};
        w.setBusy(true); w.jobs.start(w.request, QCoreApplication::applicationDirPath() + "/packsmith-fake-worker.exe");
        QTest::qWait(500); dialogCloser.stop();
        expect(promptAfterExit, "Password prompt must wait for worker exit and cleanup");
        expect(!w.resultText->toPlainText().contains("hidden-password"), "Password-required diagnostics remain redacted");
        updateHandler=QAccessible::installUpdateHandler(accessibilityEvent);announcements.clear();w.announcedOutcome=false;
        w.setBusy(true);w.jobs.start({{"operation","list"}},settings.filePath("missing-worker.exe"));QTest::qWait(100);
        expect(!w.busy && w.jobs.result.finished && !w.jobs.result.success && announcements.size()==1,"Worker start failure has one accessible terminal announcement");
        QAccessible::installUpdateHandler(updateHandler);for(auto dialog:w.findChildren<QDialog *>())if(dialog->isVisible())dialog->reject();
        if (!fixture.isEmpty()) {
            QTemporaryDir destination;expect(destination.isValid(),"Classic GUI test destination exists");
            w.passwordDefined=false;w.filenameEncoding="macintosh";
            QMimeData mime; mime.setUrls({QUrl::fromLocalFile(fixture)});
            QDropEvent dropped(QPointF(20,20),Qt::CopyAction,&mime,Qt::LeftButton,Qt::NoModifier);
            w.dropEvent(&dropped);expect(dropped.isAccepted(),"Single local file drop opens through the shared path");
            for(int i=0;i<400 && w.busy;++i)QTest::qWait(25);
            expect(w.listingValid && !w.busy,"Classic GUI test lists a real archive");
            expect(w.recent.paths().size()==1 && w.password.isEmpty() && w.filenameEncoding.isEmpty(),"Successful opening alone records history and clears archive-specific state");
            w.run({{"operation", "extract"}, {"destination", destination.path()}, {"selection_scope", "all"}});
            expect(w.request["filename_policy"] == "readable" && w.request["resource_fork_style"] == "rsrc", "GUI passes explicit extraction policies to its real worker");
            for(int i=0;i<400 && w.busy;++i)QTest::qWait(25);
            expect(w.jobs.result.success && w.jobs.result.terminal["resource_fork_style"] == "rsrc", "Native GUI extraction commits visible fork output");
            expect(w.resultText->toPlainText().contains("Resource fork output: rsrc"), "Result panel explains the chosen output style");
            auto request=w.classicRequest(true);request["destination"]=destination.filePath("Transfer.zip");w.run(request);
            QDialog *preflight=nullptr;
            for(int i=0;i<400 && !preflight;++i) { QTest::qWait(25);preflight=w.findChild<QDialog *>("classicPreflight"); }
            expect(preflight && preflight->isVisible(),"Real worker preflight reaches native review");
            QPushButton *exportButton=nullptr;
            for(auto button:preflight->findChildren<QPushButton *>())if(button->text()=="Export")exportButton=button;
            expect(exportButton && exportButton->isEnabled(),"Strict generated names enable Export");
            exportButton->setFocus();QTest::keyClick(exportButton,Qt::Key_Return);
            for(int i=0;i<400 && w.busy;++i)QTest::qWait(25);
            expect(w.jobs.result.success && QFileInfo::exists(destination.filePath("Transfer.zip")),"Keyboard export produces a verified ZIP after worker exit");
            expect(w.resultText->toPlainText().contains("Output committed: yes") && w.mappingButton->isEnabled(),"Classic result exposes commitment and mapping");
            w.jobs.result.begin({{"operation","list"}});
            w.mappingButton->click();QTest::qWait(25);expect(w.findChild<QTableWidget *>(),"Mapping uses a readable native table");
            expect(w.lastResultClassic,"Preservation review remains tied to the displayed result across a later listing");
            for(auto dialog:w.findChildren<QDialog *>())if(dialog->isVisible())dialog->reject();
            const auto previousHistory=w.recent.paths();
            auto invalid=settings.filePath("not-an-archive.cpt");QFile bad(invalid);expect(bad.open(QIODevice::WriteOnly),"Invalid input created");bad.write("not archive bytes");bad.close();
            w.openArchive(invalid);for(int i=0;i<400 && w.busy;++i)QTest::qWait(25);
            expect(!w.jobs.result.success && w.recent.paths()==previousHistory,"Failed listings are never added to history");
            for(auto dialog:w.findChildren<QDialog *>())if(dialog->isVisible())dialog->reject();
        }
        w.grab().save("ui-test.png");
    }
};
int main(int argc, char **argv) {
    QApplication app(argc, argv); app.setApplicationName("Packsmith-beta4-tests"); QStandardPaths::setTestModeEnabled(true);
    if(qEnvironmentVariableIsSet("PACKSMITH_TEST_LARGE_TEXT")) { auto font=app.font();font.setPointSize(16);app.setFont(font); }
    if(qEnvironmentVariableIsSet("PACKSMITH_TEST_CONTRAST")) { QPalette palette;palette.setColor(QPalette::Window,Qt::black);palette.setColor(QPalette::Base,Qt::black);palette.setColor(QPalette::AlternateBase,Qt::black);palette.setColor(QPalette::Text,Qt::white);palette.setColor(QPalette::WindowText,Qt::white);palette.setColor(QPalette::Button,Qt::black);palette.setColor(QPalette::ButtonText,Qt::white);palette.setColor(QPalette::Highlight,Qt::yellow);palette.setColor(QPalette::HighlightedText,Qt::black);app.setPalette(palette); }
    QTemporaryDir preferences;
    app.setWindowIcon(QIcon(":/brand/packsmith.ico")); Window window(preferences.filePath("preferences.ini")); window.show(); window.activateWindow(); QTest::qWait(100);
    if(app.arguments().contains("--manual")) { if(argc>1)window.openArchive(QString::fromLocal8Bit(argv[1]));return app.exec(); }
    GuiChecks::run(window, argc>1 ? QString::fromLocal8Bit(argv[1]) : QString()); qInfo("Native folder and classic export UI checks passed"); return 0;
}
