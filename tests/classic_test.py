"""Classic export behavior checked with independent ZIP/MacBinary readers."""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import zipfile

import worker_test as common
import legacy_fixtures as fixtures
fixtures.generate()

class ClassicTests(unittest.TestCase):
    setUp=common.WorkerTests.setUp
    tearDown=common.WorkerTests.tearDown
    def fixture(self,entries):
        path=self.root/'source.sit';path.write_bytes(fixtures.sit(entries));return path
    def preflight(self,path,**options):
        code,events=common.job('list',path,filename_encoding='macintosh');self.assertEqual(code,0,events)
        request=dict(mode='preflight',name_policy='strict',selection_scope='all',fingerprint=events[-1]['fingerprint'],filename_encoding='macintosh')
        request.update(options)
        code,events=common.job('export_classic',path,**request);self.assertEqual(code,0,events)
        return request,events[-1]['plan']
    def execute(self,path,request,plan,**options):
        request=dict(request,mode='execute',plan_digest=plan['plan_digest'],destination=str(self.root/'Transfer.zip'))
        request.update(options)
        return common.job('export_classic',path,**request)
    def inspect(self,path):
        with zipfile.ZipFile(path) as z:
            self.assertLess(len(z.infolist()),65535)
            for row in z.infolist():
                self.assertFalse(row.flag_bits&1);self.assertFalse(row.flag_bits&0x800)
                self.assertIn(row.compress_type,(0,8));row.filename.encode('ascii')
            manifest=json.loads(z.read('Report.json'))
            self.assertNotIn(str(self.root),json.dumps(manifest));self.assertIn(b'5.5',z.read('Read Me.txt'))
            for row in manifest['entries']:
                if row['directory']:continue
                blob=z.read('Files/'+row['transport_path']);h=blob[:128]
                self.assertEqual(struct.unpack_from('>H',h,124)[0],binascii.crc_hqx(h[:124],0))
                self.assertEqual(h[122:124],b'\x81\x81')
                self.assertEqual(h[2:2+h[1]].decode('mac_roman'),row['restored_components'][-1])
                d,r,c,m=struct.unpack_from('>IIII',h,83);offset=128+((d+127)&~127)
                self.assertEqual(len(blob),offset+((r+127)&~127))
                self.assertEqual(blob[128+d:offset],bytes(offset-128-d))
                self.assertEqual(blob[offset+r:],bytes((-r)%128))
                self.assertEqual(hashlib.sha256(blob[128:128+d]).hexdigest(),row['data_sha256'])
                if row.get('has_resource'):self.assertEqual(hashlib.sha256(blob[offset:offset+r]).hexdigest(),row['resource_sha256'])
                self.assertEqual((c,m),(row.get('created_1904') or 0,row.get('modified_1904') or 0))
                finder=base64.b64decode(row['finder_info']);self.assertEqual(h[65:73],finder[:8])
                flags=struct.unpack_from('>H',finder,8)[0];self.assertEqual((h[73]<<8)|h[101],flags&0xfc0e)
                self.assertEqual(h[75:81],bytes(6))
            return manifest
    def test_known_forks_empty_and_hierarchy(self):
        path=self.fixture([fixtures.sit_entry('Empty'),fixtures.sit_entry('Resource',resource=b'known resource'),
            fixtures.sit_entry('caf\u00e9',b'data',b'both'),fixtures.sit_entry('Nested',directory=0x20),
            fixtures.sit_entry('Child',b'nested'),fixtures.sit_entry('Vacant',directory=0x20),
            fixtures.sit_entry('Vacant',directory=0x21),fixtures.sit_entry('Nested',directory=0x21)])
        request,plan=self.preflight(path);self.assertTrue(plan['strict_allowed'])
        before=path.read_bytes();code,events=self.execute(path,request,plan)
        self.assertEqual(code,0,events);self.assertTrue(events[-1]['output_committed']);self.assertEqual(path.read_bytes(),before)
        manifest=self.inspect(self.root/'Transfer.zip');self.assertEqual(manifest['file_count'],4)
        with zipfile.ZipFile(self.root/'Transfer.zip') as z:self.assertIn('Files/Nested/Vacant/',z.namelist())
    def test_hfs_equivalence_duplicates_and_reviewed_mapping(self):
        path=self.fixture([fixtures.sit_entry('A',b'1'),fixtures.sit_entry('a',b'2'),
            fixtures.sit_entry('same',b'3'),fixtures.sit_entry('same',b'4'),
            fixtures.sit_entry('space name',b'5'),fixtures.sit_entry('space\u00a0name',b'6')])
        request,plan=self.preflight(path);self.assertFalse(plan['strict_allowed']);self.assertEqual(len(plan['changes']),3)
        code,events=self.execute(path,request,plan);self.assertNotEqual(code,0);self.assertEqual(events[-1]['code'],'classic_name_conflict')
        self.assertFalse((self.root/'Transfer.zip').exists())
        code,events=self.execute(path,request,plan,name_policy='mapped');self.assertEqual(code,0,events)
        self.assertEqual(len({r['restored_path'] for r in self.inspect(self.root/'Transfer.zip')['entries']}),6)
    def test_duplicate_and_nonascii_directories(self):
        path=fixtures.OUT/'duplicate-folders.sit';request,plan=self.preflight(path)
        self.assertFalse(plan['strict_allowed']);code,events=self.execute(path,request,plan,name_policy='mapped');self.assertEqual(code,0,events)
        manifest=self.inspect(self.root/'Transfer.zip');self.assertEqual(manifest['file_count'],3)
        self.assertEqual(len([x for x in manifest['entries'] if x['directory']]),3)
    def test_literal_slash_and_transport_conflict(self):
        path=self.fixture([fixtures.sit_entry('literal/slash',b'1'),fixtures.sit_entry('F00000000.bin',b'2')])
        request,plan=self.preflight(path);self.assertEqual(plan['entries'][0]['restored_components'],['literal/slash'])
        self.assertFalse(plan['strict_allowed']);code,events=self.execute(path,request,plan,name_policy='mapped');self.assertEqual(code,0,events);self.inspect(self.root/'Transfer.zip')
    def test_ascii_folder_transport_mapping(self):
        path=self.fixture([fixtures.sit_entry('caf\u00e9',directory=0x20),fixtures.sit_entry('CON',directory=0x20),
            fixtures.sit_entry('child',b'1'),fixtures.sit_entry('CON',directory=0x21),fixtures.sit_entry('caf\u00e9',directory=0x21)])
        request,plan=self.preflight(path);self.assertFalse(plan['strict_allowed'])
        code,events=self.execute(path,request,plan,name_policy='mapped');self.assertEqual(code,0,events);self.inspect(self.root/'Transfer.zip')
    def test_missing_dates_and_long_names(self):
        path=self.root/'long.hqx';path.write_bytes(fixtures.hqx('long name '+('x'*30),b'data',b'resource'))
        request,plan=self.preflight(path);self.assertFalse(plan['strict_allowed'])
        code,events=self.execute(path,request,plan,name_policy='mapped');self.assertEqual(code,0,events)
        row=self.inspect(self.root/'Transfer.zip')['entries'][0];self.assertIsNone(row.get('created_1904'))
    def test_stale_fingerprint_and_plan(self):
        path=self.fixture([fixtures.sit_entry('file',b'1')]);request,plan=self.preflight(path)
        code,events=self.execute(path,request,plan,plan_digest='wrong');self.assertEqual(events[-1]['code'],'stale_plan')
        path.write_bytes(path.read_bytes()+b'changed');code,events=self.execute(path,request,plan);self.assertEqual(events[-1]['code'],'stale_archive')
        self.assertFalse((self.root/'Transfer.zip').exists())
    def test_empty_selection_and_selected_empty_folder(self):
        path=self.fixture([fixtures.sit_entry('Empty',directory=0x20),fixtures.sit_entry('Empty',directory=0x21),fixtures.sit_entry('file',b'1')])
        request,plan=self.preflight(path,selection_scope='entries',ids=[0]);self.assertEqual(plan['file_count'],0)
        code,events=self.execute(path,request,plan);self.assertEqual(code,0,events)
        request['ids']=[];code,events=common.job('export_classic',path,**request);self.assertEqual(events[-1]['code'],'empty_selection')
    def test_corrupt_stream_no_publication(self):
        path=fixtures.OUT/'bad-resource.hqx';request,plan=self.preflight(path)
        before=path.read_bytes();code,events=self.execute(path,request,plan)
        self.assertNotEqual(code,0);self.assertFalse((self.root/'Transfer.zip').exists());self.assertEqual(path.read_bytes(),before)
        self.assertEqual(list(self.root.glob('.unarchiver-*')),[])
    def test_timezone_independent_raw_dates(self):
        path=self.fixture([fixtures.sit_entry('file',b'1')]);request,plan=self.preflight(path)
        results=[]
        for zone in ('UTC0','CST6CDT','JST-9'):
            env=dict(common.ENV,TZ=zone);r=dict(request,operation='export_classic',archive=str(path),mode='execute',plan_digest=plan['plan_digest'],destination=str(self.root/(zone.replace('-','')+'.zip')))
            p=subprocess.run([str(common.WORKER)],input=json.dumps(r)+'\n',text=True,encoding='utf-8',capture_output=True,env=env)
            self.assertEqual(p.returncode,0,p.stdout)
            with zipfile.ZipFile(r['destination']) as z:results.append(z.read('Files/F00000000.bin'))
        self.assertEqual(results[0],results[1]);self.assertEqual(results[1],results[2])
    def test_limits_rejected_before_decoding(self):
        path=self.root/'huge.bin';header=bytearray(fixtures.macbinary('Huge',b'',b''))
        struct.pack_into('>I',header,83,0x80000000);struct.pack_into('>H',header,124,binascii.crc_hqx(header[:124],0));path.write_bytes(header)
        request=dict(mode='preflight',name_policy='strict',selection_scope='all',fingerprint=hashlib.sha256(header).hexdigest())
        code,events=common.job('export_classic',path,**request)
        self.assertNotEqual(code,0);self.assertEqual(events[-1]['code'],'classic_limit')
        path=self.fixture([fixtures.sit_entry('F%05d'%i) for i in range(65532)])
        request['fingerprint']=hashlib.sha256(path.read_bytes()).hexdigest()
        code,events=common.job('export_classic',path,**request)
        self.assertNotEqual(code,0);self.assertEqual(events[-1]['code'],'classic_limit')
    def test_cancel_and_terminated_export_recovery(self):
        path=fixtures.OUT/'recovery.sit';request,plan=self.preflight(path)
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        for forced in (False,True):
            r=dict(request,operation='export_classic',archive=str(path),mode='execute',plan_digest=plan['plan_digest'],destination=str(self.root/'Transfer.zip'))
            proc=subprocess.Popen([str(common.WORKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=common.ENV)
            proc.stdin.write(json.dumps(r)+'\n');proc.stdin.flush()
            while True:
                line=proc.stdout.readline();self.assertTrue(line)
                event=json.loads(line)
                if event.get('event')=='staging':break
            if forced:proc.kill()
            else:proc.stdin.write('{"cancel":true}\n');proc.stdin.flush()
            stdout,stderr=proc.communicate(timeout=15)
            self.assertNotEqual(proc.returncode,0,stdout+stderr);self.assertFalse((self.root/'Transfer.zip').exists())
            if forced:
                code,events=common.job('cleanup',path,**{key:event[key] for key in ('path','parent','token')})
                self.assertEqual(code,0,events)
            else:self.assertIn('"event":"cancelled"',stdout)
            self.assertFalse(Path(event['path']).exists());self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
    def test_wrong_password_and_failed_cleanup(self):
        path=common.FIXTURES/'1234567.sit.bin';request,plan=self.preflight(path,password='wrong')
        code,events=self.execute(path,request,plan,name_policy='mapped');self.assertNotEqual(code,0);self.assertFalse((self.root/'Transfer.zip').exists())
        request['password']='1234567';code,events=self.execute(path,request,plan,name_policy='mapped');self.assertEqual(code,0,events)
        with zipfile.ZipFile(self.root/'Transfer.zip') as z:self.assertNotIn('1234567',z.read('Report.json').decode('utf-8'))
        path=fixtures.OUT/'recovery.sit';request,plan=self.preflight(path)
        r=dict(request,operation='export_classic',archive=str(path),mode='execute',plan_digest=plan['plan_digest'],destination=str(self.root/'Other.zip'))
        proc=subprocess.Popen([str(common.WORKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=common.ENV)
        proc.stdin.write(json.dumps(r)+'\n');proc.stdin.flush()
        while True:
            event=json.loads(proc.stdout.readline())
            if event.get('event')=='staging':break
        proc.kill();proc.communicate(timeout=15)
        marker=Path(event['path'])/'.unarchiver-job.json';kernel,handle=common.deletion_lock(marker)
        try:
            code,events=common.job('cleanup',path,**{key:event[key] for key in ('path','parent','token')})
            self.assertNotEqual(code,0);self.assertTrue(marker.exists())
        finally:kernel.CloseHandle(handle)
        code,events=common.job('cleanup',path,**{key:event[key] for key in ('path','parent','token')})
        self.assertEqual(code,0,events);self.assertFalse(Path(event['path']).exists());self.assertFalse((self.root/'Other.zip').exists())
    def test_interrupted_final_commit_preserves_source(self):
        path=fixtures.OUT/'recovery.sit';request,plan=self.preflight(path)
        before=hashlib.sha256(path.read_bytes()).hexdigest();target=self.root/'Transfer.zip'
        r=dict(request,operation='export_classic',archive=str(path),mode='execute',plan_digest=plan['plan_digest'],destination=str(target))
        proc=subprocess.Popen([str(common.WORKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=common.ENV)
        proc.stdin.write(json.dumps(r)+'\n');proc.stdin.flush()
        stage=None;lock=None;retry=False
        try:
            while line:=proc.stdout.readline():
                event=json.loads(line)
                if event.get('event')=='staging':stage=event
                # The outer ZIP exists after creation and before its final move.
                if stage and not lock and (Path(stage['path'])/'Transfer.zip').exists():
                    lock=common.deletion_lock(Path(stage['path'])/'Transfer.zip')
                if lock and event.get('phase')=='committing' and event.get('retry'):
                    retry=True;proc.kill();break
            stdout,stderr=proc.communicate(timeout=15)
        finally:
            if proc.poll() is None:proc.kill();proc.communicate(timeout=15)
            if lock:lock[0].CloseHandle(lock[1])
        self.assertTrue(retry,'Held ZIP must reach final commit retry before termination')
        self.assertFalse(target.exists());self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
        code,events=common.job('cleanup',path,**{key:stage[key] for key in ('path','parent','token')})
        self.assertEqual(code,0,events);self.assertFalse(Path(stage['path']).exists())

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ClassicTests))
    evidence=common.ROOT/'assessment/evidence/beta4';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'classic-tests.json').write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),worker_sha256=hashlib.sha256(common.WORKER.read_bytes()).hexdigest(),receipts=common.RECEIPTS),indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
