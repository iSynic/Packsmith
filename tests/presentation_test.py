"""Isolated native widget tests at forced Qt scales and a contrasting palette."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
runtime=ROOT/'assessment/outputs/beta4-test-runtime'
evidence=ROOT/os.environ.get('PACKSMITH_EVIDENCE','assessment/evidence/beta4')/'presentation'
evidence.mkdir(parents=True,exist_ok=True)
results=[]
for name,scale,large,contrast in [('100',1,False,False),('150',1.5,False,False),('200',2,False,False),('large-text-contrast',1,True,True)]:
    folder=evidence/name;folder.mkdir(exist_ok=True)
    env=os.environ.copy();env['PATH']=str(Path(os.environ['SystemRoot'])/'System32');env['QT_SCALE_FACTOR']=str(scale)
    for key in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QT_QPA_PLATFORM','PACKSMITH_TEST_LARGE_TEXT','PACKSMITH_TEST_CONTRAST'):env.pop(key,None)
    if large:env['PACKSMITH_TEST_LARGE_TEXT']='1'
    if contrast:env['PACKSMITH_TEST_CONTRAST']='1'
    command=[str(runtime/'packsmith-ui-tests.exe'),str(ROOT/'assessment/outputs/desktop-legacy-fixtures/forks.sit')]
    result=subprocess.run(command,cwd=folder,env=env,capture_output=True,text=True,encoding='utf-8',timeout=120)
    (folder/'widgets.log').write_text(result.stdout+result.stderr,encoding='utf-8')
    results.append(dict(name=name,qt_scale=scale,font_points=16 if large else 'system default',contrast_palette=contrast,passed=result.returncode==0,exit_code=result.returncode,screenshot_sha256=hashlib.file_digest((folder/'ui-test.png').open('rb'),'sha256').hexdigest() if (folder/'ui-test.png').exists() else None))
    print(name+': '+str(result.returncode),flush=True)
    if result.returncode:print(result.stdout+result.stderr,flush=True)
receipt=dict(passed=all(r['passed'] for r in results),ui_test_sha256=hashlib.file_digest((runtime/'packsmith-ui-tests.exe').open('rb'),'sha256').hexdigest(),cases=results,
    limitation='Forced Qt scale and palette on native qwindows, with keyboard/focus/accessibility interface assertions. Actual Windows display scaling, contrast theme, enlarged system text and spoken Narrator output remain separately unverified.')
(evidence/'checks.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
raise SystemExit(0 if receipt['passed'] else 1)
