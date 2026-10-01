"""Exercise pinned engines, record receipts, and never equate skips with passes."""
import binascii
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import threading
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PLATFORM='windows' if os.name=='nt' else 'linux-wsl'
WORK=ROOT/'outputs'/PLATFORM if os.name=='nt' else Path('/home/riceric/unarchiver-assessment-20260930/suite')
WORK=WORK/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%f')
WORK.mkdir(parents=True,exist_ok=True)
F=ROOT/'outputs'/'fixtures'
RAW=ROOT/'outputs'/'raw'/PLATFORM/WORK.name;RAW.mkdir(parents=True,exist_ok=True)
RESULTS=[]
if os.name=='nt':
    SEVEN=ROOT/'tools'/'sevenzip-full'/'7z.exe';NATIVE=ROOT/'experiments'/'native-probe.exe'
    BSDTAR=ROOT/'experiments'/'libarchive-windows-build'/'bin'/'bsdtar.exe'
    BASE=None
    os.environ['PATH']=r'C:\msys64\mingw64\bin'+os.pathsep+os.environ['PATH']
else:
    BASE=Path('/home/riceric/unarchiver-assessment-20260930')
    SEVEN=BASE/'sevenzip'/'7zz';NATIVE=BASE/'native-probe';BSDTAR=BASE/'libarchive-build'/'bin'/'bsdtar'

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as file:
        while chunk:=file.read(1024*1024):h.update(chunk)
    return h.hexdigest()

def run(name,args,password='',cwd=None,env=None,expect=0,kill_after=None,timeout=180):
    log=RAW/(name+'.log');start=time.monotonic();peak=0
    actual_env=os.environ.copy();actual_env.update(env or {})
    with log.open('wb') as out:
        process=subprocess.Popen([str(a) for a in args],stdin=subprocess.PIPE,stdout=out,stderr=subprocess.STDOUT,cwd=cwd,env=actual_env)
        def sample():
            nonlocal peak
            while process.poll() is None:
                try:
                    if os.name=='nt':
                        import psutil
                        peak=max(peak,psutil.Process(process.pid).memory_info().rss)
                    else:
                        for line in Path(f'/proc/{process.pid}/status').read_text().splitlines():
                            if line.startswith('VmRSS:'):peak=max(peak,int(line.split()[1])*1024)
                except (OSError,ProcessLookupError):pass
                except Exception:pass
                time.sleep(.005)
        thread=threading.Thread(target=sample);thread.start()
        timer=None;kill_requested=[]
        if kill_after is not None:
            def kill():
                if process.poll() is None:
                    kill_requested.append(time.monotonic());process.kill()
            timer=threading.Timer(kill_after,kill);timer.start()
        timed_out=False
        try:process.communicate((password+'\n').encode(),timeout=timeout)
        except subprocess.TimeoutExpired:timed_out=True;process.kill();process.communicate()
        finished=time.monotonic()
        if timer:timer.cancel()
        thread.join()
    success=process.returncode==0 if expect==0 else process.returncode!=0
    abnormal=process.returncode<0 or (os.name=='nt' and process.returncode>=0x80000000)
    if timed_out or (abnormal and not kill_requested):success=False
    row={'name':name,'platform':PLATFORM,'command':[str(a) for a in args],'cwd':str(cwd or Path.cwd()),'exit_code':process.returncode,'expected':'success' if expect==0 else 'rejection','status':'pass' if success else 'fail','elapsed_seconds':round(finished-start,4),'peak_rss_bytes_sampled':peak,'raw_log':str(log.relative_to(ROOT)),'termination_latency_ms':round((finished-kill_requested[0])*1000,3) if kill_requested else None,'termination_requested':bool(kill_requested)}
    RESULTS.append(row);save()
    print(f'{PLATFORM}: {name} {row["status"]} ({row["elapsed_seconds"]}s)',flush=True)
    return row,log.read_text(errors='replace')

def check(name,ok,details):
    RESULTS.append({'name':name,'platform':PLATFORM,'status':'pass' if ok else 'fail','details':details});save()

