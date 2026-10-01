"""Build and assemble a relocatable Windows preview from pinned local inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SEVEN_REV = "0766b733fe3e06dd2a7f9a3cfbf2108ac73abd17"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qt", type=Path, default=ROOT / "assessment/tools/qt/6.10.2/mingw_64")
    parser.add_argument("--compiler", type=Path, default=Path("C:/msys64/mingw64/bin"))
    parser.add_argument("--build", type=Path, default=ROOT / "build/windows")
    parser.add_argument("--package", type=Path, default=ROOT / "dist/Packsmith-preview")
    parser.add_argument("--reuse-legacy", action="store_true", help="Reuse the unchanged verified helper for a GUI-only rebuild")
    args = parser.parse_args()
    qt, compiler, build, package = (p.resolve() for p in (args.qt, args.compiler, args.build, args.package))
    reference = ROOT / "assessment/references/sevenzip"
    revision = subprocess.check_output(["git", "-C", str(reference), "rev-parse", "HEAD"], text=True).strip()
    if revision != SEVEN_REV:
        raise RuntimeError("7-Zip SDK revision differs from the tested pin")
    if subprocess.check_output(["git", "-C", str(reference), "status", "--porcelain"], text=True).strip():
        raise RuntimeError("The reference checkout must remain unchanged")
    version = subprocess.check_output([str(compiler / "g++.exe"), "-dumpfullversion"], text=True).strip()
    if version != "15.2.0":
        raise RuntimeError(f"Untested compiler {version}; this build pins GCC 15.2.0")
    qt_version = subprocess.check_output([str(qt / "bin/qmake.exe"), "-query", "QT_VERSION"], text=True).strip()
    if qt_version != "6.10.2":
        raise RuntimeError(f"Untested Qt {qt_version}; this preview pins Qt 6.10.2")
    env = os.environ.copy()
    env["PATH"] = str(compiler) + os.pathsep + env["PATH"]
    evidence = ROOT / "assessment/evidence/beta4/desktop-preview"
    evidence.mkdir(parents=True, exist_ok=True)
    cc1 = Path(subprocess.check_output([str(compiler / "g++.exe"), "-print-prog-name=cc1plus"], text=True).strip()).resolve()
    frozen = {"compiler/" + p.name: sha(p) for p in [compiler / "g++.exe", cc1, compiler / "cmake.exe", compiler / "ninja.exe", compiler / "libstdc++-6.dll", compiler / "libgcc_s_seh-1.dll", compiler / "libwinpthread-1.dll"]}
    for folder, key in ((qt, "qt-sdk"), (reference / "CPP", "7zip-sdk")):
        digest = hashlib.sha256()
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(folder).as_posix().encode("utf-8"))
                digest.update(bytes.fromhex(sha(path)))
        frozen[key] = digest.hexdigest()
    frozen["7z.dll"] = sha(ROOT / "assessment/tools/sevenzip-full/7z.dll")
    input_lock = ROOT / "assessment/evidence/desktop-preview/build-inputs.lock.json"
    if input_lock.exists():
        if json.loads(input_lock.read_text(encoding="utf-8"))["hashes"] != frozen:
            raise RuntimeError("Build inputs differ from the frozen preview toolchain; qualify the change separately")
    else:
        input_lock.write_text(json.dumps({"hash_provenance": "Observed local SDK/compiler hashes; source/download pins recorded separately. Not a clean-machine acquisition receipt.", "gcc_msys2_package": "15.2.0-8", "qt": qt_version, "sevenzip_revision": revision, "hashes": frozen}, indent=2)+"\n", encoding="utf-8")
    if args.reuse_legacy:
        legacy=ROOT/'assessment/evidence/beta4/desktop-legacy/build.json'
        receipt=json.loads(legacy.read_text(encoding='utf-8'))
        previous=json.loads((package/'package-manifest.json').read_text(encoding='utf-8'))
        helper=ROOT/'build/legacy/xad-stream.exe'
        expected=next(row['sha256'] for row in previous['files'] if row['path'].replace('\\','/')=='workers/legacy/xad-stream.exe')
        if receipt['exit_code'] or receipt['source_sha256']!=sha(ROOT/'app/xad_stream.m') or sha(helper)!=expected:
            raise RuntimeError('Legacy helper changed; perform the complete build')
        for name,digest in receipt['libraries_sha256'].items():
            if sha(ROOT/'assessment/experiments/xad-windows/build-clang22'/name)!=digest:raise RuntimeError('Legacy library changed: '+name)
    else:
        subprocess.run([os.sys.executable, str(ROOT / "scripts/build_legacy_windows.py")], check=True)
    commands = [
        [str(compiler / "cmake.exe"), "-S", str(ROOT), "-B", str(build), "-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release",
         "-DCMAKE_CXX_COMPILER=" + str(compiler / "g++.exe"), "-DCMAKE_RC_COMPILER=" + str(compiler / "windres.exe"), "-DCMAKE_PREFIX_PATH=" + str(qt)],
        [str(compiler / "cmake.exe"), "--build", str(build), "-j", "4"],
    ]
    with (evidence / "build.log").open("w", encoding="utf-8") as log:
        for command in commands:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    package.mkdir(parents=True, exist_ok=True)
    worker = package / "workers"
    worker.mkdir(exist_ok=True)
    shutil.copy2(build / "Packsmith.exe", package)
    shutil.copy2(build / "packsmith-worker.exe", worker)
    shutil.copy2(ROOT / "assessment/tools/sevenzip-full/7z.dll", worker)
    legacy = worker / "legacy"
    legacy.mkdir(exist_ok=True)
    for path in (ROOT / "build/legacy").iterdir():
        if path.suffix.lower() in (".exe", ".dll"):
            shutil.copy2(path, legacy)
    for name in ("Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll"):
        shutil.copy2(qt / "bin" / name, package)
    for folder, name in (("platforms", "qwindows.dll"), ("styles", "qmodernwindowsstyle.dll"), ("imageformats", "qico.dll")):
        (package / folder).mkdir(exist_ok=True)
        shutil.copy2(qt / "plugins" / folder / name, package / folder)
        # Earlier experimental assemblies duplicated dependencies beside plugins.
        # Remove only known generated DLLs whose bytes match the packaged root copy.
        for p in (package / folder).glob("*.dll"):
            if p.name != name and (package / p.name).exists() and sha(p) == sha(package / p.name):
                p.unlink()
    # Resolve native imports rather than copying an entire developer runtime.
    search = [qt / "bin", compiler, package]
    queue = list(package.rglob("*.exe")) + list(package.rglob("*.dll"))
    origins = {str(p.relative_to(package)): str(qt / "bin" / p.name)
               for p in package.glob("Qt6*.dll")}
    origins["workers/7z.dll"] = str(ROOT / "assessment/tools/sevenzip-full/7z.dll")
    while queue:
        binary = queue.pop(0)
        imports = re.findall(r"DLL Name: ([^\s]+)", subprocess.check_output([str(compiler / "objdump.exe"), "-p", str(binary)], text=True))
        for name in imports:
            if name.lower().startswith(("api-ms-", "ext-ms-")) or (Path(os.environ["SystemRoot"]) / "System32" / name).exists():
                continue
            if binary.is_relative_to(legacy):
                if not (legacy / name).exists():
                    raise RuntimeError("Unresolved private legacy import " + name)
                origins[str((legacy / name).relative_to(package))] = str(ROOT / "build/legacy" / name)
                continue
            found = next((directory / name for directory in search if (directory / name).exists()), None)
            if not found:
                raise RuntimeError(f"Unresolved DLL {name} imported by {binary.name}")
            destination = (worker if binary.is_relative_to(worker) else package) / name
            origins.setdefault(str(destination.relative_to(package)), str(found))
            if not destination.exists() or sha(destination) != sha(found):
                shutil.copy2(found, destination)
                queue.append(destination)
                origins[str(destination.relative_to(package))] = str(found)
    licenses = package / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "assessment/tools/sevenzip-full/License.txt", licenses / "7-Zip.txt")
    for name in ("gcc-libs", "libwinpthread"):
        origin = compiler.parent / "share/licenses" / name
        if origin.is_dir():
            shutil.copytree(origin, licenses / name, dirs_exist_ok=True)
    shutil.copy2(qt / "sbom/qtbase-6.10.2.spdx", licenses / "qtbase-6.10.2.spdx")
    shutil.copytree(ROOT / "assessment/outputs/windows-first/xad-worker-bundle/licenses", licenses / "legacy", dirs_exist_ok=True)
    shutil.copy2(ROOT / "NOTICE.md", package)
    shutil.copy2(ROOT / "app/patches/machfs-LICENSE.txt", licenses / "machfs.txt")
    shutil.copy2(ROOT / "README.md", package)
    shutil.copy2(ROOT / "LICENSE", package)
    sources = ROOT / "assessment/evidence/releases/sources.json"
    if not sources.exists():
        raise RuntimeError("Run scripts/prepare_release_sources.py before packaging")
    shutil.copy2(sources, package / "source-materials.json")
    qt_licenses = licenses / "qt"
    qt_licenses.mkdir(exist_ok=True)
    with tarfile.open(ROOT / "assessment/downloads/release-sources/qtbase-everywhere-src-6.10.2.tar.xz") as source:
        for member in source:
            if member.isfile() and "/LICENSES/" in member.name:
                (qt_licenses / Path(member.name).name).write_bytes(source.extractfile(member).read())
    shutil.copy2(qt / "config_qtbase.opt", qt_licenses / "config_qtbase.opt")
    (package / "icons").mkdir(exist_ok=True)
    for name in ("packsmith", "packsmith-archive"):
        for filename in (name + ".ico", name + "-256.png"):
            shutil.copy2(ROOT / "assets/icons" / filename, package / "icons")
    manifest = {
        "scope": "Local Windows preview; fresh-machine qualification pending",
        "product": "Packsmith",
        "version": re.search(r'#define PACKSMITH_VERSION "([^"]+)"', (ROOT / "app/version.h").read_text()).group(1),
        "branding": json.loads((ROOT / "assets/icons/generation.json").read_text(encoding="utf-8")),
        "icon_formats": json.loads((ROOT / "assets/icons/formats.json").read_text(encoding="utf-8")),
        "resource_compiler_sha256": sha(compiler / "windres.exe"),
        "sdk_revision": revision, "qt": qt_version, "compiler": version,
        "commands": commands,
        "build_inputs": frozen,
        "legacy_build": json.loads((ROOT / "assessment/evidence/beta4/desktop-legacy/build.json").read_text(encoding="utf-8")),
        "legacy_build_inputs": json.loads((ROOT / "assessment/evidence/beta4/desktop-legacy/build-inputs.lock.json").read_text(encoding="utf-8")),
        "authored_sources": {str(p.relative_to(ROOT)): sha(p) for p in [ROOT / "CMakeLists.txt", ROOT / "app/main.cpp", ROOT / "app/archive_model.h", ROOT / "app/archive_opening.h", ROOT / "app/job_controller.h", ROOT / "app/classic_export.h", ROOT / "app/classic_format.h", ROOT / "app/version.h", ROOT / "app/worker.cpp", ROOT / "app/legacy_worker.h", ROOT / "app/xad_stream.m", ROOT / "app/packsmith.rc", ROOT / "assets/icons/packsmith.ico", ROOT / "assets/icons/packsmith-archive.ico", ROOT / "scripts/build_icons.py", ROOT / "scripts/build_legacy_windows.py", Path(__file__)]},
        "files": [{"path": str(p.relative_to(package)), "sha256": sha(p), "bytes": p.stat().st_size,
                   "origin": origins.get(str(p.relative_to(package)))} for p in sorted(package.rglob("*")) if p.is_file() and p.name != "package-manifest.json"],
    }
    (package / "package-manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    archive = package.parent / (package.name + "-windows-x64.zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(package.rglob("*")):
            if path.is_file():
                bundle.write(path, package.name + "/" + path.relative_to(package).as_posix())
    manifest["portable_zip"] = {"path": str(archive), "sha256": sha(archive), "bytes": archive.stat().st_size}
    (evidence / "package.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Built {package}; {sum(p['bytes'] for p in manifest['files']) / 1048576:.1f} MiB")


if __name__ == "__main__":
    main()
