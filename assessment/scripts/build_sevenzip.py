"""Compile the pinned official Linux engine in an experiment copy."""
import json
from pathlib import Path
import shutil
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/home/riceric/unarchiver-assessment-20260930')
dest=BASE/'sevenzip-source'
if not dest.exists():shutil.copytree(ROOT/'references'/'sevenzip',dest,ignore=shutil.ignore_patterns('.git'))
cwd=dest/'CPP'/'7zip'/'Bundles'/'Alone2'
rows=[]
for label,args in [('build',['make','-f','makefile.gcc','-j4']),('test',[str(cwd/'_o'/'7zz'),'t',str(ROOT/'outputs'/'fixtures'/'mainstream.zip')])]:
    log=ROOT/'evidence'/('sevenzip-linux-source-'+label+'.log');start=time.monotonic()
    with log.open('w') as out:
        try:result=subprocess.run(args,cwd=cwd,stdout=out,stderr=subprocess.STDOUT);code=result.returncode
        except OSError as e:out.write(str(e));code=-1
    rows.append({'command':args,'cwd':str(cwd),'exit_code':code,'elapsed_seconds':round(time.monotonic()-start,3),'log':log.name})
    (ROOT/'evidence'/'sevenzip-linux-source-build.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(label,code,flush=True)
    if code:break
