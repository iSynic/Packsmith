"""Redistributable generated classic StuffIt/BinHex fixtures with known fork bytes."""
import binascii
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'assessment/outputs/desktop-legacy-fixtures'
ALPHABET=b'!"#$%&\'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr'
LARGE_DATA=bytes(range(256))*2048
LARGE_RESOURCE=bytes(reversed(range(256)))*1024
CRC_TABLE=[]
for index in range(256):
    value=index
    for _ in range(8):value=(value>>1)^0xa001 if value&1 else value>>1
    CRC_TABLE.append(value)

def crc(data):
    value=0
    for byte in data:
        value=(value>>8)^CRC_TABLE[(value^byte)&255]
    return value

def rle(data):
    output=bytearray();i=0
    while i<len(data):
        end=i+1
        while end<len(data) and data[end]==data[i] and end-i<255:end+=1
        output+=bytes([data[i]])+(b'\0' if data[i]==0x90 else b'')
        if end-i>=3:output+=bytes([0x90,end-i]);i=end
        else:i+=1
    return bytes(output)

def sit_entry(name,data=b'',resource=b'',method=0,directory=0):
    encoded=name.encode('mac_roman');assert len(encoded)<=31
    header=bytearray(112);header[0]=directory or method;header[1]=directory or method
    header[2]=len(encoded);header[3:3+len(encoded)]=encoded
    header[66:74]=b'TEXTttxt';header[74:76]=struct.pack('>H',0x4000)
    header[76:84]=struct.pack('>II',3660680646,3660680646)
    packed_data=rle(data) if method==1 else data;packed_resource=rle(resource) if method==1 else resource
    header[84:100]=struct.pack('>IIII',len(resource),len(data),len(packed_resource),len(packed_data))
    header[100:104]=struct.pack('>HH',crc(resource),crc(data));header[110:112]=struct.pack('>H',crc(header[:110]))
    return bytes(header)+packed_resource+packed_data

def sit(entries):
    body=b''.join(entries)
    return b'SIT!'+struct.pack('>HI',len(entries),22+len(body))+b'rLau'+b'\x01\0'+struct.pack('>I',22)+b'\0\0'+body

def hqx(name,data,resource,corrupt=None):
    name=name.encode('mac_roman')
    header=bytes([len(name)])+name+b'\0TEXTttxt'+struct.pack('>HII',0x4000,len(data),len(resource))
    decoded=header+struct.pack('>H',binascii.crc_hqx(header,0))+data+struct.pack('>H',binascii.crc_hqx(data,0))+resource+struct.pack('>H',binascii.crc_hqx(resource,0))
    if corrupt=='resource':decoded=decoded[:-1]+bytes([decoded[-1]^1])
    if corrupt=='data':
        pos=len(header)+2+len(data);decoded=decoded[:pos]+bytes([decoded[pos]^1])+decoded[pos+1:]
    if corrupt=='header':decoded=decoded[:len(header)]+bytes([decoded[len(header)]^1])+decoded[len(header)+1:]
    escaped=decoded.replace(b'\x90',b'\x90\0')
    bits=''.join(f'{byte:08b}' for byte in escaped);bits+='0'*((-len(bits))%6)
    encoded=bytes(ALPHABET[int(bits[i:i+6],2)] for i in range(0,len(bits),6))
    return b'(This file must be converted with BinHex 4.0)\r\n\r\n:'+encoded+b':\r\n'

def macbinary(name,data,resource):
    encoded=name.encode('mac_roman');assert len(encoded)<=63
    header=bytearray(128);header[1]=len(encoded);header[2:2+len(encoded)]=encoded
    header[65:73]=b'TEXTttxt';header[73]=0x40
    header[83:91]=struct.pack('>II',len(data),len(resource));header[122:124]=bytes([129,129])
    header[124:126]=struct.pack('>H',binascii.crc_hqx(header[:124],0))
    return bytes(header)+data+bytes((-len(data))%128)+resource+bytes((-len(resource))%128)

