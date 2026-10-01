#include <QtTest>
#include <iostream>
#define main packsmith_main
#include "../app/main.cpp"
#undef main

struct GuiChecks {
    static void expect(bool value, const char *message) { if (!value) { std::cerr << message << std::endl; std::exit(1); } }
    static void run(Window &w, const QString &fixture) {
        w.model.append({QJsonObject{{"id", 0}, {"path", "dir/a"}, {"components", QJsonArray{"dir", "a"}}, {"size", "2"}},
                        QJsonObject{{"id", 1}, {"path", "dir/a"}, {"components", QJsonArray{"dir", "a"}}, {"size", "3"}},
                        QJsonObject{{"id", 2}, {"path", "empty"}, {"components", QJsonArray{"empty"}}, {"directory", true}},
                        QJsonObject{{"id", 3}, {"path", "<b>literal/slash</b>"}, {"components", QJsonArray{"<b>literal/slash</b>"}}}});
        w.model.finish(); w.listingValid = true; w.readOnly = true; w.setBusy(false); w.navigated();
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
        w.table->selectRow(0); const auto before = w.selected();
        w.table->sortByColumn(1, Qt::DescendingOrder); expect(w.selected() == before, "Sorting preserves selected ID");
        w.search->setText("dir/a"); expect(w.model.searching() && w.proxy.rowCount() == 2, "Search is global");
        expect(!w.extractAction->isEnabled() && w.extractAllAction->isEnabled(), "Search requires explicit selected extraction");
        expect(w.classicRequest(false).isEmpty() && !w.classicAction->isEnabled(), "Classic search requires selection");
        w.table->selectRow(1); expect(w.extractAction->isEnabled(), "Selected search result enables extraction");
        expect(w.classicAction->isEnabled() && w.classicRequest(false)["ids"].toArray().size()==1, "Classic search uses selected IDs");
        w.search->clear(); expect(w.model.currentParts() == QStringList{"dir"} && w.selected().isEmpty(), "Clearing search restores folder and clears hidden selection");
        QTest::keyClick(&w, Qt::Key_Up, Qt::AltModifier); QTest::qWait(150);
        expect(w.model.currentParts().isEmpty(), "Alt+Up navigates to parent");
        QTest::keyClick(&w, Qt::Key_Left, Qt::AltModifier); QTest::qWait(150);
        expect(w.model.currentParts() == QStringList{"dir"}, "Alt+Left navigates back");
        w.model.navigate({"empty"}); w.navigated(); expect(w.model.currentIds() == QJsonArray({2}), "Empty directory does not request all entries");
        w.search->setText("literal"); w.table->setCurrentIndex(w.proxy.index(0,0)); w.table->setFocus();
        QTest::keyClick(w.table, Qt::Key_Return); QTest::qWait(20);
        auto details = w.findChild<QMessageBox *>();
        expect(details && details->isVisible() && details->textFormat() == Qt::PlainText, "Enter on a file opens plain-text details");
        details->close(); w.search->clear();
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
        if (!fixture.isEmpty()) {
            QTemporaryDir destination;expect(destination.isValid(),"Classic GUI test destination exists");
            w.passwordDefined=false;w.filenameEncoding="macintosh";w.openArchive(fixture);
            for(int i=0;i<400 && w.busy;++i)QTest::qWait(25);
            expect(w.listingValid && !w.busy,"Classic GUI test lists a real archive");
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
        }
        w.grab().save("ui-test.png");
    }
};
int main(int argc, char **argv) {
    QApplication app(argc, argv); app.setApplicationName("Packsmith-beta3-tests"); QStandardPaths::setTestModeEnabled(true);
    app.setWindowIcon(QIcon(":/brand/packsmith.ico")); Window window; window.show(); window.activateWindow(); QTest::qWait(100);
    GuiChecks::run(window, argc>1 ? QString::fromLocal8Bit(argv[1]) : QString()); qInfo("Native folder and classic export UI checks passed"); return 0;
}
