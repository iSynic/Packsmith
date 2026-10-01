# Packsmith â€” Windows beta

Packsmith is a native Qt Widgets archive manager with separate 7-Zip and XAD decoding processes. The Windows x64 beta supports ZIP/7z creation and editing, and classic Mac archive extraction. Production release qualification is still in progress. The historical Unarchiver checkout and the assessment references remain unchanged.

## Try it

Download the published Windows x64 ZIP from [Releases](https://github.com/iSynic/Packsmith/releases), extract the entire folder, and run `Packsmith.exe`. Beta 4 is an unpublished local candidate under `dist/candidates/v0.1.0-beta.4/`; previous candidate assets are preserved. The beta is portable and unsigned; Windows may show a SmartScreen warning. Local builds run from `dist/Packsmith-preview/Packsmith.exe`.

Open a ZIP, 7z, StuffIt (`.sit`), BinHex (`.hqx`), MacBinary (`.bin`), Compact Pro (`.cpt`), LhA (`.lha`/`.lzh`) or Amiga LZX (`.lzx`) archive and browse its folders using breadcrumbs, Back/Up, or Enter. Enter on a file opens details. Search covers the whole archive and shows locations; clearing it returns to the previous folder. Extract processes selected entries, or the current folder when nothing is selected. Search requires a selection. Extract All explicitly processes the whole archive. Ctrl+O opens, Ctrl+F searches, Ctrl+E extracts, Ctrl+Shift+E extracts all, Alt+Left goes back, Alt+Up goes up, Ctrl+T tests, F2 renames, and Delete removes selected entries. Navigation clears selection; sorting preserves entry IDs. Virtual and duplicate folder groups cannot be renamed or replaced as one entry.

Open, command-line paths, single local-file drops and Recent Archives share the same state-resetting path. File and Archive menus retain access when toolbar actions overflow. **Remember recent archives** in File is off by default. Enabling it stores at most ten successfully listed paths for this Windows user. Clear History removes them immediately; disabling history also clears them. Passwords, encoding overrides, entry names and output destinations are never stored. Missing recent files are explained and removed. A running job, recovery or export review prevents replacement.

Packsmith includes its own application and archive-document icons, with native Windows executable metadata and icon sizes for Explorer, the taskbar and Qt. Artwork, size variants and generation prompts are in `assets/icons/`. The renamed app also reads recovery journals from the previous Unarchiver preview's data directory; existing token/marker formats remain compatible.

StuffIt and BinHex support listing, selected extraction and integrity checks. The table shows data and resource-fork sizes separately. These formats are read-only; Add, Replace, Rename and Remove are disabled. MacBinary wrappers (`.bin`) are also recognized. A supported archive wrapped in BinHex/MacBinary is expanded, with wrapper checksums checked before committing extraction. When expanded, the output contains the inner archive's files; wrapper bytes and wrapper metadata are not reproduced.

Keep each extracted data file together with its `._filename` AppleDouble sidecar: entry 2 stores the resource-fork payload and entry 9 stores FinderInfo. Both payload hashes are recorded separately in the mapping. Colliding authored names such as `._filename` are preserved through suffixes. Duplicate explicit directories retain separate output directories and metadata records. Classic filenames default to Mac Roman; Filename encoding reopens the listing with an override. Raw name bytes are recorded in the mapping. Known-byte Mac Roman, Japanese and Cyrillic name fixtures are tested with explicit encoding overrides; this does not qualify every script character. Encoding availability depends on the pinned runtime. Generated stored/RLE fixtures, encrypted upstream fixtures, and a private real-world StuffIt/StuffIt 5/BinHex/MacBinary corpus have been exercised. See the [beta 4 support matrix and handoff](assessment/reports/packsmith-beta4.md) for the demonstrated subset and oracle limits. StuffIt X remains unverified.

Create builds a ZIP or 7z from selected files. Add, Replace, Rename and Remove modify the opened archive. A replacement archive is written separately and every payload is checked before committing it. Successful edits retain an original `.backup-<id>` file beside the archive. No automatic backup pruning is performed.

Extraction creates a new archive-named folder inside the chosen destination. Duplicate names, case collisions and conflicting file/folder names are preserved with suffixes. Reserved Windows names are encoded. A mapping JSON records each original entry ID, archive path and actual output path. Absolute paths, traversal and links stop the job. Destination directory reparse points are rejected and ancestor handles block replacement while writing. File modification times are preserved; ACLs, owner IDs and other metadata are not applied.

Passwords travel through private stdin pipes, without arguments or logs. The worker supports encrypted ZIP/7z and the tested StuffIt reads. Use Password to change a password after a failed attempt; creation-password controls are not yet exposed in the GUI.

The expandable Last job result panel records committed output, file/fork counts, available source-checksum coverage, filename mappings, and cleanup/recovery outcomes. It provides Open output folder, View mapping, and password-redacted diagnostic copying. Success requires a valid completion event and a normal zero worker exit. Source checksums that do not exist are reported as verification limits. Checksum failures prevent committing output; salvage extraction is unavailable. Transient Windows file-handle locks during extraction commits receive a bounded, cancellable retry. Tabs and other control characters are displayed as escapes, and archived markup remains plain text. Large BinHex-wrapped StuffIt archives are checked from the inner source outward to avoid false CRC failures after shared-stream resets.

## Export for Classic Mac

For legacy archives, choose **Classic Mac â†’ Export for Classic Macâ€¦** (Ctrl+M) or Export All (Ctrl+Shift+M). Review strict Mac Roman/HFS naming or approve mapped names in the native mapping table. Packsmith commits one verified ZIP containing MacBinary II files, a preservation report and restoration instructions. Tested restoration uses StuffIt Expander 5.5 on System 7.6 and Mac OS 9. See the [beta 4 support matrix and handoff](assessment/reports/packsmith-beta4.md) for the measured subset and limits.

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
python tests/run_beta4.py
python tests/classic_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python scripts/classic_qualification.py
```

Alternative SDK/compiler locations can be supplied with `--qt` and `--compiler`. The build rejects a modified/different SDK reference, different compiler version or different Qt version. The package manifest records hashes and imported DLL closure. This recipe currently requires provisioned local toolchains; it is not a fresh-machine bootstrap installer. Package tests remove developer PATH entries. Automated relocation evidence is separate from the user-reported clean-Windows application pass; fresh-machine source builds remain unverified.

The first build freezes the compiler, runtime, SDK trees and engine DLL by content hash in `assessment/evidence/desktop-preview/build-inputs.lock.json`; later builds reject drift. The legacy helper separately freezes its inputs under `assessment/evidence/desktop-legacy/`. Its provisioned Objective-C toolchain is Clang/lld 22.1.8, GNUstep Base 1.31.1, libobjc2 2.2.1 and a private GCC 16.1 runtime. It uses the pinned, patched XAD experiment built by `assessment/scripts/build_xad_windows.py`; see `assessment/reports/windows-first.md` for acquisition and ABI requirements. `STRICT_APPLE_COMPATIBILITY=1` is required. The helper's DLLs stay under `workers/legacy/`, separate from Qt's runtime.

Native GUI smoke and legacy recovery tests require Python `psutil` and exercise the qwindows platform plugin, actual archive listing, navigation, search/selection, fork extraction and forced-worker recovery. The model/controller/UI targets also require the pinned SDK's Qt Test development module; Qt Test is not shipped in the product. Current receipts and captures are under `assessment/evidence/beta4/`; earlier receipts remain historical.

Run `python scripts/qualify_legacy.py --corpus F:/Unarchiver` to qualify a local top-level `.sit`/`.hqx`/`.bin` corpus read-only. Private extracted payloads and per-entry inventories stay under ignored `assessment/outputs/`; public receipts contain hashes, methods, counts and failures. This checks output against decoder stream hashes and independently checks BinHex wrapper CRCs, but does not substitute for an original Mac extraction oracle.

## Current boundaries and next gates

* Windows x64 preview only. macOS/Linux desktop builds remain deferred.
* ZIP/7z creation/editing and the tested StuffIt/BinHex extraction subset are implemented. TAR creation, multipart qualification and shell integration remain work.
* Links are rejected. Legacy file forks and FinderInfo are preserved as AppleDouble, and modification times supplied by XAD are applied. Classic dates contain no timezone; this XAD revision uses the current local UTC offset, so historical daylight-saving dates can shift by an hour. Directory dates, creation dates, comments, extended attributes, ownership and ACLs are not applied. Filename script coverage and realistic StuffIt X fixtures remain open.
* Normal cancellation cleans up staging. A forcibly terminated worker leaves quarantined staging; the GUI uses a token-checked recovery worker to clean it after exit or at the next launch. Ambiguous archive-commit failures retain recovery files for review. Power-loss recovery and filesystem failure injection remain release gates.
* The extraction containment checks do not constitute a hostile same-user race audit. Disk exhaustion, backup restoration after ambiguous filesystem failures, complete spoken screen-reader qualification, Windows contrast/theme testing and installers remain open gates. The clean-Windows application pass is user-reported; automated receipts and fresh-machine source builds are unavailable.
* Archive-update verification currently uses the same engine; independent ZIP readers and 7-Zip CLI checks are exercised by the test harness. Production update handling needs broader metadata/corpus coverage.

The original reuse/dependency assessment remains under `assessment/`; this prototype does not make its incomplete preservation or platform gates pass.
