# Unarchiver dependency inventory

Assessment started September 30, 2026; updated with the Windows-first build experiment October 1 UTC. All baseline components are frozen by the containing commit and file hashes; a date or version string is labeled as such rather than invented as an exact upstream revision. Proposed dispositions authorize no product changes.

Exact candidate pins: [sources lock](../evidence/sources.lock.json). File-by-file changes and hashes: [embedded source deltas](../evidence/embedded-source-deltas.json). Windows follow-up: [build and preservation report](windows-first.md), [current runtime closure](../evidence/windows-runtime.lock.json), [compatible runtime overlay](../evidence/windows-gcc16_1.lock.json). Build dependency versions: configure logs and [Linux environment](../evidence/linux-environment.log).

## XADMaster

**Origin:** source/XADMaster; inherited fork pinned at 28a2330b16139f6d074cdf75ea34eee0ccd218c4

**Revision evidence:** Exact containing commit; no standalone engine release confidently assigned

**Adaptations and comparison boundary:** Objective-C archive parsers, handles, fork extraction and platform implementations are application-specific. Do not replace the engine with a generic compression SDK.

**Upstream:** https://github.com/MacPaw/XADMaster; stable v1.10.8 and separately pinned development revision in sources.lock.json

**Fixes and recommendation:** Stable 1.10.8 fixes the documented macOS quarantine advisory. Development revision fixes the tested 12-character StuffIt password failure and wrong-password debris. An unverified release promotion is not justified.

**License:** LGPL-2.1-or-later at source/License.txt and current LICENSE; embedded files retain their own terms

**Build requirements:** Foundation, Objective-C compiler/runtime, C/C++; whole-archive linkage. Windows head now builds with Clang 22.1.8, lld, GNUstep Base 1.31.1-10 and a compatible GCC 16.1 runtime. STRICT_APPLE_COMPATIBILITY=1 is mandatory. Two isolated Windows patches are recorded in evidence/windows-first.

**Disposition:** update and isolate

**Regression gate:** Local Windows bundle/preservation subset passes. Fresh-machine installation, independent StuffIt/StuffIt X/Compact Pro/LZX fork oracles, collision policy and containment remain required. Native macOS builds are deferred by the Windows-first direction.

## UniversalDetector

**Origin:** source/UniversalDetector; Objective-C wrapper plus Mozilla universalchardet

**Revision evidence:** Exact containing baseline commit; no original Mozilla release assigned

**Adaptations and comparison boundary:** WrappedUniversalDetector and UniversalDetector bridge Mozilla detection into XADString; possibleMIMECharsets contains additional mappings. Filename decoding behavior is a compatibility contract.

**Upstream:** https://github.com/MacPaw/universal-detector at 4eb832d999628edcd3d134e46bd35357c8c99a85; no stable release found

**Fixes and recommendation:** Compare encoding tables and wrappers before updating; do not equate a detected charset with a verified original name.

**License:** Mozilla files offer MPL-1.1/GPL-2.0-or-later/LGPL-2.1-or-later alternatives; audit wrapper notices separately

**Build requirements:** C++ and Objective-C compiler; Foundation; sibling directory expected by XAD makefiles

**Disposition:** update within isolated XAD worker

**Regression gate:** CP932, UTF-16, MacRoman and ambiguous-name fixtures with known raw name bytes and expected names; only LhA reading exercised here

## GNUstep and Objective-C runtime

**Origin:** Linked system dependency; old Windows makefile expects C:\GNUstep\GNUstep

**Revision evidence:** No bundled Foundation/runtime version found; tested Linux Base 1.29.0, Make 2.9.1, GCC Objective-C 13.3 and libobjc4 package 14.2

**Adaptations and comparison boundary:** GNU_RUNTIME, fgnu-runtime, NSConstantString and historical hardcoded include/library paths; macOS uses Apple Foundation instead.

**Upstream:** https://www.gnustep.org/resources/downloads.html; Windows MSYS2 Base 1.31.1-10, Make 2.9.3-2 and libobjc2 2.2.1-7 now tested; exact closure in windows-runtime.lock.json

**Fixes and recommendation:** Windows build uses Clang 22.1.8/lld, gnustep-2.0 ABI and STRICT_APPLE_COMPATIBILITY=1. GCC 16.2 runtime fails to load the current GNUstep package: five missing imports. GCC 16.1.0-1 overlay passes; GCC 15.2 also fails. Do not blindly refresh this runtime. See windows-first/runtime-compatibility.json.

**License:** GNUstep Base LGPL; GCC runtime has its own runtime exception terms; Apple system framework terms on macOS

