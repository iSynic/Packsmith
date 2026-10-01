"""Manifest-driven read-only qualification; all payloads stay in ignored outputs."""
import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import coverage_fixtures

def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()

def job(worker,operation,path,**extra):
    env=os.environ.copy();env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    result=subprocess.run([str(worker)],input=json.dumps(dict(operation=operation,archive=str(path),**extra))+'\n',capture_output=True,text=True,encoding='utf-8',env=env,timeout=120)
    events=[json.loads(line) for line in result.stdout.splitlines()]
    assert events and len([e for e in events if e['event'] in ('complete','error','cancelled')])==1
    return result.returncode,events

def macbinary(raw):
    assert len(raw)>=128 and raw[0]==0 and raw[122:124]==b'\x81\x81'
    assert binascii.crc_hqx(raw[:124],0)==struct.unpack_from('>H',raw,124)[0]
    data,resource=struct.unpack_from('>II',raw,83);end=128+((data+127)&~127)
    assert len(raw)==end+((resource+127)&~127)
    assert not any(raw[128+data:end]) and not any(raw[end+resource:])
    return hashlib.sha256(raw[128:128+data]).hexdigest(),hashlib.sha256(raw[end:end+resource]).hexdigest()

def qualify(case,worker,folder):
    path=(ROOT/case['path']).resolve();before=sha(path);assert before==case['archive_sha256'],'Fixture hash drift'
    encoding=case.get('filename_encoding');options=dict(filename_encoding=encoding) if encoding else {}
    row=dict(name=case['name'],archive_sha256=before,provenance=case['provenance'],oracle=case['oracle'],filename_encoding=encoding)
    code,events=job(worker,'list',path,**options);entries=[e for event in events for e in event.get('items',[])];row['listing']=events[-1]
    row['formats']=sorted({e.get('format','unknown') for e in entries});row['methods']=sorted({str(e.get(p+'_method','unknown')) for e in entries for p in ('data','resource') if e.get('has_'+p)})
    row['logical_entries']=len(entries)
    row['wrapper_chain']=events[-1].get('checksum_coverage',{}).get('wrapper_chain',[])
    if case.get('expected_format'):assert row['formats']==[case['expected_format']],row['formats']
    if case.get('expected_wrapper_chain'):assert row['wrapper_chain']==case['expected_wrapper_chain'],row['wrapper_chain']
    if code:raise ValueError(events[-1])
    code,test=job(worker,'test',path,**options);row['integrity']=test[-1]
    if case.get('expected_error'):
        assert code and test[-1]['code']==case['expected_error'],test[-1]
        target=folder/'failed-extraction';target.mkdir();rc,ex=job(worker,'extract',path,destination=str(target),selection_scope='all',**options)
        assert rc and not ex[-1].get('output_committed') and not list(target.iterdir()),ex[-1]
        pre=dict(mode='preflight',name_policy='strict',selection_scope='all',fingerprint=before,**options)
        rc,plan=job(worker,'export_classic',path,**pre);assert not rc,plan[-1]
        rc,export=job(worker,'export_classic',path,**dict(pre,mode='execute',plan_digest=plan[-1]['plan']['plan_digest'],destination=str(folder/'must-not-exist.zip')))
        assert rc and not (folder/'must-not-exist.zip').exists(),export[-1]
        assert sha(path)==before,'Original archive changed after failure'
        row.update(passed=True,status='failed/unsupported',expected_failure=True,original_unchanged=True);return row
    assert code==0,test[-1]
    expected=case.get('expected',[])
    if expected:
        if case.get('expected_complete',True): assert len(entries)==len(expected),(len(entries),len(expected))
        for want in expected:
            matches=[entry for entry in entries if entry['components']==want['components']]
            entry=matches[0] if len(matches)==1 else entries[expected.index(want)]
            assert entry['components']==want['components'],(entry,want)
            if 'raw_components' in want:assert entry['raw_components']==want['raw_components'],(entry,want)
    output=folder/'extracted';output.mkdir()
    ids=[entry['id'] for entry in entries if not entry['directory'] and not entry.get('link')]
    if not case.get('expected_complete',True): ids=[entry['id'] for entry in entries if entry['components'] in [e['components'] for e in expected]]
    assert ids,'No eligible files'
    rc,extracted=job(worker,'extract',path,destination=str(output),selection_scope='entries',ids=ids,**options);assert not rc,extracted[-1]
    root=Path(extracted[-1]['output']);mapping=json.loads((root/extracted[-1]['mapping']).read_text(encoding='utf-8'))
    for actual,want in zip(mapping['entries'],expected):
        target=root/actual['output'];assert sha(target)==want['data_sha256']
        if want['resource_sha256']!=hashlib.sha256(b'').hexdigest():
            side=(root/actual['sidecar']).read_bytes();n=struct.unpack_from('>H',side,24)[0]
            for i in range(n):
                kind,offset,size=struct.unpack_from('>III',side,26+i*12)
                if kind==2:assert hashlib.sha256(side[offset:offset+size]).hexdigest()==want['resource_sha256'];break
            else:raise AssertionError('Missing resource fork')
    rc,selected=job(worker,'test',path,ids=[ids[0]],**options);assert not rc,selected[-1]
    pre=dict(mode='preflight',name_policy='strict',selection_scope='entries',ids=ids,fingerprint=before,**options)
    rc,events=job(worker,'export_classic',path,**pre);assert not rc,events[-1];plan=events[-1]['plan']
    target=folder/'Classic.zip'
    rc,events=job(worker,'export_classic',path,**dict(pre,mode='execute',name_policy='mapped' if not plan['strict_allowed'] else 'strict',plan_digest=plan['plan_digest'],destination=str(target)));assert not rc,events[-1]
    with zipfile.ZipFile(target) as z:
        manifest=json.loads(z.read('Report.json'))
        for entry in manifest['entries']:
            if not entry['directory']:assert macbinary(z.read('Files/'+entry['transport_path']))==(entry['data_sha256'],entry['resource_sha256'])
    row.update(passed=True,status=case['oracle']['kind'],checksum_coverage=extracted[-1]['checksum_coverage'],package_sha256=sha(target),original_unchanged=sha(path)==before)
    return row

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path);p.add_argument('--private-manifest',type=Path);p.add_argument('--worker',type=Path,default=ROOT/'dist/Packsmith-preview/workers/packsmith-worker.exe');args=p.parse_args()
    if args.manifest:cases=json.loads(args.manifest.read_text(encoding='utf-8'))['cases']
    else:
        cases=coverage_fixtures.generate()
        for case in cases:
            if case['name']=='unsupported-6.sit':case['expected_error']='unsupported_codec'
            if case['name']=='corrupt-paired.cpt':case['expected_error']='integrity_failed'
    if args.private_manifest:cases+=json.loads(args.private_manifest.read_text(encoding='utf-8'))['cases']
    private=ROOT/'assessment/outputs/beta4-qualification';private.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,case in enumerate(cases):
        import tempfile
        with tempfile.TemporaryDirectory(prefix=str(i)+'-',dir=private) as temporary:
            try:row=qualify(case,args.worker,Path(temporary))
            except Exception as error:row=dict(name=case['name'],passed=False,failure=str(error),status='failed/unsupported')
        rows.append(row);print(case['name']+': '+('PASS' if row['passed'] else 'FAIL '+row['failure']),flush=True)
    receipt=dict(schema=1,xad_revision='7cb9ee0abbb163f261e4cb74501e15067032319c',detector_revision='4eb832d999628edcd3d134e46bd35357c8c99a85',worker_sha256=sha(args.worker),decoder_sha256=sha(args.worker.parent/'legacy/xad-stream.exe'),passed=all(r['passed'] for r in rows),cases=rows)
    out=ROOT/'assessment/evidence/beta4';out.mkdir(parents=True,exist_ok=True);(out/'classic-qualification.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if receipt['passed'] else 1)

if __name__=='__main__':main()