def skip(name,reason):
    RESULTS.append({'name':name,'platform':PLATFORM,'status':'unverified','reason':reason});save()

def save():
    (ROOT/'evidence'/f'suite-{PLATFORM}.json').write_text(json.dumps(RESULTS,indent=2)+'\n')

def hashes(folder):
    return {p.relative_to(folder).as_posix():digest(p) for p in folder.rglob('*') if p.is_file()}

def verify_sidecar(folder):
    expected=json.loads((ROOT/'evidence'/'fixture-manifest.json').read_text())['legacy']
    payloads={};finder=[]
    for file in folder.rglob('*'):
        if not file.is_file():continue
        data=file.read_bytes()
        if len(data)>26 and data[:4]==struct.pack('>I',0x51607):
            count=struct.unpack_from('>H',data,24)[0]
            for i in range(count):
                kind,offset,size=struct.unpack_from('>III',data,26+12*i)
                if kind==2:payloads[file.name]=hashlib.sha256(data[offset:offset+size]).hexdigest()
                if kind==9:finder.append(data[offset:offset+8].decode('ascii',errors='replace'))
    data_ok=any(digest(p)==expected['data_sha256'] for p in folder.rglob('*') if p.is_file() and not p.name.startswith('._'))
    return data_ok and expected['resource_sha256'] in payloads.values(),{'data_matches':data_ok,'resource_hashes':payloads,'finder_type_creator':finder}

def engine_matrix():
    valid=['mainstream.zip','small-zip64.zip','mainstream.tar','mainstream.tar.gz','legacy.lzh','test_read_format_lha_lh6.lzh','test_read_format_lha_lh7.lzh','test_read_format_cab_lzx_16bit.cab']
    engines={'sevenzip':lambda f:[SEVEN,'t',f], 'libarchive':lambda f:[NATIVE,'archive-test',f]}
    if BASE:
        engines['xad-stable']=lambda f:[BASE/'xad-stable'/'XADMaster'/'lsar','-t',f]
        engines['xad-head']=lambda f:[BASE/'xad-head'/'XADMaster'/'lsar','-t',f]
    for name,command in engines.items():
        for fixture in valid:run(name+'-read-'+fixture,command(F/fixture))
    for name,command in [('libzip',lambda f:[NATIVE,'zip-test',f]),*engines.items()]:
        for fixture in ('truncated.zip','bad-checksum.zip'):
            run(name+'-reject-'+fixture,command(F/fixture),expect=1)
    for name,op in [('libzip','zip'),('libarchive','archive')]:
        destination=WORK/(name+'-selected.bin')
        run(name+'-selected-extract',[NATIVE,op+'-extract',F/'mainstream.zip',destination,'nested/beta.bin'])
        expected=json.loads((ROOT/'evidence'/'fixture-manifest.json').read_text())['expected_files']['nested/beta.bin']
        check(name+'-selected-hash',destination.exists() and digest(destination)==expected,{'expected_sha256':expected})
    output=WORK/'seven-selected';output.mkdir(exist_ok=True)
    run('sevenzip-selected-extract',[SEVEN,'x',F/'mainstream.zip','nested/beta.bin','-o'+str(output),'-y'])
    check('sevenzip-selected-hash',hashes(output)=={'nested/beta.bin':json.loads((ROOT/'evidence'/'fixture-manifest.json').read_text())['expected_files']['nested/beta.bin']},hashes(output))

