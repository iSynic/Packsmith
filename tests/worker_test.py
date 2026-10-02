"""Behavioral tests using generated ZIPs, the shared corpus, and independent readers."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
import zipfile
import ctypes
from ctypes import wintypes

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / os.environ.get("PACKSMITH_EVIDENCE", "assessment/evidence/beta4")
WORKER = Path(sys.argv.pop(1)).resolve()
SEVEN = ROOT / "assessment/tools/sevenzip-full/7z.exe"
FIXTURES = ROOT / "assessment/outputs/fixtures"
ENV = os.environ.copy()
ENV["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QTDIR", "QML2_IMPORT_PATH"):
    ENV.pop(key, None)
RECEIPTS = []

def deletion_lock(path):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p)
    kernel.CreateFileW.restype=ctypes.c_void_p
    kernel.CloseHandle.argtypes=(ctypes.c_void_p,)
    handle=kernel.CreateFileW(str(path),0x80000000,3,None,3,0,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    return kernel,handle


def job(operation, archive, **extra):
    request = dict(operation=operation, archive=str(archive), **extra)
    started = time.perf_counter()
    result = subprocess.run([str(WORKER)], input=json.dumps(request) + "\n", text=True, encoding="utf-8",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=ENV, timeout=120)
    events = [json.loads(line) for line in result.stdout.splitlines()]
    RECEIPTS.append({"operation": operation, "archive": Path(archive).name,
                     "exit_code": result.returncode, "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                     "terminal": events[-1] if events else {}, "stderr": result.stderr})
    if not events:
        raise AssertionError(f"Worker produced no protocol response: {result.returncode}, {result.stderr}")
    return result.returncode, events


class WorkerTests(unittest.TestCase):
    def test_transient_commit_lock_retries_then_commits(self):
        archive=self.zip([('payload',bytes(range(256))*65536)])
        proc=subprocess.Popen([str(WORKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=ENV)
        proc.stdin.write(json.dumps(dict(operation='extract',archive=str(archive),destination=str(self.dest)))+'\n');proc.stdin.flush()
        stage=json.loads(proc.stdout.readline())
        while stage['event']!='staging':stage=json.loads(proc.stdout.readline())
        kernel,handle=deletion_lock(Path(stage['path'])/'.unarchiver-job.json')
        retried=False
        try:
            while line:=proc.stdout.readline():
                event=json.loads(line)
                if event.get('retry'):
                    retried=True;break
                if event['event'] in ('error','complete'):break
        finally:kernel.CloseHandle(handle)
        stdout,stderr=proc.communicate(timeout=10)
        self.assertTrue(retried,'A held directory marker must exercise commit retry')
        self.assertEqual(proc.returncode,0,stdout+stderr)
        events=[json.loads(line) for line in stdout.splitlines()]
        self.assertTrue(events[-1]['output_committed']);self.assertTrue(any(e['event']=='warning' for e in events))
        self.assertEqual(self.mapping(events[-1]),{0:bytes(range(256))*65536})
    def test_failed_commit_preserves_original_and_retains_recovery(self):
        archive=self.zip([('original',b'original payload')]);before=hashlib.sha256(archive.read_bytes()).hexdigest()
        kernel,handle=deletion_lock(archive)
        try:
            code,events=job('update',archive,rename=[{'id':0,'path':'renamed'}])
        finally:kernel.CloseHandle(handle)
        self.assertNotEqual(code,0);self.assertFalse(events[-1]['output_committed'])
        self.assertTrue(any(event['event']=='recovery_required' for event in events))
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),before)
        stage=next(event for event in events if event['event']=='staging')
        self.assertTrue(Path(stage['path']).exists())
        self.good('cleanup',archive,**{key:stage[key] for key in ('path','parent','token')})
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),before)

    def test_cleanup_failure_retains_journal_marker_then_can_retry(self):
        archive=FIXTURES/'large-5g.zip'
        proc=subprocess.Popen([str(WORKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=ENV)
        proc.stdin.write(json.dumps(dict(operation='extract',archive=str(archive),destination=str(self.dest)))+'\n');proc.stdin.flush()
        stage=json.loads(proc.stdout.readline())
        while stage['event']!='staging':stage=json.loads(proc.stdout.readline())
        proc.kill();proc.communicate(timeout=10)
        marker=Path(stage['path'])/'.unarchiver-job.json';kernel,handle=deletion_lock(marker)
        try:
            code,events=job('cleanup',archive,**{key:stage[key] for key in ('path','parent','token')})
            self.assertNotEqual(code,0);self.assertTrue(marker.exists());self.assertIn('Cannot remove',events[-1]['message'])
        finally:kernel.CloseHandle(handle)
        self.good('cleanup',archive,**{key:stage[key] for key in ('path','parent','token')})
        self.assertFalse(Path(stage['path']).exists())
    def test_explicit_extraction_scope(self):
        archive=self.zip([('folder/a',b'a'),('folder/b',b'b'),('keep',b'keep'),('empty/',b'')])
        rows=[row for event in self.good('list',archive) if event['event']=='entries' for row in event['items']]
        self.assertEqual(rows[0]['components'],['folder','a'])
        before=hashlib.sha256(archive.read_bytes()).hexdigest()
        for extra in (dict(selection_scope='entries',ids=[]),dict(selection_scope='unknown'),dict(selection_scope='all',ids=[0])):
            code,events=job('extract',archive,destination=str(self.dest),**extra)
            self.assertNotEqual(code,0);self.assertEqual(list(self.dest.iterdir()),[])
        end=self.good('extract',archive,destination=str(self.dest),selection_scope='entries',ids=[0,1])[-1]
        self.assertEqual(self.mapping(end),{0:b'a',1:b'b'});self.assertTrue(end['output_committed'])
        end=self.good('extract',archive,destination=str(self.dest),selection_scope='entries',ids=[3])[-1]
        self.assertEqual(end['file_count'],0);self.assertTrue((Path(end['output'])/'empty').is_dir())
        end=self.good('extract',archive,destination=str(self.dest),selection_scope='all')[-1]
        self.assertEqual(self.mapping(end),{0:b'a',1:b'b',2:b'keep'})
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),before)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="unarchiver-test-")
        self.root = Path(self.temp.name)
        self.dest = self.root / "æ—¥æœ¬-cafÃ©"
        self.dest.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def zip(self, names):
        path = self.root / "æ—¥æœ¬-cafÃ©.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, payload in names:
                    archive.writestr(name, payload)
        return path

    def good(self, operation, archive, **extra):
        code, events = job(operation, archive, **extra)
        self.assertEqual(code, 0, events[-1])
        self.assertEqual(events[-1]["event"], "complete")
        return events

    def mapping(self, event):
        output = Path(event["output"])
        mappings = json.loads((output / event["mapping"]).read_text(encoding="utf-8"))["entries"]
        return {v["id"]: (output / v["output"]).read_bytes() for v in mappings if (output / v["output"]).is_file()}

    def test_unicode_listing_and_numeric_selection(self):
        path = self.zip([("same.txt", b"first"), ("same.txt", b"second"), ("æ—¥æœ¬/cafÃ©.txt", b"Unicode")])
        events = self.good("list", path)
        items = [v for e in events if e["event"] == "entries" for v in e["items"]]
        self.assertEqual([v["id"] for v in items], [0, 1, 2])
        self.assertEqual(items[2]["path"], "æ—¥æœ¬/cafÃ©.txt")
        end = self.good("extract", path, destination=str(self.dest), ids=[1])[-1]
        self.assertEqual(self.mapping(end), {1: b"second"})

    def test_collisions_preserve_all_payloads_and_existing_destination(self):
        path = self.zip([("same.txt", b"first"), ("same.txt", b"second"), ("Case.txt", b"upper"),
                         ("case.txt", b"lower"), ("parent", b"file"), ("parent/child", b"child"),
                         ("unarchiver-mapping.json", b"authored")])
        existing = self.dest / path.stem
        existing.mkdir()
        (existing / "keep.txt").write_bytes(b"untouched")
        end = self.good("extract", path, destination=str(self.dest))[-1]
        self.assertEqual(self.mapping(end), dict(enumerate([b"first", b"second", b"upper", b"lower", b"file", b"child", b"authored"])))
        self.assertEqual((existing / "keep.txt").read_bytes(), b"untouched")

    def test_reserved_names_are_mapped(self):
        path = self.zip([("CON.txt", b"device"), ("trailing. ", b"trailing"), ("what?.txt", b"question")])
        end = self.good("extract", path, destination=str(self.dest))[-1]
        self.assertEqual(set(self.mapping(end).values()), {b"device", b"trailing", b"question"})

    def test_unsafe_paths_fail_without_output(self):
        for name in ("../escape", "/absolute", "C:/escape", "folder/../escape", "\\\\server/share/file"):
            path = self.zip([(name, b"bad")])
            code, events = job("extract", path, destination=str(self.dest))
            self.assertNotEqual(code, 0, name)
            self.assertEqual(events[-1]["event"], "error")
            self.assertEqual(list(self.dest.iterdir()), [])
        self.assertFalse((self.root / "escape").exists())

    def test_symlink_is_rejected(self):
        path = self.root / "links.zip"
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(info, "../outside")
        code, events = job("extract", path, destination=str(self.dest))
        self.assertNotEqual(code, 0, events[-1])
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_bad_checksum_and_truncated_archives(self):
        for name in ("bad-checksum.zip", "truncated.zip"):
            code, events = job("extract", FIXTURES / name, destination=str(self.dest))
            self.assertNotEqual(code, 0, events[-1])
            self.assertEqual(list(self.dest.iterdir()), [])

    def test_create_zip_and_all_edit_operations_independently(self):
        first = self.root / "alpha.txt"; first.write_bytes(b"alpha payload")
        second = self.root / "æ—¥æœ¬.txt"; second.write_bytes(b"Japanese payload")
        replacement = self.root / "replacement.txt"; replacement.write_bytes(b"replacement payload")
        archive = self.root / "created.zip"
        self.good("create", archive, format="zip", files=[str(first), str(second)])
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(z.read("alpha.txt"), first.read_bytes())
            self.assertEqual(z.read("æ—¥æœ¬.txt"), second.read_bytes())
            self.assertIsNone(z.testzip())
        old = archive.read_bytes()
        end = self.good("update", archive, remove=[0], rename=[{"id": 1, "path": "renamed.txt"}], files=[str(replacement)])[-1]
        self.assertEqual(Path(end["backup"]).read_bytes(), old)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(set(z.namelist()), {"renamed.txt", "replacement.txt"})
            self.assertEqual(z.read("renamed.txt"), second.read_bytes())
        self.good("update", archive, replace=[{"id": 0, "source": str(first)}])
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(z.read("renamed.txt"), first.read_bytes())
        self.good("test", archive)

    def test_update_error_keeps_original(self):
        path = self.zip([("alpha.txt", b"alpha"), ("beta.txt", b"beta")])
        before = path.read_bytes()
        code, events = job("update", path, rename=[{"id": 1, "path": "alpha.txt"}])
        self.assertNotEqual(code, 0, events[-1])
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(self.root.glob(".unarchiver-*")))

    def test_remove_last_entry(self):
        source = self.root / "last.txt";source.write_bytes(b"last payload")
        for format in ("zip", "7z"):
            archive = self.root / ("last." + format)
            self.good("create", archive, format=format, files=[str(source)])
            self.good("update", archive, remove=[0])
            events = self.good("list", archive)
            self.assertEqual(events[-1]["count"], 0)
            self.good("test", archive)

    def test_create_and_edit_7z_cli_verifies(self):
        first = self.root / "alpha.txt"; first.write_bytes(b"alpha" * 1000)
        second = self.root / "beta.txt"; second.write_bytes(b"beta" * 1000)
        archive = self.root / "created.7z"
        self.good("create", archive, format="7z", files=[str(first), str(second)])
        self.good("update", archive, remove=[0], rename=[{"id": 1, "path": "renamed.txt"}])
        self.good("update", archive, files=[str(first)])
        self.good("test", archive)
        output = self.root / "oracle";output.mkdir()
        result = subprocess.run([str(SEVEN), "x", "-y", "-o" + str(output), str(archive)], capture_output=True, env=ENV)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual((output / "alpha.txt").read_bytes(), first.read_bytes())
        self.assertEqual((output / "renamed.txt").read_bytes(), second.read_bytes())

    def test_encrypted_headers_password_in_stdin(self):
        source = self.root / "secret.txt";source.write_bytes(b"secret payload")
        archive = self.root / "encrypted.7z"
        # Public synthetic fixture password, not a user secret.
        subprocess.run([str(SEVEN), "a", "-t7z", "-pfixture-password", "-mhe=on", str(archive), str(source)], capture_output=True, check=True, env=ENV)
        for password in (None, "wrong-password"):
            extra = {} if password is None else {"password": password}
            code, events = job("list", archive, **extra)
            self.assertNotEqual(code, 0, events[-1])
            self.assertEqual(events[-1]['code'],'password_required' if password is None else 'decryption_failed')
        self.good("list", archive, password="fixture-password")
        end = self.good("extract", archive, destination=str(self.dest), password="fixture-password")[-1]
        self.assertEqual(self.mapping(end), {0: b"secret payload"})
        self.good("update", archive, password="fixture-password", rename=[{"id": 0, "path": "renamed.txt"}])
        code, events = job("list", archive)
        self.assertNotEqual(code, 0, "Updating must retain encrypted headers")
        self.good("test", archive, password="fixture-password")

    def test_folder_selection_rename_and_remove(self):
        path = self.zip([("folder/", b""), ("folder/one.txt", b"one"), ("folder/sub/two.txt", b"two"), ("keep.txt", b"keep")])
        end = self.good("extract", path, destination=str(self.dest), ids=[0])[-1]
        self.assertEqual(self.mapping(end), {1: b"one", 2: b"two"})
        self.good("update", path, rename=[{"id": 0, "path": "renamed"}])
        with zipfile.ZipFile(path) as z:
            self.assertEqual(set(z.namelist()), {"renamed/", "renamed/one.txt", "renamed/sub/two.txt", "keep.txt"})
        self.good("update", path, remove=[0])
        with zipfile.ZipFile(path) as z:
            self.assertEqual(z.namelist(), ["keep.txt"])

    def test_changed_archive_refuses_stale_selection(self):
        path = self.zip([("alpha", b"alpha")])
        fingerprint = self.good("list", path)[-1]["fingerprint"]
        self.zip([("beta", b"beta")])
        code, events = job("extract", path, destination=str(self.dest), fingerprint=fingerprint, ids=[0])
        self.assertNotEqual(code, 0, events[-1])
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_destination_junction_is_rejected(self):
        outside = self.root / "outside";outside.mkdir()
        junction = self.root / "junction"
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True, env=ENV)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.zip([("safe.txt", b"safe")])
        code, events = job("extract", path, destination=str(junction))
        self.assertNotEqual(code, 0, events[-1])
        self.assertEqual(list(outside.iterdir()), [])

    def test_long_paths_zip64_and_write_failure(self):
        name = "/".join(["directory" * 6] * 6) + "/æ—¥æœ¬.txt"
        path = self.zip([(name, b"long path")])
        end = self.good("extract", path, destination=str(self.dest))[-1]
        self.assertEqual(self.mapping(end), {0: b"long path"})
        self.good("test", FIXTURES / "small-zip64.zip")
        file_destination = self.root / "file-destination";file_destination.write_bytes(b"original")
        code, events = job("extract", path, destination=str(file_destination))
        self.assertNotEqual(code, 0, events[-1])
        self.assertEqual(file_destination.read_bytes(), b"original")

    def test_terminated_update_original_and_recovery_cleanup(self):
        archive = self.root / "interrupted.zip"
        shutil.copy2(FIXTURES / "large-5g.zip", archive)
        digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
        proc = subprocess.Popen([str(WORKER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=ENV)
        proc.stdin.write(json.dumps(dict(operation="update", archive=str(archive), rename=[{"id": 0, "path": "renamed.bin"}])) + "\n");proc.stdin.flush()
        stage = json.loads(proc.stdout.readline())
        while stage["event"] != "staging": stage = json.loads(proc.stdout.readline());self.assertEqual(stage["event"], "staging")
        with self.assertRaises(PermissionError):
            with archive.open("r+b"):
                pass
        proc.kill();proc.communicate(timeout=10)
        self.assertEqual(hashlib.file_digest(archive.open("rb"), "sha256").hexdigest(), digest)
        self.assertTrue(Path(stage["path"]).exists())
        bad = dict(stage);bad["token"] = "incorrect"
        code, events = job("cleanup", archive, **{key: bad[key] for key in ("path", "parent", "token")})
        self.assertNotEqual(code, 0, events[-1]);self.assertTrue(Path(stage["path"]).exists())
        self.good("cleanup", archive, **{key: stage[key] for key in ("path", "parent", "token")})
        self.assertFalse(Path(stage["path"]).exists())
        self.assertEqual(hashlib.file_digest(archive.open("rb"), "sha256").hexdigest(), digest)

    def test_100000_actual_entries(self):
        events = self.good("list", FIXTURES / "scale-100k.zip")
        count = sum(len(e["items"]) for e in events if e["event"] == "entries")
        self.assertEqual(count, 100000)

    def test_cooperative_cancel_removes_partial_output(self):
        archive = FIXTURES / "large-5g.zip"
        proc = subprocess.Popen([str(WORKER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=ENV)
        proc.stdin.write(json.dumps(dict(operation="extract", archive=str(archive), destination=str(self.dest))) + "\n")
        proc.stdin.flush()
        stage = json.loads(proc.stdout.readline())
        while stage["event"] != "staging": stage = json.loads(proc.stdout.readline())
        self.assertEqual(stage["event"], "staging")
        start = time.perf_counter()
        proc.stdin.write('{"cancel":true}\n');proc.stdin.flush()
        stdout, stderr = proc.communicate(timeout=10)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('"event":"cancelled"', stdout)
        self.assertEqual(list(self.dest.iterdir()), [])
        RECEIPTS.append({"operation": "cancel", "latency_ms": round((time.perf_counter()-start)*1000, 2), "stderr": stderr})


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkerTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = EVIDENCE / "desktop-preview"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "worker-tests.json").write_text(json.dumps({"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "environment": "Native Windows; developer PATH removed; not a clean VM", "worker_sha256": hashlib.file_digest(WORKER.open("rb"), "sha256").hexdigest(), "receipts": RECEIPTS}, indent=2)+"\n", encoding="utf-8")
    sys.exit(0 if result.wasSuccessful() else 1)
