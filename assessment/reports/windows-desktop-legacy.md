# StuffIt and BinHex Windows preview

The Windows desktop preview now lists, extracts selected entries and tests classic `.sit` and `.hqx` archives. The table distinguishes data and resource-fork sizes. Legacy archives are read-only in the GUI and worker; ZIP/7z creation and editing retain their existing backend. No release was published and the historical source/reference checkouts remain unchanged.

## Architecture and frozen inputs

`app/xad_stream.m` is a decoder-only Objective-C process. It accepts an archive and optional password/encoding through a private pipe, returns logical entries and checksum-checked fork streams, and receives no destination. `app/legacy_worker.h`, inside the Qt Core worker, owns output planning, protected filesystem writes, AppleDouble assembly, verification, staging and commit. This bypasses the assessment probe's lossy overwrite/glob extraction policy.

XADMaster is pinned to unreleased upstream commit `7cb9ee0abbb163f261e4cb74501e15067032319c`; UniversalDetector to `4eb832d999628edcd3d134e46bd35357c8c99a85`. The existing isolated source copy retains only the two recorded Windows adaptations: wide-path unlink and reversible charset conversion. No codec rewrite or reference-source modification was made. The build checks source-copy equivalence and exact patch text before updating the cached static libraries through their native CMake recipe.

The Objective-C side uses Clang/lld 22.1.8, GNUstep Base 1.31.1, libobjc2 2.2.1, `STRICT_APPLE_COMPATIBILITY=1` and the assessed GCC 16.1 runtime overlay. Qt remains on its separate GCC 15.2/Qt 6.10.2 runtime. XAD dependencies are private under `workers/legacy/`; the decoder starts by absolute path. A Windows kill-on-close job owns decoding before the request is sent, preventing an orphan after worker termination. This is lifetime management, not a security sandbox.

Evidence:

* [Frozen compiler/header/source inputs](../evidence/desktop-legacy/build-inputs.lock.json), [build command and linked-library hashes](../evidence/desktop-legacy/build.json), [build log](../evidence/desktop-legacy/build.log), [library rebuild log](../evidence/desktop-legacy/libraries.log).
* [Generated fixture provenance and archive hashes](../evidence/desktop-legacy/generated-fixtures.json), [behavior receipts](../evidence/desktop-legacy/tests.json).
* [Native GUI checks](../evidence/desktop-preview/gui-smoke.json), [StuffIt capture](../evidence/desktop-preview/forks-sit/gui.png), [BinHex capture](../evidence/desktop-preview/forks-hqx/gui.png), [legacy GUI recovery](../evidence/desktop-preview/recovery-sit/gui.json).
* [Full package and executable hashes](../evidence/desktop-preview/package.json), [original runtime acquisition/build assessment](windows-first.md), [dependency inventory](dependency-inventory.md).

These are provisioned-machine builds and native sanitized-PATH relocation checks. They are not a fresh Windows VM build or install receipt. Static XAD linking and the full dependency closure require corresponding source, notices and suitable relinking materials before public distribution.

## Preservation and failure behavior

The adapter pairs forks using their parser-specific extent/identity, rather than assuming repeated names are the same file. This preserves a resource-only duplicate followed by a data-only file as two entries. Resource-only files receive an empty data file. Classic filenames default to Mac Roman, with a GUI override and raw-name bytes in the output mapping. Literal slash/backslash/colon characters inside a Mac component are encoded rather than interpreted as Windows path syntax.

The planner reserves data paths and `._` paths together, preserving duplicate/case collisions and authored sidecar-looking names. It rejects traversal, absolute components, links and special files before writing. The existing safe destination tree rejects reparse points and holds ancestors against replacement. Extraction produces a new folder and publishes it only after all selected fork sets, sizes and available source checksums pass. Cancellation, corrupt data/resource forks and wrong passwords leave no committed extraction. Source handles prevent writes during the job; stale listing fingerprints are rejected.

AppleDouble uses magic `0x00051607`, version `0x00020000`, entry 2 for resource bytes and entry 9 for 32-byte FinderInfo. The mapping records each entry's original/raw names, interpreted encoding, actual paths, interpreted modification time and separate data/resource SHA-256 hashes. Fork payload hashes are checked independently of sidecar-container bytes. It also records source-checksum coverage: decoded streams without a source checksum are reported explicitly, rather than being described as checksum verified.

Supported BinHex/MacBinary archive wrappers expand to their inner files. Wrapper data/resource streams are checked before commit. Expanded wrapper bytes and metadata are not reproduced alongside the inner extraction. Recognized embedded formats outside the supported fork-pairing adapters remain decoded wrapper files. MacBinary decoding is exercised by the upstream encrypted StuffIt fixtures.

