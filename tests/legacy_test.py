import hashlib
import base64
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
import psutil

import legacy_fixtures as fixtures
import worker_test as common

DATA,RESOURCE=fixtures.generate()

def sidecar(path):
    import struct
    data=path.read_bytes();assert len(data)>=26 and struct.unpack_from('>II',data)[0:2]==(0x00051607,0x00020000)
    count=struct.unpack_from('>H',data,24)[0];entries={}
    for i in range(count):
        kind,offset,size=struct.unpack_from('>III',data,26+12*i)
        assert offset>=26+12*count and offset+size<=len(data)
        assert kind not in entries
        entries[kind]=data[offset:offset+size]
    return entries

class LegacyTests(unittest.TestCase):
    setUp = common.WorkerTests.setUp
    tearDown = common.WorkerTests.tearDown
    good = common.WorkerTests.good
    mapping = common.WorkerTests.mapping
    def test_explicit_scope_and_duplicate_folders(self):
        path=fixtures.OUT/'duplicate-folders.sit'
        events=self.good('list',path)
        rows=[row for event in events if event['event']=='entries' for row in event['items']]
        folders=[row['id'] for row in rows if row['components']==['folder']]
        self.assertEqual(len(folders),2)
        end=self.good('extract',path,destination=str(self.dest),selection_scope='entries',ids=folders)[-1]
        self.assertEqual(sorted(self.mapping(end).values()),[b'first',b'second'])
        empty=next(row['id'] for row in rows if row['components']==['empty'])
        end=self.good('extract',path,destination=str(self.dest),selection_scope='entries',ids=[empty])[-1]
        self.assertEqual(end['file_count'],0)
        self.assertTrue((Path(end['output'])/'empty').is_dir())
        code,events=common.job('extract',path,destination=str(self.dest),selection_scope='entries',ids=[])
        self.assertNotEqual(code,0);self.assertEqual(events[-1]['code'],'empty_selection')
        end=self.good('extract',path,destination=str(self.dest),selection_scope='all')[-1]
        self.assertEqual(end['file_count'],3);self.assertTrue(end['output_committed'])

    def test_nested_wrappers_and_structured_errors(self):
        end=self.extract('nested-wrapped.hqx',selection_scope='entries',ids=[0])
        self.assertEqual(self.mapping(end),{0:DATA})
        output=Path(end['output']);mapping=json.loads((output/end['mapping']).read_text(encoding='utf-8'))['entries'][0]
        self.assertEqual(sidecar(output/mapping['sidecar'])[2],RESOURCE)
        self.assertEqual(end['checksum_coverage']['expanded_wrappers'],2)
        code,events=common.job('extract',fixtures.OUT/'bad-resource.hqx',destination=str(self.dest))
        self.assertNotEqual(code,0);self.assertEqual(events[-1]['code'],'integrity_failed')
        self.assertEqual(events[-1]['engine'],'xad');self.assertEqual(events[-1]['part'],'resource')
        self.assertFalse(events[-1]['output_committed'])
    def extract(self,name,**extra):
        path=fixtures.OUT/name
        return self.good('extract',path,destination=str(self.dest),**extra)[-1]

    def test_sit_hqx_fork_hashes_finder_and_macroman(self):
        for name in ('forks.sit','forks.hqx'):
            events=self.good('list',fixtures.OUT/name)
            row=next(e['items'][0] for e in events if e['event']=='entries')
            self.assertEqual(row['path'],'cafÃ©.txt');self.assertTrue(row['has_resource']);self.assertTrue(row['has_data'])
            end=self.extract(name,ids=[0]);output=Path(end['output'])
            mapping=json.loads((output/end['mapping']).read_text(encoding='utf-8'))['entries'][0]
            self.assertEqual((output/mapping['output']).read_bytes(),DATA)
            forks=sidecar(output/mapping['sidecar']);self.assertEqual(forks[2],RESOURCE)
            self.assertEqual(forks[9][:10],b'TEXTttxt\x40\0')
            self.assertEqual(mapping['resource_sha256'],hashlib.sha256(RESOURCE).hexdigest())
            if name.endswith('.sit'):
                # Classic date has no timezone; XAD subtracts the current local GMT offset.
                offset=datetime.datetime.now().astimezone().utcoffset().total_seconds()
                self.assertAlmostEqual((output/mapping['output']).stat().st_mtime,3660680646-2082844800-offset,delta=2)
            checked=self.good('test',fixtures.OUT/name)[-1]['checksum_coverage']
            self.assertEqual(checked['checked_forks'],2);self.assertEqual(checked['unchecked_forks'],0)

    def test_duplicate_and_sidecar_names_preserved(self):
        end=self.extract('collisions.sit');output=Path(end['output'])
        maps=json.loads((output/end['mapping']).read_text(encoding='utf-8'))['entries']
        self.assertEqual(len(maps),5)
        self.assertEqual([(output/m['output']).read_bytes() for m in maps],[b'first',b'second',b'authored-sidecar-name',b'upper',b'lower'])
        self.assertEqual([sidecar(output/m['sidecar']).get(2) for m in maps],[b'fork-first',b'fork-second',None,b'fork-upper',b'fork-lower'])
        names=[m['output'] for m in maps]+[m['sidecar'] for m in maps]
        self.assertEqual(len(set(n.casefold() for n in names)),len(names))
        end=self.extract('collisions.sit',ids=[1]);self.assertEqual(self.mapping(end),{1:b'second'})

    def test_resource_only_duplicate_does_not_pair_with_next_file(self):
        end=self.extract('unpaired.sit');output=Path(end['output'])
        maps=json.loads((output/end['mapping']).read_text(encoding='utf-8'))['entries']
        self.assertEqual(len(maps),2)
        self.assertEqual((output/maps[0]['output']).read_bytes(),b'')
        self.assertEqual(sidecar(output/maps[0]['sidecar'])[2],b'resource-only')
        self.assertEqual((output/maps[1]['output']).read_bytes(),b'data-only')

    def test_rle_both_forks(self):
        end=self.extract('rle.sit');output=Path(end['output'])
        mapping=json.loads((output/end['mapping']).read_text(encoding='utf-8'))['entries'][0]
        self.assertEqual((output/mapping['output']).read_bytes(),b'A'*200+b'\x90'+b'B'*255)
        self.assertEqual(sidecar(output/mapping['sidecar'])[2],b'R'*200)

    def test_wrapped_binhex_expands_stuffit_and_verifies_wrapper(self):
        end=self.extract('wrapped.hqx');output=Path(end['output'])
        self.assertEqual((output/'inner.txt').read_bytes(),DATA)
        self.assertEqual(sidecar(output/'._inner.txt')[2],RESOURCE)

    def test_corrupt_data_resource_header_and_truncation(self):
        for name in ('bad-resource.hqx','bad-data.hqx','bad-header.hqx','truncated.sit','bad-data.sit','bad-wrapper.hqx','bad-large-wrapper-data.hqx','bad-large-wrapper-resource.hqx'):
            code,events=common.job('extract',fixtures.OUT/name,destination=str(self.dest))
            self.assertNotEqual(code,0,(name,events[-1]));self.assertEqual(list(self.dest.iterdir()),[])

    def test_large_wrapped_archive_all_and_selected_forks(self):
        archive=fixtures.OUT/'large-wrapped.hqx'
        for ids in ([],[1],[2],[3]):
            end=self.extract(archive.name,ids=ids);output=Path(end['output'])
            maps=json.loads((output/end['mapping']).read_text(encoding='utf-8'))['entries']
            expected={1:(b'',fixtures.LARGE_RESOURCE),2:(fixtures.LARGE_DATA,RESOURCE),3:(DATA,RESOURCE)}
            files=[m for m in maps if not (output/m['output']).is_dir()]
            self.assertEqual({m['id'] for m in files},set(ids or expected))
            for m in files:
                data,resource=expected[m['id']]
                self.assertEqual((output/m['output']).read_bytes(),data)
                self.assertEqual(sidecar(output/m['sidecar'])[2],resource)
                if m['id']!=1:
                    self.assertEqual(m['data_sha256'],hashlib.sha256(data).hexdigest())
                else:
                    self.assertNotIn('data_sha256',m)
                self.assertEqual(m['resource_sha256'],hashlib.sha256(resource).hexdigest())
                leaf={1:'\t'*14+' ',2:'large.dat',3:'last.txt'}[m['id']]
                self.assertEqual(base64.b64decode(m['raw_name']),('folder/'+leaf).encode('mac_roman'))
        checked=self.good('test',archive)[-1]['checksum_coverage']
        self.assertEqual(checked['checked_forks'],7)
        self.assertEqual(checked['unchecked_forks'],0)

    def test_classic_paths_names_and_directory_selection(self):
        end=self.extract('names.sit');self.assertEqual(set(self.mapping(end).values()),{DATA,b'literal characters',b'trailing'})
        code,events=common.job('extract',fixtures.OUT/'unsafe.sit',destination=str(self.dest))
        self.assertNotEqual(code,0,events[-1]);self.assertFalse((self.root/'outside.txt').exists())
        end=self.extract('folder.sit',ids=[0]);self.assertEqual(self.mapping(end),{1:DATA})

    def test_encrypted_stuffit_correct_wrong_and_missing(self):
        for password in ('1234567','123456789012'):
            path=common.FIXTURES/(password+'.sit.bin')
            for extra in ({},{'password':'wrong'}):
                code,events=common.job('extract',path,destination=str(self.dest),**extra)
                self.assertNotEqual(code,0,events[-1]);self.assertEqual(list(self.dest.iterdir()),[])
                if not extra:self.assertEqual(events[-1]['code'],'password_required')
            end=self.good('extract',path,destination=str(self.dest),password=password)[-1];output=Path(end['output'])
            self.assertEqual(hashlib.sha256((output/'testdoc.txt').read_bytes()).hexdigest(),'0cb716050d9e407c3fda8eeb9a30d5c53ffceb8c49cc5320b965a56529ad572b')
            self.assertEqual(hashlib.sha256(sidecar(output/'._testdoc.txt')[2]).hexdigest(),'47d93fa1812ca5d49bb2df81a077276f6c003612c57abe7ea2ef29ef7b64ce81')
            end=self.good('test',path,password=password)[-1]
            self.assertEqual(end['checksum_coverage']['checked_forks'],2)
            self.assertEqual(end['checksum_coverage']['unchecked_forks'],2)
            self.assertIn('no source checksum',end['message'])
            # Keep the next wrong-password attempt's destination empty.
            self.dest=self.root/('next-'+password);self.dest.mkdir()

    def test_mutation_refuses_legacy_and_keeps_original(self):
        path=fixtures.OUT/'forks.sit';before=path.read_bytes()
        code,events=common.job('update',path,remove=[0])
        self.assertNotEqual(code,0,events[-1]);self.assertEqual(path.read_bytes(),before)

    def test_cancel_and_terminated_decoder_recovery(self):
        # Keep decoding active long enough to observe and terminate the helper.
        archive=self.root/'active-decoder.sit'
        archive.write_bytes(fixtures.sit([fixtures.sit_entry('large.dat',bytes(range(256))*262144,RESOURCE)]))
        before=hashlib.sha256(archive.read_bytes()).hexdigest()
        for forced in (False,True):
            proc=subprocess.Popen([str(common.WORKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=common.ENV)
            children=[]
            try:
                proc.stdin.write(json.dumps(dict(operation='extract',archive=str(archive),destination=str(self.dest)))+'\n');proc.stdin.flush()
                stage=json.loads(proc.stdout.readline())
                while stage['event']!='staging': stage=json.loads(proc.stdout.readline())
                self.assertEqual(stage['event'],'staging')
                children=psutil.Process(proc.pid).children(recursive=True)
                self.assertTrue(any(child.name()=='xad-stream.exe' for child in children))
                started=time.perf_counter()
                if forced:proc.kill()
                else:proc.stdin.write('{"cancel":true}\n');proc.stdin.flush()
                stdout,stderr=proc.communicate(timeout=10)
                self.assertNotEqual(proc.returncode,0)
                if forced:
                    self.assertTrue(Path(stage['path']).exists())
                    self.good('cleanup',archive,**{key:stage[key] for key in ('path','parent','token')})
                else:self.assertIn('"event":"cancelled"',stdout)
                psutil.wait_procs(children,timeout=3)
                self.assertFalse([child for child in children if child.is_running()])
                self.assertEqual(list(self.dest.iterdir()),[])
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),before)
                common.RECEIPTS.append({'operation':'forced-recovery' if forced else 'cancel','latency_ms':round((time.perf_counter()-started)*1000,2),'decoder_terminated':True,'stderr':stderr})
            finally:
                if proc.poll() is None:proc.kill();proc.communicate(timeout=10)
                psutil.wait_procs(children,timeout=3)

    def test_encoding_override_stale_listing_and_write_failure(self):
        archive=fixtures.OUT/'forks.sit'
        events=self.good('list',archive,filename_encoding='macintosh')
        self.assertEqual(next(e['items'][0]['path'] for e in events if e['event']=='entries'),'cafÃ©.txt')
        code,events=common.job('list',archive,filename_encoding='unavailable')
        self.assertNotEqual(code,0)
        code,events=common.job('extract',archive,destination=str(self.dest),fingerprint='stale')
        self.assertNotEqual(code,0);self.assertEqual(list(self.dest.iterdir()),[])
        dest=self.root/'not-a-directory';dest.write_bytes(b'untouched')
        code,events=common.job('extract',archive,destination=str(dest))
        self.assertNotEqual(code,0);self.assertEqual(dest.read_bytes(),b'untouched')

if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(LegacyTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    out=common.EVIDENCE/'desktop-legacy/tests.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'worker_sha256':hashlib.file_digest(common.WORKER.open('rb'),'sha256').hexdigest(),'decoder_sha256':hashlib.file_digest((common.WORKER.parent/'legacy/xad-stream.exe').open('rb'),'sha256').hexdigest(),'environment':'Native Windows; developer PATH removed; generated fixtures and upstream encrypted StuffIt fixtures; no independent original Mac oracle','receipts':common.RECEIPTS},indent=2)+'\n',encoding='utf-8')
    sys.exit(0 if result.wasSuccessful() else 1)
