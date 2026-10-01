# Unarchiver implementation roadmap

Historical simultaneous three-platform baseline. Superseded by the user's Windows-first direction and the [current roadmap](implementation-roadmap.md). Retained to distinguish earlier estimates and acceptance assumptions from the revised scope.

Develop a new **C++ Qt 6 Widgets** shell with isolated engine workers, conditional on resolving the all-platform legacy build/preservation gates. This is a proposed implementation sequence following the assessment; product integration has not begun. No foundation has passed all release conditions.

Use the [assessment report](assessment.md) and [inventory](dependency-inventory.md) as the evidence baseline. The historical fork remains read-only. Treat pinned XAD head as an experiment for demonstrated StuffIt fixes, not a stable-release substitute without review and regression proof.

## Product scope and engine assignments

The first release is an archive manager with browse/search, selected or full extraction, ZIP/7z creation and editing, TAR/TAR.GZ creation, password prompts, integrity checks, an operation queue, collision decisions, recovery and explicit legacy fork/metadata reporting. Archive preview can begin with file details and safe temporary extraction; automatic launching and external viewers should not precede safe extraction. RAR creation and legacy-format creation are outside v1.

| Format or operation | Initial assignment | Why and acceptance boundary |
|---|---|---|
| Ordinary ZIP/ZIP64 list, extract, create, add, replace, delete, rename and AES encryption | libzip 1.11.4 inside native C++ worker | Typed entry indexes, write progress/cancel and mutations exercised on Windows/Linux. Preserve unsupported extra fields/methods or reject editing; never flatten a resource sidecar unnoticed. |
| ZIP methods unavailable in libzip | Qualified 7-Zip or XAD read-only fallback | Capability probe and explicit selection; do not silently route a mutation through a decoder-only backend. |
| 7z including solid archives, encrypted names and updates | 7-Zip 26.03 inside helper | Creation/mutations/password cases exercised. Prove SDK callback or controlled helper mapping for duplicate entry identity, progress and cancellation. Solid updates need space/time estimates and cancellation tests. |
| TAR/TAR.GZ creation and common extraction | 7-Zip initially; evaluate libarchive API worker if required metadata/streaming cannot round-trip | Initial creation/read cases work. The richer TAR metadata acceptance experiment chooses the final route. Shipping a fourth backend must close an observed gap; Windows bsdtar CLI remains disqualified until its Unicode/crash behavior is resolved. |
| StuffIt, StuffIt X, Compact Pro, BinHex, MacBinary, AppleSingle/AppleDouble, LhA and Amiga LZX | Isolated XAD worker with qualified parsers | Only decoder/preservation role. Current synthetic Linux fork checks pass; realistic variants, Windows runtime and macOS native forks remain mandatory gates. |
| Integrity checking | Assigned reader drains every selected stream and validates supported checksums | Report which checks exist; unverified checksum-free content is not labeled verified. Independent tools validate replacements and fixtures. |

This starting set has three essential engines. libarchive remains a proven assessment/reference tool and a conditional addition. Adapted PPMd/LZMA/WavPack/libxad/WinZip JPEG/crypto stay inside XAD until independent fixtures justify changes. Mainstream operations should avoid XAD's measured expensive 100k JSON listing path.

## Worker and model contract

Keep the Qt archive model and job controller independent of particular engines. A helper contains a library/SDK adapter; the GUI speaks one versioned protocol over local pipes. Native Foundation is used in the macOS legacy worker; the Windows/Linux legacy workers may carry GNUstep/runtime dependencies. The GUI itself needs no Objective-C ABI.

```text
Capabilities(format, operation, options) -> supported features and restrictions
List(archive, cursor, batch_limit) -> stable entry IDs, raw/display names and metadata
Extract(entry_ids, output_mapping, preservation_policy) -> per-entry results
Create(format, entries, options, staging_path) -> staged output
Update(source, changes_by_entry_id, staging_path) -> staged replacement
Test(entry_ids) -> checksum coverage and per-entry results
Cancel(job_id) -> cooperative acknowledgement followed by bounded termination
```

Requests/events carry job ID, request ID, engine revision, protocol version and ordered sequence numbers. Listing batches have backpressure and bounded memory. The UI can browse partial results while loading; virtual model rows should not create a widget per entry. The current synthetic 100k Qt probe shows a viable model/view seam, not a completed listing pipeline.