Normal cancellation removes partial staging. Forced worker termination also kills the decoder; token-checked recovery removes the quarantined stage. The native GUI recovery check exercises the controller's journal and cleanup worker, in addition to process-level tests. No archive mutation is offered for legacy formats.

## Verified scope and next checks

Twelve legacy behavior tests pass alongside eighteen mainstream worker tests and eight native GUI checks. Legacy fixtures cover independently generated stored/RLE StuffIt and BinHex data/resource bytes, Finder type/creator/flags, Mac Roman, resource-only files, duplicate names, sidecar/case collisions, selected folders, reserved/literal filenames, wrapped archives, corrupt header/data/resource checksums, truncation, stale IDs, invalid encoding, unavailable destinations, password failures, cancellation and forced recovery. Upstream encrypted StuffIt fixtures exercise both tested password lengths and expected data/resource hashes. These hashes and generated format builders are useful regression oracles; they are not an independent original-Mac-application comparison.

### Wrapped BinHex checksum regression

The user-provided `hax-13.hqx` reproduced a false archive-level checksum failure in both the previous Unarchiver and Packsmith previews. Its independent BinHex header, data and resource CRCs pass. Its BinHex data contains a 1,005,963-byte StuffIt archive. The decoder had checked outer wrapper forks before the inner parser's source checksum; opening those outer handles repositions the shared source and invalidates the inner stream's state. The adapter now checks the inner source first, then each wrapper from inside out. No integrity check is bypassed. A generated large wrapper reproduces the old failure on selected extraction, and corrupted wrapper data/resource CRCs still reject extraction with no committed output.

The complete real archive exports 131 logical entries (124 files, seven directories), with 79 data forks and 70 resource forks. All 150 source fork checks pass, including the wrapper; none is unchecked. Exported sizes, fork SHA-256 values, FinderInfo and raw Mac Roman path bytes were checked, and the input SHA-256 is unchanged. The independent CRC check covers BinHex; inner StuffIt decoding remains XAD-based. The original user archive is not copied into the redistributable fixture corpus.

The GUI now displays controls as escapes (`\t` for tabs, `\x20` for spaces in whitespace-only components), while retaining the original names and numeric selection IDs. A local adapter method also fixes raw-name mapping for nested paths: upstream `XADPath.data` omitted the leaf bytes when a parent existed. The frozen reference engine source remains unchanged. Extraction errors display a nonblocking critical dialog that explicitly says no completed output was exported, with the decoder error and archive details. A native GUI fixture verifies the visible dialog and empty destination after a real CRC failure.

Receipts: [independent BinHex CRCs](../evidence/desktop-legacy/hax-binhex.json), [before/after reproduction](../evidence/desktop-legacy/checksum-regression.json), [actual export verification](../evidence/desktop-legacy/hax-extraction.json), [actual archive GUI capture](../evidence/desktop-legacy/hax-gui/gui.png), [failure dialog](../evidence/desktop-preview/bad-large-wrapper-data-hqx/error.png). The user export is at `F:/Unarchiver/Packsmith-extracted/hax-13`; its `packsmith-mapping.json` records original names and mapped output paths. Keep AppleDouble `._` sidecars with the data files, including the 46 empty data files.

Independent BinHex diagnostic:

```powershell
python assessment/scripts/check_binhex.py F:/Unarchiver/hax-13.hqx
```

Broader StuffIt compression methods/versions and realistic StuffIt X remain unverified. `.sitx` is routed to XAD for experiments, but it has no acceptance corpus yet. Non-Roman Mac scripts depend on available Windows code pages and need realistic fixtures. Legacy 100k listings, large real fork payloads and multipart extraction remain unmeasured.

File modification times supplied by XAD are applied and recorded. Classic Mac dates carry no timezone; the current XAD implementation subtracts the current local UTC offset, so historical daylight-saving dates may shift by an hour. Directory times, creation dates, comments, extended attributes, ownership and ACLs are not applied. No claim is made that all archival metadata survives. Resource forks over AppleDouble's 32-bit extent are rejected.

The next legacy milestone is a redistributable real-world `.sit`/`.hqx` corpus checked against original Mac tools, followed by additional StuffIt methods, StuffIt X, script encodings and timestamp interpretation. Fresh Windows 11 standard-user packaging, hostile same-user filesystem races, true disk-full/power-loss faults and accessibility remain release gates.

Reproduce locally after provisioning the pinned assessment engine/runtime and Qt toolchains:

```powershell
python scripts/build_windows.py
python tests/legacy_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/worker_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/gui_smoke.py
python assessment/scripts/verify_assessment.py
```