def creation_and_updates():
    expected=json.loads((ROOT/'evidence'/'fixture-manifest.json').read_text())['expected_files']
    for ext in ('zip','7z','tar','tar.gz'):
        path=WORK/('created.'+ext)
        path.unlink(missing_ok=True)
        if ext=='tar.gz':
            run('sevenzip-create-tar.gz',[SEVEN,'a','-tgzip',path,WORK/'created.tar'])
        else:run('sevenzip-create-'+ext,[SEVEN,'a','-t'+ext,path,'.'],cwd=F/'input')
        run('libarchive-read-created-'+ext,[NATIVE,'archive-test',path])
        if ext=='zip':
            with zipfile.ZipFile(path) as z:check('python-verify-created-zip',{n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith('/')}==expected,{'oracle':'Python zipfile'})
        if ext=='7z':
            run('sevenzip-solid-property',[SEVEN,'l','-slt',path])
        destination=WORK/('created-output-'+ext);destination.mkdir(exist_ok=True)
        run('libarchive-extract-created-'+ext,[BSDTAR,'-xf',path,'-C',destination])
        check('created-payloads-'+ext,hashes(destination)==expected,hashes(destination))
    for ext in ('tar','tar.gz'):
        path=WORK/('libarchive-created.'+ext)
        run('libarchive-create-'+ext,[BSDTAR,'-czf' if ext=='tar.gz' else '-cf',path,'-C',F/'input','.'])
        run('sevenzip-verify-libarchive-created-'+ext,[SEVEN,'t',path])
    encrypted=WORK/'libzip-encrypted.zip';encrypted.unlink(missing_ok=True)
    run('libzip-create-encrypted',[NATIVE,'zip-create',encrypted],password='assessment-fixture-password')
    run('libzip-correct-password',[NATIVE,'zip-test',encrypted],password='assessment-fixture-password')
    run('libzip-wrong-password',[NATIVE,'zip-test',encrypted],password='wrong',expect=1)
    run('libarchive-correct-password',[NATIVE,'archive-test',encrypted],password='assessment-fixture-password')
    run('libarchive-wrong-password',[NATIVE,'archive-test',encrypted],password='wrong',expect=1)
    plain=WORK/'libzip-created.zip';plain.unlink(missing_ok=True)
    run('libzip-create',[NATIVE,'zip-create',plain])
    with zipfile.ZipFile(plain) as z:check('python-verify-libzip-create',z.read('alpha.txt')==b'alpha\n',{'oracle':'Python zipfile'})
    edited=WORK/'libzip-edited.zip';shutil.copyfile(F/'mainstream.zip',edited)
    run('libzip-edit',[NATIVE,'zip-edit',edited])
    with zipfile.ZipFile(edited) as z:
        check('python-verify-libzip-edit',set(z.namelist())=={'alpha.txt','added.txt','renamed.txt'} and z.read('alpha.txt')==b'replacement\n' and z.read('added.txt')==b'added\n',{'entries':z.namelist(),'oracle':'Python zipfile'})
    original=WORK/'libzip-cancelled.zip';shutil.copyfile(F/'mainstream.zip',original);before=digest(original)
    run('libzip-cancel-edit',[NATIVE,'zip-edit',original],env={'ASSESSMENT_CANCEL':'1'},expect=1)
    check('libzip-cancel-original-intact',digest(original)==before,{'before_sha256':before,'after_sha256':digest(original)})
    updates=WORK/'updates';updates.mkdir(exist_ok=True);(updates/'alpha.txt').write_bytes(b'replacement\n');(updates/'added.txt').write_bytes(b'added\n')
    for ext in ('zip','7z'):
        path=WORK/('sevenzip-edited.'+ext);shutil.copyfile(WORK/('created.'+ext),path)
        run('sevenzip-update-'+ext,[SEVEN,'u',path,'alpha.txt','added.txt'],cwd=updates)
        run('sevenzip-delete-'+ext,[SEVEN,'d',path,'nested/beta.bin'])
        run('sevenzip-rename-'+ext,[SEVEN,'rn',path,'unicode/caf\u00e9-\u65e5\u672c.txt','renamed.txt'])
        run('libarchive-verify-sevenzip-edit-'+ext,[NATIVE,'archive-test',path])
        out=WORK/('sevenzip-edit-output-'+ext);out.mkdir(exist_ok=True)
        run('libarchive-extract-sevenzip-edit-'+ext,[BSDTAR,'-xf',path,'-C',out])
        found=hashes(out);want={'alpha.txt':hashlib.sha256(b'replacement\n').hexdigest(),'added.txt':hashlib.sha256(b'added\n').hexdigest(),'renamed.txt':expected['unicode/caf\u00e9-\u65e5\u672c.txt']}
        check('sevenzip-edit-payloads-'+ext,{n:h for n,h in found.items() if not n.endswith('/')}==want,found)
    split=WORK/'split.7z'
    run('sevenzip-create-split',[SEVEN,'a','-t7z','-v256b',split,F/'input'/'nested'/'beta.bin'])
    first=WORK/'split.7z.001'
    run('sevenzip-read-split',[SEVEN,'t',first])
    parts=sorted(WORK.glob('split.7z.*'))
    if len(parts)>1:
        missing=WORK/'missing';missing.mkdir(exist_ok=True)
        for part in parts[:-1]:shutil.copyfile(part,missing/part.name)
        run('sevenzip-reject-missing-volume',[SEVEN,'t',missing/first.name],expect=1)
    else:skip('sevenzip-reject-missing-volume','Fixture did not span multiple volumes')

