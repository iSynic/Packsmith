"""Native Windows widget-render and real-worker smoke, with relocated package."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

import psutil
import legacy_fixtures
legacy_fixtures.generate()

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dist/Packsmith-preview"
EVIDENCE = ROOT / "assessment/evidence/desktop-preview"
EVIDENCE.mkdir(parents=True, exist_ok=True)
env = os.environ.copy()
env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
for key in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "QTDIR", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM"):
    env.pop(key, None)
results = []
with tempfile.TemporaryDirectory(prefix="unarchiver-relocation-") as temporary:
    relocated = Path(temporary) / "日本-café preview"
    shutil.copytree(SOURCE, relocated)
    for fixture, mode in (("mainstream.zip", "--smoke"), ("scale-100k.zip", "--smoke"), ("large-5g.zip", "--smoke-recovery"), ("forks.sit", "--smoke"), ("forks.hqx", "--smoke"), ("recovery.sit", "--smoke-recovery"), ("large-wrapped.hqx", "--smoke"), ("bad-large-wrapper-data.hqx", "--smoke-error")):
        folder = EVIDENCE / (Path(fixture).stem if fixture.endswith('.zip') else fixture.replace('.','-'))
        folder.mkdir(exist_ok=True)
        destination = Path(temporary) / fixture
        destination.mkdir()
        report = folder / "gui.json"
        legacy=fixture.endswith(('.sit','.hqx'))
        archive = ROOT / ("assessment/outputs/desktop-legacy-fixtures" if legacy else "assessment/outputs/fixtures") / fixture
        proc = subprocess.Popen([str(relocated / "Packsmith.exe"), mode, str(archive), str(destination), str(report)],
                                cwd=temporary, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        handle = psutil.Process(proc.pid)
        peak_gui = peak_workers = 0
        started = time.perf_counter()
        while proc.poll() is None:
            try:
                peak_gui = max(peak_gui, handle.memory_info().rss)
                peak_workers = max(peak_workers, sum(child.memory_info().rss for child in handle.children(recursive=True)))
            except psutil.Error:
                pass
            if time.perf_counter() - started > 60:
                proc.kill()
                raise RuntimeError("GUI smoke timed out")
            time.sleep(0.01)
        stdout, stderr = proc.communicate()
        if proc.returncode or not report.exists():
            raise RuntimeError(f"GUI smoke failed: {proc.returncode}: {stderr.decode(errors='replace')}")
        data = json.loads(report.read_text(encoding="utf-8"))
        if not data["passed"]:
            raise RuntimeError(data)
        assert data['application_name']=='Packsmith' and data['window_title'].startswith('Packsmith')
        assert data['application_icon_loaded'] and data['archive_icon_loaded']
        if mode == "--smoke":
            # Compare the selected file to the ZIP oracle, not only the process exit code.
            import zipfile
            if legacy:
                expected=b'' if fixture=='large-wrapped.hqx' and data['selected_id']==1 else legacy_fixtures.LARGE_DATA if fixture=='large-wrapped.hqx' and data['selected_id']==2 else b'Classic data\0\x90\xff\n'
                assert data['read_only'] and data['edit_actions_disabled'] and data['columns']==5
                if fixture=='large-wrapped.hqx':
                    assert data['display_names'][1]=='folder/'+'\\t'*14+'\\x20'
            else:
                assert not data['read_only'] and not data['edit_actions_disabled']
                with zipfile.ZipFile(archive) as z:
                    expected = z.read(z.infolist()[data["selected_id"]])
            output = Path(data["output"])
            maps = json.loads(next(output.glob("*mapping.json")).read_text(encoding="utf-8"))["entries"]
            assert len(maps) == 1 and maps[0]["id"] == data["selected_id"]
            assert (output / maps[0]["output"]).read_bytes() == expected
            if legacy:
                import struct
                sidecar=(output/maps[0]['sidecar']).read_bytes()
                descriptors=[struct.unpack_from('>III',sidecar,26+12*i) for i in range(struct.unpack_from('>H',sidecar,24)[0])]
                _,offset,size=next(entry for entry in descriptors if entry[0]==2)
                expected_resource=legacy_fixtures.LARGE_RESOURCE if fixture=='large-wrapped.hqx' and data['selected_id']==1 else b'Classic resource\0\x90\x01\n'
                assert sidecar[offset:offset+size]==expected_resource
            data["screenshot_sha256"] = hashlib.file_digest((folder / "gui.png").open("rb"), "sha256").hexdigest()
        else:
            assert data["stage_removed"] and not list(destination.iterdir())
            if mode=='--smoke-error':
                assert data['error_dialog_visible']
                assert data['error_dialog_text']=='Extraction failed. No completed output was exported.'
                assert 'checksum' in data['error_dialog_detail'].lower()
                data['screenshot_sha256']=hashlib.file_digest((folder/'error.png').open('rb'),'sha256').hexdigest()
        data.update(peak_gui_rss=peak_gui, peak_workers_rss=peak_workers,
                    gui_sha256=hashlib.file_digest((relocated/'Packsmith.exe').open('rb'),'sha256').hexdigest(),
                    worker_sha256=hashlib.file_digest((relocated/'workers/packsmith-worker.exe').open('rb'),'sha256').hexdigest(),
                    decoder_sha256=hashlib.file_digest((relocated/'workers/legacy/xad-stream.exe').open('rb'),'sha256').hexdigest(),
                    total_elapsed_ms=round((time.perf_counter()-started)*1000, 2),
                    scope="Native qwindows widgets and worker; relocated Unicode directory; developer PATH removed; no fresh VM or accessibility proof")
        report.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        results.append(data)
        print(f"{fixture}: {data.get('listing_ms', data.get('recovery_ms'))} ms, GUI {peak_gui/1048576:.1f} MiB, event gap {data.get('max_event_gap_ms', 'unmeasured')} ms")
(EVIDENCE / "gui-smoke.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