def generate():
    OUT.mkdir(parents=True,exist_ok=True)
    data=b'Classic data\0\x90\xff\n';resource=b'Classic resource\0\x90\x01\n'
    # Valid empty Macintosh resource map for an archive wrapper (zero types).
    wrapper_fork=struct.pack('>IIII',256,256,0,30)+bytes(240)+bytes(22)+struct.pack('>HHHh',0,28,30,-1)
    files={
        'forks.sit':sit([sit_entry('cafÃ©.txt',data,resource)]),
        'forks.hqx':hqx('cafÃ©.txt',data,resource),
        'rle.sit':sit([sit_entry('packed.txt',b'A'*200+b'\x90'+b'B'*255,b'R'*200,method=1)]),
        'collisions.sit':sit([sit_entry('same.txt',b'first',b'fork-first'),sit_entry('same.txt',b'second',b'fork-second'),sit_entry('._same.txt',b'authored-sidecar-name'),sit_entry('Case.txt',b'upper',b'fork-upper'),sit_entry('case.txt',b'lower',b'fork-lower')]),
        'unpaired.sit':sit([sit_entry('same.txt',b'',b'resource-only'),sit_entry('same.txt',b'data-only')]),
        'unsafe.sit':sit([sit_entry('..',directory=0x20),sit_entry('outside.txt',b'escape'),sit_entry('..',directory=0x21)]),
        'names.sit':sit([sit_entry('CON',data,resource),sit_entry('a:b/c\\d',b'literal characters'),sit_entry('trailing. ',b'trailing')]),
        'folder.sit':sit([sit_entry('folder',directory=0x20),sit_entry('child.txt',data,resource),sit_entry('folder',directory=0x21),sit_entry('folder/child.txt',b'not-a-descendant'),sit_entry('keep.txt',b'keep')]),
        'duplicate-folders.sit':sit([sit_entry('folder',directory=0x20),sit_entry('same.txt',b'first',b'first-fork'),sit_entry('folder',directory=0x21),
                                    sit_entry('folder',directory=0x20),sit_entry('same.txt',b'second',b'second-fork'),sit_entry('folder',directory=0x21),
                                    sit_entry('empty',directory=0x20),sit_entry('empty',directory=0x21),sit_entry('folder/same.txt',b'literal-slash')]),
        'nested-wrapped.hqx':hqx('payload.sit',macbinary('payload.sit',sit([sit_entry('inner.txt',data,resource)]),wrapper_fork),wrapper_fork),
        'bad-resource.hqx':hqx('bad.txt',data,resource,'resource'),
        'bad-data.hqx':hqx('bad.txt',data,resource,'data'),
        'bad-header.hqx':hqx('bad.txt',data,resource,'header'),
        'wrapped.hqx':hqx('payload.sit',sit([sit_entry('inner.txt',data,resource)]),wrapper_fork),
        'bad-wrapper.hqx':hqx('payload.sit',sit([sit_entry('inner.txt',data,resource)]),wrapper_fork,'resource'),
        'recovery.sit':sit([sit_entry('large.dat',bytes(range(256))*16384,resource)]),
    }
    # Exceed decoder buffers and seek between forks inside a checksum-enabled wrapper.
    large=sit([sit_entry('folder',directory=0x20),
               sit_entry('\t'*14+' ',resource=LARGE_RESOURCE),
               sit_entry('large.dat',LARGE_DATA,resource),
               sit_entry('last.txt',data,resource),
               sit_entry('folder',directory=0x21)])
    files['large-wrapped.hqx']=hqx('payload.sit',large,wrapper_fork)
    files['bad-large-wrapper-data.hqx']=hqx('payload.sit',large,wrapper_fork,'data')
    files['bad-large-wrapper-resource.hqx']=hqx('payload.sit',large,wrapper_fork,'resource')
    files['truncated.sit']=files['forks.sit'][:-4]
    files['bad-data.sit']=files['forks.sit'][:-1]+bytes([files['forks.sit'][-1]^1])
    for name,content in files.items():
        path=OUT/name
        if not path.exists() or path.read_bytes()!=content:path.write_bytes(content)
    record={'provenance':'Generated classic StuffIt stored/RLE and BinHex 4.0, with independent CRC generators; no downloaded personal archives.',
            'data_sha256':hashlib.sha256(data).hexdigest(),'resource_sha256':hashlib.sha256(resource).hexdigest(),
            'files':{name:{'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)} for name,content in files.items()}}
    evidence=ROOT/'assessment/evidence/beta3/desktop-legacy';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'generated-fixtures.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return data,resource

if __name__=='__main__':generate()
