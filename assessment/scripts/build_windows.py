"""Build C archive libraries with one consistent MinGW toolchain."""
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
ENV=os.environ.copy()
ENV['PATH']=r'C:\msys64\mingw64\bin'+os.pathsep+ENV['PATH']

def build(name):
    directory=ROOT/'experiments'/f'{name}-windows-build'
    flags=['-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DBUILD_SHARED_LIBS=OFF','-DCMAKE_C_COMPILER=C:/msys64/mingw64/bin/gcc.exe','-DCMAKE_PREFIX_PATH=C:/msys64/mingw64']
    flags += ['-DENABLE_TEST=ON','-DENABLE_CPIO=OFF','-DENABLE_CAT=OFF','-DENABLE_UNZIP=OFF'] if name=='libarchive' else ['-DBUILD_DOC=OFF','-DBUILD_EXAMPLES=OFF','-DBUILD_OSSFUZZ=OFF','-DBUILD_REGRESS=ON']
    commands=[['cmake','-S',str(ROOT/'references'/name),'-B',str(directory),*flags],['cmake','--build',str(directory),'-j','4'],['ctest','--test-dir',str(directory),'--output-on-failure','-j','4']]
    results=[]
    for label, command in zip(('configure','build','ctest'),commands):
        log=ROOT/'evidence'/f'{name}-windows-{label}.log'
        start=time.monotonic()
        with log.open('w',encoding='utf-8') as out:
            result=subprocess.run(command,env=ENV,stdout=out,stderr=subprocess.STDOUT)
        row={'name':f'{name}-windows-{label}','command':command,'exit_code':result.returncode,'elapsed_seconds':round(time.monotonic()-start,3),'log':log.name}
        results.append(row)
        print(f'{row["name"]}: exit={result.returncode} {row["elapsed_seconds"]}s',flush=True)
        if result.returncode:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-10:]),flush=True)
            break
    return results

if __name__=='__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(build,('libarchive','libzip')))
    (ROOT/'evidence'/'windows-builds.json').write_text(json.dumps(sum(results,[]),indent=2)+'\n')
