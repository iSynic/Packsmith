# Unarchiver assessment workspace

This directory contains the reuse/dependency/feasibility assessment and Windows implementation receipts. The current priority is **Windows first**. Start with the [Packsmith beta 3 handoff and support matrix](reports/packsmith-beta3.md), with current receipts under `evidence/beta3/`. The earlier [desktop preview](reports/windows-desktop-preview.md), [StuffIt/BinHex adapter](reports/windows-desktop-legacy.md) and [roadmap](reports/implementation-roadmap.md) describe historical stages. The [Windows build/preservation assessment](reports/windows-first.md), [original comparison](reports/assessment.md) and [dependency inventory](reports/dependency-inventory.md) retain the earlier evidence and limits. No production release is qualified.

The recommendation is a native Qt Widgets shell with isolated engines. The local Windows XAD build and tested preservation subset now pass; clean-machine installation, production extraction/mutation policies and remaining legacy fixtures remain gates. macOS/Linux qualification is deferred. No candidate is certified ready to ship. Exact source pins: [sources lock](evidence/sources.lock.json); native Windows package pins: [runtime closure](evidence/windows-runtime.lock.json) and [compatible runtime overlay](evidence/windows-gcc16_1.lock.json). Existing source and reference checkouts remain unchanged: [integrity receipt](evidence/reference-integrity.json).

## Directory boundaries

| Directory | Purpose |
|---|---|
| `../source/` | Historical iSynic fork at `28a2330b16139f6d074cdf75ea34eee0ccd218c4`, read-only |
| `references/` | Exact upstream candidate/test-tool checkouts, read-only and ignored |
| `scripts/` | Assessment harnesses and minimal C++/Objective-C/Qt probes |
| `experiments/` | Windows out-of-tree builds and isolated tooling experiments, ignored |
| `downloads/`, `tools/` | Downloaded assets and local Qt/acquisition tools, ignored |
| `outputs/` | Generated/copied archives, extracted files and raw run output, ignored |
| `evidence/` | Source pins, hashes, commands, process results, build/test logs and probe images |
| `reports/` | Inventory, recommendation, limits and implementation roadmap |
| `/home/riceric/unarchiver-assessment-20260930/` | Linux experiment copies/builds/extracted output inside WSL, separate from donors |

The Windows experiment applies two isolated compatibility patches: UTF-16 unlink and Windows encoding/password conversion. No codec was replaced, and donor checkouts are unchanged. The authored probes implement the assessment seam. The large ZIP contains about 5 GiB of uncompressed zeros but occupies only a small fraction of that on disk; extraction/engine source builds can require additional space. Source copies and tool downloads consume more space than the receipts.

## Windows-first worker build

The local bundle is `outputs/windows-first/xad-worker-bundle/`. Its worker is an assessment extractor with always-overwrite policy, not a production app. The final fixture receipt has 70 passing checks, two demonstrated collision failures and four unverified checks. See the follow-up report for scope and reproduction requirements.

```powershell
python assessment/scripts/acquire_windows_runtime.py
python assessment/scripts/acquire_windows_compat.py
python assessment/scripts/build_xad_windows.py
python assessment/scripts/package_xad_windows.py
python assessment/scripts/test_xad_windows.py --skip-scale
python assessment/scripts/verify_assessment.py
```

These commands reuse locked inputs and assume references/shared fixtures already exist. The current GNUstep binary requires the pinned compatible runtime and `STRICT_APPLE_COMPATIBILITY=1`; blindly substituting current GCC runtime DLLs breaks loading. `--skip-scale` avoids repeating the separately recorded XAD 100k listing timeout. Inspect receipt rows; runner exit zero alone is not acceptance.

## Reproduce the Windows and Linux assessment

The scripts record absolute commands and output paths in JSON. They assume the documented local tool locations; edit those constants for a different machine. They reproduce source pins and experiments, not a hermetic/clean-machine package. Run Windows and Linux suites sequentially if regenerating shared fixtures; the final measurements were not a controlled benchmark campaign.

Windows prerequisites used: Python 3.14.7, Git, authenticated GitHub CLI for metadata reads, MSYS2 MinGW64 GCC/G++ 15.2, CMake/Ninja and its compression/crypto development libraries. Python `psutil` samples process RSS. `acquire.py` defaults to the checked-in lock; `--refresh` intentionally discovers newer releases and rewrites it and must not be used to reproduce these results.

```powershell
python assessment/scripts/acquire.py
python assessment/scripts/generate_fixtures.py
python assessment/scripts/build_windows.py
python assessment/scripts/run_regress.py
python assessment/scripts/build_probes.py
python assessment/scripts/run_suite.py
python assessment/scripts/followup.py
python assessment/scripts/metadata_suite.py
python assessment/scripts/build_candidates.py
python assessment/scripts/audit_sources.py
```

