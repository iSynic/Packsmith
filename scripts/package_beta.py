"""Assemble versioned Windows and corresponding-source beta release assets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(version):
    stage = ROOT / 'dist/release-materials' / ('Packsmith-' + version + '-source-materials')
    stage.mkdir(parents=True, exist_ok=True)
    record = json.loads((ROOT / 'assessment/evidence/releases/sources.json').read_text())
    archives = stage / 'runtime-sources'
    archives.mkdir(exist_ok=True)
    for row in record['sources']:
        source = ROOT / 'assessment/downloads/release-sources' / row['filename']
        if sha(source) != row['sha256']:
            raise RuntimeError('Source archive drift: ' + source.name)
        shutil.copy2(source, archives)
    sources = stage / 'sources'
    sources.mkdir(exist_ok=True)
    xad = ROOT / 'assessment/experiments/xad-windows'
    for name in ('XADMaster', 'UniversalDetector'):
        shutil.copytree(xad / name, sources / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git'))
    seven = ROOT / 'assessment/downloads/7z2603-src.tar.xz'
    shutil.copy2(seven, sources)
    record['archive_engines'] = {
        'XADMaster': {'revision': '7cb9ee0abbb163f261e4cb74501e15067032319c', 'source_directory': 'sources/XADMaster', 'windows_patches': ['windows-wide-unlink.patch', 'windows-encoding.patch']},
        'UniversalDetector': {'revision': '4eb832d999628edcd3d134e46bd35357c8c99a85', 'source_directory': 'sources/UniversalDetector'},
        '7-Zip': {'version': '26.03', 'filename': 'sources/' + seven.name, 'sha256': sha(seven)}}
    relink = stage / 'relink'
    (relink / 'lib').mkdir(parents=True, exist_ok=True)
    prefix = ROOT / 'assessment/tools/windows-runtime/mingw64'
    compat = ROOT / 'assessment/tools/windows-runtime-gcc16_1/mingw64'
    for name in ('libxad.a', 'libdetector.a'):
        shutil.copy2(xad / 'build-clang22' / name, relink / 'lib')
    for name in ('libgnustep-base.dll.a', 'libobjc.dll.a', 'libz.dll.a', 'libbz2.dll.a', 'libwavpack.dll.a'):
        shutil.copy2(prefix / 'lib' / name, relink / 'lib')
    shutil.copy2(compat / 'lib/libstdc++.dll.a', relink / 'lib')
    for name in ('Foundation', 'GNUstepBase', 'CoreFoundation', 'objc'):
        shutil.copytree(prefix / 'include' / name, relink / 'include' / name, dirs_exist_ok=True)
    for name in ('Block.h', 'Block_private.h'):
        path = prefix / 'include' / name
        if path.exists():
            shutil.copy2(path, relink / 'include')
    shutil.copytree(xad / 'compat-include', relink / 'compat-include', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'app', stage / 'app', dirs_exist_ok=True)
    (stage / 'scripts').mkdir(exist_ok=True)
    for name in ('relink_legacy.py', 'build_legacy_windows.py'):
        shutil.copy2(ROOT / 'scripts' / name, stage / 'scripts')
    shutil.copy2(xad / 'project/CMakeLists.txt', relink / 'CMakeLists.observed.txt')
    for name in ('windows-wide-unlink.patch', 'windows-encoding.patch'):
        shutil.copy2(ROOT / 'assessment/evidence/windows-first' / name, sources)
    for name in ('LICENSE', 'NOTICE.md'):
        shutil.copy2(ROOT / name, stage)
    shutil.copy2(ROOT / 'docs/releasing.md', stage / 'README.md')
    (stage / 'source-materials.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print('Source/relink materials: ' + str(stage), flush=True)
    return stage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    version = re.search(r'#define PACKSMITH_VERSION "([^"]+)"', (ROOT / 'app/version.h').read_text()).group(1)
    stage = prepare(version)
    if args.prepare_only:
        return
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise RuntimeError('Commit the workspace before assembling the tagged release assets')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    subprocess.run(['git', 'archive', '--format=tar.gz', '--prefix=Packsmith/',
                    '--output=' + str(stage / 'Packsmith-source.tar.gz'), commit], cwd=ROOT, check=True)
    materials = json.loads((stage / 'source-materials.json').read_text())
    materials.update(version=version, source_commit=commit)
    (stage / 'source-materials.json').write_text(json.dumps(materials, indent=2) + '\n', encoding='utf-8')
    manifest = {str(path.relative_to(stage)).replace('\\', '/'): sha(path)
                for path in stage.rglob('*') if path.is_file() and path.name != 'materials-manifest.json'}
    (stage / 'materials-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    out = ROOT / 'dist/releases' / ('v' + version)
    out.mkdir(parents=True, exist_ok=True)
    binary = out / ('Packsmith-' + version + '-windows-x64.zip')
    package = ROOT / 'dist/Packsmith-preview'
    package_record = json.loads((package / 'package-manifest.json').read_text())
    if package_record['version'] != version:
        raise RuntimeError('Binary package version mismatch')
    for row in package_record['files']:
        if sha(package / row['path']) != row['sha256']:
            raise RuntimeError('Packaged file changed: ' + row['path'])
    with zipfile.ZipFile(binary, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(package.rglob('*')):
            if path.is_file():
                archive.write(path, 'Packsmith/' + path.relative_to(package).as_posix())
    source = out / ('Packsmith-' + version + '-source-materials.zip')
    with zipfile.ZipFile(source, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(stage.rglob('*')):
            if path.is_file():
                compressed = path.name.endswith(('.zst', '.xz', '.gz', '.png', '.ico'))
                archive.write(path, stage.name + '/' + path.relative_to(stage).as_posix(),
                              compress_type=zipfile.ZIP_STORED if compressed else zipfile.ZIP_DEFLATED)
    assets = [dict(name=path.name, sha256=sha(path), bytes=path.stat().st_size) for path in (binary, source)]
    result = dict(tag='v' + version, source_commit=commit, prerelease=True, assets=assets,
                  scope='Unsigned portable Windows x64 beta; native developer-machine relocation tested; fresh Windows VM qualification pending')
    receipt = out / 'release-manifest.json'
    receipt.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    (out / 'SHA256SUMS.txt').write_text(''.join(sha(path) + '  ' + path.name + '\n' for path in (binary, source, receipt)), encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
