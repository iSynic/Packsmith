"""Generated, redistributable payload cases for beta 4 qualification."""
import base64
import binascii
import hashlib
import json
from pathlib import Path
import struct

import legacy_fixtures as f

OUT = f.ROOT / 'assessment/outputs/beta4-coverage-fixtures'

def digest(data): return hashlib.sha256(data).hexdigest()

def entry(raw_name, data, resource=b'', method=0, packed=None):
    header=bytearray(f.sit_entry('Name',data,resource,method)[:112])
    header[2:66]=bytes(64);header[2]=len(raw_name);header[3:3+len(raw_name)]=raw_name
    def compress(raw):
        if packed is not None: return packed(raw)
        return f.rle(raw) if method==1 else raw
    pd,pr=compress(data),compress(resource)
    header[92:100]=struct.pack('>II',len(pr),len(pd))
    header[110:112]=struct.pack('>H',f.crc(header[:110]))
    return bytes(header)+pr+pd

def compress_literals(raw):
    bits=sum(byte<<(i*9) for i,byte in enumerate(raw))
    return bits.to_bytes((len(raw)*9+7)//8,'little')

def huffman(raw):
    if not raw: return b''
    assert set(raw)=={65}
    return b'\xa0\x80'  # one-leaf tree: 1 followed by eight bits for A

def cpt(files,packed=None):
    payload=bytearray();directory=bytearray(struct.pack('>HB',len(files),0))
    for name,data,resource in files:
        assert b'\x81' not in data+resource
        pd,pr=(packed(data),packed(resource)) if packed else (data,resource)
        encoded=name.encode('mac_roman')
        directory+=bytes([len(encoded)])+encoded+bytes([1])+struct.pack('>I',8+len(payload))+b'TEXTttxt'
        directory+=struct.pack('>IIHIHIIII',3660680646,3660680646,0x4000,(~binascii.crc32(resource+data))&0xffffffff,0,len(resource),len(data),len(pr),len(pd))
        payload+=pr+pd
    return b'\x01\x01\0\0'+struct.pack('>I',8+len(payload))+payload+struct.pack('>I',(~binascii.crc32(directory))&0xffffffff)+directory

def generate():
    OUT.mkdir(parents=True,exist_ok=True);cases=[]
    def save(name,archive,expected,encoding='macintosh',status='known-payload tested',source='Generated known bytes and independent CRCs'):
        path=OUT/name;path.write_bytes(archive)
        cases.append(dict(name=name,path=path.relative_to(f.ROOT).as_posix(),archive_sha256=digest(archive),filename_encoding=encoding,
            provenance='Generated redistributable fixture',oracle=dict(kind=status,source=source),expected=expected))
    def expected(name,data,resource=b'',raw=None):
        return dict(components=[name],data_sha256=digest(data),resource_sha256=digest(resource),raw_components=[base64.b64encode(raw or name.encode('mac_roman')).decode()])
    for method,compress in [(0,None),(1,None),(2,compress_literals),(3,huffman)]:
        data=b'A'*8 if method==3 else b'Known classic data\n';resource=b'A'*4 if method==3 else b'Known classic resource\n'
        if method==1:data=b'A'*20+b'\x90'*6;resource=b'B'*23
        save(f'method-{method}.sit',f.sit([entry(b'Known',data,resource,method,compress)]),[expected('Known',data,resource)])
    save('unsupported-6.sit',f.sit([entry(b'Known',b'unsupported',method=6)]),[],status='failed/unsupported')
    for encoding,codec,name in [('macintosh','mac_roman','caf\u00e9'),('x-mac-japanese','shift_jis','\u65e5\u672c'),('x-mac-cyrillic','mac_cyrillic','\u041f\u0440\u0438\u0432\u0435\u0442')]:
        raw=name.encode(codec);data=b'Known encoding data'
        save(encoding+'.sit',f.sit([entry(raw,data)]),[expected(name,data,raw=raw)],encoding)
    data=b'Classic pair data';resource=b'Classic pair resource'
    save('paired.cpt',cpt([('Same',data,resource),('Same',b'',resource),('Same',b'Next',b'')]),
         [expected('Same',data,resource),expected('Same',b'',resource),expected('Same',b'Next')])
    broken=bytearray((OUT/'paired.cpt').read_bytes());broken[9]^=1
    save('corrupt-paired.cpt',bytes(broken),[],status='failed/unsupported')
    # A known Compact Pro run packet repeats its preceding byte to the encoded count.
    run=lambda raw: raw[:1]+b'\x81\x82'+bytes([len(raw)]) if raw else b''
    save('runs.cpt',cpt([('Runs',b'A'*20,b'B'*23)],run),[expected('Runs',b'A'*20,b'B'*23)])
    inner=f.sit([entry(b'Nested',data,resource)])
    save('nested-macbinary.hqx',f.hqx('payload.sit',f.macbinary('payload.sit',inner,b''),b''),[expected('Nested',data,resource)])
    name=b'payload.txt';data=b'LhA stored payload\n'
    header=b'-lh0-'+struct.pack('<III',len(data),len(data),0)+bytes([0x20,0,len(name)])+name+struct.pack('<H',f.crc(data))
    save('stored.lzh',bytes([len(header),sum(header)&255])+header+data+b'\0',[expected(name.decode(),data)],encoding=None)
    for variant in ('header3','lh6','lh7'):
        name='test_read_format_lha_'+variant+'.lzh';path=f.ROOT/'assessment/outputs/fixtures'/name
        if path.exists():
            want=[expected('file1',b'                          file 1 contents\n'+b'hello\n'*3),expected('file2',b'                          file 2 contents\n'+b'hello\n'*6)]
            cases.append(dict(name=name,path=path.relative_to(f.ROOT).as_posix(),archive_sha256=digest(path.read_bytes()),filename_encoding=None,provenance='libarchive pinned upstream BSD-licensed regression fixture',oracle=dict(kind='independently qualified',source='libarchive test_read_format_lha.c known file1/file2 bytes'),expected=want,expected_complete=False))
    save('known-amiga.lzx',base64.b64decode('TFpYAAwACgQAAA8A0IQAAAABAAAKAgAAAAoAAAzlNFdq1CuPl8rzwwtwYXlsb2FkLnR4dCACFoQAAAAAGRgAAngawsvljUAtQn4OXi0FrbUgoO/uAY8AAAAAAIAIAPgEfv1fv2YXN8J6p3K08a5lbvjJf/z7UXq4eewjbxfnyfl+T5Py/J8n5Pk/T8nyfp+T5Pw/J8n5fk+T8vyfJ+T5P0/J8n6fk+T8PyfJ+X5Pk/L8nyfk+T9PyfJ+n5Pk/D8nyfl+T5Py/J8n5Pk/T8nyfp+T5Pw/J8n5fk+T8vyfJ+T5P0/J8n6fk+T8PyfJ+X5Pk/L8nyfk+T9PyfJ+n5Pk/D8nyfl+T5Py/J8n5Pk/T8nyfp+T5Pw/J8n5fk+T8vyfJ+T5P0/J8n6fk+T8PyfJ+f5PSkc='),[expected('payload.txt',b'Packsmith Amiga LZX known payload\n'*1000)],encoding=None,status='independently qualified',source='Generated with amiga-lzx; original Aminet unLZX 1.1 extracted exact known bytes. See amiga-lzx-oracle.json.')
    for case in cases:
        name=case['name']
        if name=='unsupported-6.sit':case['expected_error']='unsupported_codec'
        if name=='corrupt-paired.cpt':case['expected_error']='integrity_failed'
        case['expected_format']='Compact Pro' if name.endswith('.cpt') else 'LZH' if name.endswith('.lzh') else 'LZX' if name.endswith('.lzx') else 'StuffIt'
        case['expected_wrapper_chain']=['BinHex','MacBinary','StuffIt'] if name=='nested-macbinary.hqx' else [case['expected_format']]
    (OUT/'cases.json').write_text(json.dumps(dict(schema=1,cases=cases),indent=2)+'\n',encoding='utf-8')
    return cases

if __name__=='__main__': print('Generated',len(generate()),'coverage cases')
