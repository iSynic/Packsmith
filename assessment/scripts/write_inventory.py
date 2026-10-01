"""Render the audited dependency decisions and their evidence boundaries."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
rows=[]
def add(name,origin,revision,adaptations,upstream,fixes,license,build,disposition,gate):
    rows.append(dict(name=name,origin=origin,baseline_revision=revision,adaptations=adaptations,maintained_upstream=upstream,applicable_fixes=fixes,license=license,build_requirements=build,disposition=disposition,regression_gate=gate))
add('XADMaster','source/XADMaster; inherited fork pinned at 28a2330b16139f6d074cdf75ea34eee0ccd218c4','Exact containing commit; no standalone engine release confidently assigned',
    'Objective-C archive parsers, handles, fork extraction and platform implementations are application-specific. Do not replace the engine with a generic compression SDK.',
    'https://github.com/MacPaw/XADMaster; stable v1.10.8 and separately pinned development revision in sources.lock.json',
    'Stable 1.10.8 fixes the documented macOS quarantine advisory. Development revision fixes the tested 12-character StuffIt password failure and wrong-password debris. An unverified release promotion is not justified.',
    'LGPL-2.1-or-later at source/License.txt and current LICENSE; embedded files retain their own terms',
    'Foundation, Objective-C compiler/runtime, C/C++; whole-archive linkage. Windows head now builds with Clang 22.1.8, lld, GNUstep Base 1.31.1-10 and a compatible GCC 16.1 runtime. STRICT_APPLE_COMPATIBILITY=1 is mandatory. Two isolated Windows patches are recorded in evidence/windows-first.',
    'update and isolate','Local Windows bundle/preservation subset passes. Fresh-machine installation, independent StuffIt/StuffIt X/Compact Pro/LZX fork oracles, collision policy and containment remain required. Native macOS builds are deferred by the Windows-first direction.')
add('UniversalDetector','source/UniversalDetector; Objective-C wrapper plus Mozilla universalchardet','Exact containing baseline commit; no original Mozilla release assigned',
    'WrappedUniversalDetector and UniversalDetector bridge Mozilla detection into XADString; possibleMIMECharsets contains additional mappings. Filename decoding behavior is a compatibility contract.',
    'https://github.com/MacPaw/universal-detector at 4eb832d999628edcd3d134e46bd35357c8c99a85; no stable release found',
    'Compare encoding tables and wrappers before updating; do not equate a detected charset with a verified original name.',
    'Mozilla files offer MPL-1.1/GPL-2.0-or-later/LGPL-2.1-or-later alternatives; audit wrapper notices separately',
    'C++ and Objective-C compiler; Foundation; sibling directory expected by XAD makefiles',
    'update within isolated XAD worker','CP932, UTF-16, MacRoman and ambiguous-name fixtures with known raw name bytes and expected names; only LhA reading exercised here')
add('GNUstep and Objective-C runtime','Linked system dependency; old Windows makefile expects C:\\GNUstep\\GNUstep','No bundled Foundation/runtime version found; tested Linux Base 1.29.0, Make 2.9.1, GCC Objective-C 13.3 and libobjc4 package 14.2',
    'GNU_RUNTIME, fgnu-runtime, NSConstantString and historical hardcoded include/library paths; macOS uses Apple Foundation instead.',
    'https://www.gnustep.org/resources/downloads.html; Windows MSYS2 Base 1.31.1-10, Make 2.9.3-2 and libobjc2 2.2.1-7 now tested; exact closure in windows-runtime.lock.json',
    'Windows build uses Clang 22.1.8/lld, gnustep-2.0 ABI and STRICT_APPLE_COMPATIBILITY=1. GCC 16.2 runtime fails to load the current GNUstep package: five missing imports. GCC 16.1.0-1 overlay passes; GCC 15.2 also fails. Do not blindly refresh this runtime. See windows-first/runtime-compatibility.json.',
    'GNUstep Base LGPL; GCC runtime has its own runtime exception terms; Apple system framework terms on macOS',
    'Choose one compatible compiler/runtime ABI; distribute required runtime DLLs on Windows; clean runner needed',
    'isolate and update packaging','Native compilation/linking and bundled execution with system-only PATH pass on this host. Clean Windows VM/runner and full installation remain unverified.')
add('zlib','Linked -lz; Windows/include/zlib.h and Windows/lib/libz.a','Windows header 1.2.3 (2005); matching binary release not independently authenticated. Linux baseline system version unspecified. Tests used Linux package 1.3 and Windows 1.3.1.',
    'CSZlibHandle wraps stream/error behavior; XAD has its own Deflate-family implementations. Updating libz does not update those decoders.',
    'https://zlib.net/ stable 1.3.2 (2026-02-17)',
    '1.3.2 includes audit fixes and large-size APIs. Old precompiled Windows archive must be rebuilt rather than copied.',
    'zlib license','Portable C; consistent architecture and toolchain',
    'update linked dependency; retain wrapper','Deflate, ZIP64, gzip, CRC failures and NSIS-specific decoders; latter not certified')
add('bzip2','Linked -lbz2; Windows/include/bzlib.h and Windows/lib/libbz2.a','Both header and binary version string identify 1.0.5, 10-Dec-2007; tests used 1.0.8',
    'CSBzip2Handle wraps libbz2; XADNSISBzip2Handle is a separate adapted decoder and cannot be replaced by updating this library.',
    'https://sourceware.org/bzip2/ stable 1.0.8',
    'Replace historical binary with maintained source build; 1.0.8 addresses fixes absent in 1.0.5.',
    'bzip2 permissive license','Portable C; full version identity and source provenance for packaged binary',
    'update linked library; isolate adapted decoder','Bzip2 archives, concatenation, truncation and NSIS bzip2 fixtures (not present in shared suite)')
add('ICU','Linked -licuuc through XADStringICU on Linux','Baseline version unconstrained; Linux test build uses 74.2-1ubuntu3.1',
    'XADStringICU supplies non-Apple conversion behavior; Windows uses XADStringWindows.',
    'https://github.com/unicode-org/icu/releases/tag/release-78.3',
    'Latest stable audited as an update target; newer conversion behavior requires filename regression review.',
    'Unicode/ICU permissive license with third-party notices','C/C++; ICU data and ABI must be packaged consistently',
    'update and isolate to worker','Known byte-to-name fixtures; do not change detection guesses silently')
add('LZMA and branch filters','source/XADMaster/lzma; Igor Pavlov decoder sources','LzmaDec.c date 2008-11-06; LzmaDec.h date 2009-02-07. This mixed snapshot does not establish an exact SDK release.',
    'XADLZMAHandle/XADLZMA2Handle and WinZipJPEG/LZMA.h integrate streaming callbacks. All 9 embedded files are byte-identical in baseline, stable and head.',
    'https://www.7-zip.org/sdk.html and pinned 7-Zip 26.03; generic upstream is active, drop-in compatibility unproven',
    'No codec replacement applied. Treat modern SDK as a separate adapter experiment, preserving property/error semantics.',
    'Public-domain notices in decoder files; XAD wrappers LGPL-2.1-or-later','C with precise integer sizes and streaming adapter',
    'retain and isolate for legacy; use maintained 7-Zip for mainstream','LZMA/LZMA2 boundary cases, branch filters, WinZip JPEG and legacy decode hashes; coverage incomplete')
add('PPMd','source/XADMaster/PPMd; G/H/I model variants plus Brimstone allocator','Exact baseline file hashes recorded; no standalone upstream version asserted',
    'Separate SubAllocatorBrimstone and G/H/I implementations. Stable/head differ in 21 of 25 files, including added MacPaw license preambles; hash differences alone do not prove codec changes.',
    'Maintained containing project MacPaw/XADMaster; 7-Zip PPMd is an alternative for mainstream data, not demonstrated equivalent to all legacy variants',
    'Preserve adapted allocators; compare executable code separately from comments before any replacement.',
    'Current MacPaw PPMd files explicitly LGPL-2.1-or-later; baseline governed by repository terms where no separate notice exists','C; archive-specific model/allocator selection',
    'retain and isolate','StuffIt X Brimstone, G/H/I and corrupt-stream fixtures with independent hashes are required; not completed')
add('WavPack','source/XADMaster/wavpack; David Bryant/Conifer Software','Baseline bundled 4.60.1; stable/head bundled 5.1.0; current Linux worker links external 5.6.0',
    'XADWinZipWavPackHandle uses custom read/write callbacks and WinZip framing. Current non-Apple build chooses system header/library; old baseline embeds decoder source.',
    'https://www.wavpack.com/ latest 5.9.0',
    'Update through upstream adapter, not wholesale source transplant. Windows makefile needs reconciliation with current external-library requirement.',
    'BSD notices in source and the upstream project; the license.txt referenced by the headers is absent from both snapshots, so obtain version-matched license text for packaging','C; external development package on Linux, matching headers/DLLs for Windows; Apple build retains embedded source',
    'update using maintained upstream integration','WinZip WavPack payload oracle, old stream versions and malformed headers; not available here')
add('libxad','source/XADMaster/libxad; Dirk Stoecker Amiga library with Unix emulation','include/version.h says version 13 revision 0, DATETXT 31.03.2003; RCS stamp 2005-06-23; not a pristine upstream release',
    'libxad/all.c, clients.c and unix/emulation.c included directly; XADLibXADParser/XADLibXADIOHandle bridge I/O. 57/59 files identical to stable; 56/59 to head.',
    'Historical https://sourceforge.net/projects/libxad/; active independent maintenance not established. Maintained containing project is MacPaw/XADMaster.',
    'Do not replace with a similarly named modern library without proving client coverage; isolate legacy clients and report unsupported archives.',
    'LGPL-2.1-or-later in source; individual client notices require inclusion','C; Unix emulation and XAD callbacks',
    'retain and isolate','Representative Amiga LZX and obscure client archives, fork hashes, truncation and sanitizers; Amiga LZX still unverified')
add('WinZip JPEG','source/XADMaster/WinZipJPEG; repository-authored format-specific decompressor','Exact baseline hashes; no independent packaged release identified',
    'Arithmetic decoder, JPEG reconstruction and custom LZMA wrapper; XADWinZipJPEGHandle orchestrates ZIP method decoding.',
    'MacPaw/XADMaster is the containing upstream; generic libjpeg is not a replacement for this archive encoding',
    '10/12 files differ from baseline in stable/head, partly copyright/license text. Do not infer algorithm fixes from file counts.',
    'Containing repository LGPL-2.1-or-later; no separate release license established','C and XAD wrapper; embedded LZMA API',
    'retain and isolate','WinZip JPEG samples with original JPEG bytes and reconstruction hashes; not acquired')
add('Cryptography source','source/XADMaster/Crypto and archive-specific AES/DES handles','Brian Gladman AES Issue Date 20/12/2007, copyright 1998-2010; Stuart Levy DES April 1988; mixed SHA/MD5/HMAC code at exact baseline revision',
    'StuffIt DES password schedule, RAR/7z/ZIP key derivations and wrappers are format-specific. 18/20 Crypto files identical to stable/head.',
    'Containing upstream MacPaw/XADMaster; mainstream engines use their own crypto. Independent crypto origins and per-file notices retained.',
    'Tested development StuffIt password handling closes a concrete stable failure. Never modernize a legacy cipher in a way that changes archive semantics.',
    'AES permissive Gladman notice; remaining notices vary, some rely on containing LGPL terms; DES standalone grant not resolved','C; endian/integer behavior; process-isolated password channel',
    'retain and isolate legacy; use maintained engine crypto for new archives','Correct/wrong/long passwords, data/fork hashes and cleanup. New AES ZIP/7z exercised; legacy oracle incomplete')
add('Bundled iOS OpenSSL','source/Dependencies/iOS/Includes/openssl and Libraries/libcrypto.a','Binary strings identify OpenSSL 1.0.1b, 26 Apr 2012; exact original source build provenance absent',
    'iOS-specific binary outside desktop acceptance scope; presence must not be confused with a desktop build dependency.',
    'https://www.openssl.org/; current test toolchains use Windows 3.5.2 and Ubuntu 3.0.13 with distribution patches',
    'Exclude historical mobile binary from desktop packaging. Do not reuse old cryptography binaries.',
    'Historical OpenSSL/SSLeay terms; modern OpenSSL uses Apache-2.0; packaged version notices must match','Rebuild if mobile work is later authorized; not linked into this desktop assessment',
    'replace or exclude from desktop','No iOS claim; desktop crypto libraries recorded by configure/package receipts')
add('Windows compatibility code','source/XADMaster/Windows plus XADPlatformWindows.m and XADStringWindows.m','Exact baseline revision; all 9 Windows subtree files byte-identical in stable/head; includes old zlib/bzip2 static binaries',
    'regex.c compatibility shim, hardcoded GNUstep paths and Win32 filename/filesystem implementations are local portability layers.',
    'MacPaw/XADMaster for platform code; maintained OS/toolchain APIs for new worker integration',
    'Experimental native build replaces old binaries/paths and uses only the legacy regex header, avoiding old zlib/bzip2 headers. Two patches use _wunlink for UTF-16 paths and correct WideCharToMultiByte flags with round-trip rejection of lossy encoding. Unicode paths and encrypted StuffIt now pass on Windows; long paths/device names/reparse races remain open.',
    'Repository LGPL and dependency-specific notices; binary provenance incomplete','Objective-C-enabled toolchain/Foundation; compatible runtime ABI; current makefile omits WavPack linkage',
    'replace build plumbing; isolate compatibility code','Local native bundle, Unicode, resource-sidecar and tested password gates pass. Collision overwrite is demonstrated unsafe; clean installation, realistic corpus and race-safe extraction remain blockers.')
add('New evaluated libraries and toolkit','Pinned references, not integrated into product','7-Zip 26.03; libarchive 3.8.9; libzip 1.11.4. Qt probes 6.10.2 Windows and 6.4.2 Ubuntu; latest Qt 6.12.0 acquisition failed.',
    'Assessment probes only. libzip demonstrated typed progress/cancellation and ZIP updates; libarchive demonstrated streaming/fallback LhA/CAB; Qt is a native model/view/process shell.',
    'https://www.7-zip.org/ ; https://www.libarchive.org/ ; https://libzip.org/ ; https://doc.qt.io/qt-6/qt-releases.html',
    'Use pinned stable engines; rerun latest Qt and clean-runner gates before choosing a shipped toolkit revision.',
    '7-Zip LGPL-2.1-or-later plus unRAR restrictions and BSD/public-domain files; libarchive BSD per-file; libzip BSD-3-Clause; Qt Core/Gui/Widgets LGPL-3.0 or commercial/GPL alternatives',
    'Consistent C/C++ toolchains; compression/crypto deps; Qt platform/image plugins and licenses. Current libarchive links zlib,bzip2,lzma,lz4,zstd,crypto and platform XML/hash deps recorded in logs.',
    'retain as candidates; adopt only demonstrated roles','All native build/package gates, Unicode extraction and transaction security must pass')
(ROOT/'evidence'/'dependency-inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
parts=['# Unarchiver dependency inventory','Assessment started September 30, 2026; updated with the Windows-first build experiment October 1 UTC. All baseline components are frozen by the containing commit and file hashes; a date or version string is labeled as such rather than invented as an exact upstream revision. Proposed dispositions authorize no product changes.','Exact candidate pins: [sources lock](../evidence/sources.lock.json). File-by-file changes and hashes: [embedded source deltas](../evidence/embedded-source-deltas.json). Windows follow-up: [build and preservation report](windows-first.md), [current runtime closure](../evidence/windows-runtime.lock.json), [compatible runtime overlay](../evidence/windows-gcc16_1.lock.json). Build dependency versions: configure logs and [Linux environment](../evidence/linux-environment.log).']
for row in rows:
    parts+=['## '+row['name']]
    for key,label in [('origin','Origin'),('baseline_revision','Revision evidence'),('adaptations','Adaptations and comparison boundary'),('maintained_upstream','Upstream'),('applicable_fixes','Fixes and recommendation'),('license','License'),('build_requirements','Build requirements'),('disposition','Disposition'),('regression_gate','Regression gate')]:parts.append('**'+label+':** '+row[key])
parts+=['## License and maintenance limits','This is a source-notice inventory, not a complete distribution clearance. DES origins, embedded historical binaries and imported StuffIt fixture redistribution need provenance review before shipping. Root LGPL terms do not erase third-party notices. Ark code has GPL and other per-file SPDX terms; copying it creates a different licensing decision from studying its architecture. PeaZip 11.3.0 root LICENSE is LGPL-3.0; its bundled engines have separate licenses. NanaZip has its own packaging and inherited engine notices.','The old fork was compared against MacPaw snapshots, not against pristine historical releases of every embedded codec. Unresolved original-release identification and untested adaptations remain gates. The delta receipt distinguishes exact identity, changed files and removed files; comments can account for changes. No codec was replaced.']
(ROOT/'reports'/'dependency-inventory.md').write_text('\n\n'.join(parts)+'\n',encoding='utf-8')
print('wrote',len(rows),'dependency records')
