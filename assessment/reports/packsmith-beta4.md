# Packsmith beta 4: support and current-state handoff

Windows x64 portable candidate, unpublished. The tested beta 2/beta 3 baseline is local commit `56cb5c3`; no push, tag or publication is authorized by this tranche. Beta 1–3 assets and historical receipts are preserved. Candidate packaging records the exact subsequent source commit in its release manifest.

## Product changes

Open, command-line opening, one local regular-file drop and Recent Archives use the same opening path. Multiple files, directories, remote/UNC URLs and replacements during a job, recovery or export review are refused. Successful listing alone records history. File → Remember recent archives is off by default; enabling it stores at most ten normalized paths in per-user QSettings. Disabling or clearing removes paths. No password, encoding override, entry names or destinations are stored. Automated GUI/settings tests use isolated preferences.

File, Archive and Classic Mac menus retain access to operations when the toolbar overflows. Table accessibility includes names, locations, fork sizes and protection; progress/results are named. Phase announcements are deduplicated, terminal outcomes announced once, and diagnostics redact passwords. Dialog dismissal restores focus. Results expand, and Classic export changes use a native table. Mapping review remains attached to its displayed result across subsequent successful listings. System font sizes and palette colors are retained.

`.cpt`, `.lha`, `.lzh` and `.lzx` now route to the existing XAD worker. Detected formats, readable compression names and available StuffIt method IDs travel through listing/error context and entry details. Structured unsupported-codec errors remain distinct from corruption/password errors. Wrapper chains are recorded. Engine detection remains authoritative; qualification hashes are evidence, never an eligibility allowlist.

Compact Pro pairing uses shared checksum/offset/volume identity rather than adjacent display names alone. Its shared resource-then-data CRC is checked before committing output. Same-name independent entries remain distinct. Neither decompression code nor reference source was changed.

## Support matrix

These statuses apply to the specified fixtures and operations, not all archives of a format. Generated cases exercise listing, selected extraction, integrity checks and Classic Mac export, with independent ZIP/MacBinary framing/fork hash checks. Formats remain read-only except for existing mainstream ZIP/7z operations.

| Format/case | Status | Evidence and limits |
|---|---|---|
| `hax-13.hqx`, `HAX1R3.BIN`, `dark-towers-ks.hqx`, `BOutS 1.2.sit` | independently qualified | Fresh beta 4 exported fork bytes and supported metadata compared against original Expander 5.5 output and previously restored files on shut-down System 7.6/Mac OS 9 HFS disks. A new beta 4 ZIP transfer in either guest is not claimed. |
| Existing 22-archive StuffIt/BinHex/MacBinary corpus | engine-advertised/unverified for independent fidelity outside the four cases | All prior archives retained as read-only regressions. Decoder checksums/stream hashes verify output consistency, not independent fidelity. |
| StuffIt methods 0/1/2/3 | known-payload tested | Stored, RLE, literal LZW without dictionary-width transitions, and one-leaf Huffman cases with data/resource bytes. Broader method behavior remains unverified. |
| StuffIt method 6 fixture | failed/unsupported | Structured `unsupported_codec`; test/extract/export fail without published output. This is an expected rejection. Other untested methods and StuffIt X receive no blanket support claim. |
| BinHex → MacBinary → StuffIt nesting | known-payload tested | Generated wrapper chain; source CRCs and both payload hashes verified. Existing nested/corrupt wrapper regressions remain. |
| Compact Pro RLE runs in both forks, paired/resource-only/data-only duplicate names | known-payload tested | Generated forks and shared CRC; corrupted resource bytes prevent extraction/export commitment. Raw classic dates unavailable from the pinned parser remain explicitly unknown. |
| Real LZH-compressed Compact Pro sample `FRED.CPT` | engine-advertised/unverified | Private MacBinary-wrapped sample. Expander's file picker did not offer the prepared input; no original-tool expansion or fidelity claim. |
| LhA stored, header-3/lh5, lh6/lh7 | independently qualified for upstream regular-file payloads; generated stored case known-payload tested | Pinned libarchive upstream expectations for file1/file2. Unix links are listed/tested but rejected by Packsmith extraction; selected regular-file comparisons do not qualify link restoration or every header variant. |
| Actual compressed Amiga LZX | independently qualified for one generated archive | Original Aminet unLZX 1.1 extracted exact known bytes from a generated compressed LZX archive. CAB LZX is unrelated evidence. Merged groups, other header/metadata variants remain unverified. |
| Mac Roman, Mac Japanese, Mac Cyrillic names | known-payload tested | Explicit overrides, known source bytes/raw components and mapped Classic export. Japanese uses a common Shift-JIS subset; complete script coverage is unverified. |

