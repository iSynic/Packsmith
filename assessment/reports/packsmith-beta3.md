# Packsmith beta 3 current-state handoff

Beta 3 adds **Classic Mac → Export for Classic Mac…** (Ctrl+M) and **Export All for Classic Mac…** (Ctrl+Shift+M). The portable Windows candidate is unsigned and unpublished. Qt, compiler and archive engines remain pinned. Beta 1/beta 2 assets and historical receipts are preserved.

## Export contract

Selection uses real engine IDs: selected entries, otherwise the current folder; search requires selection. Export All supplies explicit `all` scope. Virtual folders expand to real descendants and retain duplicate records. Mainstream creation/editing behavior is unchanged.

Preflight reviews a deterministic plan against the archive fingerprint, entry IDs and filename encoding. Strict Mac Roman/HFS names of at most 31 encoded bytes are the default. HFS comparison weights detect equivalence collisions. Non-ASCII or Windows-unsafe transport folders, control characters, long names, duplicate directories and transport/decoded-name conflicts require explicit mapped-name approval. Suffixes derive from stable IDs. Incorrect encoding selection can change interpreted names; raw available name bytes/components remain in the report.

Execution reproduces the reviewed plan and verifies available source checksums. It stages one MacBinary II file per logical file, including empty/resource-only files, while retaining empty folders. The existing 7-Zip backend creates an unencrypted Deflate ZIP. ZIP64, 65,535 or more records, and package/uncompressed sizes reaching 2 GiB are rejected. The ZIP is reopened; every header, CRC, fork hash and padding extent is verified before committing a fresh file. Existing destinations are rejected. Cancellation/corruption publishes no completed package. Terminated workers retain token-checked recovery staging. GUI success requires completion and normal zero worker exit.

Every package contains ASCII transport paths under `Files/`, `Report.json` and `Read Me.txt`. The manifest includes interpreted/raw original components, restored names, full available FinderInfo, separate fork hashes, checksum coverage, engine revision and exporter version. Neither manifest nor guide contains passwords or absolute source paths. Raw 1904-era dates are written directly; unavailable dates remain unknown and yield zero header fields. Details show these wall-clock values separately from beta 2's interpreted Windows timestamps.

Finder flags mask `0xfc0e` preserves alias, invisible, bundle, name lock, stationery, custom icon and label color. Initialization/desktop state, icon positions, containing-folder IDs and other flags are report-only. Directory metadata, comments, extended Finder fields and unavailable lock/protection bits are not restored. Renames can break application references; application compatibility is not guaranteed.

