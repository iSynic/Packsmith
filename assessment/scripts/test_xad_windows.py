"""Native Windows bundle tests using shared fixtures and explicit limits."""
import collections
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import run_suite as s

if os.name!='nt':raise SystemExit('Run on native Windows')
arguments=argparse.ArgumentParser();arguments.add_argument('--skip-scale',action='store_true',help='Do not repeat the separately recorded 100k listing timeout');options=arguments.parse_args()
s.RESULTS=[]
OUT=s.ROOT/'evidence'/'windows-first'/'suite.json'
def save():OUT.write_text(json.dumps(s.RESULTS,indent=2)+'\n')
s.save=save
BUNDLE=s.ROOT/'outputs'/'windows-first'/'xad-worker-bundle'
WORKER=BUNDLE/'xad-worker.exe';LSAR=BUNDLE/'lsar.exe'
clean={'PATH':str(Path(os.environ['SystemRoot'])/'System32')}
manifest=json.loads((s.ROOT/'evidence'/'fixture-manifest.json').read_text())
def run(name,args,**kw):return s.run(name,args,env=clean,**kw)
def extract(name,fixture,password='',expect=0,glob=None):
    dest=s.WORK/name;dest.mkdir()
    args=[WORKER,fixture,dest]
    if glob:args.append(glob)
    row,log=run(name,args,password=password,expect=expect)
    return dest,row,log

def fork_details(folder):
    details=[]
    for file in folder.rglob('._*'):
        data=file.read_bytes()
        if len(data)<26 or data[:4]!=struct.pack('>I',0x51607):continue
        for i in range(struct.unpack_from('>H',data,24)[0]):
            kind,offset,size=struct.unpack_from('>III',data,26+i*12)
            payload=data[offset:offset+size]
            if len(payload)!=size:raise RuntimeError('Invalid sidecar extent')
            if kind in (2,9):details.append({'sidecar':file.relative_to(folder).as_posix(),'entry_id':kind,'payload_sha256':hashlib.sha256(payload).hexdigest(),'bytes':size,'finder_type_creator':payload[:8].decode('ascii',errors='replace') if kind==9 else None})
    return details

run('bundle-foundation',[BUNDLE/'foundation-probe.exe'])
row,log=run('bundle-encoding',[BUNDLE/'encoding-probe.exe'])
cases=[json.loads(line) for line in log.splitlines() if line.startswith('{')]
expected_hex=[b'1234567'.hex(),'café'.encode('mac_roman').hex(),'café'.encode('cp1252').hex(),'日本'.encode('cp932').hex(),'café-日本'.encode('utf8').hex(),'日本'.encode('gb18030').hex()]
s.check('encoding-independent-oracle',[x.get('hex') for x in cases[:6]]==expected_hex,{'cases':cases,'expected_hex':expected_hex,'oracle':'Python standard-library codecs'})
for fixture in ('legacy.bin','legacy.hqx','legacy.as','appledouble.zip'):
    dest,row,log=extract('fork-'+fixture,s.F/fixture)
    ok,details=s.verify_sidecar(dest)
    s.check('fork-payloads-'+fixture,ok and row['status']=='pass',details)
    s.check('finder-'+fixture,'TEXTttxt' in details['finder_type_creator'],details)
dest,row,log=extract('compact-pro-data',s.F/'legacy.cpt')
s.check('compact-pro-data-hash',manifest['legacy']['data_sha256'] in s.hashes(dest).values(),{'files':s.hashes(dest),'limit':'Synthetic data-only RLE fixture; no realistic Compact Pro resource-fork claim'})

for password in ('1234567','123456789012'):
    dest,row,log=extract('stuffit-'+str(len(password)),s.F/(password+'.sit.bin'),password)
    hashes=s.hashes(dest)
    linux=json.loads((s.ROOT/'evidence'/'followup-linux-wsl.json').read_text())
    oracle=next(r['details']['files'] for r in linux if r['name']=='xad-head-password-payloads-'+str(len(password)))
    s.check('stuffit-cross-platform-'+str(len(password)),bool(hashes) and sorted(hashes.values())==sorted(oracle.values()),{'windows_files':hashes,'windows_fork_payloads':fork_details(dest),'linux_head_files':oracle,'limit':'Cross-platform data and sidecar-container agreement; decoded fork payloads recorded separately. Not an independent original-application payload oracle.'})
    dest,row,log=extract('stuffit-wrong-'+str(len(password)),s.F/(password+'.sit.bin'),'wrong',expect=1)
    s.check('stuffit-wrong-cleanup-'+str(len(password)),not s.hashes(dest),s.hashes(dest))

for fixture in ('mainstream.zip','small-zip64.zip','mainstream.tar','mainstream.tar.gz'):
    run('list-'+fixture,[LSAR,'-j',s.F/fixture])
    dest,row,log=extract('extract-'+fixture,s.F/fixture)
    expected=manifest['expected_files'] if fixture!='small-zip64.zip' else {'alpha.txt':manifest['expected_files']['alpha.txt']}
    # Enclosing directory is an engine policy; compare payload multiset and record paths.
    s.check('payloads-'+fixture,sorted(s.hashes(dest).values())==sorted(expected.values()),{'files':s.hashes(dest),'expected':expected})
    if fixture.startswith('mainstream.tar'):
        for file in dest.rglob('*'):
            if file.is_file():s.check('mtime-'+fixture+'-'+file.name,abs(file.stat().st_mtime-1577934246)<2,{'mtime':file.stat().st_mtime,'expected':1577934246})