**Build requirements:** Choose one compatible compiler/runtime ABI; distribute required runtime DLLs on Windows; clean runner needed

**Disposition:** isolate and update packaging

**Regression gate:** Native compilation/linking and bundled execution with system-only PATH pass on this host. Clean Windows VM/runner and full installation remain unverified.

## zlib

**Origin:** Linked -lz; Windows/include/zlib.h and Windows/lib/libz.a

**Revision evidence:** Windows header 1.2.3 (2005); matching binary release not independently authenticated. Linux baseline system version unspecified. Tests used Linux package 1.3 and Windows 1.3.1.

**Adaptations and comparison boundary:** CSZlibHandle wraps stream/error behavior; XAD has its own Deflate-family implementations. Updating libz does not update those decoders.

**Upstream:** https://zlib.net/ stable 1.3.2 (2026-02-17)

**Fixes and recommendation:** 1.3.2 includes audit fixes and large-size APIs. Old precompiled Windows archive must be rebuilt rather than copied.

**License:** zlib license

**Build requirements:** Portable C; consistent architecture and toolchain

**Disposition:** update linked dependency; retain wrapper

**Regression gate:** Deflate, ZIP64, gzip, CRC failures and NSIS-specific decoders; latter not certified

## bzip2

**Origin:** Linked -lbz2; Windows/include/bzlib.h and Windows/lib/libbz2.a

**Revision evidence:** Both header and binary version string identify 1.0.5, 10-Dec-2007; tests used 1.0.8

**Adaptations and comparison boundary:** CSBzip2Handle wraps libbz2; XADNSISBzip2Handle is a separate adapted decoder and cannot be replaced by updating this library.

**Upstream:** https://sourceware.org/bzip2/ stable 1.0.8

**Fixes and recommendation:** Replace historical binary with maintained source build; 1.0.8 addresses fixes absent in 1.0.5.

**License:** bzip2 permissive license

**Build requirements:** Portable C; full version identity and source provenance for packaged binary

**Disposition:** update linked library; isolate adapted decoder

**Regression gate:** Bzip2 archives, concatenation, truncation and NSIS bzip2 fixtures (not present in shared suite)

## ICU

**Origin:** Linked -licuuc through XADStringICU on Linux

**Revision evidence:** Baseline version unconstrained; Linux test build uses 74.2-1ubuntu3.1

**Adaptations and comparison boundary:** XADStringICU supplies non-Apple conversion behavior; Windows uses XADStringWindows.

**Upstream:** https://github.com/unicode-org/icu/releases/tag/release-78.3

**Fixes and recommendation:** Latest stable audited as an update target; newer conversion behavior requires filename regression review.

**License:** Unicode/ICU permissive license with third-party notices

**Build requirements:** C/C++; ICU data and ABI must be packaged consistently

**Disposition:** update and isolate to worker

**Regression gate:** Known byte-to-name fixtures; do not change detection guesses silently

## LZMA and branch filters

**Origin:** source/XADMaster/lzma; Igor Pavlov decoder sources

**Revision evidence:** LzmaDec.c date 2008-11-06; LzmaDec.h date 2009-02-07. This mixed snapshot does not establish an exact SDK release.

**Adaptations and comparison boundary:** XADLZMAHandle/XADLZMA2Handle and WinZipJPEG/LZMA.h integrate streaming callbacks. All 9 embedded files are byte-identical in baseline, stable and head.

**Upstream:** https://www.7-zip.org/sdk.html and pinned 7-Zip 26.03; generic upstream is active, drop-in compatibility unproven

**Fixes and recommendation:** No codec replacement applied. Treat modern SDK as a separate adapter experiment, preserving property/error semantics.

**License:** Public-domain notices in decoder files; XAD wrappers LGPL-2.1-or-later

**Build requirements:** C with precise integer sizes and streaming adapter

**Disposition:** retain and isolate for legacy; use maintained 7-Zip for mainstream

**Regression gate:** LZMA/LZMA2 boundary cases, branch filters, WinZip JPEG and legacy decode hashes; coverage incomplete

## PPMd

**Origin:** source/XADMaster/PPMd; G/H/I model variants plus Brimstone allocator

**Revision evidence:** Exact baseline file hashes recorded; no standalone upstream version asserted

**Adaptations and comparison boundary:** Separate SubAllocatorBrimstone and G/H/I implementations. Stable/head differ in 21 of 25 files, including added MacPaw license preambles; hash differences alone do not prove codec changes.

**Upstream:** Maintained containing project MacPaw/XADMaster; 7-Zip PPMd is an alternative for mainstream data, not demonstrated equivalent to all legacy variants

