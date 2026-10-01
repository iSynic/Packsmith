#pragma once
#include <QtCore>

inline QString visibleName(const QString &name) {
    QString text;
    const bool whitespaceOnly = name.trimmed().isEmpty();
    for (QChar c : name) {
        if (c == '\t') text += "\\t";
        else if (c == '\n') text += "\\n";
        else if (c == '\r') text += "\\r";
        else if (c == '\\') text += "\\\\";
        else if (c.unicode() < 32 || c.unicode() == 127 || c.category() == QChar::Other_Format)
            text += QString("\\u%1").arg(uint(c.unicode()), 4, 16, QChar('0'));
        else if (whitespaceOnly && c == ' ') text += "\\x20";
        else text += c;
    }
    return text;
}
inline QString displayPath(const QStringList &parts) {
    QStringList escaped;
    for (const auto &part : parts) escaped.append(visibleName(part));
    return escaped.join('/');
}
struct Row {
    quint32 id = 0;
    QString name;
    quint64 size = 0;
    bool directory = false, encrypted = false, link = false;
    quint64 resourceSize = 0;
    bool resourceFork = false;
    QStringList components;
    QJsonObject metadata;
    QString displayName, displayFull, displayLocation;
};

class Entries final : public QAbstractTableModel {
    struct Node {
        QStringList parts;
        bool folder = false;
        QVector<int> realRows, children;
        QVector<quint32> ids;
        int parent = -1;
        QString displayName, displayFull, displayLocation;
    };
    QVector<Node> nodes;
    QVector<int> view;
    QVector<int> history;
    int current = 0;
    bool global = false;
    static QString key(const QStringList &parts) {
        return QString::fromUtf8(QJsonDocument(QJsonArray::fromStringList(parts)).toJson(QJsonDocument::Compact));
    }
    void refresh() {
        beginResetModel();
        view.clear();
        if (global) {
            for (int i = 0; i < rows.size(); ++i) view.append(i);
        } else if (!nodes.isEmpty()) view = nodes[current].children;
        endResetModel();
    }
    const Row *entryAt(int row) const {
        if (row < 0 || row >= view.size()) return nullptr;
        if (global) return &rows[view[row]];
        const auto &n = nodes[view[row]];
        return n.realRows.size() == 1 ? &rows[n.realRows.first()] : nullptr;
    }
  public:
    enum { IdRole = Qt::UserRole, SortRole, SearchRole };
    QVector<Row> rows;
    int rowCount(const QModelIndex &parent = {}) const override { return parent.isValid() ? 0 : int(view.size()); }
    int columnCount(const QModelIndex &parent = {}) const override { return parent.isValid() ? 0 : 6; }
    QVariant headerData(int section, Qt::Orientation orientation, int role) const override {
        if (orientation == Qt::Horizontal && role == Qt::DisplayRole)
            return QStringList{"Name", "Data size", "Resource fork", "Type", "Protection", "Location"}.value(section);
        return QAbstractTableModel::headerData(section, orientation, role);
    }
    QStringList partsAt(int row) const { return global ? rows[view[row]].components : nodes[view[row]].parts; }
    bool folderAt(int row) const { return global ? rows[view[row]].directory : nodes[view[row]].folder; }
    const Row *editableAt(int row) const {
        auto r = entryAt(row);
        if (r && r->directory && global) {
            for (const auto &n : nodes) if (n.folder && n.parts == r->components && n.realRows.size() != 1) return nullptr;
        }
        return r;
    }
    QJsonArray idsAt(int row) const {
        if (row < 0 || row >= view.size()) return {};
        if (global && !rows[view[row]].directory) return {qint64(rows[view[row]].id)};
        QStringList parts = partsAt(row);
        if (global) {
            for (const auto &n : nodes) if (n.folder && n.parts == parts) {
                QJsonArray result; for (auto id : n.ids) result.append(qint64(id)); return result;
            }
        }
        QJsonArray result;
        for (auto id : nodes[view[row]].ids) result.append(qint64(id));
        return result;
    }
    QJsonArray currentIds() const {
        QJsonArray result;
        if (!nodes.isEmpty()) for (auto id : nodes[current].ids) result.append(qint64(id));
        return result;
    }
    QStringList currentParts() const { return nodes.isEmpty() ? QStringList{} : nodes[current].parts; }
    bool searching() const { return global; }
    bool canBack() const { return !history.isEmpty() && !global; }
    bool canUp() const { return current != 0 && !global; }
    void searchMode(bool value) { if (value != global) { global = value; refresh(); } }
    bool navigate(const QStringList &parts) {
        for (int i = 0; i < nodes.size(); ++i) if (nodes[i].folder && nodes[i].parts == parts) {
            if (i != current) history.append(current);
            current = i; global = false; refresh(); return true;
        }
        return false;
    }
    void back() { if (canBack()) { current = history.takeLast(); refresh(); } }
    void up() { if (canUp()) navigate(nodes[nodes[current].parent].parts); }
    QVariant data(const QModelIndex &index, int role) const override {
        if (!index.isValid() || index.row() >= view.size() || index.column() >= 6) return {};
        auto r = entryAt(index.row());
        const auto *node = global ? nullptr : &nodes[view[index.row()]];
        const bool folder = global ? r->directory : node->folder;
        const QString &name = global ? r->displayName : node->displayName;
        const QString &path = global ? r->displayFull : node->displayFull;
        if (role == IdRole) return r ? QVariant(r->id) : QVariant();
        if (role == SearchRole) return path;
        if (role == Qt::AccessibleTextRole) return index.column() == 0 ? path : data(index, Qt::DisplayRole);
        if (role == Qt::AccessibleDescriptionRole) {
            if (folder) return QString("Folder. %1 underlying entries.").arg(idsAt(index.row()).size());
            return QString("File. Data size %1. Resource fork %2. %3").arg(QLocale().formattedDataSize(r ? r->size : 0), r && r->resourceFork ? QLocale().formattedDataSize(r->resourceSize) : "not present", r && r->encrypted ? "Encrypted." : "Not encrypted.");
        }
        if (role == Qt::ToolTipRole) return path + (r ? QString("\nEntry %1").arg(r->id) : global ? QString() : QString("\nGrouped folder: %1 explicit directory records").arg(nodes[view[index.row()]].realRows.size()));
        if (role == Qt::TextAlignmentRole && (index.column() == 1 || index.column() == 2))
            return int(Qt::AlignRight | Qt::AlignVCenter);
        if (role == SortRole) {
            if (index.column() == 1) return QVariant::fromValue(r ? r->size : quint64(0));
            if (index.column() == 2) return QVariant::fromValue(r ? r->resourceSize : quint64(0));
            if (index.column() == 0) return name;
        }
        if (role != Qt::DisplayRole && role != SortRole) return {};
        switch (index.column()) {
        case 0: return name;
        case 1: return folder || !r ? QString() : QLocale().formattedDataSize(r->size);
        case 2: return r && r->resourceFork ? QLocale().formattedDataSize(r->resourceSize) : QString();
        case 3: return folder ? "Folder" : r && r->link ? "Link" : "File";
        case 4: return r && r->encrypted ? "Encrypted" : "";
        case 5: return global ? r->displayLocation : node->displayLocation;
        }
        return {};
    }
    void clear() {
        beginResetModel(); rows.clear(); nodes.clear(); view.clear(); history.clear(); current = 0; global = false; endResetModel();
    }
    void append(const QJsonArray &items) {
        for (auto value : items) {
            const auto obj = value.toObject();
            Row r;
            r.id = quint32(obj["id"].toInteger()); r.name = obj["path"].toString();
            r.size = obj["size"].toString().toULongLong(); r.directory = obj["directory"].toBool();
            r.encrypted = obj["encrypted"].toBool(); r.link = obj["link"].toBool();
            r.resourceSize = obj["resource_size"].toString().toULongLong(); r.resourceFork = obj["has_resource"].toBool();
            for (auto part : obj["components"].toArray()) r.components.append(part.toString());
            if (r.components.isEmpty()) r.components = r.name.split('/');
            r.displayName = visibleName(r.components.value(r.components.size() - 1));
            r.displayFull = displayPath(r.components); r.displayLocation = displayPath(r.components.mid(0, r.components.size() - 1));
            r.metadata = obj; rows.append(r);
        }
    }
    void finish() {
        beginResetModel();
        nodes.clear(); nodes.append(Node{{}, true, {}, {}, {}, -1, {}, {}, {}});
        QHash<QString, int> folders; folders.insert(key({}), 0);
        for (int row = 0; row < rows.size(); ++row) {
            const auto &r = rows[row]; int parent = 0; nodes[0].ids.append(r.id);
            const int depth = r.components.size() - (r.directory ? 0 : 1);
            for (int d = 1; d <= depth; ++d) {
                const auto parts = r.components.mid(0, d); const auto k = key(parts);
                int folder = folders.value(k, -1);
                if (folder < 0) {
                    folder = nodes.size(); nodes.append(Node{parts, true, {}, {}, {}, parent, {}, {}, {}});
                    nodes[parent].children.append(folder); folders.insert(k, folder);
                }
                nodes[folder].ids.append(r.id); parent = folder;
            }
            if (r.directory) nodes[parent].realRows.append(row);
            else {
                const int file = nodes.size(); nodes.append(Node{r.components, false, {row}, {}, {r.id}, parent, {}, {}, {}});
                nodes[file].displayName = r.displayName; nodes[file].displayFull = r.displayFull; nodes[file].displayLocation = r.displayLocation;
                nodes[parent].children.append(file);
            }
        }
        for (auto &node : nodes) if (node.folder) {
            node.displayName = visibleName(node.parts.value(node.parts.size() - 1)); node.displayFull = displayPath(node.parts);
            node.displayLocation = displayPath(node.parts.mid(0, node.parts.size() - 1));
        }
        current = 0; history.clear(); global = false; view = nodes[0].children;
        endResetModel();
    }
};
