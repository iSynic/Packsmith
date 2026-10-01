"""Private classic-Mac qualification setup; no ROMs or software enter release materials."""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'assessment/outputs/beta3-oracle'
PYDEPS = Path('F:/Divinity - Codex/emulator-local/tools/pydeps')

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def macbinary(name, data, resource, created=3000000000, modified=3000000100):
    name = name.encode('mac_roman')
    header = bytearray(128)
    header[1] = len(name); header[2:2+len(name)] = name
    header[65:73] = b'TEXTttxt'
    struct.pack_into('>IIII', header, 83, len(data), len(resource), created, modified)
    header[122:124] = bytes([129,129])
    struct.pack_into('>H', header, 124, binascii.crc_hqx(header[:124], 0))
    return header + data + bytes((-len(data)) % 128) + resource + bytes((-len(resource)) % 128)

def volume(path):
    import machfs
    result = machfs.Volume(); result.read(Path(path).read_bytes()); return result

def prepare():
    sys.path.insert(0, str(PYDEPS))
    import machfs
    PRIVATE.mkdir(parents=True, exist_ok=True)
    inputs = PRIVATE / 'inputs'; inputs.mkdir(exist_ok=True)
    from macresources import make_file, Resource
    resource = make_file([Resource(b'TEST',128,data=b'Known independent resource payload')])
    cases = [('Data only', b'Known data\0\xff', b''), ('Resource only', b'', resource), ('café', b'Data and resource', resource)]
    expected = []
    for index,(name,data,fork) in enumerate(cases):
        folder = inputs / ('Nested' if index == 2 else '')
        folder.mkdir(exist_ok=True)
        path = folder / f'F{index:06}.bin'; path.write_bytes(macbinary(name,data,fork))
        expected.append(dict(name=name, folder='Nested' if index==2 else '', data_sha256=hashlib.sha256(data).hexdigest(), resource_sha256=hashlib.sha256(fork).hexdigest(),created=3000000000,modified=3000000100))
    archive = PRIVATE / 'Transfer.zip'
    if not archive.exists():
        request=dict(operation='create',archive=str(archive),format='zip',files=[str(p) for p in inputs.iterdir()])
        result=subprocess.run([str(ROOT/'dist/Packsmith-preview/workers/packsmith-worker.exe')],input=json.dumps(request)+'\n',capture_output=True,text=True,check=True)
        (PRIVATE/'zip-build-events.jsonl').write_text(result.stdout,encoding='utf-8')
    tools=volume('C:/Sheepshaver/250MB.dsk')
    expander=tools[('Applications','StuffIt Deluxe 7.0.3','StuffIt Drag and Drop','StuffIt Expander')]
    from macresources import parse_file
    versions=[r.data.hex() for r in parse_file(expander.rsrc) if r.type==b'vers']
    disk=machfs.Volume();disk.name='Packsmith Tests'
    disk['StuffIt Expander']=expander
    f=machfs.File();f.data=archive.read_bytes();f.type=b'ZIP ';f.creator=b'SITx';disk['Transfer.zip']=f
    marker=machfs.File();marker.data=b'Independent HFS known data';marker.rsrc=resource;marker.type=b'TEXT';marker.creator=b'ttxt';marker.crdate=3000000000;marker.mddate=3000000100
    disk['Reader control']=marker
    image=PRIVATE/'Tests.hfv'
    if not image.exists():image.write_bytes(disk.write(size=64*1024*1024))
    checked=volume(image)['Reader control']
    assert bytes(checked.data)==bytes(marker.data) and bytes(checked.rsrc)==bytes(marker.rsrc)
    assert (checked.crdate,checked.mddate,checked.type,checked.creator)==(marker.crdate,marker.mddate,marker.type,marker.creator)
    original=Path('F:/Divinity - Codex/emulator-local/runtime/system76.hfv')
    system=PRIVATE/'System76.hfv'
    if not system.exists():shutil.copy2(original,system)
    prefs=PRIVATE/'BasiliskII_prefs'
    prefs.write_text(f'rom C:\\Users\\Eric\\Documents\\Quadra-650.ROM\ndisk {system}\ndisk {image}\nramsize 67108864\nmodelid 14\ncpu 4\nfpu true\nscreen win/800/600\ndisplaycolordepth 8\nframeskip 1\nbootdriver 0\nnogui true\nenableextfs false\nnocdrom true\nnosound true\nxpram {PRIVATE / "basilisk-xpram.dat"}\nsdlrender software\ntitle Packsmith Classic Oracle\n',encoding='utf-8')
    record=dict(expected=expected,expander_versions_hex=versions,originals={str(p):sha(p) for p in (original,Path('C:/Sheepshaver/Mac OS 9.hfv'),Path('C:/Sheepshaver/250MB.dsk'),Path('F:/Stuffit_Expander_5.5.dsk'))},generated_zip_sha256=sha(archive),hfs_reader_control=True)
    (PRIVATE/'setup.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(private=str(PRIVATE),prefs=str(prefs),expander_versions_hex=versions,hfs_reader_control=True)))

def inspect():
    sys.path.insert(0,str(PYDEPS))
    import machfs
    v=volume(PRIVATE/'Tests.hfv')
    for path,file in v.iter_paths():
        if isinstance(file,machfs.File) and file.type!=b'APPL':
            print(json.dumps(dict(path=list(path),data_bytes=len(file.data),resource_bytes=len(file.rsrc),data_sha256=hashlib.sha256(file.data).hexdigest(),resource_sha256=hashlib.sha256(file.rsrc).hexdigest(),type=file.type.hex(),creator=file.creator.hex(),created=file.crdate,modified=file.mddate,flags=file.flags)))

def verify():
    """Read shut-down disks; compare raw bytes and independent resource records."""
    sys.path.insert(0,str(PYDEPS))
    from macresources import parse_file
    import machfs
    setup=json.loads((PRIVATE/'setup.json').read_text(encoding='utf-8'))
    results=[]
    for system,image in [('System 7.6 / Basilisk II','Tests.hfv'),('Mac OS 9 / SheepShaver','Tests9.hfv')]:
        disk=volume(PRIVATE/image)
        control=disk['Reader control']
        assert bytes(control.data)==b'Independent HFS known data'
        rows=[]
        for index,expected in enumerate(setup['expected']):
            path=('Transfer Folder',)+((expected['folder'],) if expected['folder'] else ())+ (expected['name'],)
            restored=disk[path]
            binary=(PRIVATE/'inputs'/('Nested' if index==2 else '')/f'F{index:06}.bin').read_bytes()
            d,r=struct.unpack_from('>II',binary,83)
            data=binary[128:128+d];offset=128+((d+127)&~127)
            resource=binary[offset:offset+r]
            assert bytes(restored.data)==data
            actual=bytes(restored.rsrc)
            assert len(actual)==len(resource)
            differences=[i for i,(a,b) in enumerate(zip(resource,actual)) if a!=b]
            assert all(16<=i<=255 for i in differences), 'Resource changes outside reserved header'
            def records(raw):
                return sorted((x.type,x.id,x.name,x.attribs,bytes(x.data)) for x in parse_file(raw)) if raw else []
            assert records(resource)==records(actual)
            assert (restored.crdate,restored.mddate)==(expected['created'],expected['modified'])
            assert (restored.type,restored.creator)==(b'TEXT',b'ttxt')
            rows.append(dict(name=expected['name'],folder=expected['folder'],data_sha256=hashlib.sha256(data).hexdigest(),
                original_resource_sha256=hashlib.sha256(resource).hexdigest(),restored_resource_sha256=hashlib.sha256(actual).hexdigest(),
                resource_difference_offsets=differences,resource_records_equal=True,dates_equal=True,type_creator_equal=True,
                finder_flags=restored.flags))
        results.append(dict(target=system,expander='5.5',passed=True,reader_control=True,restored=rows))
    originals=[]
    for name,expected in setup['originals'].items():
        actual=sha(Path(name));assert actual==expected,'Original image changed'
        originals.append(dict(name=Path(name).name,sha256=actual,unchanged=True))
    evidence=ROOT/'assessment/evidence/beta3';evidence.mkdir(parents=True,exist_ok=True)
    receipt=dict(passed=True,fixture='Generated known bytes; no XAD-based restoration oracle',
        zip_sha256=sha(PRIVATE/'Transfer.zip'),reader='machfs with macresources semantic resource comparison',
        procedure='File > Expand Transfer.zip in Expander 5.5; recursively decoded these three fixtures; shut down guest before reading HFS',
        limitation='System 7.6 Expander changes reserved resource header bytes 16-255. Allowed only with exact resource records and all other bytes unchanged. ZIP retains exact original forks. Directory/Finder-managed metadata not qualified.',
        unqualified='Expander 7.0.3 in this SheepShaver environment crashed on Transfer.zip, including JIT-disabled retry. No 7.0.3 compatibility claim.',
        targets=results,originals=originals)
    (evidence/'classic-restoration.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=True,targets=len(results),originals_unchanged=True)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','inspect','verify']);args=parser.parse_args()
    {'prepare':prepare,'inspect':inspect,'verify':verify}[args.action]()