Legacy extraction preserves data/resource fork hashes separately and FinderInfo through AppleDouble. Classic export preserves representable type/creator/portable flags, raw dates where available, and report-only metadata. No fork/Finder/date is invented when absent. Compact Pro exposes interpreted timestamps but lacks raw classic date fields here; Classic export uses zero/unknown. The historical current-offset/DST interpretation limitation remains for Windows extraction. Directory metadata, comments, application references after renaming and all FinderInfo bytes are not restored.

## Qualification procedures and blockers

`tests/coverage_fixtures.py` generates public known-byte fixtures and a hashed case manifest. `scripts/classic_qualification.py --manifest …` consumes it; an optional private manifest adds nonredistributable cases without committing payloads. Receipts record detected format/method/wrapper chain, revisions, checksum coverage, expected hashes and outcomes. `assessment/qualification/classic-oracles.json` replaces the four-case hard-coded oracle list; `scripts/classic_corpus_oracle.py refresh` creates new exports and compares them through independent HFS inventories. The reader is checked against known control forks/catalog values before comparisons.

The prior narrowly accepted resource-header exception is unchanged: only reserved bytes 16–255 may differ, with identical resource records/payloads. Any other difference fails. Private inventories, images, ROMs, applications, archives and extracted content remain ignored and excluded from candidates.

Acquisition is bounded to two working days; unresolved cases do not block unrelated usability delivery. Next experiments: recognized original Compact Pro input/application for LZH and paired forks; more original-tool StuffIt LZW/Huffman/method variants; independent Amiga LZX merged/stored/header variants; additional LhA headers and full Mac script character fixtures. No shipped engines or broad codec rewrites were added. Original unLZX and the auxiliary LZX compressor are qualification tools only.

Clean-Windows application testing is **completed by user report**. Commands, machine details and automated receipts were not supplied. Fresh-machine source builds and system timezone/DST changes remain separately unverified. Expander 7.0.3's cause is undetermined; investigation is deferred until a reproducible bug report. No guarantee of that emulator/tool path is made.

## Validation and delivery

Current receipts live under `assessment/evidence/beta4/`. The acceptance runner executes worker/legacy/Classic export tests, Qt model/controller/native GUI checks, generated/private qualification, the 22-archive corpus, shut-down HFS comparisons, native recovery, branding, relink, presentation, 100k performance and integrity checks sequentially. Native GUI and QSettings tests are isolated from user history.

The presentation suite forces Qt 100%/150%/200% scaling and tests enlarged font/contrast palettes. This is distinct from changing Windows display scaling, contrast themes or system text settings. Qt accessibility interfaces/focus/announcement events are automated evidence; full spoken Narrator qualification is recorded separately and unavailable checks remain unverified. Performance compares listing time/peak memory to beta 3 on the same machine, with no competing owned build/test/emulator jobs. Existing user applications are left alone.

Final measured outcomes are recorded in `acceptance.json`, `performance.json`, `presentation/checks.json`, `classic-qualification.json`, `classic-corpus-oracle.json` and `handoff-verification.json`. Package validation checks matching HEAD source bytes, exact runtime/relink materials, ZIP integrity, exclusions and SHA-256 digests. The candidate is portable and unsigned; installer/signing, associations, publication, additional platforms, engine updates and archive-creation expansion remain deferred.

## Final measured outcome

The final automated gates passed: 22 worker tests, 14 legacy tests, 14 Classic export tests, model/controller/native UI checks, eight native GUI/recovery scenarios, four presentation configurations, 18 manifest qualification cases (including two expected safe failures), the 22-archive corpus and original/modified relinking. Independent HFS comparison passed for 297 files on each of System 7.6 and Mac OS 9, including the known generated control. The eleven reference/baseline checkouts and 247 historical evidence/candidate files remained unchanged.

The same-machine 100,000-entry listing took 2.094 seconds (-2.88% versus beta 3), with 246.5 MiB peak GUI RSS (-1.39%) and a 445 ms maximum event gap. No 20% regression or one-second stall was observed. Core model construction took 1.073 seconds; folder navigation took 5 ms.

The recorded Narrator session is partial: Windows UIA exposes the named controls/cells, command-line opening/search worked, and row selection/Enter-to-details worked after a scan-mode toggle. The automation focus field remained stale and modal keyboard targeting was inconclusive. Spoken output and full Narrator-assisted workflows remain unverified. The owned processes and computer-use session were closed before final code/documentation work.
