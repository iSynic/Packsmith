"""Verify unpublished committed assets without modifying authored receipts."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'dist/candidates/v0.1.0-beta.4'
record=json.loads((out/'release-manifest.json').read_text(encoding='utf-8'))
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
assert record['source_commit']==commit and record['candidate'] and record['tag'] is None and not record['workspace_dirty']
assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(),'Committed candidate requires a clean authored tree'
assets={row['name']:row for row in record['assets']}
for name,row in assets.items():
    path=out/name
    assert path.stat().st_size==row['bytes']
    with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
    with zipfile.ZipFile(path) as z:assert z.testzip() is None
binary=next(out.glob('*windows-x64.zip'));source=next(out.glob('*source-materials.zip'))
with zipfile.ZipFile(binary) as z:
    package=json.loads(z.read('Packsmith/package-manifest.json'))
    for row in package['files']:assert hashlib.sha256(z.read('Packsmith/'+row['path'].replace('\\','/'))).hexdigest()==row['sha256']
    assert not any('Qt6Test' in name or 'test-runtime' in name or name.endswith(('.hfv','.dsk','.ROM','.sit','.hqx','.cpt','.lzx')) for name in z.namelist())
with zipfile.ZipFile(source) as z:
    prefix=z.namelist()[0].split('/')[0]+'/'
    materials=json.loads(z.read(prefix+'source-materials.json'));assert materials['source_commit']==commit
    manifest=json.loads(z.read(prefix+'materials-manifest.json'))
    for name,digest in manifest.items():assert hashlib.sha256(z.read(prefix+name)).hexdigest()==digest,name
    with tarfile.open(fileobj=io.BytesIO(z.read(prefix+'Packsmith-source.tar.gz')),mode='r:gz') as archive:
        files={m.name.removeprefix('Packsmith/'):archive.extractfile(m).read() for m in archive if m.isfile()}
    tree=subprocess.check_output(['git','ls-tree','-rz','HEAD'],cwd=ROOT).split(b'\0')
    blobs={row.split(b'\t',1)[1].decode():row.split()[2].decode() for row in tree if row}
    assert set(files)==set(blobs),'Source snapshot file set differs from HEAD'
    for name,data in files.items():assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==blobs[name],name
    for name,digest in package['authored_sources'].items():assert hashlib.sha256(files[name.replace('\\','/')]).hexdigest()==digest,'Binary source differs from committed source: '+name
    for name in files:
        assert not name.startswith(('assessment/outputs/','assessment/tools/','assessment/downloads/','dist/','build/','source/'))
        assert not name.lower().endswith(('.hfv','.dsk','.rom','.sit','.hqx','.cpt','.lzx'))
for line in (out/'SHA256SUMS.txt').read_text().splitlines():
    digest,name=line.split('  ',1)
    with (out/name).open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==digest
result=dict(passed=True,source_commit=commit,zip_integrity=True,matching_corresponding_sources=True,private_payloads_excluded=True,source_files=len(files),materials_files=len(manifest),assets=list(assets))
private=ROOT/'assessment/outputs/beta4';private.mkdir(parents=True,exist_ok=True)
(private/'candidate-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
