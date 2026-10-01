#include "../app/archive_model.h"
#include "../app/job_controller.h"
#include <QtTest/QAbstractItemModelTester>
#include <iostream>

static void expect(bool value, const char *message) { if (!value) qFatal("%s", message); }
static QJsonObject item(int id, QStringList parts, bool directory = false) {
    return {{"id", id}, {"components", QJsonArray::fromStringList(parts)}, {"path", parts.join('/')},
            {"directory", directory}, {"size", "0"}};
}
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    Entries model;
    QAbstractItemModelTester tester(&model, QAbstractItemModelTester::FailureReportingMode::Fatal);
    model.append({item(0, {"dir", "a"}), item(1, {"dir", "a"}), item(2, {"dir"}, true), item(3, {"dir"}, true),
                  item(4, {"Dir", "b"}), item(5, {"literal/slash"}), item(6, {"empty"}, true)});
    model.finish();
    expect(model.rowCount() == 4, "Root folders, case variants and literal slash must remain distinct");
    expect(model.idsAt(0) == QJsonArray({0, 1, 2, 3}), "Grouped folder must retain both duplicate directory IDs");
    expect(!model.editableAt(0), "Grouped directory cannot be renamed as a file");
    expect(model.navigate({"dir"}) && model.rowCount() == 2, "Implicit folder must expose duplicate files");
    expect(model.idsAt(0) == QJsonArray({0}) && model.idsAt(1) == QJsonArray({1}), "Duplicate file IDs must survive navigation");
    model.searchMode(true); expect(model.rowCount() == 7, "Search must include all archive entries");
    expect(model.data(model.index(5, 0), Qt::DisplayRole) == "literal/slash", "Literal Mac slash is a single component");
    model.searchMode(false); expect(model.currentParts() == QStringList{"dir"}, "Clearing search restores current folder");
    model.up(); expect(model.currentParts().isEmpty(), "Up returns to root");
    model.back(); expect(model.currentParts() == QStringList{"dir"}, "Back restores navigation history");
    model.navigate({"empty"}); expect(model.rowCount() == 0 && model.currentIds() == QJsonArray({6}), "Empty explicit folder retains extractable directory ID");
    expect(!model.navigate({"literal", "slash"}), "Literal slash must not create virtual folders");
    QSortFilterProxyModel proxy; proxy.setSourceModel(&model); proxy.setSortRole(Entries::SortRole);
    proxy.setFilterRole(Entries::SearchRole); proxy.setFilterKeyColumn(0);
    model.searchMode(true); proxy.setFilterFixedString("dir/a"); proxy.sort(0, Qt::DescendingOrder);
    expect(proxy.rowCount() == 2, "Global search must retain duplicate file results");
    expect(proxy.index(0,0).data(Entries::IdRole).isValid(), "Sorting must preserve numeric identity");
    model.clear(); expect(model.rowCount() == 0, "Clearing archive clears hierarchy");
    QElapsedTimer clock; clock.start();
    QJsonArray batch;
    for (int i = 0; i < 100000; ++i) {
        batch.append(item(i, {QString("folder%1").arg(i / 1000), QString("file%1").arg(i)}));
        if (batch.size() == 500) { model.append(batch); batch = {}; }
    }
    model.finish(); const auto buildMs = clock.elapsed();
    clock.restart(); model.navigate({"folder99"}); expect(model.rowCount() == 1000, "Scale folder count");
    const auto navMs = clock.elapsed();

    for (const QString mode : {"ok", "nonzero", "missing", "invalid", "duplicate", "password", "burst"}) {
        JobController job; QEventLoop loop;
        int events = 0; job.onEvent = [&](const QJsonObject &) { ++events; };
        QObject::connect(&job.process, &QProcess::started, &app, [&] { job.process.write(QJsonDocument(QJsonObject{{"mode", mode}, {"password", "secret-value"}}).toJson(QJsonDocument::Compact) + "\n"); });
        job.onFinished = [&](int, QProcess::ExitStatus) { loop.quit(); };
        job.onStartFailure = [&] { loop.quit(); };
        QTimer timeout; timeout.setSingleShot(true); QObject::connect(&timeout, &QTimer::timeout, &loop, &QEventLoop::quit); timeout.start(5000);
        job.start({{"operation", "extract"}, {"password", "secret-value"}}, QString::fromLocal8Bit(argv[1]));
        loop.exec(); expect(job.result.finished, "Controller must receive process termination");
        expect(job.result.success == (mode == "ok" || mode == "burst"), "Only normal zero exit with one complete event is success");
        if (mode == "burst") expect(events == 10001, "Buffered events must drain before worker exit is finalized");
        expect(!job.result.report().contains("secret-value"), "Diagnostics must redact passwords");
        if (mode == "password") expect(job.result.terminal["code"] == "password_required", "Password code must remain structured");
    }
    JobResult result; result.begin({{"operation", "extract"}});
    result.accept({{"event", "error"}, {"message", "Checksum failed"}});
    result.accept({{"event", "cleanup_failed"}, {"message", "Keep stage"}, {"path", "recovery-path"}});
    result.finish(1, QProcess::NormalExit); result.cleanup += "; later cleanup succeeded";
    expect(result.report().contains("Checksum failed") && result.report().contains("later cleanup succeeded"), "Cleanup must not erase original failure");
    JobResult crash; crash.begin({}); crash.accept({{"event", "complete"}}); crash.finish(0, QProcess::CrashExit);
    expect(!crash.success, "Crash after completion must fail");
    JobResult incomplete; incomplete.begin({{"operation", "extract"}}); incomplete.accept({{"event", "complete"}}); incomplete.finish(0, QProcess::NormalExit);
    expect(!incomplete.success, "Extraction success requires confirmation of committed output");
    JobResult classic; classic.begin({{"operation", "export_classic"}}); classic.accept({{"event", "complete"}}); classic.finish(0, QProcess::NormalExit);
    expect(!classic.success, "Classic export requires committed output");
    JobResult preflight; preflight.begin({{"operation", "export_classic"}}); preflight.accept({{"event", "complete"}, {"preflight", true}}); preflight.finish(0, QProcess::NormalExit);
    expect(preflight.success, "Preflight succeeds without claiming output");
    JobController missing; QEventLoop loop;
    missing.onStartFailure = [&] { loop.quit(); }; missing.start({}, "Z:/missing-packsmith-worker.exe");
    QTimer::singleShot(5000, &loop, &QEventLoop::quit); loop.exec();
    expect(missing.result.finished && !missing.result.success && missing.result.failure.contains("Cannot start"), "Worker start failure must be a result");
    std::cout << "{\"passed\":true,\"entries\":100000,\"model_build_ms\":" << buildMs << ",\"folder_navigation_ms\":" << navMs << "}\n";
}
