# Packsmith beta 2: current-state handoff

This report supersedes the preview-era application status in the earlier Windows desktop reports. Those reports, the original engine assessment, beta 1 receipts and published beta 1 assets remain historical evidence. Beta 2 is an unpublished portable Windows x64 candidate built from a recorded workspace snapshot, not a tagged release.

## Implemented behavior

- Folder navigation uses exact engine components, breadcrumbs, Back/Up and keyboard activation. Duplicate/case-variant files keep distinct engine IDs. Virtual folders group original paths without inventing IDs; duplicate explicit directories retain all IDs and separate mapped metadata/output directories.
- Extract uses selected real entries or the current folder; global search requires a selection. Extract All is explicit. Empty `entries` scope is rejected before output creation. Unique real directories retain mainstream rename support; virtual/duplicate groups cannot be renamed or replaced as one record.
- Archive models and worker lifecycle/results are separate from the window. Completion requires the terminal event, normal zero exit and committed-output confirmation. Start/crash/malformed/missing-terminal failures receive visible results. Password codes pass through the legacy adapter and retry after exit/cleanup.
- The session-local result panel retains output/file/fork counts, source-checksum limits, mappings, warnings and recovery paths. Cleanup does not erase the original error. Diagnostics redact the session password. Entry details show components, fork presence, encoding, Finder type/creator/flags and interpreted timestamps.
- Event parsing yields between short batches; sorting uses cached display fields. Cancellation remains cooperative with the existing watchdogs. Fresh-folder commits retry Windows access-denied/sharing/lock errors for at most one second without overwriting a target.

The commit retry addresses a demonstrated corpus failure. Earlier runs are retained in `legacy-corpus-first-pass.json` and `legacy-corpus-before-retry.json`; the latter contains actual Windows error 5 failures. Native marker-lock tests exercise a failed commit followed by a successful retry. Persistent update locks retain the exact original and manual recovery candidates. Cleanup locks retain the ownership marker and allow a later retry.

## Demonstrated support

| Format or behavior | Evidence | Qualification boundary |
|---|---|---|
| ZIP/7z list, extract, test, create and edit | Worker tests; independent Python ZIP reader and official 7-Zip CLI; generated Unicode/collision/unsafe/large fixtures | Broad metadata round trips, multipart and filesystem race audits remain open |
| Classic StuffIt stored/RLE | Redistributable generated payloads, separately checked data/resource bytes and FinderInfo | Exact generated scenarios, not every classic method |
| StuffIt LZ+Huffman and StuffIt 5 Arsenic/None | Local real archives covering older/newer Realmz, HAX and other applications; fork hashes and source-checksum coverage recorded | User-owned corpus is not redistributable; original Mac extraction fidelity is unverified |
| Encrypted StuffIt | Existing upstream seven-/twelve-character-password fixtures, correct/wrong/missing-password checks and known fork hashes | Other encryption variants are unverified; absent checksums are reported |
| BinHex | Generated fixtures, corrupt header/data/resource CRC rejection and independently checked real BinHex wrapper CRCs | Wrapper CRC proof is not an independent oracle for inner StuffIt decoding |
| MacBinary | Generated BinHex → MacBinary → StuffIt fixture, upstream encrypted wrappers and real `.BIN` files | MacBinary has no data/resource source CRC; verification limits remain visible |
| Resource-only files and duplicate names/directories | Generated exact payload fixtures and real corpus; AppleDouble entries 2/9 checked separately | Windows sidecars must stay with mapped data files; unsupported metadata is reported |
| StuffIt X, other Mac script encodings and all legacy methods | Parser/override availability only | Unverified; no expanded support claim |

BinHex's pinned parser does not automatically mark `.hqx` payloads as embedded archives. BinHex-in-BinHex therefore remains a payload to extract, rather than automatic recursive expansion. No engine source rewrite was made to change that policy.

## Reproduce and inspect

```powershell
python scripts/build_windows.py
python tests/worker_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/legacy_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/run_beta2.py
python tests/gui_smoke.py
python tests/branding_test.py
python scripts/qualify_legacy.py --corpus F:/Unarchiver
python scripts/package_beta.py --prepare-only
python tests/relink_test.py
python assessment/scripts/verify_assessment.py
python scripts/package_beta.py --candidate
```

Current receipts and native captures live under [beta 2 evidence](../evidence/beta2/). The shared engines, frozen toolchains and original reference checkouts are unchanged. Core tests use Qt's model tester and cover duplicate/implicit/literal-slash folders, empty scopes, sorting, controller event/exit failures and buffered-event draining. GUI tests exercise actual qwindows widgets, keyboard navigation, file details, plain-text rendering and selection preservation.

The real corpus qualification writes its per-entry fork inventories and extracted payloads under ignored `assessment/outputs/beta2-corpus/`. Public receipts record provenance, archive hashes, methods, counts, output-inventory digests, source-checksum coverage, timings, peak worker memory and failures. It verifies exported bytes against decoder stream hashes, checks FinderInfo and AppleDouble resource payloads, and rehashes originals after every operation. Generated known bytes and the independent BinHex CRC checker provide independent checks for their respective layers. They do not establish a complete original-Mac oracle.

## Final receipts

- 22 mainstream worker tests, 14 legacy tests, two native model/controller/UI executables, eight native GUI smoke scenarios, branding/previous-name recovery and eight original/modified relink scenarios passed. Handoff integrity passed with no errors; original assessment failures remain reported.
- All 22 local corpus archives passed listing, transactional extraction, exported fork-hash/FinderInfo checks and unchanged-original checks. Generated coverage consists of 21 redistributable fixtures.
- `hax-13.hqx`: 131 logical entries, 79 data forks, 70 resource forks and 46 empty data files; 150 source-checksummed streams including the wrapper, zero unchecked streams. The independent BinHex checker also validated header/data/resource CRCs.
- `HAX1R3.BIN`: 132 logical entries, 78 data forks and 71 resource forks; 149 checked streams and one unchecked MacBinary wrapper stream. That absent source checksum remains visible.
- The final 100,000-entry native run listed in 2404 ms, navigated into its 100,000-file folder in 200 ms and peaked at 255.6 MiB GUI memory. The maximum heartbeat gap was 443 ms, including smoke instrumentation. These are local measurements, not benchmark or clean-machine certification.

## Remaining gates

Fresh Windows 11/standard-user VM qualification, screen-reader/accessibility certification, original Mac extraction comparisons, historical timestamp semantics, other legacy encodings/methods, power-loss testing, actual disk exhaustion, broad update metadata preservation and hostile same-user filesystem races remain unverified. Native sharing-lock/write-failure tests do not certify disk exhaustion or every filesystem failure mode.

Classic dates have no timezone and this XAD revision uses the current local UTC offset. Directory timestamps, creation dates, comments, extended attributes, ownership and ACLs are not applied. Private corpus payloads are excluded from Git, corresponding-source snapshots and beta assets.

Publishing, signing/installers, macOS/Linux, additional engines, creation UI changes and salvage extraction remain separate work. Candidate packaging preserves the exact authored workspace and records its base commit, dirty state and hashes; publication still requires a clean release commit, tag, asset verification and a separate release instruction.
