"""Record availability of the exact latest stable toolkit selected at start."""
import json
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
env=os.environ.copy();env['PYTHONPATH']=str(ROOT/'tools'/'aqt')
args=[sys.executable,'-m','aqt','list-qt','windows','desktop','--arch','6.12.0']
log=ROOT/'evidence'/'qt-latest-availability.log'
with log.open('w') as out:
    try:code=subprocess.run(args,cwd=ROOT/'tools'/'aqt',env=env,stdout=out,stderr=subprocess.STDOUT,timeout=45).returncode
    except subprocess.TimeoutExpired:code=-1
(ROOT/'evidence'/'qt-latest-availability.json').write_text(json.dumps({'selected_release':'6.12.0','release_source':'https://www.qt.io/blog/qt-6.12-released','command':args,'exit_code':code,'log':log.name,'tested_windows_release':'6.10.2','tested_ubuntu_release':'6.4.2','scope':'Metadata availability check, not a source build or package proof'},indent=2)+'\n')
print('Qt latest metadata exit:',code)
