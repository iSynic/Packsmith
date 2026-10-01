"""Private original-software extraction/restoration comparisons on isolated HFS disks."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zipfile
from classic_oracle import ROOT,PRIVATE,PYDEPS,volume,sha

CASES=[('HaxHQX','hax-13.hqx'),('HaxBIN','HAX1R3.BIN'),('Old','dark-towers-ks.hqx'),('New','BOutS 1.2.sit')]

def worker(request):
    p=subprocess.run([str(ROOT/'dist/Packsmith-preview/workers/packsmith-worker.exe')],input=json.dumps(request)+'\n',
        capture_output=True,text=True,encoding='utf-8',timeout=120)
    events=[json.loads(line) for line in p.stdout.splitlines()]
    if p.returncode:raise RuntimeError(str(events[-1]))
    return events[-1]

def prepare():
    sys.path.insert(0,str(PYDEPS));import machfs
    generated=PRIVATE/'corpus';generated.mkdir(exist_ok=True)
    cases=[]
    originals=generated/'Originals.zip';exports=generated/'Exports.zip'
    with zipfile.ZipFile(originals,'w',zipfile.ZIP_DEFLATED) as oz,zipfile.ZipFile(exports,'w',zipfile.ZIP_DEFLATED) as ez:
        for label,name in CASES:
            source=Path('F:/Unarchiver')/name
            listed=worker(dict(operation='list',archive=str(source),filename_encoding='macintosh'))
            request=dict(operation='export_classic',mode='preflight',name_policy='strict',selection_scope='all',
                archive=str(source),filename_encoding='macintosh',fingerprint=listed['fingerprint'])
            plan=worker(request)['plan'];package=generated/(label+'.zip')
            if not package.exists():worker(dict(request,mode='execute',name_policy='mapped',plan_digest=plan['plan_digest'],destination=str(package)))
            with zipfile.ZipFile(package) as z:manifest=json.loads(z.read('Report.json'))
            oz.write(source,label+'/Source'+source.suffix.lower());ez.write(package,label+'.zip')
            cases.append(dict(label=label,name=name,source_sha256=sha(source),package_sha256=sha(package),manifest=manifest))
        # Qualification of the actual worker with known resource records, empty forks and folders.
        sys.path.insert(0,str(ROOT/'tests'));import legacy_fixtures as fixtures
        from macresources import make_file,Resource
        resource=make_file([Resource(b'TEST',128,data=b'Known worker export resource payload')])
        fixture=generated/'Known.sit'
        fixture.write_bytes(fixtures.sit([fixtures.sit_entry('Data',b'Known data'),fixtures.sit_entry('Resource',resource=resource),
            fixtures.sit_entry('caf\u00e9',b'both',resource),fixtures.sit_entry('Empty'),fixtures.sit_entry('Nested',directory=0x20),
            fixtures.sit_entry('Child',b'nested'),fixtures.sit_entry('Vacant',directory=0x20),fixtures.sit_entry('Vacant',directory=0x21),fixtures.sit_entry('Nested',directory=0x21)]))
        fingerprint=sha(fixture);request=dict(operation='export_classic',archive=str(fixture),mode='preflight',fingerprint=fingerprint,filename_encoding='macintosh',name_policy='strict',selection_scope='all')
        plan=worker(request)['plan'];package=generated/'Known.zip'
        if not package.exists():worker(dict(request,mode='execute',plan_digest=plan['plan_digest'],destination=str(package)))
        ez.write(package,'Known.zip')
        with zipfile.ZipFile(package) as z:manifest=json.loads(z.read('Report.json'))
        cases.append(dict(label='Known',name='Generated known forks and empty folders',source_sha256=fingerprint,package_sha256=sha(package),manifest=manifest))
    disk=machfs.Volume();disk.name='Packsmith Corpus'
    donor=volume(PRIVATE/'Tests9.hfv');disk['Expander 5.5']=donor['Expander 5.5'];disk['Reader control']=donor['Reader control']
    for name,path in [('Originals.zip',originals),('Exports.zip',exports)]:
        f=machfs.File();f.data=path.read_bytes();f.type=b'ZIP ';f.creator=b'SITx';disk[name]=f
    for name in ['Corpus76.hfv','Corpus9.hfv']:
        image=PRIVATE/name
        if not image.exists():image.write_bytes(disk.write(size=256*1024*1024))
    for original,new,old_image,new_image in [('BasiliskII_prefs','BasiliskCorpus_prefs','Tests.hfv','Corpus76.hfv'),('SheepShaver_prefs','SheepCorpus_prefs','Tests9.hfv','Corpus9.hfv')]:
        prefs=(PRIVATE/original).read_text();(PRIVATE/new).write_text(prefs.replace(old_image,new_image))
    (generated/'expected.json').write_text(json.dumps(cases,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(cases=len(cases),private=str(generated),originals_zip_bytes=originals.stat().st_size,exports_zip_bytes=exports.stat().st_size)))

def verify(target_filter=None):
    sys.path.insert(0,str(PYDEPS));import machfs
    from macresources import parse_file
    cases=json.loads((PRIVATE/'corpus/expected.json').read_text(encoding='utf-8'))
    for case in cases:
        if case['label']!='Known':assert sha(Path('F:/Unarchiver')/case['name'])==case['source_sha256'],'Original archive changed'
    results=[]
    for target,image in [('System 7.6','Corpus76.hfv'),('Mac OS 9','Corpus9.hfv')]:
        if target_filter and target_filter!=target:continue
        disk=volume(PRIVATE/image);allfiles=[(path,f) for path,f in disk.iter_paths() if isinstance(f,machfs.File)]
        inventory=[];failures=[];matched=0
        for case in cases:
            label=case['label'];package=PRIVATE/'corpus'/(label+'.zip')
            with zipfile.ZipFile(package) as z:
                for row in case['manifest']['entries']:
                    if row['directory']:
                        directory_path=('Exports Folder',label+' Folder','Files')+tuple(row['restored_components'])
                        try:assert isinstance(disk[directory_path],machfs.Folder)
                        except (KeyError,AssertionError):failures.append(dict(case=label,id=row['id'],layer='restoration',reason='Missing directory'))
                        continue
                    name=tuple(row['restored_components'])
                    candidates=[(p,f) for p,f in allfiles if 'Exports Folder' in p and (label+' Folder') in p and p[-len(name):]==name]
                    if len(candidates)!=1:failures.append(dict(case=label,id=row['id'],layer='restoration',reason='Missing or ambiguous HFS path'));continue
                    path,restored=candidates[0];binary=z.read('Files/'+row['transport_path']);d,r=struct.unpack_from('>II',binary,83);offset=128+((d+127)&~127)
                    data=binary[128:128+d];resource=binary[offset:offset+r]
                    def compare(f):
                        actual=bytes(f.rsrc);diff=[i for i,(a,b) in enumerate(zip(resource,actual)) if a!=b]
                        equal=len(resource)==len(actual) and all(16<=i<256 for i in diff)
                        semantic=False
                        if equal:
                            try:
                                def records(raw):return sorted((x.type,x.id,x.name,x.attribs,bytes(x.data)) for x in parse_file(raw)) if raw else []
                                semantic=records(resource)==records(actual)
                            except Exception:semantic=not diff
                        return dict(data_equal=bytes(f.data)==data,resource_equal=actual==resource,
                            resource_records_equal=semantic,reserved_header_only=equal,resource_difference_offsets=diff,
                            actual_data_sha256=hashlib.sha256(f.data).hexdigest(),actual_resource_sha256=hashlib.sha256(f.rsrc).hexdigest())
                    comparison=compare(restored);passed=comparison['data_equal'] and comparison['reserved_header_only'] and comparison['resource_records_equal']
                    expected_dates=(row.get('created_1904') or 0,row.get('modified_1904') or 0)
                    date_equal=all(not a or a==b for a,b in zip(expected_dates,(restored.crdate,restored.mddate)))
                    finder=__import__('base64').b64decode(row.get('finder_info',''));type_creator_equal=not finder or finder[:8]==restored.type+restored.creator
                    portable_flags=struct.unpack_from('>H',finder,8)[0]&0xfc0e if finder else 0
                    flags_equal=(restored.flags&0xfc0e)==portable_flags
                    if not (passed and date_equal and type_creator_equal and flags_equal):failures.append(dict(case=label,id=row['id'],layer='restoration',reason='Fork/date/type-creator/portable-flags mismatch',comparison=comparison,dates_equal=date_equal,type_creator_equal=type_creator_equal,flags_equal=flags_equal))
                    original=None
                    if label!='Known':
                        original_name=tuple(row['components'])
                        if label in ('HaxHQX','HaxBIN'):
                            roots=[name for name,folder in disk['Originals Folder'].items() if isinstance(folder,machfs.Folder) and name.startswith('Hax 1.3 ') and sum(isinstance(f,machfs.File) for _,f in folder.iter_paths())==case['manifest']['file_count']]
                            # Expander places both Hax outputs beside the input folders,
                            # adding .1 to the second root; file counts distinguish them.
                            original_path=('Originals Folder',roots[0])+original_name[1:] if len(roots)==1 else ()
                        elif label=='New':original_path=('Originals Folder','Source Folder')+original_name
                        else:original_path=('Originals Folder',)+original_name
                        found=[f for p,f in allfiles if p==original_path]
                        if len(found)==1:
                            source_file=found[0];original=compare(source_file)
                            original['dates_equal']=all(not a or a==b for a,b in zip(expected_dates,(source_file.crdate,source_file.mddate)))
                            original['type_creator_equal']=not finder or finder[:8]==source_file.type+source_file.creator
                            original['portable_flags_equal']=(source_file.flags&0xfc0e)==portable_flags
                        else:failures.append(dict(case=label,id=row['id'],layer='original extraction',reason='Missing or ambiguous original-tool output'))
                        if original and not (original['data_equal'] and original['reserved_header_only'] and original['resource_records_equal'] and original['dates_equal'] and original['type_creator_equal'] and original['portable_flags_equal']):failures.append(dict(case=label,id=row['id'],layer='original extraction',reason='Fork or supported metadata mismatch',comparison=original))
                    inventory.append(dict(case=label,id=row['id'],restoration=comparison,dates_equal=date_equal,type_creator_equal=type_creator_equal,portable_flags_equal=flags_equal,original=original));matched+=1
        private=PRIVATE/'corpus'/(image+'.inventory.json');private.write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
        results.append(dict(target=target,expander='5.5',compared_files=matched,passed=not failures,failures=failures,inventory_sha256=sha(private)))
    record=dict(passed=all(r['passed'] for r in results),targets=results,original_archives_unchanged=True,worker_sha256=sha(ROOT/'dist/Packsmith-preview/workers/packsmith-worker.exe'),
        engine_revision=cases[0]['manifest']['engine_revision'],
        reader_source_sha256=sha(PYDEPS/'machfs/main.py'),
        procedure='Expand Exports.zip, select its five ZIPs with Finder Edit > Select All and drag to Expander 5.5. Expand Originals.zip, then drag Originals Folder to Expander. Shut down before HFS inventory. Original Hax root collisions distinguished by complete file counts.',
        archives=[dict(name=c['name'],archive_sha256=c['source_sha256'],package_sha256=c['package_sha256'],files=c['manifest']['file_count']) for c in cases],
        limitation='Raw resource differences permitted only in bytes 16-255 with independent resource records equal. Private inventories, archives and disk images excluded from Git/releases.')
    evidence=ROOT/'assessment/evidence/beta3';(evidence/'classic-corpus-oracle.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record));raise SystemExit(0 if record['passed'] else 1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify']);p.add_argument('--target',choices=['System 7.6','Mac OS 9']);args=p.parse_args()
    prepare() if args.action=='prepare' else verify(args.target)
