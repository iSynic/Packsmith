"""Run native model/controller/UI checks from an isolated runtime and record receipts."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def main():
    runtime=ROOT/'assessment/outputs/beta2-test-runtime'
    shutil.copytree(ROOT/'dist/Packsmith-preview',runtime,dirs_exist_ok=True)
    for name in ('packsmith-core-tests','packsmith-ui-tests','packsmith-fake-worker'):
        shutil.copy2(ROOT/'build/windows'/(name+'.exe'),runtime)
    shutil.copy2(ROOT/'assessment/tools/qt/6.10.2/mingw_64/bin/Qt6Test.dll',runtime)
    evidence=ROOT/'assessment/evidence/beta2';evidence.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    for name in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QTDIR','QT_QPA_PLATFORM'):
        env.pop(name,None)
    receipts=[]
    for name,args in (('packsmith-core-tests',[str(runtime/'packsmith-fake-worker.exe')]),('packsmith-ui-tests',[])):
        command=[str(runtime/(name+'.exe')),*args]
        result=subprocess.run(command,env=env,cwd=evidence,capture_output=True,text=True,encoding='utf-8',timeout=120)
        (evidence/(name+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8')
        row=dict(name=name,command=command,exit_code=result.returncode,passed=result.returncode==0,
                 executable_sha256=hashlib.file_digest((runtime/(name+'.exe')).open('rb'),'sha256').hexdigest())
        if name=='packsmith-core-tests' and result.returncode==0:row['measurements']=json.loads(result.stdout)
        receipts.append(row); print(name+': '+str(result.returncode),flush=True)
        if result.returncode:print(result.stdout+result.stderr,flush=True)
    (evidence/'model-controller-ui.json').write_text(json.dumps(dict(passed=all(r['passed'] for r in receipts),
        environment='Native qwindows UI and model/controller tests; developer PATH removed; developer machine, no accessibility or VM certification',
        receipts=receipts),indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if all(r['passed'] for r in receipts) else 1)

if __name__=='__main__':main()
