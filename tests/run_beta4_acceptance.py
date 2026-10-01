"""Run beta 4 gates sequentially; do not publish or change user history."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
worker='dist/Packsmith-preview/workers/packsmith-worker.exe'
commands=[['tests/worker_test.py',worker],['tests/legacy_test.py',worker],['tests/classic_test.py',worker],['tests/run_beta4.py'],
    ['scripts/classic_qualification.py'],['scripts/qualify_legacy.py'],['scripts/classic_corpus_oracle.py','refresh'],
    ['scripts/package_beta.py','--prepare-only'],['tests/relink_test.py'],['tests/gui_smoke.py'],['tests/presentation_test.py'],
    ['tests/branding_test.py'],['tests/performance_beta4.py'],['assessment/scripts/verify_assessment.py']]
private=ROOT/'assessment/outputs/beta4-acceptance';private.mkdir(parents=True,exist_ok=True)
private_manifest=ROOT/'assessment/outputs/beta4-oracles/cases.json'
if private_manifest.exists():commands[4]+=['--private-manifest',str(private_manifest)]
p=argparse.ArgumentParser();p.add_argument('--resume',action='store_true');args=p.parse_args()
receipt_path=ROOT/'assessment/evidence/beta4/acceptance.json'
prior=json.loads(receipt_path.read_text())['commands'] if args.resume else []
receipts=[]
for i,args in enumerate(commands):
    command=[sys.executable,*args];print('Running '+args[0],flush=True)
    if i<len(prior) and prior[i]['command']==command and prior[i]['exit_code']==0:
        receipts.append(prior[i]);print('Already passed '+args[0],flush=True);continue
    with (private/(str(i)+'.log')).open('w',encoding='utf-8') as log:
        result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    receipts.append(dict(command=command,exit_code=result.returncode))
    receipt_path.write_text(json.dumps(dict(passed=False,commands=receipts),indent=2)+'\n',encoding='utf-8')
    if result.returncode:
        print((private/(str(i)+'.log')).read_text(encoding='utf-8')[-6000:],flush=True)
        break
    print('PASS '+args[0],flush=True)
(ROOT/'assessment/evidence/beta4/acceptance.json').write_text(json.dumps(dict(passed=len(receipts)==len(commands) and all(r['exit_code']==0 for r in receipts),commands=receipts),indent=2)+'\n',encoding='utf-8')
raise SystemExit(receipts[-1]['exit_code'])
