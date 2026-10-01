# Unarchiver implementation roadmap: Windows first

Build and qualify **Windows 11 x64 first**, using a new native C++/Qt 6 Widgets archive manager with isolated engines. Keep macOS/Linux as future targets, with portable archive models and job contracts; their builds no longer block this Windows sequence. The full-manager scope remains ZIP/7z creation/editing, TAR/TAR.GZ creation and faithful legacy extraction with AppleDouble resource-fork preservation.

The [Windows experiment](windows-first.md) closes local XAD compilation/runtime and the tested preservation subset. The [desktop preview](windows-desktop-preview.md) implements an archive-fed GUI, safe extraction and ZIP/7z mutation; the [legacy adapter](windows-desktop-legacy.md) now integrates read-only StuffIt/BinHex with AppleDouble. These qualify neither the complete release nor a clean-machine install. The [original assessment](assessment.md), [updated inventory](dependency-inventory.md) and [historical three-platform roadmap](implementation-roadmap-three-platform-baseline.md) preserve the comparison and earlier assumptions. No publishing has occurred.

## Foundation and engine assignments

| Role | Windows assignment | Acceptance boundary |
|---|---|---|
| Native UI | Qt Core/Gui/Widgets; C++ model/view and job controller | Qt 6.10.2 deployed and tested through real qwindows listing/selection/extraction and recovery. Toolkit upgrade, fresh-machine packaging and accessibility remain unverified. |
| ZIP/ZIP64 | 7-Zip 26.03 DLL worker in the first GUI; libzip remains a specialist candidate | Index-based list/select/extract/create/add/replace/remove/rename now exercised through the GUI worker. Qualify opaque extras, unsupported methods and resource-sidecar pairing before deciding whether libzip closes a gap. |
| 7z | 7-Zip 26.03 adapter in a helper | Creation/editing and encrypted names exercised. Qualify progress/password callbacks and index-based entry identity; localized CLI prompts are not the production interface. |
| TAR/TAR.GZ | 7-Zip initially; add libarchive API integration if required metadata fails round-trip | Windows Unicode TAR passed through 7-Zip. Assessed Windows bsdtar CLI is unsuitable; its API is a separate evaluated candidate. Decide through metadata fixtures before shipping another backend. |
| Legacy extraction | Isolated decoder-only XAD with Qt-owned safe output | Desktop StuffIt/BinHex fork pairing, AppleDouble, selected extraction, passwords, collision preservation and recovery pass the tested subset. Realistic StuffIt X, Compact Pro forks, Amiga LZX, additional script encodings and independent original-application oracles remain open. No legacy creation/editing API. |
| Large mainstream listings | Assigned 7-Zip reader | Native GUI 100k ZIP listing demonstrated around 1.6–1.7 seconds in local samples. XAD's earlier JSON listing exceeded 180 seconds; it is used for legacy formats. Cold/warm performance distributions remain open. |

Keep the Objective-C ABI and GNUstep DLLs private to the legacy helper. Its experimental bundle has four executables and 28 non-system DLLs, totaling 64.92 MiB for native files. Use separate helper directories and explicit executable paths; keep this runtime out of the Qt process's dependency search path.

Review the two Windows compatibility patches for adoption. Retain adapted codecs until fixtures justify replacement. Historical fork/reference sources remain read-only.

## Worker contract and safety

Use a versioned private-pipe protocol for capabilities, batched listing, selected extraction, creation, replacement updates, integrity checks and cancellation. Carry job/request IDs, engine revision and sequence numbers. Apply backpressure and bounded memory; use archive/session identity plus numeric entry index, since paths cannot distinguish duplicates. Keep original raw names/encodings, display paths, data/fork streams, sizes, timestamps, checksums, links, permissions and Finder fields separate.