Before the suites, unpack the locked official full Windows 7-Zip package under `assessment/tools/sevenzip-full`; the suite expects both `7z.exe` and `7z.dll`. The existing machine's 7-Zip 25.01 was used only as the bootstrap extractor, not the tested engine:

```powershell
& 'C:/Program Files/7-Zip/7z.exe' x assessment/downloads/7z2603-extra.7z '-oassessment/tools/sevenzip' -y
& 'C:/Program Files/7-Zip/7z.exe' x assessment/downloads/7z2603-x64.exe '-oassessment/tools/sevenzip-full' -y
```

The extra package alone supplies `7za`, not the same full-format engine as the suite. Alternative unpacking tools are acceptable; verify the locked asset SHA-256 and `7z i` version before testing.

Qt is an isolated optional seam probe. The Windows run uses Qt 6.10.2 MinGW64 installed under `assessment/tools/qt`, acquired with aqtinstall 3.3.0 under `assessment/tools/aqt`. The latest 6.12.0 metadata query failed and remains recorded separately.

```powershell
python -m pip install --target assessment/tools/aqt aqtinstall==3.3.0
$env:PYTHONPATH = (Resolve-Path assessment/tools/aqt).Path
python -m aqt install-qt windows desktop 6.10.2 win64_mingw --archives qtbase -O assessment/tools/qt
python assessment/scripts/build_qt.py
python assessment/scripts/check_qt_latest.py
```

Run Linux scripts in the Ubuntu distribution. Native Linux runners can use equivalent prerequisites and adapt the explicit experiment root; WSL does not establish desktop functionality.

```bash
# Development prerequisites used in this environment; distribution package
# versions are recorded in evidence/linux-environment.log.
sudo apt-get install build-essential cmake ninja-build gobjc libgnustep-base-dev \
  libwavpack-dev libicu-dev zlib1g-dev libbz2-dev liblzma-dev liblz4-dev \
  libzstd-dev libssl-dev libxml2-dev libacl1-dev libarchive-dev libzip-dev \
  qt6-base-dev qt6-base-dev-tools qt6-qpa-plugins \
  lazarus-ide lcl-utils lcl-gtk2

cd /mnt/c/Users/Eric/Documents/ChatGPT/Unarchiver
mkdir -p /home/riceric/unarchiver-assessment-20260930/sevenzip
tar -xf assessment/downloads/7z2603-linux-x64.tar.xz \
  -C /home/riceric/unarchiver-assessment-20260930/sevenzip
python3 assessment/scripts/build_linux.py
python3 assessment/scripts/run_regress.py
python3 assessment/scripts/build_probes.py
python3 assessment/scripts/build_sevenzip.py
python3 assessment/scripts/run_suite.py
python3 assessment/scripts/followup.py
python3 assessment/scripts/metadata_suite.py
python3 assessment/scripts/build_candidates.py
python3 assessment/scripts/build_qt.py
```

The candidate script registers metadarkstyle into an isolated Lazarus configuration and compiles experiment copies. It also runs a shared libzip regression build so the preload test is meaningful. Ark's missing prerequisites are recorded, not silently bypassed. On a new Linux filesystem, ensure `make`, Python and executable file permissions are available; copied reference sources are never built in place.

Reports' dependency text is rendered from `scripts/write_inventory.py`. Run `python assessment/scripts/write_inventory.py` and `python assessment/scripts/audit_sources.py` after a deliberate audit update; changing dependency decisions requires evidence review, not just refreshing their prose.

## Receipt interpretation and remaining scope

`pass` means the stated process or payload-policy assertion passed, not that an entire format is proven correct. `fail` includes demonstrated data-loss policies and engine/toolchain incompatibilities. `unverified` identifies unavailable or unfinished checks. Upstream tests are counted as actual passed/failed/skipped, with initial zero-test libzip runs retained separately.

The main suites return a console summary and save JSON; **the Python runner's exit code alone is not acceptance**, since it continues collecting failures. Inspect all result rows. Raw logs referenced by receipts live in ignored `outputs/raw`; Windows's original main run uses the earlier flat directory, later focused runs use timestamped directories. No real password or private archive was used.

Fixtures are generated from small known payloads or copied/decoded from pinned upstream tests. Generated payload hashes, metadata expectations and imported paths appear in the fixture manifest and scripts. Regeneration repeats payloads and expectations; gzip container timestamps and source-tree file timestamps can vary, so the manifest identifies the exact archive bytes used in this assessment. Imported StuffIt archives still need independent original-application hashes and redistribution provenance. Do not publish the imported corpus without that check. CAB LZX is explicitly not an Amiga LZX archive. The generated Compact Pro fixture only covers data/RLE.

No macOS executor, native Linux desktop, screen-reader acceptance, real disk-full injection, complete reparse-point races or production crash-recovery transaction is verified. Windows XAD now has a native build and local runtime bundle, tested with developer PATH removed; a fresh-machine installation is still unverified. Qt 6.12.0 needs acquisition and testing. The Windows-first report lists the next experiments; there is no published CI run or release artifact to substitute for them.