**Fixes and recommendation:** Preserve adapted allocators; compare executable code separately from comments before any replacement.

**License:** Current MacPaw PPMd files explicitly LGPL-2.1-or-later; baseline governed by repository terms where no separate notice exists

**Build requirements:** C; archive-specific model/allocator selection

**Disposition:** retain and isolate

**Regression gate:** StuffIt X Brimstone, G/H/I and corrupt-stream fixtures with independent hashes are required; not completed

## WavPack

**Origin:** source/XADMaster/wavpack; David Bryant/Conifer Software

**Revision evidence:** Baseline bundled 4.60.1; stable/head bundled 5.1.0; current Linux worker links external 5.6.0

**Adaptations and comparison boundary:** XADWinZipWavPackHandle uses custom read/write callbacks and WinZip framing. Current non-Apple build chooses system header/library; old baseline embeds decoder source.

**Upstream:** https://www.wavpack.com/ latest 5.9.0

**Fixes and recommendation:** Update through upstream adapter, not wholesale source transplant. Windows makefile needs reconciliation with current external-library requirement.

**License:** BSD notices in source and the upstream project; the license.txt referenced by the headers is absent from both snapshots, so obtain version-matched license text for packaging

**Build requirements:** C; external development package on Linux, matching headers/DLLs for Windows; Apple build retains embedded source

**Disposition:** update using maintained upstream integration

**Regression gate:** WinZip WavPack payload oracle, old stream versions and malformed headers; not available here

## libxad

**Origin:** source/XADMaster/libxad; Dirk Stoecker Amiga library with Unix emulation

**Revision evidence:** include/version.h says version 13 revision 0, DATETXT 31.03.2003; RCS stamp 2005-06-23; not a pristine upstream release

**Adaptations and comparison boundary:** libxad/all.c, clients.c and unix/emulation.c included directly; XADLibXADParser/XADLibXADIOHandle bridge I/O. 57/59 files identical to stable; 56/59 to head.

**Upstream:** Historical https://sourceforge.net/projects/libxad/; active independent maintenance not established. Maintained containing project is MacPaw/XADMaster.

**Fixes and recommendation:** Do not replace with a similarly named modern library without proving client coverage; isolate legacy clients and report unsupported archives.

**License:** LGPL-2.1-or-later in source; individual client notices require inclusion

**Build requirements:** C; Unix emulation and XAD callbacks

**Disposition:** retain and isolate

**Regression gate:** Representative Amiga LZX and obscure client archives, fork hashes, truncation and sanitizers; Amiga LZX still unverified

## WinZip JPEG

**Origin:** source/XADMaster/WinZipJPEG; repository-authored format-specific decompressor

**Revision evidence:** Exact baseline hashes; no independent packaged release identified

**Adaptations and comparison boundary:** Arithmetic decoder, JPEG reconstruction and custom LZMA wrapper; XADWinZipJPEGHandle orchestrates ZIP method decoding.

**Upstream:** MacPaw/XADMaster is the containing upstream; generic libjpeg is not a replacement for this archive encoding

**Fixes and recommendation:** 10/12 files differ from baseline in stable/head, partly copyright/license text. Do not infer algorithm fixes from file counts.

**License:** Containing repository LGPL-2.1-or-later; no separate release license established

**Build requirements:** C and XAD wrapper; embedded LZMA API

**Disposition:** retain and isolate

**Regression gate:** WinZip JPEG samples with original JPEG bytes and reconstruction hashes; not acquired

## Cryptography source

**Origin:** source/XADMaster/Crypto and archive-specific AES/DES handles

**Revision evidence:** Brian Gladman AES Issue Date 20/12/2007, copyright 1998-2010; Stuart Levy DES April 1988; mixed SHA/MD5/HMAC code at exact baseline revision

**Adaptations and comparison boundary:** StuffIt DES password schedule, RAR/7z/ZIP key derivations and wrappers are format-specific. 18/20 Crypto files identical to stable/head.

**Upstream:** Containing upstream MacPaw/XADMaster; mainstream engines use their own crypto. Independent crypto origins and per-file notices retained.

**Fixes and recommendation:** Tested development StuffIt password handling closes a concrete stable failure. Never modernize a legacy cipher in a way that changes archive semantics.

**License:** AES permissive Gladman notice; remaining notices vary, some rely on containing LGPL terms; DES standalone grant not resolved

**Build requirements:** C; endian/integer behavior; process-isolated password channel

**Disposition:** retain and isolate legacy; use maintained engine crypto for new archives

**Regression gate:** Correct/wrong/long passwords, data/fork hashes and cleanup. New AES ZIP/7z exercised; legacy oracle incomplete

