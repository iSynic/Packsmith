"""Bundle the assessment worker's transitive native DLL dependencies."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'experiments'/'xad-windows'
PREFIX=ROOT/'tools'/'windows-runtime'/'mingw64'
COMPAT=ROOT/'tools'/'windows-runtime-gcc16_1'/'mingw64'
OUT=ROOT/'outputs'/'windows-first'/'xad-worker-bundle';OUT.mkdir(parents=True,exist_ok=True)
EVIDENCE=ROOT/'evidence'/'windows-first'
roots=[COMPAT/'bin',PREFIX/'bin']
queue=[];rows=[];seen=set();systems=set()
origins={}
for source in (BASE/'build-clang22'/'xad-worker.exe',BASE/'build-clang22'/'lsar.exe',BASE/'build-clang22'/'encoding-probe.exe',BASE/'foundation-probe.exe'):
    shutil.copy2(source,OUT/source.name);queue.append(OUT/source.name);origins[source.name.lower()]=str(source)
while queue:
    path=queue.pop(0)
    if path.name.lower() in seen:continue
    seen.add(path.name.lower())
    text=subprocess.check_output(['C:/msys64/mingw64/bin/objdump.exe','-p',str(path)],text=True,errors='replace')
    imports=re.findall(r'DLL Name:\s+(\S+)',text)
    for name in imports:
        source=next((r/name for r in roots if (r/name).exists()),None)
        if source:
            target=OUT/name;shutil.copy2(source,target);queue.append(target);origins[name.lower()]=str(source)
        elif (Path(os.environ['SystemRoot'])/'System32'/name).exists() or name.lower().startswith(('api-ms-win-','ext-ms-win-')):
            systems.add(name)
        else:raise RuntimeError('Unresolved DLL: '+name+' imported by '+path.name)
    rows.append({'file':path.name,'origin':origins[path.name.lower()],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'imports':imports})
licenses=OUT/'licenses';licenses.mkdir(exist_ok=True)
for prefix in (PREFIX,COMPAT):
    directory=prefix/'share'/'licenses'
    if directory.exists():shutil.copytree(directory,licenses,dirs_exist_ok=True)
for ref in ('xad-head','detector'):
    dest=licenses/ref;dest.mkdir(exist_ok=True)
    for file in (ROOT/'references'/ref).iterdir():
        if file.is_file() and file.name.lower().startswith(('license','copying')):shutil.copy2(file,dest/file.name)
manifest={'bundle_directory':str(OUT),'purpose':'Local assessment experiment, not an installer or release package','sources_lock':'assessment/evidence/sources.lock.json','runtime_locks':['assessment/evidence/windows-runtime.lock.json','assessment/evidence/windows-gcc16_1.lock.json'],'patches':['assessment/evidence/windows-first/windows-wide-unlink.patch','assessment/evidence/windows-first/windows-encoding.patch'],'native_files':rows,'system_imports':sorted(systems),'native_total_bytes':sum(r['bytes'] for r in rows),'limits':'Runtime tests on this development host with sanitized PATH do not establish clean-machine installation. License/source/relink obligations need review before distribution.'}
(EVIDENCE/'bundle.json').write_text(json.dumps(manifest,indent=2)+'\n')
(OUT/'README.txt').write_text('Local Windows XAD assessment bundle. No production GUI or installer.\nRun foundation-probe.exe to check the runtime.\nlsar.exe -j archive lists contents.\nxad-worker.exe archive destination [glob] extracts, preserving resource forks as AppleDouble sidecars.\nSupply the fixture password on stdin; an empty line means no password. Use fresh destinations.\nThe worker always overwrites collisions and is not approved for arbitrary user archives.\nReproduction, source revisions, package pins and experimental patch are in assessment/.\n')
print('Native files:',len(rows),'MiB:',round(manifest['native_total_bytes']/1048576,2),'bundle:',OUT)
