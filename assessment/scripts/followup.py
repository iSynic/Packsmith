"""Focused follow-ups; preserve first-run evidence and reference sources."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import run_suite as suite

ROOT=suite.ROOT
suite.RESULTS=[]
platform=suite.PLATFORM
def save():
    (ROOT/'evidence'/f'followup-{platform}.json').write_text(json.dumps(suite.RESULTS,indent=2)+'\n')
suite.save=save

if suite.BASE:
    for version in ('stable','head'):
        for password in ('1234567','123456789012'):
            out=suite.WORK/(version+password);out.mkdir()
            row,log=suite.run(f'xad-{version}-password-{len(password)}',[suite.BASE/f'xad-{version}-probe',suite.F/(password+'.sit.bin'),out],password=password)
            found=suite.hashes(out)
            suite.check(f'xad-{version}-password-payloads-{len(password)}',bool(found) and row['status']=='pass',{'files':found,'worker_output':log,'limit':'Hash agreement between revisions is not an independent original-application oracle'})
            wrong=suite.WORK/(version+password+'-wrong');wrong.mkdir()
            suite.run(f'xad-{version}-wrong-{len(password)}',[suite.BASE/f'xad-{version}-probe',suite.F/(password+'.sit.bin'),wrong],password='wrong',expect=1)
            suite.check(f'xad-{version}-wrong-cleanup-{len(password)}',not suite.hashes(wrong),suite.hashes(wrong))

encrypted=suite.WORK/'encrypted.7z'
suite.run('sevenzip-encrypted-create',[suite.SEVEN,'a','-t7z','-p','-mhe=on',encrypted,suite.F/'input'/'alpha.txt'],password='assessment-fixture-password\nassessment-fixture-password',timeout=20)
suite.run('sevenzip-encrypted-correct',[suite.SEVEN,'t',encrypted],password='assessment-fixture-password',timeout=20)
suite.run('sevenzip-encrypted-wrong',[suite.SEVEN,'t',encrypted],password='wrong',expect=1,timeout=20)
suite.run('sevenzip-encrypted-hidden-list',[suite.SEVEN,'l',encrypted],password='wrong',expect=1,timeout=20)

ascii_dir=suite.WORK/'ascii';ascii_dir.mkdir();(ascii_dir/'hello.txt').write_bytes(b'hello\n')
suite.run('bsdtar-ascii-create',[suite.BSDTAR,'-cf',suite.WORK/'ascii.tar','-C',ascii_dir,'.'])
suite.run('sevenzip-ascii-verify',[suite.SEVEN,'t',suite.WORK/'ascii.tar'])
save()
