import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(os.environ.get('ASSESSMENT_WORK','/home/riceric/unarchiver-assessment-20260930'))
RESULTS=[]

def run(name,args,env=None):
    start=time.monotonic();log=ROOT/'evidence'/f'{name}.log'
    with log.open('w') as out: result=subprocess.run(args,env=env,stdout=out,stderr=subprocess.STDOUT)
    RESULTS.append({'name':name,'command':args,'exit_code':result.returncode,'elapsed_seconds':round(time.monotonic()-start,3),'log':log.name})
    (ROOT/'evidence'/f'probe-builds-{os.name}.json').write_text(json.dumps(RESULTS,indent=2)+'\n')
    print(f'{name}: {result.returncode}',flush=True)
    if result.returncode:print('\n'.join(log.read_text(errors='replace').splitlines()[-8:]),flush=True)

if os.name=='nt':
    env=os.environ.copy();env['PATH']=r'C:\msys64\mingw64\bin'+os.pathsep+env['PATH']
    build=ROOT/'experiments';source=ROOT/'references'
    ninja=(build/'libarchive-windows-build'/'build.ninja').read_text()
    libs=re.search(r'  LINK_LIBRARIES = (libarchive/libarchive.a[^\n]+)',ninja).group(1).split()
    libs[0]=str(build/'libarchive-windows-build'/'libarchive'/'libarchive.a')
    libs += [str(build/'libzip-windows-build'/'lib'/'libzip.a'),'-lz','-lbz2','-llzma','-lzstd','-lssl','-lcrypto','-lbcrypt']
    run('native-windows-build',[r'C:\msys64\mingw64\bin\g++.exe','-std=c++17','-O2',str(ROOT/'scripts'/'native_probe.cpp'),'-I'+str(source/'libarchive'/'libarchive'),'-I'+str(source/'libzip'/'lib'),'-I'+str(build/'libzip-windows-build'),*libs,'-o',str(build/'native-probe.exe')],env)
else:
    src=ROOT/'references'
    libs=['-lz','-lbz2','-llzma','-llz4','-lzstd','-lcrypto','-lxml2','-lacl','-lssl']
    run('native-linux-build',['g++','-std=c++17','-O2',str(ROOT/'scripts'/'native_probe.cpp'),'-I'+str(src/'libarchive'/'libarchive'),'-I'+str(src/'libzip'/'lib'),'-I'+str(WORK/'libzip-build'),str(WORK/'libzip-build'/'lib'/'libzip.a'),str(WORK/'libarchive-build'/'libarchive'/'libarchive.a'),*libs,'-o',str(WORK/'native-probe')])
    for variant in ('stable','head','baseline'):
        engine=WORK/f'xad-{variant}'/'XADMaster'
        if not (engine/'libXADMaster.a').exists():continue
        objcflags=subprocess.check_output(['gnustep-config','--objc-flags'],text=True).split()
        run(f'xad-{variant}-probe-build',['gcc',*objcflags,'-I'+str(engine),str(ROOT/'scripts'/'xad_probe.m'),'-Wl,--whole-archive',str(engine/'libXADMaster.a'),str(engine.parent/'UniversalDetector'/'libUniversalDetector.a'),'-Wl,--no-whole-archive','-lgnustep-base','-lz','-lbz2','-lwavpack','-licuuc','-lobjc','-lm','-lstdc++','-o',str(WORK/f'xad-{variant}-probe')])
