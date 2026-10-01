"""Read-only BinHex 4.0 fork/CRC diagnostic, independent of XADMaster."""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import struct

ALPHABET = b'!"#$%&\'()*+,-012345689@ABCDEFGHIJKLMNPQRSTUVXYZ[`abcdefhijklmpqr'


def inspect(path):
    source = path.read_bytes()
    marker = source.index(b'(This file must be converted with BinHex 4.0)')
    start = source.index(b':', marker) + 1
    end = source.index(b':', start)
    packed = bytearray()
    bits = value = 0
    for char in source[start:end]:
        if char in b' \t\r\n':
            continue
        value = (value << 6) | ALPHABET.index(char)
        bits += 6
        if bits >= 8:
            bits -= 8
            packed.append((value >> bits) & 255)
            value &= (1 << bits) - 1
    decoded = bytearray()
    i = 0
    while i < len(packed):
        char = packed[i]
        i += 1
        if char != 0x90:
            decoded.append(char)
        else:
            count = packed[i]
            i += 1
            if not count:
                decoded.append(0x90)
            else:
                if not decoded:
                    raise ValueError('BinHex repetition precedes a literal byte')
                decoded.extend(bytes([decoded[-1]]) * (count - 1))
    header_length = 20 + decoded[0]
    data_length, resource_length = struct.unpack_from('>II', decoded, header_length - 8)
    sections = {}
    offset = 0
    for name, length in (('header', header_length), ('data', data_length), ('resource', resource_length)):
        payload = decoded[offset:offset + length]
        if len(payload) != length:
            raise ValueError('Truncated ' + name)
        stored = struct.unpack_from('>H', decoded, offset + length)[0]
        computed = binascii.crc_hqx(payload, 0)
        sections[name] = dict(bytes=length, sha256=hashlib.sha256(payload).hexdigest(),
                              stored_crc=stored, computed_crc=computed, crc_valid=stored == computed)
        offset += length + 2
    return dict(archive_sha256=hashlib.sha256(source).hexdigest(), archive_bytes=len(source),
                implementation='Python stdlib six-bit decode, BinHex RLE and binascii.crc_hqx; no XAD code',
                sections=sections, trailing_decoded_bytes=len(decoded) - offset,
                passed=all(section['crc_valid'] for section in sections.values()) and offset == len(decoded))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    record = inspect(args.archive)
    output = json.dumps(record, indent=2) + '\n'
    if args.report:
        args.report.write_text(output, encoding='utf-8')
    print(output)
    raise SystemExit(0 if record['passed'] else 1)
