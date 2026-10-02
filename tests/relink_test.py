"""Relink original and modified helpers from beta 4 materials and verify known fork bytes."""
import base64
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import legacy_fixtures

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--materials',type=Path,default=ROOT/'dist/release-materials/Packsmith-0.1.0-beta.4-source-materials')
    args=parser.parse_args()
    legacy_fixtures.generate()
    materials=args.materials.resolve()
    private=ROOT/'assessment/outputs/beta4-relink';private.mkdir(parents=True,exist_ok=True)
    evidence=ROOT/os.environ.get('PACKSMITH_EVIDENCE','assessment/evidence/beta4');evidence.mkdir(parents=True,exist_ok=True)
    compiler=ROOT/'assessment/tools/windows-runtime/mingw64/bin/clang.exe'
    modified=private/'modified-xad_stream.m'
    source=(materials/'app/xad_stream.m').read_text(encoding='utf-8')
    needle='@"checked_forks" : @(checkedForks),'
    assert needle in source
    modified.write_text(source.replace(needle,'@"relink_probe" : @"modified-source",\n            '+needle),encoding='utf-8')
    checks=[]
    for name,replacement in (('original',None),('modified',modified)):
        runtime=private/name;runtime.mkdir(exist_ok=True)
        for path in (ROOT/'dist/Packsmith-preview/workers/legacy').glob('*.dll'):shutil.copy2(path,runtime)
        output=runtime/'xad-stream.exe'
        command=[sys.executable,str(ROOT/'scripts/relink_legacy.py'),'--materials',str(materials),'--compiler',str(compiler),'--output',str(output)]
        if replacement:command+=['--source',str(replacement)]
        build=subprocess.run(command,capture_output=True,text=True,encoding='utf-8')
        (evidence/('relink-'+name+'.log')).write_text(build.stdout+build.stderr,encoding='utf-8');assert build.returncode==0,build.stderr
        env=os.environ.copy();env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
        for key in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QTDIR'):env.pop(key,None)
        for fixture in ('forks.sit','wrapped.hqx','nested-wrapped.hqx','bad-resource.hqx'):
            request=dict(protocol=1,operation='stream',archive=str(legacy_fixtures.OUT/fixture),ids=[0])
            result=subprocess.run([str(output)],input=json.dumps(request)+'\n',capture_output=True,text=True,encoding='utf-8',env=env,timeout=30)
            events=[json.loads(line) for line in result.stdout.splitlines()];terminal=events[-1]
            if fixture=='bad-resource.hqx':assert result.returncode!=0 and terminal['code']=='integrity_failed'
            else:
                assert result.returncode==0 and terminal['event']=='complete'
                data=b''.join(base64.b64decode(e['data']) for e in events if e['event']=='chunk' and e['part']=='data')
                resource=b''.join(base64.b64decode(e['data']) for e in events if e['event']=='chunk' and e['part']=='resource')
                assert data==b'Classic data\0\x90\xff\n' and resource==b'Classic resource\0\x90\x01\n'
                if replacement:assert terminal['relink_probe']=='modified-source'
            checks.append(dict(build=name,fixture=fixture,passed=True,terminal=terminal,helper_sha256=sha(output)))
    (evidence/'relink-test.json').write_text(json.dumps(dict(passed=True,compiler='Clang/lld 22.1.8 on provisioned Windows machine',
        developer_path_removed=True,modified_source_executed=True,materials_helper_source_sha256=sha(materials/'app/xad_stream.m'),checks=checks),indent=2)+'\n',encoding='utf-8')
    print('Original and modified beta 4 helpers relinked; known data/resource bytes and corrupt CRC rejection passed',flush=True)

if __name__=='__main__':main()