def filesystem_cases():
    for engine in ('sevenzip','libarchive'):
        args=[SEVEN,'l','-slt',F/'unsafe-paths.zip'] if engine=='sevenzip' else [NATIVE,'archive-list',F/'unsafe-paths.zip']
        run(engine+'-list-absolute-and-drive-paths',args)
        for fixture in ('relative-escape.zip','links.tar','case-collision.zip','duplicates.zip','windows-names.zip'):
            sandbox=WORK/(engine+'-'+fixture+'-sandbox');sandbox.mkdir(exist_ok=True)
            out=sandbox/'dest';out.mkdir(exist_ok=True)
            args=[SEVEN,'x',F/fixture,'-o'+str(out),'-y'] if engine=='sevenzip' else [BSDTAR,'-xf',F/fixture,'-C',out]
            expected_rejection=fixture=='links.tar' or (engine=='libarchive' and fixture=='relative-escape.zip')
            row,log=run(engine+'-fs-'+fixture,args,expect=1 if expected_rejection else 0)
            outside=[str(p.relative_to(sandbox)) for p in sandbox.rglob('*') if p.is_file() and not p.is_relative_to(out)]
            check(engine+'-containment-'+fixture,not outside,{'outside_files':outside,'output_files':hashes(out),'note':'Observed sandbox only; not a complete destination/symlink/reparse-point security audit'})
            if fixture in ('case-collision.zip','duplicates.zip'):
                expected_count=2 if fixture=='case-collision.zip' else 2
                check(engine+'-collision-preservation-'+fixture,len(hashes(out))==expected_count,{'files':hashes(out),'required_application_behavior':'Resolve collisions explicitly before extracting; preserve every selected payload'})
        destination=WORK/(engine+'-write-failure');destination.write_bytes(b'not a directory')
        args=[SEVEN,'x',F/'mainstream.zip','-o'+str(destination),'-y'] if engine=='sevenzip' else [BSDTAR,'-xf',F/'mainstream.zip','-C',destination]
        run(engine+'-write-failure',args,expect=1)

