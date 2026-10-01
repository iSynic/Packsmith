"""Pin assessment references and downloads without changing donor source."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
import sys

ROOT = Path(__file__).resolve().parents[1]
for name in ('references', 'downloads', 'experiments', 'outputs', 'reports', 'evidence', 'tools'):
    (ROOT / name).mkdir(exist_ok=True)

def api(endpoint):
    return json.loads(subprocess.check_output(['gh', 'api', endpoint], text=True))

def reference(name, repo, selector):
    if selector == 'release':
        release = api(f'repos/{repo}/releases/latest')
        ref = release['tag_name']
        selection = {'kind': 'stable-release', 'published_at': release['published_at']}
    elif selector == 'tag':
        tag = api(f'repos/{repo}/tags?per_page=1')[0]
        ref = tag['name']
        selection = {'kind': 'upstream-tag'}
    else:
        ref = api(f'repos/{repo}/commits/{selector}')['sha']
        selection = {'kind': 'unreleased-reference', 'note': 'Not represented as a stable release'}
    dest = ROOT / 'references' / name
    if dest.exists() and subprocess.check_output(['git','-C',str(dest),'status','--porcelain'],text=True).strip():
        raise RuntimeError(f'{name}: reference has local changes; refusing checkout')
    log = ROOT / 'evidence' / f'acquire-{name}.log'
    if not dest.exists():
        command = ['git', 'clone', '--depth', '1']
        if len(ref) != 40:
            command += ['--branch', ref]
        command += [f'https://github.com/{repo}.git', str(dest)]
        with log.open('w', encoding='utf-8') as f:
            subprocess.run(command, stdout=f, stderr=subprocess.STDOUT, check=True)
        if len(ref) == 40:
            subprocess.run(['git', '-C', str(dest), 'fetch', '--depth', '1', 'origin', ref], stdout=subprocess.DEVNULL, check=True)
            subprocess.run(['git', '-C', str(dest), 'checkout', '--detach', ref], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    sha = subprocess.check_output(['git', '-C', str(dest), 'rev-parse', 'HEAD'], text=True).strip()
    subprocess.run(['git', '-C', str(dest), 'checkout', '--detach', sha], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if len(ref) == 40 and sha != ref:
        raise RuntimeError(f'{name}: expected {ref}, found {sha}')
    info = {'name': name, 'repository': f'https://github.com/{repo}', 'ref': ref, 'commit': sha, **selection}
    print(f'{name}: {ref} {sha}', flush=True)
    return info

def download(url, filename):
    dest = ROOT / 'downloads' / filename
    if not dest.exists():
        with urllib.request.urlopen(url, timeout=90) as src, dest.open('wb') as out:
            while chunk := src.read(1024 * 1024):
                out.write(chunk)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    print(f'download: {filename} {digest}', flush=True)
    return {'filename': filename, 'url': url, 'sha256': digest, 'bytes': dest.stat().st_size}

if __name__ == '__main__':
    if '--refresh' not in sys.argv:
        lock=json.loads((ROOT/'evidence'/'sources.lock.json').read_text())
        for item in lock['references']:
            repo=item['repository'].removeprefix('https://github.com/')
            reference(item['name'],repo,item['commit'])
        for item in lock['downloads']:
            actual=download(item['url'],item['filename'])
            if actual['sha256']!=item['sha256']:raise RuntimeError('Download digest mismatch: '+item['filename'])
        baseline=ROOT.parent/'source'
        if not baseline.exists():
            subprocess.run(['git','clone','https://github.com/iSynic/Unarchiver.git',str(baseline)],check=True)
            subprocess.run(['git','-C',str(baseline),'checkout','--detach',lock['baseline_commit']],check=True)
        if subprocess.check_output(['git','-C',str(baseline),'rev-parse','HEAD'],text=True).strip()!=lock['baseline_commit']:
            raise RuntimeError('Historical baseline differs from lock')
        sys.exit(0)
    specs = [
        ('xad-stable', 'MacPaw/XADMaster', 'release'),
        ('xad-head', 'MacPaw/XADMaster', 'master'),
        ('detector', 'MacPaw/universal-detector', 'master'),
        ('libarchive', 'libarchive/libarchive', 'release'),
        ('libzip', 'nih-at/libzip', 'release'),
        ('sevenzip', 'ip7z/7zip', 'release'),
        ('peazip', 'peazip/PeaZip', 'release'),
        ('ark', 'KDE/ark', 'tag'),
        ('nanazip', 'M2Team/NanaZip', 'release'),
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        references = list(pool.map(lambda spec: reference(*spec), specs))
    release = api('repos/ip7z/7zip/releases/latest')
    wanted = ('-extra.7z', '-linux-x64.tar.xz', '-src.tar.xz', '-x64.exe')
    assets = [a for a in release['assets'] if a['name'].endswith(wanted)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        downloads = list(pool.map(lambda a: download(a['browser_download_url'], a['name']), assets))
    lock = {'assessment_date': '2026-09-30', 'baseline_commit': '28a2330b16139f6d074cdf75ea34eee0ccd218c4', 'references': references, 'downloads': downloads}
    (ROOT / 'evidence' / 'sources.lock.json').write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8')
