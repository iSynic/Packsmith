#include <windows.h>
#include <objbase.h>
#include <oleauto.h>
#include <propidl.h>
#include "Common/MyInitGuid.h"
#include "7zip/Archive/IArchive.h"
#include "7zip/IPassword.h"
#include "7zip/PropID.h"
#include <QtCore>
#include <atomic>
#include <iostream>
#include <memory>
#include <mutex>
#include <thread>
#include <stdexcept>

// One request per process. The engine never receives destination paths from an archive.
static std::atomic<bool> cancelled{false};
static std::mutex outputMutex;
static QElapsedTimer progressClock;
static void emitEvent(QJsonObject obj) {
    std::lock_guard<std::mutex> lock(outputMutex);
    auto bytes = QJsonDocument(obj).toJson(QJsonDocument::Compact);
    std::cout.write(bytes.constData(), bytes.size());
    std::cout << '\n';
    std::cout.flush();
}
static void require(bool ok, const QString &message) {
    if (!ok)
        throw std::runtime_error(message.toUtf8().constData());
}
static void check(HRESULT hr, const QString &what) {
    require(hr == S_OK, what + QString(" (engine code 0x%1)").arg(quint32(hr), 8, 16, QChar('0')));
}
static QString wide(BSTR s) {
    return s ? QString::fromWCharArray(s, SysStringLen(s)) : QString();
}
static BSTR bstr(const QString &s) {
    return SysAllocStringLen(reinterpret_cast<const OLECHAR *>(s.utf16()), s.size());
}
static std::wstring winPath(const QString &path) {
    QString p = QDir::toNativeSeparators(QFileInfo(path).absoluteFilePath());
    return (p.startsWith("\\\\") ? p : "\\\\?\\" + p).toStdWString();
}
static QString winError(const QString &op) {
    return op + QString(" (Windows error %1)").arg(GetLastError());
}

template <class T> struct ComPtr {
    T *p = nullptr;
    ~ComPtr() {
        if (p)
            p->Release();
    }
    T *operator->() const {
        return p;
    }
    T **put() {
        if (p)
            p->Release();
        p = nullptr;
        return &p;
    }
    ComPtr() = default;
    ComPtr(const ComPtr &) = delete;
    ComPtr &operator=(const ComPtr &) = delete;
};
#define REFS                                                                                       \
    std::atomic<ULONG> refs{1};                                                                    \
    ULONG STDMETHODCALLTYPE AddRef() throw() override {                                            \
        return ++refs;                                                                             \
    }                                                                                              \
    ULONG STDMETHODCALLTYPE Release() throw() override {                                           \
        auto n = --refs;                                                                           \
        if (!n)                                                                                    \
            delete this;                                                                           \
        return n;                                                                                  \
    }
#define QI_START                                                                                   \
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID iid, void **out) throw() override {            \
        *out = nullptr;
#define QI_TYPE(Type)                                                                              \
    if (iid == IID_##Type) {                                                                       \
        *out = static_cast<Type *>(this);                                                          \
    }
#define QI_END                                                                                     \
    if (iid == IID_IUnknown) {                                                                     \
        *out = static_cast<IUnknown *>(static_cast<Primary *>(this));                              \
    }                                                                                              \
    if (!*out) {                                                                                   \
        return E_NOINTERFACE;                                                                      \
    }                                                                                              \
    AddRef();                                                                                      \
    return S_OK;                                                                                   \
    }

