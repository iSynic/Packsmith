"""Compare the published beta 4 and local GUI sequentially on the same 100k archive."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time
import zipfile
import psutil

ROOT=Path(__file__).resolve().parents[1]
evidence=ROOT/'assessment/evidence/extraction-options'
baseline=ROOT/'dist/historical/v0.1.0-beta.4/423582e/Packsmith-0.1.0-beta.4-windows-x64.zip'
if not baseline.exists():baseline=ROOT/'dist/releases/v0.1.0-beta.4/Packsmith-0.1.0-beta.4-windows-x64.zip'
assert hashlib.sha256(baseline.read_bytes()).hexdigest()=='6c9f6828395dd736bf7114309a9be978679fd75aa7c08fa13f221bd9804be90b','Compare against the preserved original beta 4 binary ZIP'
source=ROOT/'dist/Packsmith-preview'
env=os.environ.copy();env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
for key in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QTDIR','QT_QPA_PLATFORM'):env.pop(key,None)
measurements=[]
with tempfile.TemporaryDirectory(prefix='packsmith-listing-comparison-') as temp:
    temp=Path(temp)
    with zipfile.ZipFile(baseline) as archive:archive.extractall(temp/'baseline')
    shutil.copytree(source,temp/'current')
    for run,kind in enumerate(('current','baseline','baseline','current')):
        executable=temp/(kind+'/Packsmith' if kind=='baseline' else kind)/'Packsmith.exe'
        case=temp/f'run-{run}';case.mkdir();destination=case/'output';destination.mkdir()
        report=case/'gui.json'
        proc=subprocess.Popen([str(executable),'--smoke',str(ROOT/'assessment/outputs/fixtures/scale-100k.zip'),str(destination),str(report)],env=env,cwd=case,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        peak=0;started=time.monotonic();handle=psutil.Process(proc.pid)
        while proc.poll() is None:
            try:peak=max(peak,handle.memory_info().rss)
            except psutil.Error:pass
            if time.monotonic()-started>60:proc.kill();raise RuntimeError('100k comparison timed out')
            time.sleep(.01)
        stdout,stderr=proc.communicate()
        assert proc.returncode==0,(proc.returncode,stderr)
        result=json.loads(report.read_text(encoding='utf-8'));assert result['passed']
        measurements.append(dict(kind=kind,listing_ms=result['listing_ms'],peak_gui_rss=peak,max_event_gap_ms=result['max_event_gap_ms']))
summary={kind:{key:statistics.median(r[key] for r in measurements if r['kind']==kind) for key in ('listing_ms','peak_gui_rss')} for kind in ('baseline','current')}
changes={key:round(100*(summary['current'][key]/summary['baseline'][key]-1),2) for key in summary['current']}
result=dict(passed=all(n<=20 for n in changes.values()) and all(r['max_event_gap_ms']<=1000 for r in measurements),measurements=measurements,median=summary,change_percent=changes,baseline_zip_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),gui_sha256=hashlib.sha256((source/'Packsmith.exe').read_bytes()).hexdigest(),environment='Sequential alternating native runs on the same developer machine; no competing owned build/test/emulator jobs. Existing user applications unchanged.')
evidence.mkdir(parents=True,exist_ok=True);(evidence/'performance-comparison.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
