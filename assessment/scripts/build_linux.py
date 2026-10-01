"""Build pinned references in disposable experiment copies on Linux/WSL."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get('ASSESSMENT_WORK', '/home/riceric/unarchiver-assessment-20260930'))
WORK.mkdir(parents=True, exist_ok=True)
EVIDENCE = ROOT / 'evidence'
RESULTS = []

def run(name, command, cwd=None):
    start = time.monotonic()
    log = EVIDENCE / f'{name}.log'
    with log.open('w') as out:
        result = subprocess.run(command, cwd=cwd, stdout=out, stderr=subprocess.STDOUT)
    row = {'name': name, 'command': command, 'cwd': str(cwd or WORK), 'exit_code': result.returncode, 'elapsed_seconds': round(time.monotonic()-start, 3), 'log': log.name}
    RESULTS.append(row)
    (EVIDENCE / 'linux-builds.json').write_text(json.dumps(RESULTS, indent=2)+'\n')
    print(f'{name}: exit={result.returncode} {row["elapsed_seconds"]}s', flush=True)
    if result.returncode:
        print('\n'.join(log.read_text(errors='replace').splitlines()[-12:]), flush=True)
    return result.returncode == 0

def copy(name, src):
    dest = WORK / name
    if not dest.exists():
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns('.git'))
    return dest

if __name__ == '__main__':
    for name in ('libarchive', 'libzip'):
        source = ROOT / 'references' / name
        build = WORK / f'{name}-build'
        flags = ['-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=OFF']
        if name == 'libarchive':
            flags += ['-DENABLE_TEST=ON', '-DENABLE_CPIO=OFF', '-DENABLE_CAT=OFF', '-DENABLE_UNZIP=OFF']
        else:
            flags += ['-DBUILD_DOC=OFF', '-DBUILD_EXAMPLES=OFF', '-DBUILD_OSSFUZZ=OFF', '-DBUILD_REGRESS=ON']
        if run(f'{name}-linux-configure', ['cmake', '-S', str(source), '-B', str(build), *flags]):
            if run(f'{name}-linux-build', ['cmake', '--build', str(build), '-j', '4']):
                run(f'{name}-linux-ctest', ['ctest', '--test-dir', str(build), '--output-on-failure', '-j', '4'])
    for variant in ('stable', 'head', 'baseline'):
        parent = WORK / f'xad-{variant}'
        parent.mkdir(exist_ok=True)
        src = ROOT.parent / 'source' / 'XADMaster' if variant == 'baseline' else ROOT / 'references' / f'xad-{variant}'
        detector = ROOT.parent / 'source' / 'UniversalDetector' if variant == 'baseline' else ROOT / 'references' / 'detector'
        engine = parent / 'XADMaster'
        if not engine.exists():
            shutil.copytree(src, engine, ignore=shutil.ignore_patterns('.git'))
            shutil.copytree(detector, parent/'UniversalDetector', ignore=shutil.ignore_patterns('.git'))
        run(f'xad-{variant}-linux-build', ['make', '-f', 'Makefile.linux', '-j4'], engine)
    run('linux-environment', ['bash', '-lc', 'uname -a; cat /etc/os-release; gcc --version; cmake --version; dpkg-query -W'])
