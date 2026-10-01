# Windows-first build and preservation assessment

The native **Windows 11 x64 XAD worker now builds and runs as a local DLL bundle**, including the tested legacy resource-fork cases. This closes the earlier local Objective-C build blocker. It does not qualify an installer, a production worker, or the full archive-manager GUI.

Windows is the next build and qualification target. macOS and Linux remain future targets; their native desktop gates no longer block this Windows development sequence. Archive creation/editing and legacy extraction with AppleDouble preservation remain required. The recommended foundation remains a native C++/Qt Widgets shell with separate engine workers.

## Build result and exact inputs

Experiments ran September 30 local time / October 1, 2026 UTC. The historical fork at `28a2330b16139f6d074cdf75ea34eee0ccd218c4` and all reference checkouts remain unchanged. Only isolated experiment copies carry the two patches below. No production GUI integration or publishing occurred.

| Component | Tested Windows selection |
|---|---|
| XADMaster | Separately pinned unreleased head `7cb9ee0abbb163f261e4cb74501e15067032319c`, with two experimental Windows patches |
| UniversalDetector | `4eb832d999628edcd3d134e46bd35357c8c99a85` |
| Compiler/linker | MSYS2 MinGW64 Clang and lld `22.1.8-3`; CMake 4.1.1 and Ninja from the existing MSYS2 installation |
| Foundation | GNUstep Base `1.31.1-10`; GNUstep Make configuration `2.9.3-2` |
| Objective-C runtime | libobjc2 `2.2.1-7`, `gnustep-2.0` ABI |
| C++ runtime overlay | MSYS2 GCC/GCC-libs `16.1.0-1`, import library and DLLs selected before the current closure |
| Linked compression libraries | zlib `1.3.2-2`, bzip2 `1.0.8-4`, external WavPack `5.9.0-1` |
| Foundation's ICU | ICU `78.3-4`; XAD's Windows string adapter uses Windows code-page APIs |

The [current package lock](../evidence/windows-runtime.lock.json) records the complete 42-package development closure, URLs, SHA-256 values, licenses and dependencies. The [compatible runtime overlay](../evidence/windows-gcc16_1.lock.json) records its separate exact package hashes. Current-package hashes came from the frozen MSYS2 database; historical overlay hashes were recorded after verified HTTPS downloads from the official repository and are checked on reuse. Neither acquisition script installs packages into the system.

The build uses modern Objective-C exception/block flags, `NSConstantString`, `STRICT_APPLE_COMPATIBILITY=1`, lld, explicit runtime linkage and whole-archive links for parser/category discovery. It compiles XAD's existing codecs; it does not replace them. The historical Windows compression binaries are unused. Only `regex.h` is supplied from the old compatibility include directory, so its zlib/bzip2 headers cannot shadow the maintained headers.

[Build commands and results](../evidence/windows-first/builds.json) identify the exact invocations. `lsar` still prints its upstream hardcoded `v1.10.7` banner; that banner does not identify the evaluated revision. Use the commit and patch records above.

## Failures resolved in the experiment

