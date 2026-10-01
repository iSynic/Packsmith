"""Acquire exact MSYS2/Qt source archives for the shipped runtime closure."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'assessment/downloads/release-sources'
EVIDENCE = ROOT / 'assessment/evidence/releases'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(item):
    target = CACHE / item['filename']
    if not target.exists():
        temporary = target.with_suffix(target.suffix + '.part')
        with urllib.request.urlopen(item['url'], timeout=45) as response, temporary.open('wb') as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
        temporary.replace(target)
    item.update(sha256=sha(target), bytes=target.stat().st_size)
    print('Source acquired: ' + target.name, flush=True)
    return item


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    package = ROOT / 'dist/Packsmith-preview'
    binaries = {str(path.relative_to(package)).replace('\\', '/'): sha(path)
                for path in package.rglob('*.dll')}
    wanted = {path: digest for path, digest in binaries.items()
              if path.startswith('workers/legacy/') or Path(path).name.startswith(('libgcc_', 'libstdc++', 'libwinpthread'))}
    runtime_names = {'libwinpthread', 'libffi', 'libiconv', 'gettext-runtime', 'zlib', 'zstd',
                     'libxml2', 'brotli', 'libunistring', 'libidn2', 'gmp', 'nettle', 'p11-kit',
                     'gnutls', 'icu', 'libobjc2', 'libxslt', 'gnustep-base', 'wavpack', 'bzip2', 'libtasn1'}
    lock = json.loads((ROOT / 'assessment/evidence/windows-runtime.lock.json').read_text())
    archives = [ROOT / 'assessment/downloads/windows-runtime' / row['filename']
                for row in lock['packages'] if row['name'].removeprefix('mingw-w64-x86_64-') in runtime_names]
    archives += [ROOT / 'assessment/downloads/windows-runtime/mingw-w64-x86_64-gcc-libs-16.1.0-1-any.pkg.tar.zst',
                 Path('C:/msys64/var/cache/pacman/pkg/mingw-w64-x86_64-gcc-libs-15.2.0-8-any.pkg.tar.zst'),
                 Path('C:/msys64/var/cache/pacman/pkg/mingw-w64-x86_64-libwinpthread-13.0.0.r155.g849a151ba-1-any.pkg.tar.zst')]
    components = {}
    matched = {}
    for archive in archives:
        metadata = {}
        matches = []
        with tarfile.open(archive) as source:
            for member in source:
                if member.name == '.PKGINFO':
                    for line in source.extractfile(member).read().decode().splitlines():
                        key, sep, value = line.partition(' = ')
                        if sep:
                            metadata.setdefault(key, []).append(value)
                elif member.isfile() and member.name.startswith('mingw64/bin/') and member.name.endswith('.dll'):
                    digest = hashlib.sha256(source.extractfile(member).read()).hexdigest()
                    for path, expected in wanted.items():
                        if Path(path).name == Path(member.name).name and digest == expected:
                            matches.append(path)
        if not matches:
            continue
        base, version = metadata['pkgbase'][0], metadata['pkgver'][0]
        filename = f'{base}-{version}.src.tar.zst'
        row = components.setdefault(filename, dict(filename=filename, component=base, version=version,
                            url='https://repo.msys2.org/mingw/sources/' + filename, binaries=[],
                            license=metadata.get('license', []), binary_packages=[]))
        row['binaries'] += sorted(set(matches) - set(row['binaries']))
        row['binary_packages'].append(dict(filename=archive.name, sha256=sha(archive)))
        for path in matches:
            if path in matched and matched[path] != filename:
                raise RuntimeError('Ambiguous runtime origin: ' + path)
            matched[path] = filename
    if missing := set(wanted) - set(matched):
        raise RuntimeError('No exact source package origin for ' + repr(sorted(missing)))
    components['qtbase-everywhere-src-6.10.2.tar.xz'] = dict(
        filename='qtbase-everywhere-src-6.10.2.tar.xz', component='Qt Base', version='6.10.2',
        url='https://download.qt.io/archive/qt/6.10/6.10.2/submodules/qtbase-everywhere-src-6.10.2.tar.xz',
        binaries=sorted(path for path in binaries if path not in wanted and Path(path).name != '7z.dll'),
        license=['LGPL-3.0-only and embedded third-party notices'])
    with ThreadPoolExecutor(max_workers=6) as pool:
        sources = list(pool.map(download, components.values()))
    for row in sources:
        path = CACHE / row['filename']
        with tarfile.open(path) as archive:
            names = archive.getnames()
            if path.name.endswith('.src.tar.zst'):
                if not any(name.endswith('/PKGBUILD') for name in names):
                    raise RuntimeError('Missing source build recipe: ' + path.name)
                if not any(name.endswith(('.tar.gz', '.tar.xz', '.tar.bz2', '.tar.lz', '.tgz', '.zip')) or name.endswith('.git/HEAD') for name in names):
                    # Git sources may be stored as bare git trees with another suffix.
                    if not any('/objects/' in name for name in names):
                        raise RuntimeError('Missing upstream payload in source package: ' + path.name)
    result = dict(provenance='Exact DLL content matched to cached binary packages; source archives acquired over HTTPS from official repositories. SHA256 observed at acquisition.',
                  sources=sources, runtime_binary_sha256=binaries)
    (EVIDENCE / 'sources.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f'Prepared {len(sources)} source archives covering {len(binaries)} shipped DLLs', flush=True)


if __name__ == '__main__':
    main()
