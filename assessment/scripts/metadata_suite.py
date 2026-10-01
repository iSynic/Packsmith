"""Additional bounded metadata, encoding and legacy capability receipts."""
import json
import os
from pathlib import Path
import stat
import struct
import run_suite as s

s.RESULTS=[]
def save():(s.ROOT/'evidence'/f'metadata-{s.PLATFORM}.json').write_text(json.dumps(s.RESULTS,indent=2)+'\n')
s.save=save
for engine in ('sevenzip','libarchive'):
    out=s.WORK/(engine+'-metadata');out.mkdir()
    args=[s.SEVEN,'x',s.F/'mainstream.tar','-o'+str(out),'-y'] if engine=='sevenzip' else [s.BSDTAR,'-xf',s.F/'mainstream.tar','-C',out]
    s.run(engine+'-tar-metadata-extract',args)
    for path in out.rglob('*'):
        if path.is_file():
            info=path.stat()
            s.check(engine+'-mtime-'+path.relative_to(out).as_posix(),abs(info.st_mtime-1577934246)<2,{'mtime':info.st_mtime,'expected':1577934246})
            if os.name!='nt':s.check(engine+'-mode-'+path.relative_to(out).as_posix(),stat.S_IMODE(info.st_mode)==0o644,{'mode':oct(stat.S_IMODE(info.st_mode)),'expected':'0644'})
    if os.name=='nt':s.skip(engine+'-POSIX-permissions','NTFS Windows permissions do not represent Unix mode bits directly')
for fixture in sorted(s.F.glob('test_read_format_lha*.lzh')):
    rejection=1 if 'oversize_header' in fixture.name or 'symlink_missing_target' in fixture.name else 0
    s.run('libarchive-lha-'+fixture.stem,[s.NATIVE,'archive-test',fixture],expect=rejection)
    s.run('sevenzip-lha-'+fixture.stem,[s.SEVEN,'t',fixture],expect=rejection)
    if s.BASE:s.run('xad-lha-'+fixture.stem,[s.BASE/'xad-head'/'XADMaster'/'lsar','-t',fixture],expect=rejection)
cab=s.WORK/'lzx16.bin'
s.run('libarchive-cab-lzx-oracle',[s.NATIVE,'archive-extract',s.F/'test_read_format_cab_lzx_16bit.cab',cab,'lzx16.bin'])
s.check('libarchive-cab-lzx-payload',cab.exists() and cab.read_bytes()==b'ABABABABABABABAB',{'expected_hex':b'ABABABABABABABAB'.hex(),'source':'libarchive/test/test_read_format_cab_lzx_16bit.c'})
if s.BASE:
    out=s.WORK/'xad-selected';out.mkdir()
    s.run('xad-selected-extraction',[s.BASE/'xad-head-probe',s.F/'mainstream.zip',out,'nested/beta.bin'])
    expected=json.loads((s.ROOT/'evidence'/'fixture-manifest.json').read_text())['expected_files']['nested/beta.bin']
    found=s.hashes(out)
    s.check('xad-selected-hash',len(found)==1 and list(found.values())==[expected] and next(iter(found)).endswith('nested/beta.bin'),{'files':found,'layout':'XAD may add an archive-named enclosing directory; adapter must select an explicit layout'})
    for fixture in ('relative-escape.zip','links.tar'):
        sandbox=s.WORK/('xad-'+fixture);sandbox.mkdir();out=sandbox/'dest';out.mkdir()
        row,_=s.run('xad-containment-'+fixture,[s.BASE/'xad-head-probe',s.F/fixture,out],expect=1 if fixture=='links.tar' else 0)
        outside=[str(p.relative_to(sandbox)) for p in sandbox.rglob('*') if p.is_file() and not p.is_relative_to(out)]
        s.check('xad-outside-files-'+fixture,not outside,{'outside_files':outside,'output_files':s.hashes(out),'limit':'Bounded fixtures only; no race or reparse-point proof'})
save()
