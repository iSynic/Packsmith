"""Check embedded Windows resources and recovery across the Packsmith rename."""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dist/Packsmith-preview"
EVIDENCE = ROOT / "assessment/evidence/desktop-preview"
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.LoadLibraryExW.argtypes = (wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD)
kernel.LoadLibraryExW.restype = ctypes.c_void_p
kernel.FindResourceW.argtypes = (ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
kernel.FindResourceW.restype = ctypes.c_void_p
kernel.LoadResource.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
kernel.LoadResource.restype = ctypes.c_void_p
kernel.LockResource.argtypes = (ctypes.c_void_p,)
kernel.LockResource.restype = ctypes.c_void_p
kernel.SizeofResource.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
kernel.SizeofResource.restype = wintypes.DWORD
kernel.FreeLibrary.argtypes = (ctypes.c_void_p,)


def main():
    executable = PACKAGE / "Packsmith.exe"
    module = kernel.LoadLibraryExW(str(executable), None, 0x22)
    assert module, ctypes.get_last_error()

    def resource(kind, identity):
        entry = kernel.FindResourceW(module, identity, kind)
        assert entry, (kind, identity, ctypes.get_last_error())
        data = kernel.LockResource(kernel.LoadResource(module, entry))
        assert data
        return ctypes.string_at(data, kernel.SizeofResource(module, entry))

    groups = []
    try:
        for identity, name in ((101, "packsmith"), (102, "packsmith-archive")):
            expected = (ROOT / "assets/icons" / (name + ".ico")).read_bytes()
            group = resource(14, identity)
            assert group[:6] == expected[:6]
            count = struct.unpack_from("<H", group, 4)[0]
            sizes = []
            for i in range(count):
                width, height, colors, reserved, planes, bits, length, image_id = struct.unpack_from("<BBBBHHIH", group, 6 + i * 14)
                original = struct.unpack_from("<BBBBHHII", expected, 6 + i * 16)
                # windres normalizes an ICO's unspecified planes (0) to one plane.
                assert (width, height, colors, reserved) == original[:4]
                assert planes == (original[4] or 1) and (bits, length) == original[5:7]
                assert resource(3, image_id) == expected[original[7]:original[7] + length]
                sizes.append(width or 256)
            groups.append({"resource_id": identity, "name": name, "sizes": sizes})
    finally:
        kernel.FreeLibrary(module)

    version = ctypes.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
    version.GetFileVersionInfoW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
    version.VerQueryValueW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT))
    size = version.GetFileVersionInfoSizeW(str(executable), None)
    assert size
    buffer = ctypes.create_string_buffer(size)
    assert version.GetFileVersionInfoW(str(executable), 0, size, buffer)
    values = {}
    for key, expected in (("ProductName", "Packsmith"), ("FileDescription", "Packsmith archive manager"), ("OriginalFilename", "Packsmith.exe"), ("FileVersion", "0.1.0-beta.1"), ("ProductVersion", "0.1.0-beta.1")):
        value = ctypes.c_void_p(); length = wintypes.UINT()
        assert version.VerQueryValueW(buffer, "\\StringFileInfo\\040904b0\\" + key, ctypes.byref(value), ctypes.byref(length))
        values[key] = ctypes.wstring_at(value, length.value).rstrip("\0")
        assert values[key] == expected, values

    env = os.environ.copy()
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QTDIR", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM"):
        env.pop(key, None)
    gui_receipts = json.loads((EVIDENCE / "gui-smoke.json").read_text(encoding="utf-8"))
    current = Path(gui_receipts[0]["journal_directory"])
    legacy = current.parents[2] / "Unarchiver/Unarchiver/jobs"
    legacy.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="packsmith-recovery-") as temporary:
        destination = Path(temporary)
        archive = ROOT / "assessment/outputs/fixtures/large-5g.zip"
        worker = subprocess.Popen([str(PACKAGE / "workers/packsmith-worker.exe")], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        worker.stdin.write(json.dumps({"operation": "extract", "archive": str(archive), "destination": str(destination)}) + "\n"); worker.stdin.flush()
        stage = json.loads(worker.stdout.readline())
        assert stage["event"] == "staging"
        worker.kill(); worker.communicate(timeout=10)
        assert Path(stage["path"]).exists()
        journal = legacy / (stage["token"] + ".json")
        assert not journal.exists()
        journal.write_text(json.dumps(stage), encoding="utf-8")
        report = EVIDENCE / "previous-name-recovery.json"
        result = subprocess.run([str(executable), "--smoke-startup-recovery", stage["path"], str(destination), str(report)], env=env, capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr
        recovery = json.loads(report.read_text(encoding="utf-8"))
        assert recovery["passed"] and recovery["stage_removed"]
        assert not journal.exists() and not Path(stage["path"]).exists()
    receipt = {"passed": True, "gui_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
               "embedded_icons": groups, "version_strings": values, "previous_name_recovery": recovery}
    (EVIDENCE / "branding.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("Packsmith embedded icons, Windows version strings and previous-name recovery: PASS")


if __name__ == "__main__":
    main()
