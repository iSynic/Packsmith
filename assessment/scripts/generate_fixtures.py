"""Generate bounded, reproducible archive fixtures with independent payload hashes."""
import binascii
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import tarfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
F=ROOT/'outputs'/'fixtures'
F.mkdir(parents=True,exist_ok=True)
DATA=b'Legacy data fork\n'
RSRC=b'Legacy resource fork\n'
NAME=b'legacy.txt'
FILES={'alpha.txt': b'alpha\n','nested/beta.bin':bytes(range(256))*4,'unicode/caf\u00e9-\u65e5\u672c.txt':'Unicode names\n'.encode()}

def crc16(data):
    value=0
    for byte in data:
        value ^= byte
        for _ in range(8):
            value=(value>>1)^0xa001 if value&1 else value>>1
    return value

def apple(magic,entries):
    pos=26+12*len(entries)
    descriptors=b''; body=b''
    for entry_id,content in entries:
        descriptors+=struct.pack('>III',entry_id,pos,len(content)); body+=content; pos+=len(content)
    return struct.pack('>II16sH',magic,0x20000,b'\0'*16,len(entries))+descriptors+body

def zip_write(path, entries):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,content in entries:
            info=zipfile.ZipInfo(name,(2020,1,2,3,4,6));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,content)

def uu_decode(path):
    lines=path.read_bytes().splitlines(); result=b'';active=False
    for line in lines:
        if line.startswith(b'begin '): active=True;continue
        if active and line==b'end': break
        if active and line:
            count=(line[0]-32)&63
            bits=''.join(f'{(byte-32)&63:06b}' for byte in line[1:])
            result+=bytes(int(bits[i:i+8],2) for i in range(0,count*8,8))
    return result

