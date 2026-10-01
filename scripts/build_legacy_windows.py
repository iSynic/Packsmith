"""Build the decoder-only helper against the separately pinned XAD experiment."""
import hashlib
import difflib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "assessment"
PREFIX = ASSESSMENT / "tools/windows-runtime/mingw64"
COMPAT = ASSESSMENT / "tools/windows-runtime-gcc16_1/mingw64"
XAD = ASSESSMENT / "experiments/xad-windows"
BUILD = ROOT / "build/legacy"
EVIDENCE = ASSESSMENT / "evidence/beta3/desktop-legacy"


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def tree_sha(folder):
    digest=hashlib.sha256()
    for path in sorted(folder.rglob('*')):
        if path.is_file() and '.git' not in path.relative_to(folder).parts:
            digest.update(path.relative_to(folder).as_posix().encode('utf-8'))
            digest.update(bytes.fromhex(sha(path)))
    return digest.hexdigest()


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for name, expected in (("xad-head", "7cb9ee0abbb163f261e4cb74501e15067032319c"), ("detector", "4eb832d999628edcd3d134e46bd35357c8c99a85")):
        path = ASSESSMENT / "references" / name
        if subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip() != expected or subprocess.check_output(["git", "-C", str(path), "status", "--porcelain"], text=True).strip():
            raise RuntimeError("Unexpected reference revision or changes: " + name)
    env = os.environ.copy()
    env["PATH"] = str(COMPAT / "bin") + os.pathsep + str(PREFIX / "bin") + os.pathsep + env["PATH"]
    patches={'XADStuffItParser.m':'XADStuffItParser.m.patch','XADStuffIt5Parser.m':'XADStuffIt5Parser.m.patch','XADMacArchiveParser.m':'XADMacArchiveParser.m.patch','XADUnarchiver.m':'windows-wide-unlink.patch','XADStringWindows.m':'windows-encoding.patch'}
    for name, reference in (('XADMaster','xad-head'),('UniversalDetector','detector')):
        source=ASSESSMENT/'references'/reference
        for path in source.rglob('*'):
            if not path.is_file() or '.git' in path.relative_to(source).parts:continue
            relative=path.relative_to(source);copy=XAD/name/relative
            if name=='XADMaster' and relative.as_posix() in patches:
                patch=''.join(difflib.unified_diff(path.read_text().splitlines(True),copy.read_text().splitlines(True),fromfile='a/'+relative.as_posix(),tofile='b/'+relative.as_posix()))
                if patch!=((ROOT/'app/patches' if relative.as_posix() in ('XADStuffItParser.m','XADStuffIt5Parser.m','XADMacArchiveParser.m') else ASSESSMENT/'evidence/windows-first')/patches[relative.as_posix()]).read_text():
                    raise RuntimeError('Unexpected legacy adaptation: '+str(relative))
            elif not copy.exists() or sha(path)!=sha(copy):
                raise RuntimeError('Unexpected legacy source changes: '+str(relative))
    frozen={str(path.relative_to(ASSESSMENT)):sha(path) for path in [
        PREFIX/'bin/clang.exe',PREFIX/'bin/clang++.exe',PREFIX/'bin/ld.lld.exe',
        PREFIX/'lib/libgnustep-base.dll.a',PREFIX/'lib/libobjc.dll.a',PREFIX/'lib/libz.dll.a',
        PREFIX/'lib/libbz2.dll.a',PREFIX/'lib/libwavpack.dll.a',COMPAT/'lib/libstdc++.dll.a',
        XAD/'project/CMakeLists.txt',XAD/'compat-include/regex.h',
        ASSESSMENT/'evidence/windows-first/windows-wide-unlink.patch',ASSESSMENT/'evidence/windows-first/windows-encoding.patch']}
    for folder in (PREFIX/'include',PREFIX/'lib/clang',XAD/'XADMaster',XAD/'UniversalDetector'):
        frozen[str(folder.relative_to(ASSESSMENT))]=tree_sha(folder)
    lock=EVIDENCE/'build-inputs.lock.json'
    historical=json.loads((ASSESSMENT/'evidence/desktop-legacy/build-inputs.lock.json').read_text())['hashes']
    for key,value in historical.items():
        if key.replace('\\','/')!='experiments/xad-windows/XADMaster' and frozen.get(key)!=value:raise RuntimeError('Frozen toolchain drift: '+key)
    if lock.exists():
        if json.loads(lock.read_text(encoding='utf-8'))['hashes']!=frozen:
            raise RuntimeError('Legacy build inputs differ from the frozen toolchain')
    else:lock.write_text(json.dumps({'provenance':'Observed local compiler/headers/imports/source hashes; acquired packages and engine build receipts are in windows-first. Not fresh-machine proof.','hashes':frozen},indent=2)+'\n',encoding='utf-8')
    libraries=[str(Path('C:/msys64/mingw64/bin/cmake.exe')),'--build',str(XAD/'build-clang22'),'--target','xad','detector','-j','4']
    with (EVIDENCE/'libraries.log').open('w',encoding='utf-8') as log:
        subprocess.run(libraries,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    output = BUILD / "xad-stream.exe"
    command = [str(PREFIX / "bin/clang.exe"), "-O2", "-fobjc-runtime=gnustep-2.0", "-fexceptions", "-fobjc-exceptions", "-fblocks",
               "-fconstant-string-class=NSConstantString", "-DSTRICT_APPLE_COMPATIBILITY=1", "-D_NATIVE_OBJC_EXCEPTIONS", "-D_FILE_OFFSET_BITS=64",
               "-I" + str(PREFIX / "include"), "-I" + str(XAD / "XADMaster"), "-I" + str(XAD / "compat-include"), "-L" + str(COMPAT / "lib"), "-L" + str(PREFIX / "lib"),
               "-fuse-ld=lld", str(ROOT / "app/xad_stream.m"), "-Wl,--whole-archive", str(XAD / "build-clang22/libxad.a"),
               str(XAD / "build-clang22/libdetector.a"), "-Wl,--no-whole-archive", "-lgnustep-base", "-lobjc", "-lstdc++", "-lz", "-lbz2", "-lwavpack", "-lwinmm", "-lgdi32", "-o", str(output)]
    with (EVIDENCE / "build.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    (EVIDENCE / "build.json").write_text(json.dumps({"command": command, "libraries_command":libraries,"libraries_sha256":{p.name:sha(p) for p in (XAD/'build-clang22/libxad.a',XAD/'build-clang22/libdetector.a')},"source_sha256":sha(ROOT/'app/xad_stream.m'),"exit_code": result.returncode}, indent=2)+"\n", encoding="utf-8")
    if result.returncode:
        print((EVIDENCE / "build.log").read_text(encoding="utf-8", errors="replace")[-6000:])
        raise SystemExit(result.returncode)
    # Reuse and verify the tested runtime closure; never mix this with the Qt worker runtime.
    manifest = json.loads((ASSESSMENT / "evidence/windows-first/bundle.json").read_text())
    for row in manifest["native_files"]:
        if not row["file"].lower().endswith(".dll"):
            continue
        path = Path(manifest["bundle_directory"]) / row["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise RuntimeError("Legacy runtime drift: " + row["file"])
        shutil.copy2(path, BUILD)
    print("Built decoder-only legacy helper", flush=True)


if __name__ == "__main__":
    main()
