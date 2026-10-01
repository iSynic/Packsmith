"""Check handoff integrity without treating engine failures as release acceptance."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import difflib
ROOT=Path(__file__).resolve().parents[1]
DESKTOP_EVIDENCE=ROOT/'evidence/beta3'
errors=[]
counts={}
for path in (ROOT/'evidence').rglob('*.json'):
    try:json.loads(path.read_text())
    except Exception as e:errors.append(str(path)+': '+str(e))
lock=json.loads((ROOT/'evidence'/'sources.lock.json').read_text())
for item in lock['references']:
    path=ROOT/'references'/item['name']
    sha=subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
    dirty=subprocess.check_output(['git','-C',str(path),'status','--porcelain'],text=True).strip()
    if sha!=item['commit'] or dirty:errors.append('Reference mismatch/changes: '+item['name'])
baseline=ROOT.parent/'source'
if subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip()!=lock['baseline_commit']:errors.append('Baseline mismatch')
if subprocess.check_output(['git','-C',str(baseline),'status','--porcelain'],text=True).strip():errors.append('Baseline changed')
manifest=json.loads((ROOT/'evidence'/'fixture-manifest.json').read_text())
for name,info in manifest['archives'].items():
    path=ROOT/'outputs'/'fixtures'/name
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:errors.append('Fixture mismatch: '+name)
for pattern in ('suite-*.json','followup-*.json','metadata-*.json'):
    for path in (ROOT/'evidence').glob(pattern):
        rows=json.loads(path.read_text())
        counts[path.name]={k:sum(r['status']==k for r in rows) for k in ('pass','fail','unverified')}
        for row in rows:
            if row.get('raw_log') and not (ROOT/row['raw_log'].replace('\\','/')).exists():errors.append('Missing raw log: '+row['raw_log'])
            if row.get('exit_code',0)!=0 and row['status']=='pass' and row.get('expected')!='rejection':errors.append('Invalid success: '+row['name'])
windows=ROOT/'evidence'/'windows-first'
if (windows/'suite.json').exists():
    rows=json.loads((windows/'suite.json').read_text())
    counts['windows-first/suite.json']={k:sum(r['status']==k for r in rows) for k in ('pass','fail','unverified')}
    for row in rows:
        if row.get('raw_log') and not (ROOT/row['raw_log'].replace('\\','/')).exists():errors.append('Missing Windows raw log: '+row['name'])
        if row.get('exit_code',0)!=0 and row['status']=='pass' and row.get('expected')!='rejection':errors.append('Invalid Windows success: '+row['name'])
    builds=json.loads((windows/'builds.json').read_text())
    for row in builds:
        if not (windows/row['log']).exists():errors.append('Missing Windows build log: '+row['name'])
        if row['exit_code']!=row['expected_exit_code']:errors.append('Windows build/probe expectation failed: '+row['name'])
    bundle=json.loads((windows/'bundle.json').read_text())
    for row in bundle['native_files']:
        file=Path(bundle['bundle_directory'])/row['file']
        if not file.exists() or hashlib.sha256(file.read_bytes()).hexdigest()!=row['sha256']:errors.append('Bundle digest mismatch: '+row['file'])
    allowed={'XADUnarchiver.m','XADStringWindows.m','XADStuffItParser.m','XADStuffIt5Parser.m','XADMacArchiveParser.m'}
    experiment=ROOT/'experiments'/'xad-windows'/'XADMaster'
    for file in (ROOT/'references'/'xad-head').rglob('*'):
        if not file.is_file() or '.git' in file.relative_to(ROOT/'references'/'xad-head').parts:continue
        relative=file.relative_to(ROOT/'references'/'xad-head')
        copy=experiment/relative
        if relative.as_posix() in {'XADStuffItParser.m','XADStuffIt5Parser.m','XADMacArchiveParser.m'}:
            observed=''.join(difflib.unified_diff(file.read_text().splitlines(True),copy.read_text().splitlines(True),fromfile='a/'+relative.as_posix(),tofile='b/'+relative.as_posix()))
            patch=ROOT.parent/'app/patches'/(relative.as_posix()+'.patch')
            if observed!=patch.read_text():errors.append('Metadata patch mismatch: '+relative.as_posix())
        if relative.as_posix() not in allowed and (not copy.exists() or copy.read_bytes()!=file.read_bytes()):errors.append('Unexpected experiment source change: '+relative.as_posix())
for doc in [ROOT/'README.md',*(ROOT/'reports').glob('*.md')]:
    for link in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
        if ':' in link or link.startswith('#'):continue
        if not (doc.parent/link.split('#')[0]).exists():errors.append('Broken link: '+str(doc)+' '+link)
desktop=ROOT.parent/'dist/Packsmith-preview'
if desktop.exists():
    package=json.loads((DESKTOP_EVIDENCE/'desktop-preview/package.json').read_text(encoding='utf-8'))
    for row in package['files']:
        path=desktop/row['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:errors.append('Desktop package mismatch: '+row['path'])
    for name,digest in package['authored_sources'].items():
        if hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest()!=digest:errors.append('Desktop source changed since build: '+name)
    binaries={'worker_sha256':desktop/'workers/packsmith-worker.exe','decoder_sha256':desktop/'workers/legacy/xad-stream.exe','gui_sha256':desktop/'Packsmith.exe'}
    for name in ('desktop-preview/worker-tests.json','desktop-legacy/tests.json','desktop-preview/gui-smoke.json','desktop-preview/branding.json'):
        receipt=json.loads((DESKTOP_EVIDENCE/name).read_text(encoding='utf-8'))
        rows=receipt if isinstance(receipt,list) else [receipt]
        for row in rows:
            if row.get('failures',0) or row.get('errors',0) or not row.get('passed',True):errors.append('Desktop tests failed: '+name)
            for key,path in binaries.items():
                if key in row and hashlib.sha256(path.read_bytes()).hexdigest()!=row[key]:errors.append('Desktop receipt binary mismatch: '+name+' '+key)
    generated=json.loads((DESKTOP_EVIDENCE/'desktop-legacy/generated-fixtures.json').read_text(encoding='utf-8'))
    for name,row in generated['files'].items():
        if hashlib.sha256((ROOT/'outputs/desktop-legacy-fixtures'/name).read_bytes()).hexdigest()!=row['sha256']:errors.append('Legacy fixture mismatch: '+name)
    counts['desktop']={'worker_behavior_tests':json.loads((DESKTOP_EVIDENCE/'desktop-preview/worker-tests.json').read_text())['tests'],'legacy_behavior_tests':json.loads((DESKTOP_EVIDENCE/'desktop-legacy/tests.json').read_text())['tests'],'native_gui_checks':len(json.loads((DESKTOP_EVIDENCE/'desktop-preview/gui-smoke.json').read_text())),'generated_legacy_fixtures':len(generated['files'])}
    checks=json.loads((DESKTOP_EVIDENCE/'model-controller-ui.json').read_text())
    if not checks['passed']:errors.append('Beta3 model/controller/UI tests failed')
    classic=json.loads((DESKTOP_EVIDENCE/'classic-tests.json').read_text())
    if classic['failures'] or classic['errors'] or classic['worker_sha256']!=hashlib.sha256(binaries['worker_sha256'].read_bytes()).hexdigest():errors.append('Classic export tests failed or binary changed')
    counts['desktop']['classic_export_tests']=classic['tests']
result={'handoff_integrity':'pass' if not errors else 'fail','production_release_qualified':False,'errors':errors,'reference_count':len(lock['references'])+1,'fixture_count':len(manifest['archives']),'checks':counts,'limits':'Validates artifact/receipt integrity; known engine and application-policy failures remain reported, not waived.'}
(DESKTOP_EVIDENCE/'handoff-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
raise SystemExit(bool(errors))
