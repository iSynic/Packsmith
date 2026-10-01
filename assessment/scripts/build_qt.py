"""Build and run the isolated Qt Widgets process/model probe offscreen."""
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
platform='windows' if os.name=='nt' else 'linux'
base=ROOT/'experiments' if os.name=='nt' else Path('/home/riceric/unarchiver-assessment-20260930')
build=base/('qt-windows-build' if os.name=='nt' else 'qt-build')
env=os.environ.copy();flags=[]
if os.name=='nt':
    qt=ROOT/'tools'/'qt'/'6.10.2'/'mingw_64'
    env['PATH']=str(qt/'bin')+os.pathsep+r'C:\msys64\mingw64\bin'+os.pathsep+env['PATH']
    flags=['-G','Ninja','-DCMAKE_CXX_COMPILER=C:/msys64/mingw64/bin/g++.exe','-DCMAKE_PREFIX_PATH='+str(qt)]
env['QT_QPA_PLATFORM']='offscreen'
binary=build/('qt_probe.exe' if os.name=='nt' else 'qt_probe')
seven=ROOT/'tools'/'sevenzip-full'/'7z.exe' if os.name=='nt' else base/'sevenzip'/'7zz'
rows=[]
for label,args in [
    ('configure',['cmake','-S',str(ROOT/'scripts'/'qt_probe'),'-B',str(build),*flags]),
    ('build',['cmake','--build',str(build),'-j','4']),
    ('run',[str(binary),str(seven),str(ROOT/'outputs'/'fixtures'/'scale-100k.zip'),str(ROOT/'evidence'/f'qt-{platform}-probe')])]:
    log=ROOT/'evidence'/f'qt-{platform}-{label}.log';start=time.monotonic()
    with log.open('w') as out:result=subprocess.run(args,env=env,stdout=out,stderr=subprocess.STDOUT)
    rows.append({'command':args,'exit_code':result.returncode,'elapsed_seconds':round(time.monotonic()-start,3),'log':log.name})
    if result.returncode:break
(ROOT/'evidence'/f'qt-{platform}-builds.json').write_text(json.dumps(rows,indent=2)+'\n')
print(platform,rows[-1]['exit_code'])
