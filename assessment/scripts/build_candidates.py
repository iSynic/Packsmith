"""Bounded candidate build attempts with all outputs outside donor trees."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'experiments' if os.name=='nt' else Path('/home/riceric/unarchiver-assessment-20260930')
PLATFORM='windows' if os.name=='nt' else 'linux'
rows=[]
def run(label,args,cwd=None):
    log=ROOT/'evidence'/f'{label}-{PLATFORM}.log';start=time.monotonic()
    env=os.environ.copy()
    if os.name=='nt':env['PATH']=r'C:\msys64\mingw64\bin'+os.pathsep+env['PATH']
    try:
        with log.open('w') as out:result=subprocess.run(args,cwd=cwd,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=240)
        code=result.returncode
    except (OSError,subprocess.TimeoutExpired) as error:
        log.write_text(str(error));code=-1
    rows.append({'name':label,'command':args,'cwd':str(cwd or Path.cwd()),'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,3),'log':log.name})
    (ROOT/'evidence'/f'candidate-builds-{PLATFORM}.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(label,code,flush=True)
    return code==0

run('ark-configure',['cmake','-S',str(ROOT/'references'/'ark'),'-B',str(BASE/'ark-build')])
if os.name=='nt':
    probe=BASE/'foundation-prerequisite.m';probe.write_text('#import <Foundation/Foundation.h>\nint main(void) { return 0; }\n')
    run('xad-foundation-prerequisite',[r'C:\msys64\mingw64\bin\gcc.exe','-c',str(probe),'-o',str(BASE/'foundation-prerequisite.o')])
    run('peazip-lazbuild-prerequisite',['lazbuild','--version'])
else:
    src=ROOT/'references'/'peazip'/'peazip-sources';dest=BASE/'peazip'
    if not dest.exists():shutil.copytree(src,dest)
    if run('peazip-lazbuild-prerequisite',['lazbuild','--version']):
        config=BASE/'lazarus-config'
        run('peazip-metadarkstyle',['lazbuild','--pcp='+str(config),'--add-package',str(dest/'dev'/'metadarkstyle'/'metadarkstyle.lpk')])
        run('peazip-build',['lazbuild','--pcp='+str(config),'--widgetset=gtk2',str(dest/'dev'/'project_peach.lpi')])
        run('pea-build',['lazbuild','--pcp='+str(config),'--widgetset=gtk2',str(dest/'dev'/'project_pea.lpi')])
    build=BASE/'libzip-shared-build'
    if run('libzip-shared-configure',['cmake','-S',str(ROOT/'references'/'libzip'),'-B',str(build),'-DCMAKE_BUILD_TYPE=Release','-DBUILD_SHARED_LIBS=ON','-DBUILD_DOC=OFF','-DBUILD_EXAMPLES=OFF','-DBUILD_REGRESS=ON','-DNIHTEST='+str(BASE/'nihtest')]):
        if run('libzip-shared-build',['cmake','--build',str(build),'-j','4']):
            run('libzip-shared-ctest',['ctest','--test-dir',str(build),'--output-on-failure','-j','4'])
