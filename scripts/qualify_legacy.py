"""Read-only local archive qualification; extracted private payloads stay in ignored outputs."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import time
import tempfile

import psutil

ROOT=Path(__file__).resolve().parents[1]
XAD_REV='7cb9ee0abbb163f261e4cb74501e15067032319c'
DETECTOR_REV='4eb832d999628edcd3d134e46bd35357c8c99a85'

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def apple_double(path):
    raw=path.read_bytes()
    if len(raw)<26 or struct.unpack_from('>II',raw)!=(0x00051607,0x00020000):raise ValueError('Invalid AppleDouble header')
    count=struct.unpack_from('>H',raw,24)[0];result={}
    for index in range(count):
        kind,offset,size=struct.unpack_from('>III',raw,26+12*index)
        if kind in result or offset<26+12*count or offset+size>len(raw):raise ValueError('Invalid AppleDouble extent')
        result[kind]=raw[offset:offset+size]
    return result

def job(worker,request,env,timeout):
    started=time.perf_counter();peak=0
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as error:
        proc=subprocess.Popen([str(worker)],stdin=subprocess.PIPE,stdout=output,stderr=error,env=env)
        proc.stdin.write((json.dumps(request)+'\n').encode('utf-8'));proc.stdin.flush();proc.stdin.close()
        handle=psutil.Process(proc.pid)
        while proc.poll() is None:
            try:peak=max(peak,handle.memory_info().rss+sum(p.memory_info().rss for p in handle.children(recursive=True)))
            except psutil.Error:pass
            if time.perf_counter()-started>timeout:
                proc.kill();proc.wait();raise TimeoutError('Qualification worker exceeded time limit')
            time.sleep(.02)
        output.seek(0);events=[json.loads(line) for line in output.read().splitlines()]
        error.seek(0);stderr=error.read().decode('utf-8',errors='replace')
    terminal=[event for event in events if event.get('event') in ('complete','error','cancelled')]
    if len(terminal)!=1:raise ValueError('Missing or duplicate terminal event')
    return dict(exit_code=proc.returncode,elapsed_ms=round((time.perf_counter()-started)*1000,2),peak_worker_tree_rss=peak,
                terminal=terminal[0],stderr=stderr),events

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus',type=Path,default=Path('F:/Unarchiver'))
    parser.add_argument('--worker',type=Path,default=ROOT/'dist/Packsmith-preview/workers/packsmith-worker.exe')
    parser.add_argument('--timeout',type=int,default=300)
    parser.add_argument('--names',nargs='*',help='Exact filenames; default is every top-level .sit/.hqx/.bin')
    args=parser.parse_args();worker=args.worker.resolve();corpus=args.corpus.resolve()
    run=time.strftime('%Y%m%dT%H%M%S');private=ROOT/'assessment/outputs/beta4-corpus'/run;private.mkdir(parents=True)
    evidence=ROOT/'assessment/evidence/beta4';evidence.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    for name in ('QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','QTDIR'):env.pop(name,None)
    spec=importlib.util.spec_from_file_location('check_binhex',ROOT/'assessment/scripts/check_binhex.py')
    binhex=importlib.util.module_from_spec(spec);spec.loader.exec_module(binhex)
    paths=[corpus/name for name in args.names] if args.names else sorted(p for p in corpus.iterdir() if p.is_file() and p.suffix.lower() in ('.sit','.hqx','.bin'))
    records=[]
    for index,path in enumerate(paths):
        before=sha(path);record=dict(name=path.name,archive_sha256=before,archive_bytes=path.stat().st_size,
            provenance='User-owned local archive; redistribution permission unknown; payload excluded from source/release',
            fidelity_oracle='unverified: output bytes checked against decoder stream hashes; no original Mac extraction oracle')
        destination=private/str(index);destination.mkdir()
        rows=[]
        try:
            request=dict(operation='list',archive=str(path))
            listed,events=job(worker,request,env,args.timeout);record['listing']=listed
            rows=[row for event in events if event.get('event')=='entries' for row in event['items']]
            record['logical_entries']=len(rows)
            record['methods']=sorted({str(row.get(key,'unknown')) for row in rows for key,presence in (('data_method','has_data'),('resource_method','has_resource')) if row.get(presence) and not row['directory']})
            record['format']=listed['terminal'].get('format');record['outer_format']=listed['terminal'].get('checksum_coverage',{}).get('outer_format')
            (destination/'listing.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
            if path.suffix.lower()=='.hqx':record['independent_binhex']=binhex.inspect(path)
            if listed['exit_code']!=0:raise ValueError('Listing failed')
            extracted,events=job(worker,dict(operation='extract',archive=str(path),destination=str(destination),selection_scope='all',fingerprint=listed['terminal']['fingerprint']),env,args.timeout)
            record['extraction']=extracted
            record['warnings']=[event['message'] for event in events if event['event']=='warning']
            if extracted['exit_code']!=0:raise ValueError('Extraction failed')
            end=extracted['terminal'];root=Path(end['output']);mapping=json.loads((root/end['mapping']).read_text(encoding='utf-8'))
            if {entry['id'] for entry in mapping['entries']}!={row['id'] for row in rows}:raise ValueError('Missing logical entry')
            data_forks=resource_forks=empty_data=0
            inventory=[]
            for entry in mapping['entries']:
                row=rows[entry['id']];target=root/entry['output'];receipt=dict(entry)
                if row['directory']:
                    if not target.is_dir():raise ValueError('Missing directory')
                else:
                    if target.stat().st_size!=int(row['size']):raise ValueError('Data size mismatch')
                    digest=sha(target);receipt['exported_data_sha256']=digest
                    if row['has_data']:
                        data_forks+=1
                        if digest!=entry['data_sha256']:raise ValueError('Data payload differs from stream hash')
                    if target.stat().st_size==0:empty_data+=1
                if 'sidecar' in entry:
                    forks=apple_double(root/entry['sidecar'])
                    finder=base64.b64decode(row['finder_info'])
                    if finder and forks.get(9)!=finder:raise ValueError('Finder metadata mismatch')
                    if row['has_resource']:
                        resource_forks+=1;payload=forks[2]
                        if len(payload)!=int(row['resource_size']) or hashlib.sha256(payload).hexdigest()!=entry['resource_sha256']:raise ValueError('Resource payload differs from stream hash')
                    receipt['finder_info_hex']=forks.get(9,b'').hex()
                inventory.append(receipt)
            inventory_path=destination/'fork-inventory.json';inventory_path.write_text(json.dumps(inventory,indent=2)+'\n',encoding='utf-8')
            record.update(data_forks=data_forks,resource_forks=resource_forks,empty_data_files=empty_data,
                fork_inventory_sha256=sha(inventory_path),private_inventory=str(inventory_path.relative_to(ROOT)),
                checksum_coverage=end['checksum_coverage'],passed=True)
        except Exception as error:
            record.update(passed=False,failure=str(error))
        record['original_unchanged']=sha(path)==before
        record['passed']=record.get('passed',False) and record['original_unchanged']
        records.append(record)
        result=dict(xad_revision=XAD_REV,detector_revision=DETECTOR_REV,worker_sha256=sha(worker),decoder_sha256=sha(worker.parent/'legacy/xad-stream.exe'),
            environment='Native Windows developer machine, private corpus; no original Mac extraction oracle',records=records)
        (evidence/'legacy-corpus.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(f"{path.name}: {'pass' if record['passed'] else 'FAIL'}; {len(rows)} entries",flush=True)
    print(f"{sum(r['passed'] for r in records)}/{len(records)} passed; private outputs: {private}",flush=True)
    # Corpus failures are evidence; they must remain visible without pretending every archive is supported.
    raise SystemExit(0 if all(r['passed'] for r in records) else 1)

if __name__=='__main__':main()
