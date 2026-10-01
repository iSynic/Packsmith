# Windows desktop preview handoff

The application is now named **Packsmith**. The current executable is `dist/Packsmith-preview/Packsmith.exe`, with a `packsmith-worker.exe` helper. Both generated icons have PNG size variants and ten-frame Windows ICOs under `assets/icons/`; the exact generation prompts are recorded there. The application icon is embedded for Explorer and loaded by Qt for the window/taskbar/header; the companion archive-document icon is used by Open. Native version strings identify Packsmith. [Branding checks](../evidence/desktop-preview/branding.json) verify embedded icon payloads, version strings and recovery from the previous Unarchiver journal directory. The hidden staging/token format remains compatible.

The native Windows GUI is implemented in `app/`, independently of the unchanged historical fork. It uses C++17 and Qt 6.10.2 Widgets, with a private Qt Core worker loading 7-Zip 26.03 through its DLL interfaces. The prototype opens ZIP/ZIP64 and 7z, searches/sorts real entries, extracts selected files/folders, tests integrity, creates ZIP/7z and adds/replaces/removes/renames entries. It now integrates decoder-only XAD for read-only StuffIt/BinHex extraction with AppleDouble preservation. See the [legacy handoff](windows-desktop-legacy.md) for coverage and limits.

This is a local development preview. The Windows-first assessment's full v1 legacy-preservation and creation baseline is still incomplete. Nothing was published, installed into the shell or claimed as release-qualified.

## Evidence and build inputs

* Build: [log](../evidence/desktop-preview/build.log), [frozen inputs](../evidence/desktop-preview/build-inputs.lock.json), [package manifest](../evidence/desktop-preview/package.json).
* Worker behavior: [mainstream receipts](../evidence/desktop-preview/worker-tests.json), [legacy receipts](../evidence/desktop-legacy/tests.json). Renamed packaging retains all 29 passing behavior checks and six GUI checks.
* Native widgets/controller: [receipts](../evidence/desktop-preview/gui-smoke.json), [ordinary archive capture](../evidence/desktop-preview/mainstream/gui.png), [100k capture](../evidence/desktop-preview/scale-100k/gui.png).
* Existing baseline, 11 source checkouts and 36 archive-fixture hashes still pass [handoff integrity](../evidence/handoff-verification.json). Historical assessment failures remain recorded separately.

The compiler/runtime is MSYS2 MinGW64 GCC/GCC-libs 15.2.0-8, with content hashes for GCC, cc1plus, CMake, Ninja and runtime DLLs. The entire acquired Qt SDK tree and 7-Zip SDK tree are hashed. The SDK checkout is `0766b733fe3e06dd2a7f9a3cfbf2108ac73abd17`; the unmodified official DLL is `65e4c1f855f9ef6e8f0f5df8e3f27d9eb5f07311408639da0a1ca0b8f4871b0d`. Further builds reject drift. These are observed local toolchain hashes, not clean-machine acquisition proof.

`python scripts/build_windows.py` assembles the GUI, qwindows/style plugins, private worker, isolated legacy decoder and imported runtime DLL closures. Package footprint is approximately 110 MiB. GCC/winpthreads notices, 7-Zip license, legacy runtime notices and the vendor Qt SPDX are included. Exact source/relink artifacts and complete third-party notices remain public-distribution gates. The recipe also produces a local portable ZIP.

## Observed behavior

The worker suite currently has 18 passing behavioral tests. It covers numeric duplicate-entry selection, Unicode filenames, duplicate/case/file-directory collision preservation, reserved names, traversal/absolute-path rejection, archive links, destination junctions, long paths, ZIP64, damaged archives, unchanged destination files, ZIP/7z creation and edits, empty archives after deleting the last entry, encrypted headers retained after updates, stale fingerprint rejection, cooperative cancellation and forced-update termination/recovery. Python's ZIP reader independently checks ZIP payloads; the official 7-Zip CLI checks the 7z output through a separate execution path. That CLI shares the engine implementation and is not an independent codec oracle.

The six GUI smoke checks run the native **qwindows** platform from a copied Unicode/space installation directory, with developer PATH and Qt environment overrides removed. They use actual archive data and the GUI's search/selection model, compare ZIP selections against Python's ZIP reader, compare legacy data/resource bytes against generated oracles, check legacy edit actions and render widget captures. Mainstream and legacy recovery checks kill an extraction worker after the GUI journals staging and verify automatic cleanup through the controller.

Exact timings, sampled process-tree memory and executable hashes are in the linked JSON. Recent runs loaded the 100,000-entry ZIP in approximately 1.6–1.7 seconds, with interaction gaps below 100 ms for that sample. The first ordinary Unicode fixture still has a roughly 0.8-second font-render stall. These are local samples, including a concurrent behavior-test run; they are not cold/warm distributions or acceptance guarantees. The first Unicode font-render cost remains a performance issue.

Extraction plans outputs before writing, retains all collisions through suffixes and a mapping, rejects links/traversal, uses extended Windows paths and holds non-reparse destination ancestors against replacement. It publishes only a completed folder. Cooperative cancellation cleans staging. Interrupted jobs are token-checked before cleanup; ambiguous update-commit errors retain recovery artifacts. Updates verify replacement payload hashes and leave an original backup beside the archive. A test proves the original cannot be opened for writing during a pending update, and forced termination leaves its byte hash unchanged.

## Revised engine choice and next acceptance gates

The initial GUI uses **one 7-Zip DLL worker for both ZIP and 7z**. This removes an extra runtime/backend from the preview while satisfying its demonstrated mainstream operations. libzip remains an assessed option if opaque ZIP metadata or an unsupported update operation demonstrates a gap. The DLL API closes the assessment's CLI password and duplicate-name selection concerns; this changes the first implementation assignment, not the legacy preservation requirement.

1. Qualify the exact portable bundle and build recipe in a fresh standard-user Windows 11 VM/runner. The current sanitized-PATH/relocation tests do not substitute for that proof. Produce complete dependency acquisition, source/relink artifacts and installer/upgrade receipts.
2. Add TAR/TAR.GZ creation and metadata fixtures. Use the existing 7-Zip adapter first; add a specialist only for a demonstrated preservation gap.
3. Broaden the integrated XAD decoder's legacy corpus and metadata qualification. The desktop adapter now preserves tested data/resource forks and FinderInfo through protected staging; it does not use the assessment helper's overwrite/glob extraction interface. Real StuffIt X/Compact Pro/LZX fixtures, script encodings, historical timestamps and independent legacy oracles remain mandatory.
4. Broaden mutation preservation: opaque ZIP extras/comments, directory metadata, resource sidecar pairing, encrypted replacement entries and mixed-encryption archives. Version the worker contract and add typed errors/backpressure before multiple backends.
5. Test true disk exhaustion, commit-failure/power-loss recovery, adversarial same-user filesystem races, accessibility/screen readers, keyboard-only operation and cold font startup. Current native rendering/controller proof does not establish all of these.

Windows remains the active platform. macOS/Linux source portability and native qualification are deferred. This preview closes the first archive-fed GUI/controller and mainstream worker milestones; it does not qualify the complete release.