## Bundled iOS OpenSSL

**Origin:** source/Dependencies/iOS/Includes/openssl and Libraries/libcrypto.a

**Revision evidence:** Binary strings identify OpenSSL 1.0.1b, 26 Apr 2012; exact original source build provenance absent

**Adaptations and comparison boundary:** iOS-specific binary outside desktop acceptance scope; presence must not be confused with a desktop build dependency.

**Upstream:** https://www.openssl.org/; current test toolchains use Windows 3.5.2 and Ubuntu 3.0.13 with distribution patches

**Fixes and recommendation:** Exclude historical mobile binary from desktop packaging. Do not reuse old cryptography binaries.

**License:** Historical OpenSSL/SSLeay terms; modern OpenSSL uses Apache-2.0; packaged version notices must match

**Build requirements:** Rebuild if mobile work is later authorized; not linked into this desktop assessment

**Disposition:** replace or exclude from desktop

**Regression gate:** No iOS claim; desktop crypto libraries recorded by configure/package receipts

## Windows compatibility code

**Origin:** source/XADMaster/Windows plus XADPlatformWindows.m and XADStringWindows.m

**Revision evidence:** Exact baseline revision; all 9 Windows subtree files byte-identical in stable/head; includes old zlib/bzip2 static binaries

**Adaptations and comparison boundary:** regex.c compatibility shim, hardcoded GNUstep paths and Win32 filename/filesystem implementations are local portability layers.

**Upstream:** MacPaw/XADMaster for platform code; maintained OS/toolchain APIs for new worker integration

**Fixes and recommendation:** Experimental native build replaces old binaries/paths and uses only the legacy regex header, avoiding old zlib/bzip2 headers. Two patches use _wunlink for UTF-16 paths and correct WideCharToMultiByte flags with round-trip rejection of lossy encoding. Unicode paths and encrypted StuffIt now pass on Windows; long paths/device names/reparse races remain open.

**License:** Repository LGPL and dependency-specific notices; binary provenance incomplete

**Build requirements:** Objective-C-enabled toolchain/Foundation; compatible runtime ABI; current makefile omits WavPack linkage

**Disposition:** replace build plumbing; isolate compatibility code

**Regression gate:** Local native bundle, Unicode, resource-sidecar and tested password gates pass. Collision overwrite is demonstrated unsafe; clean installation, realistic corpus and race-safe extraction remain blockers.

## New evaluated libraries and toolkit

**Origin:** Pinned references, not integrated into product

**Revision evidence:** 7-Zip 26.03; libarchive 3.8.9; libzip 1.11.4. Qt probes 6.10.2 Windows and 6.4.2 Ubuntu; latest Qt 6.12.0 acquisition failed.

**Adaptations and comparison boundary:** Assessment probes only. libzip demonstrated typed progress/cancellation and ZIP updates; libarchive demonstrated streaming/fallback LhA/CAB; Qt is a native model/view/process shell.

**Upstream:** https://www.7-zip.org/ ; https://www.libarchive.org/ ; https://libzip.org/ ; https://doc.qt.io/qt-6/qt-releases.html

**Fixes and recommendation:** Use pinned stable engines; rerun latest Qt and clean-runner gates before choosing a shipped toolkit revision.

**License:** 7-Zip LGPL-2.1-or-later plus unRAR restrictions and BSD/public-domain files; libarchive BSD per-file; libzip BSD-3-Clause; Qt Core/Gui/Widgets LGPL-3.0 or commercial/GPL alternatives

**Build requirements:** Consistent C/C++ toolchains; compression/crypto deps; Qt platform/image plugins and licenses. Current libarchive links zlib,bzip2,lzma,lz4,zstd,crypto and platform XML/hash deps recorded in logs.

**Disposition:** retain as candidates; adopt only demonstrated roles

**Regression gate:** All native build/package gates, Unicode extraction and transaction security must pass

## License and maintenance limits

This is a source-notice inventory, not a complete distribution clearance. DES origins, embedded historical binaries and imported StuffIt fixture redistribution need provenance review before shipping. Root LGPL terms do not erase third-party notices. Ark code has GPL and other per-file SPDX terms; copying it creates a different licensing decision from studying its architecture. PeaZip 11.3.0 root LICENSE is LGPL-3.0; its bundled engines have separate licenses. NanaZip has its own packaging and inherited engine notices.

The old fork was compared against MacPaw snapshots, not against pristine historical releases of every embedded codec. Unresolved original-release identification and untested adaptations remain gates. The delta receipt distinguishes exact identity, changed files and removed files; comments can account for changes. No codec was replaced.