An entry ID must survive duplicate names within the open archive session: engine plus archive identity plus numeric entry index is preferable to a path-only key. Keep raw name bytes, declared/detected encoding, display path, data/resource stream identities, sizes, checksums, timestamps, permissions, links and Finder fields separately. Enclosing-directory behavior is an explicit output policy; the observed XAD default must not unexpectedly move selected files under an archive-named folder.

Errors should identify operation, entry ID, engine code, category and whether output is complete, partial, cleaned or retained for recovery. Distinguish unsupported format/method, password required/wrong password, missing volume, corrupt content, destination conflict, blocked path, write failure, cancellation and worker crash. Do not claim all per-entry errors mean a wrong password.

Send passwords over the private channel or API callback after a request. Never include them in process argv, serialized job history, command previews, logs or progress events. Clear owned buffers when practical; no claim of perfect memory erasure is made. The measured bare `-p` stdin path is acceptable for isolated experiments; a product helper should expose a structured password callback instead of depending on localized console prompts. Set bounded retries and clear distinction between password cancellation and archive cancellation.

Progress includes phase, processed entries/bytes, estimated total and whether the total is known. Extraction of a selected member from a solid archive may require decoding earlier data; expose that work honestly. Cooperative cancellation stops at safe engine boundaries, reports cleanup and then escalates to helper termination if necessary. The measured 2–5 ms Qt helper-kill latency does not establish archive cleanup latency.

## Extraction and preservation policy

Resolve duplicate names, case-folded conflicts, Windows device/trailing-dot names, long paths and existing files before writing. Default to preserving both with explicit safe output mappings; allow overwrite only through a concrete user decision. Retain the original archive entry name in a preservation manifest when a filesystem cannot represent it. Do not substitute a changed display name as the original metadata value.

Canonical string-prefix checks alone are insufficient for containment. Use a destination handle/descriptor and validated relative traversal, reject absolute/drive/UNC escapes, inspect link targets and defend against symlink/reparse-point replacement races. Test each backend's output mapping; helpers must not receive unrestricted writable destination trees without the application policy. Current probes write only bounded test paths and do not implement this production security layer.

On macOS, write the native resource fork and representable Finder metadata using the qualified native implementation, including quarantine propagation. On Windows/Linux, write documented AppleDouble `._name` sidecars paired with the data file; compare the fork payload hashes separately from sidecar serialization. Preserve unavailable metadata in an explicit manifest or report it as unrepresentable. A Finder creator/type observation does not prove all flags, dates, extended attributes or permissions were retained.

## Archive replacement transaction

1. Read/archive-fingerprint the original, detect external modification and estimate space for the full replacement plus recovery margin.
2. Write a unique replacement on the same destination filesystem. The engine never mutates the original path during this phase.
3. Close, flush and independently reopen/test the replacement; compare intended entry IDs, payloads and required metadata. Preserve unknown entries/metadata or reject the edit rather than silently converting them.
4. Commit through a qualified platform replacement operation with recoverable state. Validate sharing/permissions behavior on Windows and durability on POSIX; same-filesystem rename alone is not a full power-loss proof.
5. Reconcile the recovery record after restart. Failure/cancellation before commit preserves the original hash; an interrupted commit leaves a recoverable original or fully verified replacement.

Test kills and write faults during compression, verification and commit; test ENOSPC, antivirus/open-file interference, permission loss, cross-filesystem destinations, external changes and restart. The assessment's staged-copy and libzip cancel probes prove only narrow preservation cases, not this full transaction.

## Milestones and acceptance

Estimates below are **engineering planning ranges**, not measured throughput forecasts. Assume one experienced C++/desktop engineer with access to Windows, Intel/ARM Macs and Linux desktop testing, plus part-time QA/design. The experiments establish that several engines and seams compile; they do not establish GUI implementation velocity. Gate failures can expand or invalidate later estimates.

