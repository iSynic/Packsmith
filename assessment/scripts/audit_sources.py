"""Snapshot reference cleanliness and file-level embedded-source differences."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def git(path,*args):return subprocess.check_output(['git','-C',str(path),*args],text=True).strip()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
baseline=ROOT.parent/'source'
checks=[]
for directory in [baseline,*sorted((ROOT/'references').iterdir())]:
    if not (directory/'.git').exists():continue
    checks.append({'directory':str(directory.relative_to(ROOT.parent)),'commit':git(directory,'rev-parse','HEAD'),'status_porcelain':git(directory,'status','--porcelain')})
(ROOT/'evidence'/'reference-integrity.json').write_text(json.dumps(checks,indent=2)+'\n')
comparisons={}
for group in ('lzma','PPMd','wavpack','libxad','WinZipJPEG','Crypto','Windows'):
    a=baseline/'XADMaster'/group
    groups={}
    for variant in ('stable','head'):
        b=ROOT/'references'/('xad-'+variant)/group
        aa={p.relative_to(a).as_posix():sha(p) for p in a.rglob('*') if p.is_file()}
        bb={p.relative_to(b).as_posix():sha(p) for p in b.rglob('*') if p.is_file()} if b.exists() else {}
        groups[variant]={'identical':sorted(n for n in aa.keys()&bb.keys() if aa[n]==bb[n]),'different':sorted(n for n in aa.keys()&bb.keys() if aa[n]!=bb[n]),'baseline_only':sorted(aa.keys()-bb.keys()),'reference_only':sorted(bb.keys()-aa.keys()),'baseline_hashes':aa,'reference_hashes':bb}
    comparisons[group]=groups
(ROOT/'evidence'/'embedded-source-deltas.json').write_text(json.dumps(comparisons,indent=2)+'\n')
tests={}
for file in sorted((ROOT/'evidence').glob('*ctest*.log')):
    content=file.read_text(errors='replace')
    tests[file.name]={'passed':len(re.findall(r'Test\s+#\d+:.*?\bPassed\b',content)),'failed':len(re.findall(r'Test\s+#\d+:.*?\*\*\*Failed',content)),'skipped':len(re.findall(r'Test\s+#\d+:.*?\*\*\*Skipped',content)),'no_tests':'No tests were found' in content}
(ROOT/'evidence'/'upstream-test-counts.json').write_text(json.dumps(tests,indent=2)+'\n')
print(json.dumps({'clean_references':sum(not c['status_porcelain'] for c in checks),'total_references':len(checks),'tests':tests},indent=2))