The Qt model should show partial batches without creating a widget per entry. Enclosing-directory and selected-extraction layout are explicit policies. The [historical worker contract](implementation-roadmap-three-platform-baseline.md#worker-and-model-contract) supplies the detailed interface; its platform rollout gates are superseded here.

Passwords go through the private channel/API callback, excluded from argv, logs and history. Distinguish wrong/missing password, corruption, unsupported method, missing volume, destination conflict, write failure, cancellation and worker crash. Report checksum coverage honestly. Progress includes phase, bytes/entries, known totals and solid-archive work preceding a selected member. Cooperative cancellation escalates to termination after a bounded wait and reports cleanup. The 3.74 ms forced-kill sample proves process termination only; a partial extracted file remains.

Resolve duplicate names, case collisions, devices/trailing dots, long paths and existing files before writing. Preserve both payloads by default using safe output mappings and a record of original names. Qualify index-based extraction in each backend. The current always-overwrite probe fails both collision-preservation fixtures and cannot become product policy.

Use validated relative traversal rooted in a destination handle and defend against reparse/link replacement races. String-prefix checks and the bounded escape fixtures do not establish arbitrary archive safety. Stage extracted files, track completeness, and reconcile temporary files after cancellation/write failure/crash. Test standard-user/read-only permissions, disk-full, sharing interference, Unicode and long paths.

On Windows, pair data files with documented AppleDouble sidecars, checking decoded fork hashes separately from container bytes. Preserve representable Finder fields; report or record unavailable metadata explicitly. A preservation manifest must retain names/metadata that the filesystem cannot represent. Do not equate TAR POSIX modes with Windows ACLs.

## Creation, editing and recovery

1. Fingerprint the original, detect external changes and estimate replacement/recovery space.
2. Write a unique full replacement on the destination filesystem; never mutate the original during staging.
3. Close/flush/reopen and independently verify payloads, intended entry changes and required metadata. Reject edits that would silently discard unknown entries or metadata.
4. Commit through a qualified Windows replacement operation with recoverable state and explicit sharing/permission handling.
5. Reconcile recovery after restart; failure/cancellation preserves the original or leaves a verified recoverable replacement.

Inject faults/termination during compression, verification and commit. Test disk-full, permission loss, open-file interference and external modification. Existing staged-copy/libzip cancel probes cover narrow cases; the production transaction remains to be implemented. ZIP/7z add/replace/remove/rename and TAR/TAR.GZ creation remain mandatory. RAR creation is outside the open-source baseline.

## Milestones and acceptance

These are remaining **planning ranges**, not measured implementation velocity. Assume one experienced C++/Windows desktop engineer plus part-time QA/design. Experiments reduce engine/runtime uncertainty; they do not establish UI, security or recovery throughput. Independent legacy defects may expand the ranges.

| Milestone | Remaining effort | Acceptance criteria |
|---|---:|---|
| 0. Qualify the Windows foundation | 1–2 engineer-weeks | Fresh Windows source build and bundle run as standard user without developer libraries; select/deploy toolkit; obtain realistic legacy oracles. Retain runtime/BOOL negative controls. Decide whether to pin the working GNUstep binary or rebuild it against a coherent current runtime. |
| 1. Worker protocol and safe extraction | 2–3 weeks | Private password channel, stable IDs, bounded listings, structured errors/progress, collision mapping, containment, cancellation/cleanup across engines. Close both collision failures; no known silent data loss. |
| 2. Creation/editing and recovery | 2–4 weeks | Required mutations and TAR/TAR.GZ creation; independent replacement verification; fault/restart preservation; opaque metadata policy. Decide whether libarchive closes a demonstrated shipped gap. |
| 3. Native archive-manager GUI | 3–5 weeks | Browse/search/details, extraction, drag/drop, creation/update dialogs, queue, passwords, collisions, settings and light/dark presentation. Keyboard operation and screen-reader names/focus. Real engine-fed 100k listing remains interactive with bounded sorting/search memory. |
| 4. Legacy/filesystem hardening | 2–4 weeks | Independent realistic data/fork oracles; encodings, missing volumes, links, reserved names, long paths and unsupported metadata reporting. No lossy rename or broken sidecar pairing. |
| 5. Windows packaging/qualification | 1–2 weeks | Reviewed portable package/installer, fresh VM tests, source/version records, notices and LGPL source/relink artifacts; complete correctness/recovery receipts. Signatures belong to the separately authorized release phase. |

The remaining Windows sequence totals roughly **11–20 engineer-weeks** under these assumptions. Work may overlap after relevant gates close. The historical 13–23-week simultaneous-platform estimate is retained separately; the difference is not measured savings. PeaZip remains the strongest alternate if a native Windows comparison demonstrates materially lower UI effort without sacrificing preservation/safety/recovery.

Calibrate on supported hardware: first ordinary ZIP batch around one second, interaction stalls under 100 ms, bounded 100k memory and cooperative cancel acknowledgement around 250 ms where supported. These are proposed targets. Measure cold/warm runs, process-tree peak memory and cleanup latency; isolated samples are not finished-app benchmarks.

## Windows deployment and deferred platforms

Pin compiler/runtime combinations per executable. The current GNUstep package fails with current GCC 16.2 runtime DLLs and passes with the isolated 16.1 overlay. Dependency updates must rerun the loader and BOOL probes. The current bundle is a local experiment, not a qualified installer.

Deploy version-matched Qt platform/image plugins, helpers and private dependency closures. Begin with a portable bundle and scoped standard-user installer; qualify file associations and drag/drop. Defer shell extensions until the manager is qualified. NanaZip remains a Windows integration reference.

Test Unicode/space installation paths, developer PATH removal, read-only program directories, standard users, upgrade/removal and recovery records. Collect SBOM, source pins, version-matched notices and actual source/relink artifacts. Match Qt licensing to selected modules. [Qt licensing](https://doc.qt.io/qt-6/licensing.html).

No signing, publishing or installer registration occurred in this assessment. Latest Qt 6.12.0, a fresh Windows VM build and realistic legacy fixtures remain immediate qualification gaps. Windows GUI development can advance independently of deferred platform builds; no production foundation is qualified yet.

Keep portable engine/model/job code with platform filesystem/packaging adapters. Later macOS work requires arm64/x86_64 builds, native forks/Finder/quarantine and framework/helper deployment. Linux requires native Ubuntu desktop/X11/Wayland, packaging and accessibility. WSL results remain reference engine evidence; neither future platform blocks the Windows sequence.
