#pragma once
#include <QtCore>

inline QString normalizedArchivePath(const QString &path) {
    return QDir::cleanPath(QFileInfo(path).absoluteFilePath());
}

inline QString archiveDropPath(const QList<QUrl> &urls, QString &error) {
    if (urls.size() != 1) error = "Drop exactly one archive file.";
    else if (!urls.first().isLocalFile() || !urls.first().host().isEmpty() || urls.first().toLocalFile().startsWith("//") || urls.first().toLocalFile().startsWith("\\\\")) error = "Only local archive files can be opened.";
    else if (!QFileInfo(urls.first().toLocalFile()).isFile()) error = "Choose an existing archive file, not a folder.";
    else return normalizedArchivePath(urls.first().toLocalFile());
    return {};
}

class RecentArchives {
    QSettings settings;
    static QString storagePath(QString path) {
        if (path.isEmpty()) path = QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation) + "/preferences.ini";
        return path;
    }
  public:
    explicit RecentArchives(QString path = {}) : settings(storagePath(path), QSettings::IniFormat) {}
    bool enabled() const { return settings.value("recent/enabled", false).toBool(); }
    QStringList paths() const { return enabled() ? settings.value("recent/paths").toStringList().mid(0, 10) : QStringList{}; }
    void clear() { settings.remove("recent/paths"); settings.sync(); }
    void enable(bool value) {
        settings.setValue("recent/enabled", value);
        if (!value) clear();
        settings.sync();
    }
    void remove(const QString &path) {
        if (!enabled()) return;
        auto list = paths();
        list.removeIf([&](const QString &p) { return p.compare(normalizedArchivePath(path), Qt::CaseInsensitive) == 0; });
        settings.setValue("recent/paths", list); settings.sync();
    }
    void opened(const QString &path) {
        if (!enabled()) return;
        remove(path); auto list = paths(); list.prepend(normalizedArchivePath(path));
        settings.setValue("recent/paths", list.mid(0, 10)); settings.sync();
    }
};
