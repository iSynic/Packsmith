"""Known-byte regressions and read-only hax-13 comparison for extraction output policies."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

import worker_test as common
import legacy_fixtures as fixtures
from legacy_test import sidecar


class ExtractionOptionsTests(unittest.TestCase):
    setUp = common.WorkerTests.setUp
    tearDown = common.WorkerTests.tearDown
    good = common.WorkerTests.good

    def make_archive(self):
        archive = self.root / 'names.sit'
        archive.write_bytes(fixtures.sit([
            fixtures.sit_entry('folder', directory=0x20),
            fixtures.sit_entry('\t'*14+' ', resource=b'resource-only'),
            fixtures.sit_entry('folder', directory=0x21),
            fixtures.sit_entry('a/b', directory=0x20), fixtures.sit_entry('child', b'first-directory'), fixtures.sit_entry('a/b', directory=0x21),
            fixtures.sit_entry('a\\b', directory=0x20), fixtures.sit_entry('child', b'second-directory'), fixtures.sit_entry('a\\b', directory=0x21),
            fixtures.sit_entry('both?', b'data', b'resource'),
            fixtures.sit_entry('both_.rsrc', b'authored-rsrc'),
            fixtures.sit_entry('Case', b'upper'), fixtures.sit_entry('case', b'lower'),
            fixtures.sit_entry('CON', b'device-name'), fixtures.sit_entry('empty'),
        ]))
        return archive

    def mappings(self, end):
        root = Path(end['output'])
        report = json.loads((root / end['mapping']).read_text(encoding='utf-8'))
        return root, report, report['entries']

    def test_modes_names_collisions_metadata_empty_files_and_dates(self):
        archive = self.make_archive()
        before = hashlib.sha256(archive.read_bytes()).hexdigest()
        for policy in ('readable', 'escaped'):
            for style in ('rsrc', 'appledouble'):
                end = self.good('extract', archive, destination=str(self.dest), filename_policy=policy, resource_fork_style=style)[-1]
                root, report, maps = self.mappings(end)
                self.assertEqual(report['filename_policy'], policy)
                self.assertEqual(report['resource_fork_style'], style)
                self.assertIn('preservation', end)
                names = [m['output'] for m in maps if m['output_written']] + [m['sidecar'] for m in maps if 'sidecar' in m]
                self.assertEqual(len(names), len(set(n.casefold() for n in names)))
                expected = [b'first-directory', b'second-directory', b'data', b'authored-rsrc', b'upper', b'lower', b'device-name', b'']
                files = [(root/m['output']).read_bytes() for m in maps if m['has_data'] and not m['directory']]
                self.assertEqual(files, expected)
                resource = next(m for m in maps if m['has_resource'] and not m['has_data'])
                self.assertEqual(sidecar(root/resource['sidecar'])[2], b'resource-only')
                self.assertEqual((root/resource['output']).exists(), style=='appledouble')
                self.assertEqual(resource['output_written'], style=='appledouble')
                self.assertEqual(resource['components'][-1], '\t'*14+' ')
                self.assertEqual(resource['output'].split('/')[-1], '_'*15 if policy=='readable' else '~0009'*14+'~0020')
                empty = next(m for m in maps if m['components']==['empty'])
                self.assertTrue(empty['output_written']); self.assertEqual((root/empty['output']).read_bytes(), b'')
                folders = [m for m in maps if m['directory']]
                for folder in folders:
                    self.assertEqual('sidecar' in folder, style=='appledouble')
                    self.assertTrue(folder['finder_info'])
                    self.assertAlmostEqual((root/folder['output']).stat().st_mtime, folder['modified_ms']/1000, delta=2)
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), before)

    def test_defaults_remain_compatible_and_invalid_options_publish_nothing(self):
        end = self.good('extract', self.make_archive(), destination=str(self.dest))[-1]
        _, report, _ = self.mappings(end)
        self.assertEqual(report['filename_policy'], 'escaped'); self.assertEqual(report['resource_fork_style'], 'appledouble')
        for extra in ({'filename_policy':'unknown'}, {'resource_fork_style':'raw'}):
            before = set(self.dest.iterdir())
            code, events = common.job('extract', fixtures.OUT/'forks.sit', destination=str(self.dest), **extra)
            self.assertNotEqual(code, 0); self.assertEqual(events[-1]['code'], 'invalid_request'); self.assertEqual(set(self.dest.iterdir()), before)

    def test_selected_scope_and_corruption_keep_originals_and_no_partial_output(self):
        archive = self.make_archive()
        end = self.good('extract', archive, destination=str(self.dest), selection_scope='entries', ids=[1], filename_policy='readable', resource_fork_style='rsrc')[-1]
        root, _, maps = self.mappings(end)
        self.assertEqual(len(maps), 1); self.assertEqual(maps[0]['id'], 1)
        self.assertFalse((root/maps[0]['output']).exists()); self.assertEqual(sidecar(root/maps[0]['sidecar'])[2], b'resource-only')
        archive = fixtures.OUT/'bad-resource.hqx'; before_hash = hashlib.sha256(archive.read_bytes()).hexdigest(); before = set(self.dest.iterdir())
        code, events = common.job('extract', archive, destination=str(self.dest), filename_policy='readable', resource_fork_style='rsrc')
        self.assertNotEqual(code, 0); self.assertFalse(events[-1]['output_committed']); self.assertEqual(set(self.dest.iterdir()), before)
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), before_hash)

    def test_real_hax13_forks_and_output_shape(self):
        archive = Path('F:/Unarchiver/hax-13.hqx')
        if not archive.exists(): self.skipTest('Local hax-13 archive unavailable')
        before = hashlib.sha256(archive.read_bytes()).hexdigest()
        inventories = []
        counts = []
        for policy, style in (('escaped','appledouble'), ('readable','rsrc')):
            end = self.good('extract', archive, destination=str(self.dest), filename_policy=policy, resource_fork_style=style)[-1]
            root, _, maps = self.mappings(end)
            inventory = {}
            for m in maps:
                if m['directory']: continue
                data = (root/m['output']).read_bytes() if m['has_data'] else None
                forks = sidecar(root/m['sidecar']) if 'sidecar' in m else {}
                resource = forks.get(2)
                if resource is not None: self.assertEqual(hashlib.sha256(resource).hexdigest(), m['resource_sha256'])
                inventory[m['id']] = (data, resource, forks.get(9))
            inventories.append(inventory)
            top = next(p for p in root.iterdir() if p.is_dir())
            counts.append(len(list(top.iterdir())))
        self.assertEqual(inventories[0], inventories[1]); self.assertEqual(counts, [84,44])
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), before)

    def test_rsrc_cancellation_and_crash_recovery(self):
        archive = fixtures.OUT/'recovery.sit'; original = hashlib.sha256(archive.read_bytes()).hexdigest()
        for forced in (False, True):
            proc = subprocess.Popen([str(common.WORKER)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=common.ENV)
            try:
                proc.stdin.write(json.dumps(dict(operation='extract',archive=str(archive),destination=str(self.dest),filename_policy='readable',resource_fork_style='rsrc'))+'\n'); proc.stdin.flush()
                event = json.loads(proc.stdout.readline())
                while event['event']!='staging': event = json.loads(proc.stdout.readline())
                if forced: proc.kill()
                else: proc.stdin.write('{"cancel":true}\n'); proc.stdin.flush()
                stdout, stderr = proc.communicate(timeout=10)
                self.assertNotEqual(proc.returncode, 0)
                if forced: self.good('cleanup',archive,**{key:event[key] for key in ('path','parent','token')})
                else: self.assertIn('"event":"cancelled"',stdout)
                self.assertEqual(list(self.dest.iterdir()),[])
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),original)
            finally:
                if proc.poll() is None: proc.kill(); proc.communicate(timeout=10)


if __name__=='__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ExtractionOptionsTests))
    common.EVIDENCE.mkdir(parents=True,exist_ok=True)
    (common.EVIDENCE/'extraction-options.json').write_text(json.dumps(dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped), worker_sha256=hashlib.sha256(common.WORKER.read_bytes()).hexdigest(), real_hax13_original_unchanged=not result.failures and not result.errors and not result.skipped),indent=2)+'\n',encoding='utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