The writer follows the [MacBinary specification](https://github.com/MacPaw/XADMaster/wiki/MacBinarySpecs). HFS weights derive from MIT-licensed machfs 1.3; the notice ships with the materials. Isolated metadata-only patches expose raw dates from StuffIt, StuffIt 5 and MacBinary parsers. Reference checkouts and decompression algorithms remain unchanged. XAD remains at `7cb9ee0abbb163f261e4cb74501e15067032319c`; detector, 7-Zip 26.03, Qt 6.10.2 and GCC 15.2 remain pinned by the existing build locks.

## Independent restoration and extraction

Tests used isolated copies of writable system disks, preferences and NVRAM. Original disks, ROMs, software and archives were not changed. The tiny generated transfer first qualified known data-only/resource-only/combined forks, accented names and nested folders. Actual worker output then qualified empty files/directories and five generated files, alongside four real archives.

**StuffIt Expander 5.5** passed on **Basilisk II/System 7.6** and **SheepShaver/Mac OS 9**. The installed Expander 7.0.3/build 277 crashed on the transfer ZIP, including a JIT-disabled retry. Qualification explicitly used the existing 5.5 application instead; 7.0.3 remains unqualified.

Procedure: expand the outer test bundle, then explicitly expand its individual ZIPs. For these fixtures, 5.5 decoded MacBinary during ZIP expansion. The package guide still directs users to expand remaining `.bin` files in their existing folders. For original-software comparison, expand the originals bundle and drag its folder to Expander. Shut down before reading HFS. Original Hax top-folder collisions receive Expander's `.1` suffix; complete file counts distinguish the two copied outputs. Intentional mapped directories are compared through the manifest, without claiming original directory-name fidelity. Tests used explicit Mac Roman decoding; other encoding interpretations need their own qualification.

An independent machfs/macresources reader was validated with known bytes, resource records, dates and type/creator. Each shut-down test disk passed **297 file comparisons**: 292 real files plus five generated files. Original-software extraction and restoration agreed on data/resource payloads, available raw dates, type/creator and portable flags. Empty directory presence also passed.

| Fixture/variant | Windows evidence | Original-software and restoration evidence |
|---|---|---|
| `hax-13.hqx` | BinHex → classic StuffIt, LZ+Huffman/None; 131 logical entries | 124 files on both systems |
| `HAX1R3.BIN` | MacBinary → StuffIt 5, Arsenic/None; 132 logical entries | 125 files on both systems; absent wrapper checksum remains a limit |
| `dark-towers-ks.hqx` | BinHex → older StuffIt, LZ+Huffman | Four files on both systems |
| `BOutS 1.2.sit` | StuffIt 5, Arsenic/None | 39 files on both systems |
| Generated worker package | Empty/data/resource/combined files, accents, nested/empty folders | Five files plus empty folders on both systems |
| Other local legacy archives | All 22 local archives passed engine extraction/fork checks | Original-Mac evidence limited to the four real archives above |
| Other StuffIt methods, StuffIt X and encodings | Parser availability/earlier engine evidence only | Unverified |

**Accepted resource limitation:** System 7.6/Expander 5.5 changes reserved resource-header bytes 16–255. The corpus run had 152 restored forks and 150 original-extraction forks with different raw hashes; all changes stayed in that region, with independent resource records and payloads equal. Mac OS 9 had no raw fork differences. Packages preserve exact original bytes. Any length change, difference outside that region or altered resource record fails qualification. This exception was explicitly accepted by the user.

Public receipts: [tiny restoration](../evidence/beta3/classic-restoration.json), [corpus oracle](../evidence/beta3/classic-corpus-oracle.json), [Windows corpus](../evidence/beta3/legacy-corpus.json). Private per-file inventories, extracted files, disks, ROMs and software remain under ignored outputs and outside Git/release assets.

## Reproduce and deliver

```powershell
python scripts/build_windows.py
python tests/worker_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/legacy_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/classic_test.py dist/Packsmith-preview/workers/packsmith-worker.exe
python tests/run_beta3.py
python tests/gui_smoke.py
python tests/branding_test.py
python scripts/qualify_legacy.py
python scripts/package_beta.py --prepare-only
python tests/relink_test.py
python assessment/scripts/verify_assessment.py
python scripts/package_beta.py --candidate
```

Private oracle setup uses `scripts/classic_oracle.py` and `scripts/classic_corpus_oracle.py`, local tool paths and explicit UI expansion/shutdown steps. It does not redistribute proprietary inputs or certify unattended emulation. Native model/controller checks use Qt's model tester; UI checks include search/current-folder scope, plain-text preflight, keyboard export through the real worker and durable results. Original and modified helpers relink from the supplied materials and execute known-fork/checksum regressions.

See [beta 3 evidence](../evidence/beta3/) for final hashes, counts and measurements. The 100,000-entry native smoke listed in 2156 ms, peaked at 250.0 MiB GUI memory and had a 388 ms maximum heartbeat gap, including instrumentation. These are developer-machine measurements.

Final acceptance includes 22 mainstream worker tests, 14 legacy tests, 14 classic-export tests, two native model/controller/UI executables, eight native GUI smoke scenarios, branding/previous-name recovery and eight original/modified relink scenarios. Classic regressions include a sharing-locked final ZIP commit interrupted by worker termination, failed cleanup/retry, corruption, wrong passwords, stale plans/fingerprints, scope, limits, HFS collisions and raw-date byte checks. The source archive remains unchanged and no destination is published in those failure cases.

## Certification limits

Process `TZ` variants produced identical MacBinary bytes; changing Windows system timezone/daylight-saving settings itself is unverified. Raw export dates avoid a timezone round trip; existing interpreted timestamps retain their beta 2 limitation. Clean-machine Windows, screen readers, power loss, actual disk exhaustion, every filesystem race/failure, broader legacy variants, installers, signing, publication and other platforms remain separate. Worker termination/sharing-lock checks do not certify power loss. No production release is qualified.