dest,row,log=extract('selected',s.F/'mainstream.zip',glob='nested/beta.bin')
s.check('selected-hash',list(s.hashes(dest).values())==[manifest['expected_files']['nested/beta.bin']],s.hashes(dest))
unicode_archive=s.WORK/'日本-café.zip';shutil.copy2(s.F/'mainstream.zip',unicode_archive)
dest,row,log=extract('日本-café-output',unicode_archive)
s.check('unicode-paths-and-payloads',sorted(s.hashes(dest).values())==sorted(manifest['expected_files'].values()) and any('café-日本.txt' in n for n in s.hashes(dest)),s.hashes(dest))

seven=s.WORK/'mainstream.7z'
run('independent-7z-create',[s.SEVEN,'a','-t7z',seven,'.'],cwd=s.F/'input')
dest,row,log=extract('extract-7z',seven)
s.check('payloads-7z',sorted(s.hashes(dest).values())==sorted(manifest['expected_files'].values()),s.hashes(dest))
for fixture in ('truncated.zip','bad-checksum.zip'):
    run('reject-'+fixture,[LSAR,'-t',s.F/fixture],expect=1)
for fixture in ('legacy.lzh','test_read_format_lha_header3.lzh','test_read_format_lha_lh6.lzh','test_read_format_lha_lh7.lzh','test_read_format_cab_lzx_16bit.cab'):
    run('legacy-integrity-'+fixture,[LSAR,'-t',s.F/fixture])
dest,row,log=extract('lzx-cab',s.F/'test_read_format_cab_lzx_16bit.cab')
s.check('lzx-cab-oracle',any(p.read_bytes()==b'ABABABABABABABAB' for p in dest.rglob('*') if p.is_file()),{'files':s.hashes(dest),'limit':'CAB LZX, not Amiga LZX archive coverage'})

for fixture in ('duplicates.zip','case-collision.zip'):
    dest,row,log=extract('collisions-'+fixture,s.F/fixture)
    with s.zipfile.ZipFile(s.F/fixture) as archive:
        originals=[hashlib.sha256(archive.read(info)).hexdigest() for info in archive.infolist() if not info.is_dir()]
    s.check('preserve-collisions-'+fixture,collections.Counter(s.hashes(dest).values())==collections.Counter(originals),{'output_files':s.hashes(dest),'expected_payload_hashes':originals,'limit':'Bare always-overwrite probe; product must provide entry-ID/output-mapping collision policy'})
for fixture in ('relative-escape.zip','links.tar'):
    sandbox=s.WORK/('containment-'+fixture);sandbox.mkdir();dest=sandbox/'dest';dest.mkdir()
    run('bounded-containment-'+fixture,[WORKER,s.F/fixture,dest],expect=1 if fixture=='links.tar' else 0)
    outside=[str(p.relative_to(sandbox)) for p in sandbox.rglob('*') if p.is_file() and not p.is_relative_to(dest)]
    s.check('bounded-no-escape-'+fixture,not outside,{'outside':outside,'files':s.hashes(dest),'limit':'Bounded fixtures; reparse races, reserved names and long paths remain unverified'})
blocked=s.WORK/'blocked-destination';blocked.write_bytes(b'destination sentinel')
run('write-failure',[WORKER,s.F/'mainstream.zip',blocked],expect=1)
s.check('write-failure-preserves-sentinel',blocked.read_bytes()==b'destination sentinel',{'limit':'File-as-directory rejection, not disk-full injection'})
run('large-5g-integrity',[LSAR,'-t',s.F/'large-5g.zip'],timeout=180)
original=s.digest(s.F/'large-5g.zip');dest=s.WORK/'terminated-extraction';dest.mkdir()
run('terminate-extraction',[WORKER,s.F/'large-5g.zip',dest],kill_after=.08,expect=1)
s.check('termination-source-unchanged',s.digest(s.F/'large-5g.zip')==original,{'partial_outputs':s.hashes(dest),'limit':'Forced termination leaves a partial destination; product extraction staging and cleanup are pending'})
if options.skip_scale:s.skip('scale-100k-list','Earlier native run retained in suite-before-encoding-fix.json; no repeated benchmark after password-encoding fix')
else:run('scale-100k-list',[LSAR,'-j',s.F/'scale-100k.zip'],timeout=180)
s.skip('clean-machine-install','Sanitized PATH on this development host only; no fresh VM/runner')
s.skip('realistic-legacy-corpus','StuffIt X, realistic Compact Pro forks and Amiga LZX require independently verified corpus')
s.skip('production-safety-and-gui','Worker is an assessment probe; entry-ID mappings, secure containment, cooperative cancel, recovery and native GUI integration are pending')
save()
print(collections.Counter(r['status'] for r in s.RESULTS))