def legacy():
    if not BASE:
        skip('xad-windows-legacy','No demonstrated Windows GNUstep/XADMaster build');return
    for version in ('baseline','stable','head'):
        probe=BASE/f'xad-{version}-probe'
        if not probe.exists():skip('xad-'+version,'Engine/probe build unavailable');continue
        for fixture in ('legacy.bin','legacy.hqx','legacy.as','legacy.cpt','legacy.lzh','appledouble.zip'):
            out=WORK/(version+'-'+fixture);out.mkdir(exist_ok=True)
            run('xad-'+version+'-'+fixture,[probe,F/fixture,out])
            if fixture in ('legacy.bin','legacy.hqx','legacy.as','appledouble.zip'):
                ok,details=verify_sidecar(out);check('xad-'+version+'-forks-'+fixture,ok,details)
        if version!='baseline':
            for password in ('1234567','123456789012'):
                filename=password+'.sit.bin';out=WORK/(version+'-'+filename);out.mkdir(exist_ok=True)
                row,_=run('xad-'+version+'-stuffit-'+str(len(password)),[probe,F/filename,out],password=password)
                check('xad-'+version+'-stuffit-payloads-'+str(len(password)),row['status']=='pass' and any(p.stat().st_size>0 for p in out.rglob('*') if p.is_file() and not p.name.startswith('._')),{'files':hashes(out),'limit':'No independent original-application oracle for imported StuffIt payloads'})
                wrong=WORK/(version+'-wrong-'+filename);wrong.mkdir(exist_ok=True)
                run('xad-'+version+'-stuffit-wrong-'+str(len(password)),[probe,F/filename,wrong],password='wrong',expect=1)
                check('xad-'+version+'-wrong-password-cleanup-'+str(len(password)),not hashes(wrong),{'remaining_files':hashes(wrong)})
    skip('amiga-lzx-archive','CAB LZX fixture exercises a different container; no independently verified Amiga LZX archive fixture available')
    skip('stuffit-x-oracle','No independently verified StuffIt X archive with known payload/fork hashes available')

def scale():
    run('sevenzip-list-100k',[SEVEN,'l','-slt',F/'scale-100k.zip'])
    run('libzip-list-100k',[NATIVE,'zip-list',F/'scale-100k.zip'])
    run('libarchive-list-100k',[NATIVE,'archive-list',F/'scale-100k.zip'])
    if BASE:run('xad-stable-list-100k',[BASE/'xad-stable'/'XADMaster'/'lsar','-j',F/'scale-100k.zip'])
    large=F/'large-5g.zip'
    if not large.exists():
        block=b'\0'*(1024*1024)
        temporary=large.with_suffix('.zip.tmp')
        with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
            with z.open('zeros.bin','w',force_zip64=True) as out:
                for _ in range(5121):out.write(block)
        temporary.replace(large)
        manifest=json.loads((ROOT/'evidence'/'fixture-manifest.json').read_text())
        manifest['archives'][large.name]={'sha256':digest(large),'bytes':large.stat().st_size,'uncompressed_bytes':5121*1024*1024,'expected_payload':'5121 MiB of zero bytes; CRC verified by readers'}
        (ROOT/'evidence'/'fixture-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name,args in [('sevenzip',[SEVEN,'t',large]),('libzip',[NATIVE,'zip-test',large]),('libarchive',[NATIVE,'archive-test',large])]:run(name+'-read-5g',args,timeout=240)
    row,_=run('native-worker-termination',[NATIVE,'zip-test',large],expect=1,kill_after=.05)
    check('worker-termination-observed',row['termination_requested'],{'termination_latency_ms':row['termination_latency_ms']})
    before=digest(F/'mainstream.zip');staged=WORK/'staged-update.zip';shutil.copyfile(F/'mainstream.zip',staged)
    shutil.copyfile(F/'mainstream.zip',WORK/'original-for-update.zip')
    run('staged-update-failure',[NATIVE,'zip-edit',staged],env={'ASSESSMENT_CANCEL':'1'},expect=1)
    check('staged-original-preserved',digest(WORK/'original-for-update.zip')==before,{'note':'Isolated staging experiment, not a production transaction implementation'})

if __name__=='__main__':
    run('native-versions',[NATIVE,'versions','unused'])
    run('sevenzip-version',[SEVEN,'i'])
    engine_matrix();creation_and_updates();filesystem_cases();legacy();scale()
    for name,reason in [('macos-native','No macOS executor available'),('linux-desktop','WSL engine and Qt offscreen evidence does not establish native X11/Wayland desktop behavior'),('accessibility','No screen-reader/keyboard acceptance run on product GUI'),('disk-full','Write failure tested; actual bounded ENOSPC fault injection not performed'),('windows-reparse','No complete native reparse-point race test'),('native-resource-forks','macOS filesystem unavailable')]:skip(name,reason)
    print(json.dumps({status:sum(r['status']==status for r in RESULTS) for status in ('pass','fail','unverified')}))