| Milestone | Planned effort | Acceptance criteria |
|---|---|---|
| 0. Close feasibility blockers | 2–4 engineer-weeks initially | Fresh Windows XAD worker builds/installs; both native macOS builds; fork/Finder/quarantine payload oracle; independent StuffIt/StuffIt X/Compact Pro/Amiga LZX corpus; Qt 6.12.0 acquired and minimal native GUI built everywhere. Bound the Windows XAD investigation to 5 working days before architecture review. |
| 1. Worker protocol, entry model and safety | 2–3 weeks | Versioned protocol, entry IDs/batched listings, password channel, structured errors, selected extraction, collision mapping, cancellation and malicious-path tests across all mandatory backends. No known data-loss policy remains. |
| 2. Creation/editing and recovery | 2–4 weeks | ZIP/7z add/replace/remove/rename; TAR/TAR.GZ creation; independent replacement verification; interruption/fault recovery preserves original; metadata routing decides whether libarchive joins the shipped set. |
| 3. Native archive-manager interface | 3–5 weeks | Browse/search/detail panel, drag/drop, queue, password and collision dialogs, settings, light/dark themes, keyboard operation and screen-reader names/focus. Real 100k engine-fed listing remains interactive; bounded sorting/search memory. |
| 4. Preservation and compatibility hardening | 2–4 weeks | Realistic legacy corpus and all required encodings/forks across three OSes; Windows sidecar naming/long-path behavior; links/permissions/quarantine and missing-volume diagnostics; no silent unsupported metadata loss. |
| 5. Packaging and release qualification | 2–3 weeks | Fresh-runner source builds, installed packages without developer libraries, signatures/notarization where applicable, native X11/Wayland desktop runs, architecture-specific receipts, license/source notices and complete correctness/performance acceptance. |

The sequence totals roughly **13–23 engineer-weeks**, with the initial blocker investigation inside that range and platform availability/codec defects capable of increasing it. Some implementation can overlap after milestone 0; the acceptance gates cannot be skipped. A smaller extraction-only launch would reduce work but would violate the agreed v1 scope. A PeaZip adaptation may save part of milestone 3; its worker/preservation/safety/recovery work remains and needs a short native desktop trial before assigning a competing estimate.

Suggested performance targets to calibrate on the actual supported hardware: first listing batch within 1 second for ordinary ZIP; 100k listing without unbounded model growth; normal interaction/frame stalls under 100 ms; cooperative cancel acknowledgement under 250 ms where supported, with declared escalation/cleanup bounds. These are proposed acceptance targets, not proven outcomes from the half-second offscreen probe. Measure peak process-tree memory and both cold/warm runs on local filesystems.

## Platform packaging

| Platform | Requirements and checks |
|---|---|
| Windows 11 x64 | Select a reproducible native compiler/runtime ABI; bundle Qt platform/image plugins, engine helpers, compression DLLs and GNUstep/Foundation/runtime dependencies used by the legacy worker. Enable/test UTF-16 and long paths, file associations and native drag/drop. Use a scoped installer/portable package first; shell extensions are a later isolated component. Test installation and extraction with developer PATH removed, read-only directories and standard-user permissions. NanaZip is a packaging reference, not a portable app donor. |
| macOS arm64 and x86_64 | Build and test both architectures; use separate or verified universal binaries. Bundle Qt frameworks/plugins and native XAD helper, fix install names/RPATH, sign nested binaries and notarize a reviewed release artifact. Exercise resource forks, Finder info, quarantine, sandbox/file permissions, drag/drop and Finder integration on real Macs. Signing/notarization/publishing require the separately authorized release phase. |
| Ubuntu 24.04 x64 | Build against a deliberate glibc/toolkit baseline; package the Qt X11/Wayland plugins and required helper/runtime dependencies. Choose a DEB plus portable package or another deliberately tested distribution format. Run native X11 and Wayland sessions, MIME/desktop integration, permissions/links and accessibility. WSL/offscreen results remain engine evidence only. |

Pin the selected Qt release and required modules; confirm its deployment/platform support from official documentation before accepting these OS minimums. Qt Core/Gui/Widgets have open-source license options, but some modules are GPL-only. Use the smallest module set and ship version-matched third-party notices/SBOM; do not assume every Qt module has the same terms. Engine notices, LGPL source/relink conditions and imported fixture redistribution must be resolved for the actual packaged artifacts. [Qt licensing](https://doc.qt.io/qt-6/licensing.html).

## Decision after the next gate

Proceed with the Qt shell only after native Windows and macOS legacy preservation pass. If the bounded Windows runtime build fails or realistic legacy fixtures expose unresolved data loss, stop full-GUI implementation and report the exact blocker. Revisit PeaZip only with measured evidence that its native workflows reduce the remaining work; choosing its GUI does not remove the shared legacy worker problem.

The next executable task is milestone 0's Windows XAD build/preservation probe and a matching native Mac oracle run. This assessment supplies scripts, exact pins and receipts for that work; no production integration or publishing was performed.
