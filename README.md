# Packsmith — Windows beta

Packsmith is a native Qt Widgets archive manager with separate 7-Zip and XAD decoding processes. The Windows x64 beta supports ZIP/7z creation and editing, and classic Mac archive extraction. Production release qualification is still in progress. The historical Unarchiver checkout and the assessment references remain unchanged.

## Try it

Download the Windows x64 ZIP from [Releases](https://github.com/iSynic/Packsmith/releases), extract the entire folder, and run `Packsmith.exe`. The beta is portable and unsigned; Windows may show a SmartScreen warning. Local builds run from `dist/Packsmith-preview/Packsmith.exe`. Open a ZIP, 7z, StuffIt (`.sit`) or BinHex (`.hqx`) archive, search or sort its entries, and select rows for extraction. With no selection, Extract processes the entire archive. Ctrl+O opens, Ctrl+F searches, Ctrl+E extracts, Ctrl+T tests, F2 renames, and Delete removes selected entries.

Packsmith includes its own application and archive-document icons, with native Windows executable metadata and icon sizes for Explorer, the taskbar and Qt. Artwork, size variants and generation prompts are in `assets/icons/`. The renamed app also reads recovery journals from the previous Unarchiver preview's data directory; existing token/marker formats remain compatible.

StuffIt and BinHex support listing, selected extraction and integrity checks. The table shows data and resource-fork sizes separately. These formats are read-only; Add, Replace, Rename and Remove are disabled. MacBinary wrappers (`.bin`) are also recognized. A supported archive wrapped in BinHex/MacBinary is expanded, with wrapper checksums checked before committing extraction. When expanded, the output contains the inner archive's files; wrapper bytes and wrapper metadata are not reproduced.

Keep each extracted data file together with its `._filename` AppleDouble sidecar: entry 2 stores the resource-fork payload and entry 9 stores FinderInfo. Both payload hashes are recorded separately in the mapping. Colliding authored names such as `._filename` are preserved through suffixes. Classic filenames default to Mac Roman; Filename encoding reopens the listing with an override. Raw name bytes are recorded in the mapping. Other Mac script encodings need realistic fixtures; availability depends on Windows code pages. Test coverage includes generated stored/RLE StuffIt and BinHex, plus upstream encrypted StuffIt fixtures; broader StuffIt versions and StuffIt X remain unverified.

Create builds a ZIP or 7z from selected files. Add, Replace, Rename and Remove modify the opened archive. A replacement archive is written separately and every payload is checked before committing it. Successful edits retain an original `.backup-<id>` file beside the archive. No automatic backup pruning is performed.

Extraction creates a new archive-named folder inside the chosen destination. Duplicate names, case collisions and conflicting file/folder names are preserved with suffixes. Reserved Windows names are encoded. A mapping JSON records each original entry ID, archive path and actual output path. Absolute paths, traversal and links stop the job. Destination directory reparse points are rejected and ancestor handles block replacement while writing. File modification times are preserved; ACLs, owner IDs and other metadata are not applied.

Passwords travel through private stdin pipes, without arguments or logs. The worker supports encrypted ZIP/7z and the tested StuffIt reads. Use Password to change a password after a failed attempt; creation-password controls are not yet exposed in the GUI.

Extraction failures display a dialog and leave no completed output. Tabs and other control characters in filenames are displayed as escapes. Large BinHex-wrapped StuffIt archives are checked from the inner source outward to avoid false CRC failures after shared-stream resets.

## License and source materials

Packsmith's authored code retains the original project's LGPL-2.1-or-later license; see [LICENSE](LICENSE) and [third-party notices](NOTICE.md). Each beta provides source materials for the exact shipped libraries, Windows patches, build recipes and legacy relinking materials as a separate release asset. See [release packaging](docs/releasing.md).

## Build

The tested toolchain is Qt 6.10.2 MinGW x64 and MSYS2 GCC 15.2.0, CMake and Ninja. The engine SDK is 7-Zip 26.03 at `0766b733fe3e06dd2a7f9a3cfbf2108ac73abd17`, using the official matching Windows `7z.dll`. Pinned reference acquisition and engine assets are recorded in `assessment/evidence/sources.lock.json`. Qt 6.10.2 is the previously acquired working SDK; upgrading it is a separate qualification task.

```powershell
python scripts/build_windows.py
python tests/worker_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/legacy_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/gui_smoke.py
python tests/branding_test.py
```

Alternative SDK/compiler locations can be supplied with `--qt` and `--compiler`. The build rejects a modified/different SDK reference, different compiler version or different Qt version. The package manifest records hashes and imported DLL closure. This recipe currently requires provisioned local toolchains; it is not a fresh-machine bootstrap installer. Package tests remove developer PATH entries. That verifies local relocation, not a pristine Windows VM.

The first build freezes the compiler, runtime, SDK trees and engine DLL by content hash in `assessment/evidence/desktop-preview/build-inputs.lock.json`; later builds reject drift. The legacy helper separately freezes its inputs under `assessment/evidence/desktop-legacy/`. Its provisioned Objective-C toolchain is Clang/lld 22.1.8, GNUstep Base 1.31.1, libobjc2 2.2.1 and a private GCC 16.1 runtime. It uses the pinned, patched XAD experiment built by `assessment/scripts/build_xad_windows.py`; see `assessment/reports/windows-first.md` for acquisition and ABI requirements. `STRICT_APPLE_COMPATIBILITY=1` is required. The helper's DLLs stay under `workers/legacy/`, separate from Qt's runtime.

Native GUI smoke and legacy recovery tests require Python `psutil` and exercise the qwindows platform plugin, actual archive listing, search/selection, fork extraction and forced-worker recovery. Widget captures and measurements are under `assessment/evidence/desktop-preview/`; legacy receipts are under `assessment/evidence/desktop-legacy/`.

## Current boundaries and next gates

* Windows x64 preview only. macOS/Linux desktop builds remain deferred.
* ZIP/7z creation/editing and the tested StuffIt/BinHex extraction subset are implemented. TAR creation, multipart qualification and shell integration remain work.
* Links are rejected. Legacy file forks and FinderInfo are preserved as AppleDouble, and modification times supplied by XAD are applied. Classic dates contain no timezone; this XAD revision uses the current local UTC offset, so historical daylight-saving dates can shift by an hour. Directory dates, creation dates, comments, extended attributes, ownership and ACLs are not applied. Filename script coverage and realistic StuffIt X fixtures remain open.
* Normal cancellation cleans up staging. A forcibly terminated worker leaves quarantined staging; the GUI uses a token-checked recovery worker to clean it after exit or at the next launch. Ambiguous archive-commit failures retain recovery files for review. Power-loss recovery and filesystem failure injection remain release gates.
* The extraction containment checks do not constitute a hostile same-user race audit. Disk exhaustion, backup restoration after ambiguous filesystem failures, accessibility/screen-reader testing, installers and a clean Windows VM are open gates.
* Archive-update verification currently uses the same engine; independent ZIP readers and 7-Zip CLI checks are exercised by the test harness. Production update handling needs broader metadata/corpus coverage.

The original reuse/dependency assessment remains under `assessment/`; this prototype does not make its incomplete preservation or platform gates pass.
