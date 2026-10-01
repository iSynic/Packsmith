"""Record PE-symbol and loader evidence for GNUstep runtime candidates."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
PREFIX=ROOT/'tools'/'windows-runtime'/'mingw64'
BASE=ROOT/'experiments'/'xad-windows'
OUT=ROOT/'evidence'/'windows-first'
OBJDUMP='C:/msys64/mingw64/bin/objdump.exe'
def dump(path):return subprocess.check_output([OBJDUMP,'-p',str(path)],text=True,errors='replace')
text=dump(PREFIX/'bin'/'gnustep-base-1_31.dll')
chunk=text.split('DLL Name: libstdc++-6.dll')[1].split('DLL Name: ')[0]
imports={m.group(1) for line in chunk.splitlines() if (m:=re.search(r'<none>\s+[0-9a-f]+\s+(\S+)',line))}
rows=[]
for version,prefix in [('16.2.0-4',PREFIX),('15.2.0-13',ROOT/'tools'/'windows-runtime-gcc15'/'mingw64'),('16.1.0-1',ROOT/'tools'/'windows-runtime-gcc16_1'/'mingw64')]:
    runtime=prefix/'bin'/'libstdc++-6.dll'
    exports=dump(runtime).split('Ordinal/Name Pointer')[1].split('The Function Table')[0]
    names={m.group(1) for line in exports.splitlines() if (m:=re.search(r'\]\s+(?:[0-9a-f]+\s+)?(\S+)$',line))}
    folder=BASE/('runtime-'+version);folder.mkdir(exist_ok=True)
    shutil.copy2(BASE/'foundation-probe.exe',folder/'foundation-probe.exe')
    shutil.copy2(runtime,folder/runtime.name)
    env=os.environ.copy();env['PATH']=str(prefix/'bin')+os.pathsep+str(PREFIX/'bin')+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32')
    p=subprocess.run([str(folder/'foundation-probe.exe')],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=20)
    log=OUT/('runtime-'+version+'.log');log.write_bytes(p.stdout)
    rows.append({'gcc_runtime_version':version,'runtime_path':str(runtime),'gnustep_libstdcxx_imports':len(imports),'missing_symbols':sorted(imports-names),'foundation_exit_code':p.returncode,'raw_log':str(log.relative_to(ROOT)),'status':'pass' if p.returncode==0 and not imports-names else 'fail'})
(OUT/'runtime-compatibility.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps([{k:v for k,v in r.items() if k!='missing_symbols'} | {'missing_symbol_count':len(r['missing_symbols'])} for r in rows],indent=2))