1. **Runtime loading:** GNUstep Base's binary imports 7,052 libstdc++ names. Five are absent from the current GCC `16.2.0-4` runtime; the Foundation process exits with `0xC0000139`. GCC `15.2.0-13` also fails, missing 228 names. The isolated `16.1.0-1` overlay has all required names and passes the Foundation and worker tests. This demonstrates package compatibility on this host, not general GCC ABI compatibility. [PE-symbol and loader comparisons](../evidence/windows-first/runtime-compatibility.json).
2. **Objective-C BOOL ABI:** omitting GNUstep's configured `STRICT_APPLE_COMPATIBILITY` flag made `BOOL` four bytes. False class-membership results acquired nonzero upper bytes, so XAD skipped all normal parsers and returned unrecognized archive. With the flag, `BOOL` is one byte and recognition works. The strengthened Foundation probe checks false results and class membership, Unicode, exceptions, UTF-16 paths and eight-byte `off_t`; a deliberately misconfigured build fails as expected. [Positive probe](../evidence/windows-first/foundation-run.log), [negative control](../evidence/windows-first/foundation-negative-run.log). No parser-registration source patch is needed.
3. **Wide-path unlink:** XAD's unsafe-link recovery branch passes GNUstep's UTF-16 filesystem representation to narrow `unlink`. Clang rejects the pointer mismatch. The isolated patch selects `_wunlink` on Windows and retains POSIX `unlink` elsewhere. This is a compile correction; complete recovery-branch runtime coverage remains open. [Patch](../evidence/windows-first/windows-wide-unlink.patch).
4. **Password/encoding conversion:** `XADStringWindows` passes `MB_ERR_INVALID_CHARS` to `WideCharToMultiByte`. That API requires its own flags; the original adapter returned nil for all six tested conversions and rejected correct StuffIt passwords. The patch selects supported flags, checks conversion completion and rejects conversions that cannot round-trip exactly. It also rejects malformed UTF-16 for UTF-8/GB18030. Both tested StuffIt passwords now work. [Patch](../evidence/windows-first/windows-encoding.patch), [before](../evidence/windows-first/encoding-before-fix.log), [after](../evidence/windows-first/encoding-after-fix.log). Flag requirements are documented by [Microsoft](https://learn.microsoft.com/en-us/windows/win32/api/stringapiset/nf-stringapiset-widechartomultibyte).

The encoding probe compares bytes independently with Python's MacRoman, CP1252, CP932, UTF-8 and GB18030 codecs. It also tests lossy MacRoman conversion and an unpaired UTF-16 surrogate. These checks qualify the listed cases, not every code page or legacy filename.

## Bundle and fixture receipts

The local bundle is `assessment/outputs/windows-first/xad-worker-bundle/`: `xad-worker.exe`, `lsar.exe`, Foundation and encoding probes, plus their 28 transitive non-system DLLs. Native files total **64.92 MiB**, excluding notices. The [bundle manifest](../evidence/windows-first/bundle.json) records every native file's digest, origin and PE imports. Dependency notices are copied into `licenses/`; actual source/relink/distribution obligations still require review before shipping.

The [final Windows fixture receipt](../evidence/windows-first/suite.json) records **70 passing assertions/process checks, two failed collision-preservation checks and four unverified checks**. Every worker process in that suite runs with `PATH` restricted to Windows System32; DLLs come from the bundle. This proves local execution without the developer PATH, not installation on a clean machine.

| Area | Observed result and boundary |
|---|---|
| MacBinary II, BinHex, AppleSingle, AppleDouble-in-ZIP | Generated data/resource-fork SHA-256 values match; AppleDouble entry payloads are inspected separately; Finder type/creator `TEXT`/`ttxt` preserved. Other Finder fields and realistic archive variants remain unverified. |
| Compact Pro | Synthetic data-only RLE fixture passes. No realistic compression/fork oracle claim. |
| StuffIt encrypted fixtures | Correct seven- and twelve-character passwords extract data and sidecars matching the earlier Linux head outputs. Decoded resource fork is separately hashed: 454 bytes, SHA-256 `47d93fa1812ca5d49bb2df81a077276f6c003612c57abe7ea2ef29ef7b64ce81`. Wrong passwords are rejected and leave no files. Same-engine cross-platform agreement is not an original-application oracle. |
| ZIP/ZIP64, TAR, TAR.GZ, 7z | Listing/extraction fixture subset passes, including selected ZIP extraction, Unicode members and Unicode archive/destination paths. TAR timestamp checks pass. 7z fixture created independently by the locked 7-Zip engine. XAD has no archive-creation/editing API. |
| LhA / CAB LZX | Tested LhA header-3, lh6 and lh7 integrity cases pass. CAB LZX payload equals the independent upstream `ABABABABABABABAB` oracle. CAB evidence does not qualify Amiga LZX archives. |
| Truncation / checksum / write failure | Corrupt ZIPs rejected. File-as-directory write rejection preserves the destination sentinel. This is not disk-full injection. |
| Bounded containment | Relative escape fixture writes no file outside its destination; link fixture is rejected without an outside file. Reparse races, reserved names and long-path policies remain open. |
| Forced termination | Termination latency 3.74 ms in the final single run; source archive hash unchanged. A partial `zeros.bin` remains. Product extraction staging/cleanup is required. |
| Duplicate and case-colliding names | **Fails preservation:** always-overwrite extraction loses one payload in each fixture. Do not ship this probe's extraction policy. |

The [shared fixture manifest](../evidence/fixture-manifest.json) supplies archive hashes, generation/import provenance and expected payloads. Imported StuffIt fixture redistribution and independent original-application hashes remain unresolved. Use fresh destinations when reproducing; the worker intentionally overwrites for bounded experiments and has no production collision UI.

Single-run measurements:

| Operation | Time | Sampled peak RSS | Interpretation |
|---|---:|---:|---|
| XAD integrity test of 5,369,757,696-byte compressible ZIP payload | 2.7902 s | 24.22 MiB | Reads and validates the full uncompressed stream; does not establish a successful >4 GiB disk extraction or creation/update round trip. |
| XAD JSON listing, 100,000 entries | **Timed out at 180.0429 s** | 379.04 MiB | Earlier corrected-ABI run, before the password-conversion patch. Retained failure; not repeated as an unrelated benchmark after that patch. |

The listing failure is in [the pre-encoding-fix receipt](../evidence/windows-first/suite-before-encoding-fix.json). The earlier baseline measurements showed Windows ZIP listing through libzip at 0.527 s / 36.79 MiB and 7-Zip at 0.433 s / 28.52 MiB. Output formats and conditions differ; this is not a controlled engine ranking. It supports using the mainstream backend for large ZIP listings and keeping XAD for demonstrated specialist gaps. Engine-fed GUI responsiveness remains a separate requirement.

## Reproduce

Prerequisites: native Windows, Git/reference acquisition, Python 3.14 with zstd-capable `tarfile`, `psutil`, CMake/Ninja at the documented MSYS2 paths and Windows curl. Existing fixtures/reference revisions are locked; the paths in these scripts are local assumptions, not a clean-machine bootstrap guarantee.

```powershell
python assessment/scripts/acquire.py
# Generate only if fixtures are absent; regeneration changes some container dates.
# python assessment/scripts/generate_fixtures.py
python assessment/scripts/acquire_windows_runtime.py
python assessment/scripts/acquire_windows_compat.py
python assessment/scripts/build_xad_windows.py
python assessment/scripts/package_xad_windows.py
python assessment/scripts/test_xad_windows.py --skip-scale
python assessment/scripts/verify_assessment.py
```

Omit `--skip-scale` to request another bounded 180-second scale run. The runner continues collecting failures, so its zero Python exit code is not suite acceptance; inspect receipt rows. Package locks are reused by default, not silently refreshed.

To reproduce all runtime comparisons, additionally run:

```powershell
python assessment/scripts/acquire_windows_compat.py --rejected-gcc15
python assessment/scripts/check_windows_runtime.py
```

## What remains before a Windows release

The next feasibility checks are a fresh Windows VM/runner source build and bundled execution, toolkit selection/deployment, and independent realistic StuffIt X/Compact Pro/Amiga LZX preservation fixtures. The current native Qt Widgets seam was built with Qt 6.10.2; latest 6.12.0 acquisition remains unverified. Keyboard/screen-reader operation and a real archive-fed GUI are not proven by its synthetic offscreen model probe.

Product work must introduce stable entry IDs, output mapping for collisions, race-resistant containment, structured password/error/progress handling, cooperative cancellation and partial-output cleanup. ZIP/7z mutations must write and verify a replacement before committing it. No foundation passes production qualification yet. The [revised roadmap](implementation-roadmap.md) prioritizes Windows and retains these requirements.