struct Input final : IInStream {
    using Primary = IInStream;
    HANDLE handle = INVALID_HANDLE_VALUE;
    explicit Input(const QString &path) {
        auto p = winPath(path);
        handle = CreateFileW(p.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING,
                             FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        require(handle != INVALID_HANDLE_VALUE, winError("Cannot open input"));
        FILE_ATTRIBUTE_TAG_INFO info{};
        if (!GetFileInformationByHandleEx(handle, FileAttributeTagInfo, &info, sizeof(info)) ||
            (info.FileAttributes & (FILE_ATTRIBUTE_REPARSE_POINT | FILE_ATTRIBUTE_DIRECTORY))) {
            CloseHandle(handle);
            handle = INVALID_HANDLE_VALUE;
            require(false, "Input must be a regular file");
        }
    }
    ~Input() {
        if (handle != INVALID_HANDLE_VALUE)
            CloseHandle(handle);
    }
    REFS QI_START QI_TYPE(IInStream) QI_TYPE(ISequentialInStream) QI_END HRESULT STDMETHODCALLTYPE
        Read(void *data, UInt32 size, UInt32 *done) throw() override {
        if (done)
            *done = 0;
        if (cancelled)
            return E_ABORT;
        DWORD n = 0;
        if (!ReadFile(handle, data, size, &n, nullptr))
            return E_FAIL;
        if (done)
            *done = n;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE Seek(Int64 offset, UInt32 origin, UInt64 *position) throw() override {
        LARGE_INTEGER n{}, p{};
        n.QuadPart = offset;
        if (!SetFilePointerEx(handle, n, &p, origin))
            return E_FAIL;
        if (position)
            *position = p.QuadPart;
        return S_OK;
    }
};

struct Output final : IOutStream {
    using Primary = IOutStream;
    HANDLE handle = INVALID_HANDLE_VALUE;
    explicit Output(const QString &path) {
        auto p = winPath(path);
        handle = CreateFileW(p.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                             FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        require(handle != INVALID_HANDLE_VALUE, winError("Cannot create output"));
    }
    ~Output() {
        if (handle != INVALID_HANDLE_VALUE)
            CloseHandle(handle);
    }
    REFS QI_START QI_TYPE(IOutStream) QI_TYPE(ISequentialOutStream) QI_END HRESULT STDMETHODCALLTYPE
        Write(const void *data, UInt32 size, UInt32 *done) throw() override {
        if (done)
            *done = 0;
        if (cancelled)
            return E_ABORT;
        DWORD n = 0;
        if (!WriteFile(handle, data, size, &n, nullptr))
            return E_FAIL;
        if (done)
            *done = n;
        return n == size ? S_OK : E_FAIL;
    }
    HRESULT STDMETHODCALLTYPE Seek(Int64 offset, UInt32 origin, UInt64 *position) throw() override {
        LARGE_INTEGER n{}, p{};
        n.QuadPart = offset;
        if (!SetFilePointerEx(handle, n, &p, origin))
            return E_FAIL;
        if (position)
            *position = p.QuadPart;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetSize(UInt64 size) throw() override {
        LARGE_INTEGER n{}, zero{}, old{};
        n.QuadPart = size;
        if (!SetFilePointerEx(handle, zero, &old, FILE_CURRENT) ||
            !SetFilePointerEx(handle, n, nullptr, FILE_BEGIN) || !SetEndOfFile(handle))
            return E_FAIL;
        return SetFilePointerEx(handle, old, nullptr, FILE_BEGIN) ? S_OK : E_FAIL;
    }
    bool flush() {
        return FlushFileBuffers(handle);
    }
};

// Holding each ancestor without FILE_SHARE_DELETE prevents directory replacement
// while child paths are used. Reparse points are never traversed.
struct SafeTree {
    QString root;
    QMap<QString, HANDLE> dirs;
    explicit SafeTree(QString path) : root(QDir::cleanPath(QFileInfo(path).absoluteFilePath())) {
        require(QRegularExpression("^[A-Za-z]:/").match(root).hasMatch(),
                "Choose a local drive destination");
        QString current = root.left(3);
        lockDir(current);
        for (const auto &part : root.mid(3).split('/', Qt::SkipEmptyParts)) {
            current = QDir(current).filePath(part);
            lockDir(current);
        }
    }
    ~SafeTree() {
        release();
    }
    void release() {
        for (auto h : dirs)
            CloseHandle(h);
        dirs.clear();
    }
    void lockDir(const QString &path) {
        auto key = path.toCaseFolded();
        if (dirs.contains(key))
            return;
        auto p = winPath(path);
        HANDLE h = CreateFileW(p.c_str(), FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE,
                               nullptr, OPEN_EXISTING,
                               FILE_FLAG_BACKUP_SEMANTICS | FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        require(h != INVALID_HANDLE_VALUE, winError("Cannot lock destination directory"));
        FILE_ATTRIBUTE_TAG_INFO info{};
        if (!GetFileInformationByHandleEx(h, FileAttributeTagInfo, &info, sizeof(info)) ||
            !(info.FileAttributes & FILE_ATTRIBUTE_DIRECTORY) ||
            (info.FileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
            CloseHandle(h);
            require(false, "Destination contains a link or reparse point");
        }
        dirs.insert(key, h);
    }
    QString directory(const QString &relative) {
        QString current = root;
        for (const auto &part : relative.split('/', Qt::SkipEmptyParts)) {
            current = QDir(current).filePath(part);
            auto p = winPath(current);
            if (!CreateDirectoryW(p.c_str(), nullptr))
                require(GetLastError() == ERROR_ALREADY_EXISTS,
                        winError("Cannot create directory"));
            lockDir(current);
        }
        return current;
    }
};

static QString safeName(QString name) {
    name.replace('\\', '/');
    require(!name.isEmpty() && !name.startsWith('/') && !name.contains(':') &&
                !name.contains(QChar(0)),
            "Unsafe entry path: " + name);
    auto parts = name.split('/', Qt::SkipEmptyParts);
    require(!parts.isEmpty(), "Empty entry path");
    static QRegularExpression device("^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\\.|$)",
                                     QRegularExpression::CaseInsensitiveOption);
    for (auto &part : parts) {
        require(part != "." && part != "..", "Destination escape in entry path: " + name);
        // Invalid Windows components are encoded rather than silently truncated.
        QString clean;
        for (QChar c : part) {
            if (c.unicode() < 32 || QString("<>:\"|?*").contains(c))
                clean += QString("~%1").arg(uint(c.unicode()), 4, 16, QChar('0'));
            else
                clean += c;
        }
        while (clean.endsWith('.') || clean.endsWith(' ')) {
            auto c = clean.back();
            clean.chop(1);
            clean += QString("~%1").arg(uint(c.unicode()), 4, 16, QChar('0'));
        }
        if (device.match(clean).hasMatch())
            clean = "~" + clean;
        require(clean.size() <= 240, "Entry filename component is too long");
        part = clean;
    }
    return parts.join('/');
}

struct Entry {
    UInt32 id;
    QString path;
    quint64 size;
    bool dir;
    bool encrypted;
    bool link;
    FILETIME mtime{};
};
static QString propertyString(IInArchive *a, UInt32 i, PROPID id) {
    PROPVARIANT p{};
    check(a->GetProperty(i, id, &p), "Read property");
    QString s = p.vt == VT_BSTR ? wide(p.bstrVal) : QString();
    PropVariantClear(&p);
    return s;
}
static Entry entry(IInArchive *a, UInt32 i) {
    Entry e{i, propertyString(a, i, kpidPath), 0, false, false, false, {}};
    e.path.replace('\\', '/');
    if (e.path.isEmpty())
        e.path = "payload";
    for (auto id : {kpidSize, kpidIsDir, kpidEncrypted, kpidAttrib, kpidPosixAttrib, kpidMTime}) {
        PROPVARIANT p{};
        check(a->GetProperty(i, id, &p), "Read entry metadata");
        if (id == kpidSize && p.vt == VT_UI8)
            e.size = p.uhVal.QuadPart;
        if (id == kpidIsDir && p.vt == VT_BOOL)
            e.dir = p.boolVal != VARIANT_FALSE;
        if (id == kpidEncrypted && p.vt == VT_BOOL)
            e.encrypted = p.boolVal != VARIANT_FALSE;
        if (id == kpidAttrib && p.vt == VT_UI4)
            e.link |= (p.ulVal & FILE_ATTRIBUTE_REPARSE_POINT) != 0 ||
                      ((p.ulVal >> 16) & 0170000) == 0120000;
        if (id == kpidPosixAttrib && p.vt == VT_UI4)
            e.link |= (p.ulVal & 0170000) == 0120000;
        if (id == kpidMTime && p.vt == VT_FILETIME)
            e.mtime = p.filetime;
        PropVariantClear(&p);
    }
    e.link |= !propertyString(a, i, kpidSymLink).isEmpty() ||
              !propertyString(a, i, kpidHardLink).isEmpty();
    return e;
}

static HRESULT progress(UInt64 total, const UInt64 *completed) {
    if (cancelled)
        return E_ABORT;
    std::lock_guard<std::mutex> lock(outputMutex);
    if (progressClock.elapsed() < 100)
        return S_OK;
    progressClock.restart();
    QJsonObject obj{{"event", "progress"},
                    {"total", QString::number(total)},
                    {"completed", QString::number(completed ? *completed : 0)}};
    auto b = QJsonDocument(obj).toJson(QJsonDocument::Compact);
    std::cout.write(b.constData(), b.size());
    std::cout << '\n';
    std::cout.flush();
    return S_OK;
}
struct OpenCallback final : IArchiveOpenCallback, ICryptoGetTextPassword {
    using Primary = IArchiveOpenCallback;
    QString password;
    bool defined;
    bool requested = false;
    OpenCallback(QString p, bool d) : password(p), defined(d) {}
    REFS QI_START QI_TYPE(IArchiveOpenCallback)
        QI_TYPE(ICryptoGetTextPassword) QI_END HRESULT STDMETHODCALLTYPE
        SetTotal(const UInt64 *, const UInt64 *) throw() override {
        return cancelled ? E_ABORT : S_OK;
    }
    HRESULT STDMETHODCALLTYPE SetCompleted(const UInt64 *, const UInt64 *) throw() override {
        return cancelled ? E_ABORT : S_OK;
    }
    HRESULT STDMETHODCALLTYPE CryptoGetTextPassword(BSTR *p) throw() override {
        requested = true;
        if (!defined)
            return E_ABORT;
        *p = bstr(password);
        return *p ? S_OK : E_OUTOFMEMORY;
    }
};

struct Engine {
    HMODULE dll = nullptr;
    using Create = HRESULT(WINAPI *)(const GUID *, const GUID *, void **);
    Create create = nullptr;
    ComPtr<IInArchive> archive;
    ComPtr<Input> input;
    QString password;
    bool defined;
    int format = 0;
    bool encryptedHeader = false;
    Engine(const QJsonObject &r)
        : password(r["password"].toString()), defined(r.contains("password")) {
        auto path = winPath(QCoreApplication::applicationDirPath() + "/7z.dll");
        dll = LoadLibraryExW(path.c_str(), nullptr,
                             LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
        require(dll, "Cannot load the packaged 7-Zip engine");
        auto address = GetProcAddress(dll, "CreateObject");
        static_assert(sizeof(address) == sizeof(create), "Windows function pointer ABI");
        std::memcpy(&create, &address, sizeof(create));
        require(create, "7-Zip API unavailable");
    }
    ~Engine() {
        if (archive.p) {
            archive->Close();
            archive.p->Release();
            archive.p = nullptr;
        }
        if (input.p) {
            input.p->Release();
            input.p = nullptr;
        }
        if (dll)
            FreeLibrary(dll);
    }
    static GUID clsid(int id) {
        return GUID{0x23170F69, 0x40C1, 0x278A, {0x10, 0, 0, 1, 0x10, static_cast<BYTE>(id), 0, 0}};
    }
    void open(const QString &path, int force = 0) {
        input.p = new Input(path);
        QString ext = QFileInfo(path).suffix().toLower();
        QList<int> formats = force         ? QList<int>{force}
                             : ext == "7z" ? QList<int>{7, 1}
                                           : QList<int>{1, 7};
        bool requested = false;
        for (int id : formats) {
            auto guid = clsid(id);
            check(create(&guid, &IID_IInArchive, reinterpret_cast<void **>(archive.put())),
                  "Create archive reader");
            UInt64 pos = 0;
            input->Seek(0, STREAM_SEEK_SET, &pos);
            ComPtr<OpenCallback> cb;
            cb.p = new OpenCallback(password, defined);
            HRESULT hr = archive->Open(input.p, nullptr, cb.p);
            requested |= cb->requested;
            if (hr == S_OK) {
                format = id;
                encryptedHeader = cb->requested;
                return;
            }
            archive->Close();
        }
        require(false,
                requested
                    ? (defined ? "Wrong password or damaged encrypted header" : "Password required")
                    : "Unsupported or damaged archive (this prototype opens ZIP and 7z)");
    }
};

struct HashOutput final : ISequentialOutStream {
    using Primary = ISequentialOutStream;
    QCryptographicHash hash{QCryptographicHash::Sha256};
    quint64 bytes = 0;
    REFS QI_START QI_TYPE(ISequentialOutStream) QI_END HRESULT STDMETHODCALLTYPE
        Write(const void *p, UInt32 n, UInt32 *done) throw() override {
        if (done)
            *done = 0;
        if (cancelled)
            return E_ABORT;
        hash.addData(QByteArrayView(static_cast<const char *>(p), n));
        bytes += n;
        if (done)
            *done = n;
        return S_OK;
    }
};

struct ExtractCallback final : IArchiveExtractCallback, ICryptoGetTextPassword {
    using Primary = IArchiveExtractCallback;
    Engine &engine;
    SafeTree *tree;
    QMap<UInt32, QString> names;
    ComPtr<Output> current;
    ComPtr<HashOutput> hash;
    QMap<UInt32, QByteArray> hashes;
    UInt32 currentId = 0;
    quint64 total = 0;
    bool hashOnly = false;
    bool requested = false;
    QString error;
    ExtractCallback(Engine &e, SafeTree *t) : engine(e), tree(t) {}
    REFS QI_START QI_TYPE(IArchiveExtractCallback) QI_TYPE(IProgress)
        QI_TYPE(ICryptoGetTextPassword) QI_END HRESULT STDMETHODCALLTYPE
        SetTotal(UInt64 n) throw() override {
        total = n;
        return progress(total, nullptr);
    }
    HRESULT STDMETHODCALLTYPE SetCompleted(const UInt64 *n) throw() override {
        return progress(total, n);
    }
    HRESULT STDMETHODCALLTYPE CryptoGetTextPassword(BSTR *p) throw() override {
        requested = true;
        if (!engine.defined)
            return E_ABORT;
        *p = bstr(engine.password);
        return *p ? S_OK : E_OUTOFMEMORY;
    }
    HRESULT STDMETHODCALLTYPE PrepareOperation(Int32) throw() override {
        return cancelled ? E_ABORT : S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetStream(UInt32 i, ISequentialOutStream **stream,
                                        Int32 mode) throw() override {
        *stream = nullptr;
        current.put();
        hash.put();
        currentId = i;
        if (cancelled)
            return E_ABORT;
        if (mode != NArchive::NExtract::NAskMode::kExtract)
            return S_OK;
        try {
            auto e = entry(engine.archive.p, i);
            if (hashOnly) {
                if (!e.dir) {
                    hash.p = new HashOutput();
                    hash->AddRef();
                    *stream = hash.p;
                }
                return S_OK;
            }
            if (!names.contains(i))
                return S_OK;
            QString relative = names.value(i);
            if (e.dir) {
                tree->directory(relative);
                return S_OK;
            }
            auto slash = relative.lastIndexOf('/');
            if (slash >= 0)
                tree->directory(relative.left(slash));
            current.p = new Output(QDir(tree->root).filePath(relative));
            current->AddRef();
            *stream = current.p;
            return S_OK;
        } catch (const std::exception &e) {
            error = QString::fromUtf8(e.what());
            return E_FAIL;
        }
    }
    HRESULT STDMETHODCALLTYPE SetOperationResult(Int32 result) throw() override {
        if (result != NArchive::NExtract::NOperationResult::kOK) {
            error = QString("Entry %1 failed integrity/decryption (result %2)")
                        .arg(currentId)
                        .arg(result);
            current.put();
            hash.put();
            return E_FAIL;
        }
        if (hash.p)
            hashes.insert(currentId, hash->hash.result());
        if (current.p) {
            if (!current->flush()) {
                error = "Cannot flush extracted file";
                return E_FAIL;
            }
            try {
                auto e = entry(engine.archive.p, currentId);
                if (e.mtime.dwHighDateTime || e.mtime.dwLowDateTime)
                    if (!SetFileTime(current->handle, nullptr, nullptr, &e.mtime)) {
                        error = "Cannot preserve file timestamp";
                        return E_FAIL;
                    }
            } catch (const std::exception &e) {
                error = QString::fromUtf8(e.what());
                return E_FAIL;
            }
        }
        current.put();
        hash.put();
        return S_OK;
    }
};
static void extractCheck(Engine &e, ExtractCallback *cb, const QVector<UInt32> &ids = {},
                         bool test = false) {
    HRESULT hr = e.archive->Extract(ids.isEmpty() ? nullptr : ids.constData(),
                                    ids.isEmpty() ? UInt32(-1) : ids.size(), test ? 1 : 0, cb);
    if (cancelled)
        require(false, "Cancelled");
    if (!cb->error.isEmpty())
        require(false, cb->error);
    if (cb->requested && !e.defined)
        require(false, "Password required");
    check(hr, "Archive operation failed");
}

// Plan collisions before creating anything. Parents shared by files stay shared;
// duplicate files, case collisions and file/directory conflicts receive suffixes.
static QString sidecarName(const QString &name) {
    int slash = name.lastIndexOf('/');
    return name.left(slash + 1) + "._" + name.mid(slash + 1);
}
static QMap<UInt32, QString> planNames(const QVector<Entry> &entries,
                                       const QSet<UInt32> &sidecars = {}) {
    QMap<UInt32, QString> names;
    QMap<QString, bool> used;
    QMap<QString, QString> parents;
    used.insert(".unarchiver-job.json", false);
    for (const auto &e : entries) {
        require(!e.link,
                "Links require an explicit preservation policy; extraction stopped: " + e.path);
        auto parts = safeName(e.path).split('/');
        QString parent, source;
        for (int j = 0; j < parts.size(); ++j) {
            bool dir = j < parts.size() - 1 || e.dir;
            source = source.isEmpty() ? parts[j] : source + "/" + parts[j];
            if (dir && parents.contains(source)) {
                parent = parents.value(source);
                continue;
            }
            QString base = parent.isEmpty() ? parts[j] : parent + "/" + parts[j];
            QString chosen = base;
            int n = 2;
            bool paired = j == parts.size() - 1 && sidecars.contains(e.id);
            while (used.contains(chosen.toCaseFolded()) ||
                   (paired && used.contains(sidecarName(chosen).toCaseFolded())))
                chosen = base + QString(" (%1)").arg(n++);
            used.insert(chosen.toCaseFolded(), dir);
            if (paired)
                used.insert(sidecarName(chosen).toCaseFolded(), false);
            if (dir)
                parents.insert(source, chosen);
            parent = chosen;
        }
        names.insert(e.id, parent);
    }
    // Reserve the mapping file too; an archive may legitimately have that name.
    return names;
}

static void cleanChildren(const QString &root);
struct Staging {
    QTemporaryDir temp;
    explicit Staging(const QString &parent) : temp(QDir(parent).filePath(".unarchiver-XXXXXX")) {
        require(temp.isValid(), "Cannot create staging directory");
        QString token = QUuid::createUuid().toString(QUuid::Id128);
        {
            Output marker(temp.filePath(".unarchiver-job.json"));
            auto b =
                QJsonDocument(
                    QJsonObject{{"token", token},
                                {"parent", QDir::cleanPath(QFileInfo(parent).absoluteFilePath())}})
                    .toJson();
            UInt32 done;
            check(marker.Write(b.constData(), b.size(), &done), "Write job marker");
            require(marker.flush(), "Flush job marker");
        }
        emitEvent({{"event", "staging"},
                   {"path", temp.path()},
                   {"parent", QDir::cleanPath(QFileInfo(parent).absoluteFilePath())},
                   {"token", token}});
    }
    ~Staging() {
        if (!temp.autoRemove() || !QFileInfo::exists(temp.path()))
            return;
        temp.setAutoRemove(false);
        try {
            cleanChildren(temp.path());
            auto p = winPath(temp.path());
            require(RemoveDirectoryW(p.c_str()), winError("Remove staging"));
        } catch (const std::exception &e) {
            emitEvent({{"event", "cleanup_failed"},
                       {"path", temp.path()},
                       {"message", QString::fromUtf8(e.what())}});
        }
    }
};

static void cleanChildren(const QString &root) {
    SafeTree lock(root);
    for (const auto &info : QDir(root).entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot |
                                                     QDir::Hidden | QDir::System)) {
        auto p = winPath(info.absoluteFilePath());
        DWORD attr = GetFileAttributesW(p.c_str());
        require(attr != INVALID_FILE_ATTRIBUTES, "Cannot inspect interrupted output");
        if ((attr & FILE_ATTRIBUTE_DIRECTORY) && !(attr & FILE_ATTRIBUTE_REPARSE_POINT))
            cleanChildren(info.absoluteFilePath());
        require((attr & FILE_ATTRIBUTE_DIRECTORY) ? RemoveDirectoryW(p.c_str())
                                                  : DeleteFileW(p.c_str()),
                winError("Cannot remove interrupted output"));
    }
}
static void cleanupJob(const QJsonObject &r) {
    QString path = QDir::cleanPath(QFileInfo(r["path"].toString()).absoluteFilePath());
    QString parent = QDir::cleanPath(QFileInfo(r["parent"].toString()).absoluteFilePath());
    require(!r["path"].toString().isEmpty() && !r["parent"].toString().isEmpty(),
            "Cleanup paths required");
    require(QFileInfo(path).absolutePath().compare(parent, Qt::CaseInsensitive) == 0 &&
                QRegularExpression("^\\.unarchiver-[A-Za-z0-9]{6}$")
                    .match(QFileInfo(path).fileName())
                    .hasMatch(),
            "Cleanup path is outside the job parent");
    SafeTree parentLock(parent);
    if (QFileInfo::exists(path)) {
        {
            SafeTree stageLock(path);
            QFile marker(QDir(path).filePath(".unarchiver-job.json"));
            require(marker.open(QIODevice::ReadOnly), "Missing recovery marker");
            auto stored = QJsonDocument::fromJson(marker.read(8192)).object();
            require(!r["token"].toString().isEmpty() && stored["token"] == r["token"] &&
                        stored["parent"].toString().compare(parent, Qt::CaseInsensitive) == 0,
                    "Recovery marker differs from the interrupted job");
        }
        cleanChildren(path);
        auto p = winPath(path);
        require(RemoveDirectoryW(p.c_str()),
                winError("Cannot remove interrupted staging directory"));
    }
    emitEvent({{"event", "complete"}, {"message", "Interrupted staging cleaned"}});
}

static QByteArray fileHash(const QString &path);
static void listArchive(Engine &e, const QString &path) {
    UInt32 count = 0;
    check(e.archive->GetNumberOfItems(&count), "Count entries");
    QJsonArray batch;
    for (UInt32 i = 0; i < count; ++i) {
        if (cancelled)
            require(false, "Cancelled");
        auto v = entry(e.archive.p, i);
        batch.append(QJsonObject{{"id", qint64(i)},
                                 {"path", v.path},
                                 {"size", QString::number(v.size)},
                                 {"directory", v.dir},
                                 {"encrypted", v.encrypted},
                                 {"link", v.link}});
        if (batch.size() == 500) {
            emitEvent({{"event", "entries"}, {"items", batch}});
            batch = {};
        }
    }
    if (!batch.isEmpty())
        emitEvent({{"event", "entries"}, {"items", batch}});
    emitEvent({{"event", "complete"},
               {"count", qint64(count)},
               {"format", e.format == 7 ? "7z" : "ZIP"},
               {"fingerprint", QString::fromLatin1(fileHash(path).toHex())}});
}
static void extractArchive(Engine &e, const QJsonObject &r) {
    QString destination = QFileInfo(r["destination"].toString()).absoluteFilePath();
    require(!r["destination"].toString().isEmpty(), "Destination is required");
    SafeTree parent(destination);
    Staging stage(destination);
    SafeTree tree(stage.temp.path());
    UInt32 count = 0;
    check(e.archive->GetNumberOfItems(&count), "Count entries");
    QSet<UInt32> chosen;
    for (auto id : r["ids"].toArray()) {
        auto n = id.toInteger(-1);
        require(n >= 0 && n < count, "Invalid entry ID");
        chosen.insert(UInt32(n));
    }
    QStringList selectedFolders;
    for (auto id : chosen) {
        auto v = entry(e.archive.p, id);
        if (v.dir)
            selectedFolders.append(v.path + "/");
    }
    for (UInt32 i = 0; i < count && !selectedFolders.isEmpty(); ++i) {
        auto v = entry(e.archive.p, i);
        for (const auto &folder : selectedFolders)
            if (v.path.startsWith(folder)) {
                chosen.insert(i);
                break;
            }
    }
    QVector<Entry> items;
    QVector<UInt32> ids;
    for (UInt32 i = 0; i < count; ++i)
        if (chosen.isEmpty() || chosen.contains(i)) {
            items.append(entry(e.archive.p, i));
            ids.append(i);
        }
    require(!items.isEmpty(), "Archive has no selected entries");
    auto names = planNames(items);
    ComPtr<ExtractCallback> cb;
    cb.p = new ExtractCallback(e, &tree);
    cb->names = names;
    extractCheck(e, cb.p, ids);
    QJsonArray mappings;
    for (const auto &item : items)
        mappings.append(QJsonObject{
            {"id", qint64(item.id)}, {"original", item.path}, {"output", names.value(item.id)}});
    QString mapName = "packsmith-mapping.json";
    while (QFileInfo::exists(QDir(tree.root).filePath(mapName)))
        mapName.prepend('_');
    {
        Output map(QDir(tree.root).filePath(mapName));
        auto b = QJsonDocument(QJsonObject{{"entries", mappings},
                                           {"preservation",
                                            "File payloads and file modification times; links are "
                                            "rejected. See README for metadata limits."}})
                     .toJson();
        UInt32 done = 0;
        check(map.Write(b.constData(), b.size(), &done), "Write mapping");
        require(map.flush(), "Flush mapping");
    }
    cb.put();
    tree.release();
    QString label = safeName(QFileInfo(r["archive"].toString()).completeBaseName());
    label.replace('/', '_');
    if (label.isEmpty())
        label = "Extracted";
    QString output = QDir(destination).filePath(label);
    int n = 2;
    while (QFileInfo::exists(output))
        output = QDir(destination).filePath(label + QString(" (%1)").arg(n++));
    auto from = winPath(stage.temp.path()), to = winPath(output);
    require(!cancelled, "Cancelled");
    require(MoveFileExW(from.c_str(), to.c_str(), MOVEFILE_WRITE_THROUGH),
            winError("Cannot commit extraction"));
    stage.temp.setAutoRemove(false);
    {
        SafeTree committed(output);
        auto marker = winPath(QDir(output).filePath(".unarchiver-job.json"));
        if (!DeleteFileW(marker.c_str()))
            emitEvent({{"event", "warning"},
                       {"message", "Verified output committed; job marker could not be removed"}});
    }
    emitEvent(
        {{"event", "complete"}, {"output", output}, {"mapping", mapName}, {"count", items.size()}});
}

struct UpdateItem {
    UInt32 old = UInt32(-1);
    QString path, source;
    bool dir = false;
    quint64 size = 0;
    FILETIME time{};
    bool props = false;
};
struct UpdateCallback final : IArchiveUpdateCallback,
                              ICryptoGetTextPassword2,
                              ICryptoGetTextPassword {
    using Primary = IArchiveUpdateCallback;
    Engine &engine;
    QVector<UpdateItem> items;
    quint64 total = 0;
    QString error;
    explicit UpdateCallback(Engine &e) : engine(e) {}
    REFS QI_START QI_TYPE(IArchiveUpdateCallback) QI_TYPE(IProgress)
        QI_TYPE(ICryptoGetTextPassword2)
            QI_TYPE(ICryptoGetTextPassword) QI_END HRESULT STDMETHODCALLTYPE
        SetTotal(UInt64 n) throw() override {
        total = n;
        return progress(n, nullptr);
    }
    HRESULT STDMETHODCALLTYPE SetCompleted(const UInt64 *n) throw() override {
        return progress(total, n);
    }
    HRESULT STDMETHODCALLTYPE CryptoGetTextPassword2(Int32 *defined, BSTR *p) throw() override {
        *defined = engine.defined;
        *p = engine.defined ? bstr(engine.password) : nullptr;
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE CryptoGetTextPassword(BSTR *p) throw() override {
        if (!engine.defined)
            return E_ABORT;
        *p = bstr(engine.password);
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetUpdateItemInfo(UInt32 i, Int32 *data, Int32 *props,
                                                UInt32 *old) throw() override {
        if (i >= UInt32(items.size()))
            return E_INVALIDARG;
        const auto &v = items[i];
        *data = v.old == UInt32(-1) || !v.source.isEmpty();
        *props = *data || v.props;
        *old = v.old;
        return cancelled ? E_ABORT : S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetProperty(UInt32 i, PROPID id, PROPVARIANT *p) throw() override {
        PropVariantInit(p);
        if (i >= UInt32(items.size()))
            return E_INVALIDARG;
        auto &v = items[i];
        if (v.old != UInt32(-1) && id != kpidPath && v.source.isEmpty())
            return engine.archive->GetProperty(v.old, id, p);
        if (id == kpidPath) {
            p->vt = VT_BSTR;
            p->bstrVal = bstr(v.path);
        }
        if (id == kpidIsDir) {
            p->vt = VT_BOOL;
            p->boolVal = v.dir ? VARIANT_TRUE : VARIANT_FALSE;
        }
        if (id == kpidSize) {
            p->vt = VT_UI8;
            p->uhVal.QuadPart = v.size;
        }
        if (id == kpidMTime) {
            p->vt = VT_FILETIME;
            p->filetime = v.time;
        }
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE GetStream(UInt32 i, ISequentialInStream **stream) throw() override {
        *stream = nullptr;
        if (cancelled)
            return E_ABORT;
        try {
            if (!items[i].dir)
                *stream = new Input(items[i].source);
            return S_OK;
        } catch (const std::exception &e) {
            error = QString::fromUtf8(e.what());
            return E_FAIL;
        }
    }
    HRESULT STDMETHODCALLTYPE SetOperationResult(Int32 r) throw() override {
        return r == 0 ? S_OK : E_FAIL;
    }
};
static QByteArray fileHash(const QString &path) {
    QFile f(path);
    require(f.open(QIODevice::ReadOnly), "Cannot hash input");
    QCryptographicHash h(QCryptographicHash::Sha256);
    while (!f.atEnd()) {
        require(!cancelled, "Cancelled");
        auto b = f.read(1024 * 1024);
        require(!b.isEmpty() || f.atEnd(), "Read error while hashing");
        h.addData(b);
    }
    return h.result();
}
static void addInputs(QVector<UpdateItem> &items, const QString &source, const QString &name) {
    QFileInfo fi(source);
    require(fi.exists() && !fi.isSymLink() && !fi.isJunction(),
            "Missing source or unsupported source link");
    auto p = winPath(source);
    DWORD attr = GetFileAttributesW(p.c_str());
    require(attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_REPARSE_POINT),
            "Source reparse points are unsupported");
    UpdateItem item;
    item.path = safeName(name);
    item.source = source;
    item.dir = fi.isDir();
    item.size = fi.size();
    item.props = true;
    quint64 ticks = (quint64(fi.lastModified().toMSecsSinceEpoch()) + 11644473600000ULL) * 10000ULL;
    item.time = {DWORD(ticks), DWORD(ticks >> 32)};
    items.append(item);
    if (item.dir) {
        auto children = QDir(source).entryInfoList(
            QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System, QDir::Name);
        for (const auto &child : children)
            addInputs(items, child.absoluteFilePath(), item.path + "/" + child.fileName());
    }
}
static void mutateArchive(Engine &e, const QJsonObject &r, bool update) {
    QString target = QFileInfo(r["archive"].toString()).absoluteFilePath();
    require(!r["archive"].toString().isEmpty(), "Archive path required");
    SafeTree parent(QFileInfo(target).absolutePath());
    require(update || !QFileInfo::exists(target), "Archive already exists");
    Staging stage(QFileInfo(target).absolutePath());
    QString replacement = stage.temp.filePath("replacement");
    ComPtr<UpdateCallback> cb;
    cb.p = new UpdateCallback(e);
    QMap<UInt32, QByteArray> originals;
    QByteArray oldDigest;
    if (update) {
        require(e.format == 1 || e.format == 7, "Only ZIP/7z updates are available");
        oldDigest = fileHash(target);
        UInt32 count = 0;
        check(e.archive->GetNumberOfItems(&count), "Count update entries");
        QSet<UInt32> remove;
        for (auto id : r["remove"].toArray()) {
            auto n = id.toInteger(-1);
            require(n >= 0 && n < count, "Invalid removal ID");
            remove.insert(UInt32(n));
        }
        QMap<UInt32, QString> rename;
        for (auto v : r["rename"].toArray()) {
            auto obj = v.toObject();
            auto n = obj["id"].toInteger(-1);
            require(n >= 0 && n < count, "Invalid rename ID");
            rename[UInt32(n)] = safeName(obj["path"].toString());
        }
        QStringList removedFolders;
        QMap<QString, QString> renamedFolders;
        for (auto id : remove) {
            auto v = entry(e.archive.p, id);
            if (v.dir)
                removedFolders.append(v.path + "/");
        }
        for (auto it = rename.begin(); it != rename.end(); ++it) {
            auto v = entry(e.archive.p, it.key());
            if (v.dir)
                renamedFolders.insert(v.path + "/", it.value() + "/");
        }
        for (UInt32 i = 0; i < count; ++i) {
            auto v = entry(e.archive.p, i);
            for (const auto &folder : removedFolders)
                if (v.path.startsWith(folder)) {
                    remove.insert(i);
                    break;
                }
            for (auto it = renamedFolders.begin(); it != renamedFolders.end(); ++it)
                if (v.path.startsWith(it.key()))
                    rename.insert(i, it.value() + v.path.mid(it.key().size()));
        }
        for (UInt32 i = 0; i < count; ++i)
            if (!remove.contains(i)) {
                auto item = entry(e.archive.p, i);
                require(!item.link, "Updating archives with links is unsupported");
                cb->items.append({i,
                                  rename.value(i, item.path),
                                  {},
                                  item.dir,
                                  item.size,
                                  item.mtime,
                                  rename.contains(i)});
            }
        for (auto v : r["replace"].toArray()) {
            auto obj = v.toObject();
            auto n = obj["id"].toInteger(-1);
            require(n >= 0 && n < count && !remove.contains(UInt32(n)), "Invalid replacement ID");
            QString source = QFileInfo(obj["source"].toString()).absoluteFilePath();
            QFileInfo fi(source);
            require(fi.isFile() && !fi.isSymLink() && !fi.isJunction(),
                    "Replacement must be a regular file");
            auto p = winPath(source);
            DWORD attr = GetFileAttributesW(p.c_str());
            require(attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_REPARSE_POINT),
                    "Replacement links are unsupported");
            for (auto &item : cb->items)
                if (item.old == UInt32(n)) {
                    require(!item.dir, "Cannot replace a folder with a file");
                    item.source = source;
                    item.size = fi.size();
                    item.props = true;
                }
        }
        ComPtr<ExtractCallback> hash;
        hash.p = new ExtractCallback(e, nullptr);
        hash->hashOnly = true;
        extractCheck(e, hash.p);
        originals = hash->hashes;
    }
    for (auto v : r["files"].toArray()) {
        QString path = QFileInfo(v.toString()).absoluteFilePath();
        addInputs(cb->items, path, QFileInfo(path).fileName());
    }
    require(update || !cb->items.isEmpty(), "Choose input files for the new archive");
    QSet<QString> paths;
    QVector<QByteArray> expected;
    for (const auto &v : cb->items) {
        require(!paths.contains(v.path.toCaseFolded()),
                "Update would create duplicate/case-colliding paths: " + v.path);
        paths.insert(v.path.toCaseFolded());
        expected.append(v.dir                ? QByteArray()
                        : v.source.isEmpty() ? originals.value(v.old)
                                             : fileHash(v.source));
    }
    int format = update ? e.format : r["format"].toString() == "7z" ? 7 : 1;
    ComPtr<IOutArchive> writer;
    if (update)
        check(e.archive->QueryInterface(IID_IOutArchive, reinterpret_cast<void **>(writer.put())),
              "Engine cannot update this archive");
    else {
        auto guid = Engine::clsid(format);
        check(e.create(&guid, &IID_IOutArchive, reinterpret_cast<void **>(writer.put())),
              "Create archive writer");
    }
    if (e.defined) {
        ComPtr<ISetProperties> props;
        check(writer->QueryInterface(IID_ISetProperties, reinterpret_cast<void **>(props.put())),
              "Configure encryption");
        PROPVARIANT value{};
        const wchar_t *name;
        if (format == 7) {
            name = L"he";
            value.vt = VT_BOOL;
            value.boolVal = (!update || e.encryptedHeader) ? VARIANT_TRUE : VARIANT_FALSE;
        } else {
            name = L"em";
            value.vt = VT_BSTR;
            value.bstrVal = SysAllocString(L"AES256");
        }
        HRESULT hr = props->SetProperties(&name, &value, 1);
        PropVariantClear(&value);
        check(hr, "Set encryption properties");
    }
    ComPtr<Output> out;
    out.p = new Output(replacement);
    check(writer->UpdateItems(out.p, cb->items.size(), cb.p), "Create replacement archive");
    require(cb->error.isEmpty(), cb->error);
    require(out->flush(), "Flush replacement archive");
    out.put();
    writer.put();
    // Verify every new payload and pathname before changing the original.
    {
        Engine verify(r);
        verify.open(replacement, format);
        UInt32 n = 0;
        check(verify.archive->GetNumberOfItems(&n), "Verify entry count");
        require(n == UInt32(cb->items.size()), "Replacement entry count differs");
        ComPtr<ExtractCallback> hash;
        hash.p = new ExtractCallback(verify, nullptr);
        hash->hashOnly = true;
        extractCheck(verify, hash.p);
        for (UInt32 i = 0; i < n; ++i) {
            auto v = entry(verify.archive.p, i);
            require(v.path == cb->items[i].path && v.dir == cb->items[i].dir,
                    "Replacement metadata differs");
            if (!v.dir)
                require(hash->hashes.value(i) == expected[i], "Replacement payload differs");
        }
    }
    require(!cancelled, "Cancelled");
    if (update) {
        require(fileHash(target) == oldDigest, "Original archive changed during update");
        auto targetPath = winPath(target);
        HANDLE guard =
            CreateFileW(targetPath.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_DELETE,
                        nullptr, OPEN_EXISTING, FILE_FLAG_OPEN_REPARSE_POINT, nullptr);
        require(guard != INVALID_HANDLE_VALUE, winError("Cannot protect original during commit"));
        e.archive->Close();
        e.input.put();
        // Keep an exact original as a recovery copy. ReplaceFile is the sole commit.
        QString backup = target + ".backup-" + QUuid::createUuid().toString(QUuid::Id128);
        auto original = winPath(target), rep = winPath(replacement), back = winPath(backup);
        bool replaced =
            ReplaceFileW(original.c_str(), rep.c_str(), back.c_str(), 0, nullptr, nullptr);
        DWORD error = GetLastError();
        CloseHandle(guard);
        if (!replaced) {
            SetLastError(error);
            stage.temp.setAutoRemove(false);
            emitEvent({{"event", "recovery_required"},
                       {"path", stage.temp.path()},
                       {"backup", backup},
                       {"archive", target}});
            require(false, winError("Archive commit failed; retain recovery files at " +
                                    stage.temp.path() + " and " + backup));
        }
        emitEvent({{"event", "complete"},
                   {"output", target},
                   {"backup", backup},
                   {"count", cb->items.size()}});
    } else {
        auto from = winPath(replacement), to = winPath(target);
        require(MoveFileExW(from.c_str(), to.c_str(), MOVEFILE_WRITE_THROUGH),
                winError("Cannot commit new archive"));
        emitEvent({{"event", "complete"}, {"output", target}, {"count", cb->items.size()}});
    }
}

#include "legacy_worker.h"

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_APPLICATION_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    progressClock.start();
    std::string line;
    if (!std::getline(std::cin, line))
        return 2;
    QJsonParseError parse{};
    auto doc = QJsonDocument::fromJson(QByteArray::fromStdString(line), &parse);
    if (parse.error != QJsonParseError::NoError || !doc.isObject()) {
        emitEvent({{"event", "error"}, {"message", "Invalid request JSON"}});
        return 2;
    }
    std::thread([] {
        std::string cmd;
        while (std::getline(std::cin, cmd))
            if (QJsonDocument::fromJson(QByteArray::fromStdString(cmd)).object()["cancel"].toBool())
                cancelled = true;
    }).detach();
    int result = 0;
    try {
        QJsonObject r = doc.object();
        QString operation = r["operation"].toString();
        if (operation == "cleanup") {
            cleanupJob(r);
            std::cout.flush();
            ExitProcess(0);
        }
        if (usesLegacy(r)) {
            legacyJob(r);
            std::cout.flush();
            ExitProcess(0);
        }
        Engine engine(r);
        if (operation != "create")
            engine.open(r["archive"].toString());
        if (r.contains("fingerprint"))
            require(QString::fromLatin1(fileHash(r["archive"].toString()).toHex()) ==
                        r["fingerprint"].toString(),
                    "Archive changed; reopen it before using the selected entry IDs");
        if (operation == "list")
            listArchive(engine, r["archive"].toString());
        else if (operation == "extract")
            extractArchive(engine, r);
        else if (operation == "test") {
            ComPtr<ExtractCallback> cb;
            cb.p = new ExtractCallback(engine, nullptr);
            extractCheck(engine, cb.p, {}, true);
            emitEvent({{"event", "complete"}, {"message", "Integrity check passed"}});
        } else if (operation == "create" || operation == "update")
            mutateArchive(engine, r, operation == "update");
        else
            require(false, "Unknown operation");
    } catch (const std::exception &e) {
        emitEvent({{"event", cancelled ? "cancelled" : "error"},
                   {"message", QString::fromUtf8(e.what())}});
        result = 1;
    }
    // The stdin cancellation reader can be blocked; process teardown closes it.
    std::cout.flush();
    ExitProcess(result);
}
