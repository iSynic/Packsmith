"""Pin a GCC 16.1 runtime candidate for GNUstep's May 2026 build.

The current GCC 16 runtime omits five symbols imported by that binary.
This overlay stays separate from the current-package closure.
"""
import hashlib
import argparse
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--rejected-gcc15',action='store_true',help='Acquire the retained failed GCC 15 comparison instead of the active overlay');options=parser.parse_args()
version='15.2.0-13' if options.rejected_gcc15 else '16.1.0-1'
slug='gcc15' if options.rejected_gcc15 else 'gcc16_1'
DOWNLOAD=ROOT/'downloads'/'windows-runtime'
STAGE=ROOT/'tools'/('windows-runtime-'+slug);STAGE.mkdir(exist_ok=True)
LOCK=ROOT/'evidence'/('windows-'+slug+'.lock.json')
if LOCK.exists():
    rows=json.loads(LOCK.read_text())['packages']
else:
    rows=[]
    for name in ('gcc','gcc-libs'):
        filename=f'mingw-w64-x86_64-{name}-{version}-any.pkg.tar.zst'
        rows.append({'name':name,'version':version,'filename':filename,'url':'https://repo.msys2.org/mingw/mingw64/'+filename})
for item in rows:
    file=DOWNLOAD/item['filename']
    if not file.exists():
        subprocess.run(['C:/Windows/System32/curl.exe','--fail','--location','--silent','--show-error','--retry','2','--max-time','180','--output',str(file)+'.partial',item['url']],check=True)
        Path(str(file)+'.partial').replace(file)
    digest=hashlib.sha256(file.read_bytes()).hexdigest()
    if item.get('sha256',digest)!=digest:raise RuntimeError('Digest mismatch')
    item['sha256']=digest
    marker=STAGE/(file.name+'.extracted')
    if not marker.exists():
        with tarfile.open(file) as archive:archive.extractall(STAGE,filter='data')
        marker.write_text(digest)
    print(item['name'],item['version'],flush=True)
reason='Rejected comparison: GCC 15.2.0-13 lacks 228 GNUstep imports and fails the loader probe.' if options.rejected_gcc15 else 'GNUstep 1.31.1-10 imports five libstdc++ symbols absent from GCC 16.2. GCC 16.1.0-1 overlay passes the native loader/ABI and worker fixture probes. GCC 15 also fails.'
LOCK.write_text(json.dumps({'reason':reason,'hash_provenance':'SHA256 recorded after initial download over verified HTTPS from official MSYS2 repository; checked on reuse.','packages':rows},indent=2)+'\n')
