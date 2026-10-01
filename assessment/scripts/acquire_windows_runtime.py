"""Acquire an isolated, hash-checked native MSYS2 toolchain/runtime closure."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DOWNLOAD=ROOT/'downloads'/'windows-runtime';DOWNLOAD.mkdir(exist_ok=True)
STAGE=ROOT/'tools'/'windows-runtime';STAGE.mkdir(exist_ok=True)
LOCK=ROOT/'evidence'/'windows-runtime.lock.json'
BASE='https://mirror.msys2.org/mingw/mingw64/'

def fetch(url,path):
    if path.exists():return
    temp=path.with_suffix(path.suffix+'.partial')
    direct=url.replace('https://mirror.msys2.org/','https://repo.msys2.org/')
    subprocess.run(['C:/Windows/System32/curl.exe','--fail','--location','--silent','--show-error','--retry','2','--max-time','180','--output',str(temp),direct],check=True)
    temp.replace(path)

if LOCK.exists() and any(p['name']=='mingw-w64-x86_64-lld' for p in json.loads(LOCK.read_text())['packages']):
    lock=json.loads(LOCK.read_text());selected=lock['packages']
else:
    database=DOWNLOAD/'mingw64.db';fetch(BASE+'mingw64.db',database)
    packages={};providers={}
    with tarfile.open(database) as archive:
        for member in archive:
            if not member.name.endswith('/desc'):continue
            fields={}
            for part in archive.extractfile(member).read().decode().strip().split('\n\n'):
                lines=part.splitlines();fields[lines[0].strip('%')]=lines[1:]
            name=fields['NAME'][0];packages[name]=fields
            for provide in fields.get('PROVIDES',[]):providers.setdefault(re.split('[<>=]',provide)[0],name)
    selected=[];seen=set()
    def choose(name):
        name=re.split('[<>=]',name)[0]
        if name not in packages:name=providers.get(name,name)
        if name in seen:return
        if name not in packages:raise RuntimeError('Unresolved package: '+name)
        seen.add(name);p=packages[name]
        for dep in p.get('DEPENDS',[]):choose(dep)
        selected.append({'name':name,'version':p['VERSION'][0],'filename':p['FILENAME'][0],'url':BASE+p['FILENAME'][0],'sha256':p['SHA256SUM'][0],'license':p.get('LICENSE',[]),'dependencies':p.get('DEPENDS',[]),'compressed_bytes':int(p['CSIZE'][0])})
    for name in ('clang','lld','gcc','gnustep-base','libobjc2','wavpack','bzip2','zlib','gnustep-make','make'):
        choose('mingw-w64-x86_64-'+name)
    if LOCK.exists():
        previous=json.loads(LOCK.read_text())
        current={p['name']:p for p in selected}
        for item in previous['packages']:
            if current.get(item['name'])!=item:raise RuntimeError('Existing package pin changed: '+item['name'])
    lock={'repository':BASE,'database_sha256':hashlib.sha256(database.read_bytes()).hexdigest(),'selection':'Native MinGW64 Clang + GNUstep modern Objective-C runtime; isolated package closure','packages':selected}
    LOCK.write_text(json.dumps(lock,indent=2)+'\n')

print('Packages:',len(selected),'download MiB:',round(sum(p['compressed_bytes'] for p in selected)/1048576,1),flush=True)
def acquire(item):
    file=DOWNLOAD/item['filename'];fetch(item['url'],file)
    if hashlib.sha256(file.read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Digest mismatch: '+item['name'])
    marker=STAGE/(item['filename']+'.extracted')
    if not marker.exists():
        with tarfile.open(file) as archive:archive.extractall(STAGE,filter='data')
        marker.write_text(item['sha256'])
    print(item['name'],item['version'],flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(acquire,selected))
