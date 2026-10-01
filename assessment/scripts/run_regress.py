"""Run the real libzip regression suite with a pinned, isolated nihtest."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'experiments' if os.name == 'nt' else Path('/home/riceric/unarchiver-assessment-20260930')
platform = 'windows' if os.name == 'nt' else 'linux'
wrapper = BASE/('nihtest.cmd' if os.name == 'nt' else 'nihtest')
if os.name == 'nt':
    wrapper.write_text('@echo off\nset "PYTHONPATH='+str(ROOT/'references'/'nihtest')+'"\n"'+sys.executable+'" -m nihtest %*\n')
else:
    wrapper.write_text('#!/bin/sh\nPYTHONPATH="'+str(ROOT/'references'/'nihtest')+'" exec "'+sys.executable+'" -m nihtest "$@"\n')
    wrapper.chmod(0o755)
build = BASE/('libzip-windows-build' if os.name == 'nt' else 'libzip-build')
env=os.environ.copy()
if os.name=='nt':env['PATH']=r'C:\msys64\mingw64\bin'+os.pathsep+env['PATH']
rows=[]
for label,command in [
    ('configure',['cmake','-S',str(ROOT/'references'/'libzip'),'-B',str(build),'-DBUILD_REGRESS=ON','-DNIHTEST='+str(wrapper)]),
    ('build',['cmake','--build',str(build),'-j','4']),
    ('ctest',['ctest','--test-dir',str(build),'--output-on-failure','-j','4'])]:
    log=ROOT/'evidence'/f'libzip-{platform}-regress-{label}.log'
    start=time.monotonic()
    with log.open('w') as out:result=subprocess.run(command,env=env,stdout=out,stderr=subprocess.STDOUT)
    rows.append({'command':command,'exit_code':result.returncode,'elapsed_seconds':round(time.monotonic()-start,3),'log':log.name})
    print(platform,label,result.returncode,flush=True)
    if result.returncode and label!='ctest':break
(ROOT/'evidence'/f'libzip-{platform}-regress.json').write_text(json.dumps(rows,indent=2)+'\n')
