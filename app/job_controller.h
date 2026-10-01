#pragma once
#include <QtCore>
#include <functional>

struct JobResult {
    QString operation, archive, password;
    QJsonObject terminal;
    QStringList warnings;
    QString failure, cleanup;
    bool finished = false, success = false;
    void begin(const QJsonObject &request) {
        *this = {}; operation = request["operation"].toString(); archive = request["archive"].toString();
        password = request["password"].toString();
    }
    QString redact(QString text) const { if (!password.isEmpty()) text.replace(password, "[redacted]"); return text; }
    void accept(const QJsonObject &event) {
        const auto kind = event["event"].toString();
        if (kind == "complete" || kind == "error" || kind == "cancelled") {
            if (!terminal.isEmpty()) failure = "Worker sent multiple terminal events.";
            else terminal = event;
        }
        if (kind == "error" || kind == "cancelled") failure = event["message"].toString();
        if (kind == "warning") warnings.append(event["message"].toString());
        if (kind == "cleanup_failed") cleanup = event["message"].toString() + " " + event["path"].toString();
        if (kind == "recovery_required") cleanup = "Manual recovery required: " + event["archive"].toString() + " " + event["backup"].toString();
    }
    void finish(int code, QProcess::ExitStatus exit) {
        finished = true;
        success = failure.isEmpty() && terminal["event"] == "complete" && code == 0 && exit == QProcess::NormalExit;
        if (success && (operation == "extract" || operation == "create" || operation == "update" || (operation == "export_classic" && !terminal["preflight"].toBool())) &&
            (!terminal["output_committed"].toBool() || terminal["output"].toString().isEmpty())) {
            success = false; failure = "Worker completed without confirming committed output.";
        }
        if (success && operation == "list" && (terminal["fingerprint"].toString().isEmpty() || terminal["count"].toInteger(-1) < 0)) {
            success = false; failure = "Worker completed without a valid archive identity and count.";
        }
        if (!success && failure.isEmpty()) failure = terminal.isEmpty()
            ? QString("Worker stopped without a terminal result (exit %1).").arg(code)
            : QString("Worker exited unsuccessfully after its completion event (exit %1).").arg(code);
    }
    QString report() const {
        QStringList lines{operation.isEmpty() ? "Recovery" : operation + ": " + (finished ? success ? "Completed" : "Failed or cancelled" : "Running"), "Archive: " + archive};
        const bool committed = terminal["output_committed"].toBool();
        if (operation == "extract" || operation == "export_classic") lines.append(QString("Output committed: %1").arg(committed ? "yes" : "no"));
        if (!terminal["output"].toString().isEmpty()) lines.append("Output: " + terminal["output"].toString());
        if (!terminal["message"].toString().isEmpty() && success) lines.append(terminal["message"].toString());
        if (!failure.isEmpty()) lines.append("Failure: " + failure);
        if (!terminal["code"].toString().isEmpty()) lines.append("Code: " + terminal["code"].toString());
        if (!terminal["engine"].toString().isEmpty()) lines.append("Backend: " + terminal["engine"].toString());
        if (terminal["id"].toInteger(-1) >= 0) lines.append(QString("Entry: %1 · Fork: %2").arg(terminal["id"].toInteger()).arg(terminal["part"].toString()));
        if (terminal.contains("count")) lines.append(QString("Entries: %1").arg(terminal["count"].toInteger()));
        if (terminal.contains("file_count")) lines.append(QString("Files: %1 · Data forks: %2 · Resource forks: %3").arg(terminal["file_count"].toInteger()).arg(terminal["data_forks"].toInteger()).arg(terminal["resource_forks"].toInteger()));
        const auto coverage = terminal["checksum_coverage"].toObject();
        if (!coverage.isEmpty() && operation != "list") {
            lines.append(QString("Source checksums: %1 checked fork streams; %2 without source checksums; %3 expanded wrappers.").arg(coverage["checked_forks"].toInteger()).arg(coverage["unchecked_forks"].toInteger()).arg(coverage["expanded_wrappers"].toInteger()));
            if (coverage["unchecked_forks"].toInteger()) lines.append("Completed with verification limits: decoded streams without source checksums are not checksum-verified.");
        }
        if (terminal.contains("mapped_names")) lines.append(QString("Mapped names: %1 (see mapping for substitutions and collisions)").arg(terminal["mapped_names"].toInteger()));
        if (!terminal["preservation"].toString().isEmpty()) lines.append("Preservation limits: " + terminal["preservation"].toString());
        for (const auto &warning : warnings) lines.append("Warning: " + warning);
        if (!cleanup.isEmpty()) lines.append("Cleanup/recovery: " + cleanup);
        return redact(lines.join('\n'));
    }
};

class JobController : public QObject {
    QByteArray incoming;
    bool drainScheduled = false, exitPending = false;
    bool discardEvents = false;
    int exitCode = 0;
    QProcess::ExitStatus exitStatus = QProcess::NormalExit;
    void finishIfReady() {
        if (!exitPending || drainScheduled || incoming.contains('\n')) return;
        if (!incoming.trimmed().isEmpty()) result.failure = "Incomplete worker event.";
        incoming.clear(); exitPending = false;
        result.finish(exitCode, exitStatus); if (onFinished) onFinished(exitCode, exitStatus);
    }
    void read() {
        incoming += process.readAllStandardOutput();
        if (discardEvents) incoming.clear();
        if (!drainScheduled) drain();
    }
    void drain() {
        drainScheduled = false;
        QElapsedTimer budget; budget.start();
        qsizetype pos;
        while ((pos = incoming.indexOf('\n')) >= 0) {
            auto line = incoming.left(pos); incoming.remove(0, pos + 1);
            QJsonParseError error;
            auto doc = QJsonDocument::fromJson(line, &error);
            if (error.error != QJsonParseError::NoError || !doc.isObject()) result.failure = "Invalid worker event.";
            else {
                auto event = doc.object(); result.accept(event); if (onEvent) onEvent(event);
            }
            if (budget.elapsed() >= 8 && incoming.contains('\n')) {
                drainScheduled = true; QTimer::singleShot(0, this, [this] { drain(); }); return;
            }
        }
        finishIfReady();
    }
  public:
    QProcess process;
    JobResult result;
    std::function<void(const QJsonObject &)> onEvent;
    std::function<void(int, QProcess::ExitStatus)> onFinished;
    std::function<void()> onStartFailure;
    JobController() {
        connect(&process, &QProcess::readyReadStandardOutput, this, [this] { read(); });
        connect(&process, &QProcess::readyReadStandardError, this, [this] { process.readAllStandardError(); });
        connect(&process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus exit) {
            read(); exitCode = code; exitStatus = exit; exitPending = true; finishIfReady();
        });
        connect(&process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
            if (error == QProcess::FailedToStart) {
                result.failure = "Cannot start the packaged worker: " + process.errorString();
                result.finish(-1, QProcess::CrashExit); if (onStartFailure) onStartFailure();
            }
        });
    }
    void start(const QJsonObject &request, const QString &program) {
        incoming.clear(); drainScheduled = false; exitPending = false; discardEvents = false; result.begin(request); process.setProgram(program); process.setArguments({}); process.start();
    }
    void cancel() {
        if (process.state() != QProcess::NotRunning) process.write("{\"cancel\":true}\n");
        else {
            discardEvents = true; incoming.clear(); result.failure = "Cancelled while reading the worker result.";
            result.terminal = {{"event", "cancelled"}, {"code", "cancelled"}, {"message", result.failure}};
            finishIfReady();
        }
    }
};