if __name__=='__main__':
    source=F/'input'
    source.mkdir(exist_ok=True)
    for name,data in FILES.items():
        p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    zip_write(F/'mainstream.zip',FILES.items())
    with zipfile.ZipFile(F/'small-zip64.zip','w') as archive:
        with archive.open('alpha.txt','w',force_zip64=True) as out: out.write(FILES['alpha.txt'])
    for mode,name in [('w','mainstream.tar'),('w:gz','mainstream.tar.gz')]:
        with tarfile.open(F/name,mode,format=tarfile.PAX_FORMAT) as archive:
            for path,data in FILES.items():
                info=tarfile.TarInfo(path);info.size=len(data);info.mtime=1577934246;info.mode=0o644
                archive.addfile(info,io.BytesIO(data))
    zip_write(F/'duplicates.zip',[('same.txt',b'first'),('same.txt',b'second')])
    zip_write(F/'case-collision.zip',[('Case.txt',b'upper'),('case.txt',b'lower')])
    zip_write(F/'unsafe-paths.zip',[('../escape.txt',b'escape'),('/absolute.txt',b'absolute'),('C:/drive.txt',b'drive'),('safe.txt',b'safe')])
    zip_write(F/'relative-escape.zip',[('../escape.txt',b'escape'),('safe.txt',b'safe')])
    zip_write(F/'windows-names.zip',[('CON',b'device'),('AUX.txt',b'device'),('trailing. ',b'trailing'),('deep/'+'a'*240+'/file.txt',b'long')])
    content=bytearray((F/'mainstream.zip').read_bytes());content[42]^=0xff
    (F/'bad-checksum.zip').write_bytes(content)
    (F/'truncated.zip').write_bytes((F/'mainstream.zip').read_bytes()[:40])
    with tarfile.open(F/'links.tar','w') as archive:
        info=tarfile.TarInfo('escape-link');info.type=tarfile.SYMTYPE;info.linkname='../outside';archive.addfile(info)
        info=tarfile.TarInfo('escape-link/payload.txt');info.size=7;archive.addfile(info,io.BytesIO(b'payload'))
    finder=b'TEXTttxt'+b'\0'*24
    (F/'legacy.as').write_bytes(apple(0x51600,[(1,DATA),(2,RSRC),(3,NAME),(9,finder)]))
    zip_write(F/'appledouble.zip', [('legacy.txt',DATA),('__MACOSX/._legacy.txt',apple(0x51607,[(2,RSRC),(9,finder)]))])
    header=bytearray(128);header[1]=len(NAME);header[2:2+len(NAME)]=NAME
    header[65:73]=b'TEXTttxt';header[83:91]=struct.pack('>II',len(DATA),len(RSRC))
    header[91:99]=struct.pack('>II',3660680646,3660680646);header[122]=129;header[123]=129
    header[124:126]=struct.pack('>H',binascii.crc_hqx(header[:124],0))
    (F/'legacy.bin').write_bytes(header+DATA+b'\0'*((-len(DATA))%128)+RSRC+b'\0'*((-len(RSRC))%128))
    bh=bytes([len(NAME)])+NAME+b'\0TEXTttxt'+struct.pack('>HII',0,len(DATA),len(RSRC))
    decoded=bh+struct.pack('>H',binascii.crc_hqx(bh,0))+DATA+struct.pack('>H',binascii.crc_hqx(DATA,0))+RSRC+struct.pack('>H',binascii.crc_hqx(RSRC,0))
    escaped=decoded.replace(b'\x90',b'\x90\0')
    alphabet=b'!"#$%&\'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr'
    bits=''.join(f'{byte:08b}' for byte in escaped);bits+='0'*((-len(bits))%6)
    encoded=bytes(alphabet[int(bits[i:i+6],2)] for i in range(0,len(bits),6))
    (F/'legacy.hqx').write_bytes(b'(This file must be converted with BinHex 4.0)\r\n\r\n:'+encoded+b':\r\n')
    payload=b'LhA stored payload\n'
    lha=b'-lh0-'+struct.pack('<III',len(payload),len(payload),0)+bytes([0x20,0,len(NAME)])+NAME+struct.pack('<H',crc16(payload))
    (F/'legacy.lzh').write_bytes(bytes([len(lha),sum(lha)&255])+lha+payload+b'\0')
    # Compact Pro's no-XOR CRC and RLE-only path, derived from its parser.
    payload=DATA
    metadata=bytes([1])+struct.pack('>I',8)+b'TEXTttxt'+struct.pack('>IIHIHIIII',3660680646,3660680646,0,(~binascii.crc32(payload))&0xffffffff,0,0,len(payload),0,len(payload))
    directory=struct.pack('>HB',1,0)+bytes([len(NAME)])+NAME+metadata
    cpt=bytes([1,1,0,0])+struct.pack('>I',8+len(payload))+payload+struct.pack('>I',(~binascii.crc32(directory))&0xffffffff)+directory
    (F/'legacy.cpt').write_bytes(cpt)
    (F/'scale-100k.zip').unlink(missing_ok=True)
    with zipfile.ZipFile(F/'scale-100k.zip','w',allowZip64=True) as archive:
        for i in range(100000):
            info=zipfile.ZipInfo(f'entries/{i:06}.txt',(2020,1,2,3,4,6));archive.writestr(info,b'x')
    imported=[]
    ref=ROOT/'references'/'libarchive'/'libarchive'/'test'
    for pattern in ('test_read_format_lha*.lzh.uu','test_read_format_cab_lzx_16bit.cab.uu'):
        for path in ref.glob(pattern):
            data=uu_decode(path);dest=F/path.name.removesuffix('.uu');dest.write_bytes(data)
            imported.append({'fixture':dest.name,'source':str(path.relative_to(ROOT)),'oracle':'Upstream test assertions; CAB LZX does not establish Amiga LZX archive coverage'})
    for path in (ROOT/'references'/'xad-head'/'XADMasterTests'/'Stuffit'/'StuffitFixtures').glob('*.sit.bin'):
        shutil.copy2(path,F/path.name);imported.append({'fixture':path.name,'source':str(path.relative_to(ROOT)),'oracle':'Upstream XCTest extraction assertions; payload hashes still need an independent oracle'})
    manifest={'generator':'assessment/scripts/generate_fixtures.py','expected_files':{n:hashlib.sha256(d).hexdigest() for n,d in FILES.items()},'legacy':{'filename':NAME.decode(),'data_sha256':hashlib.sha256(DATA).hexdigest(),'resource_sha256':hashlib.sha256(RSRC).hexdigest(),'finder_type':'TEXT','finder_creator':'ttxt'},'imported':imported,'archives':{p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in F.iterdir() if p.is_file()}}
    (ROOT/'evidence'/'fixture-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Generated {len(manifest["archives"])} archives')
