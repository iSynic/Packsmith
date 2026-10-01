"""Compile XAD in an isolated copy using a pinned modern native runtime."""
import json
import difflib
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
PREFIX=ROOT/'tools'/'windows-runtime'/'mingw64'
COMPAT=ROOT/'tools'/'windows-runtime-gcc16_1'/'mingw64'
BASE=ROOT/'experiments'/'xad-windows';BASE.mkdir(exist_ok=True)
EVIDENCE=ROOT/'evidence'/'windows-first';EVIDENCE.mkdir(exist_ok=True)
env=os.environ.copy();env['PATH']=str(COMPAT/'bin')+os.pathsep+str(PREFIX/'bin')+os.pathsep+env['PATH']
rows=[]
def run(name,args,cwd=None,expected=0):
    args=[str(a).replace('\\','/') for a in args]
    log=EVIDENCE/(name+'.log');start=time.monotonic()
    with log.open('w') as out:result=subprocess.run([str(a) for a in args],env=env,cwd=cwd,stdout=out,stderr=subprocess.STDOUT)
    rows.append({'name':name,'command':[str(a) for a in args],'cwd':str(cwd or Path.cwd()),'exit_code':result.returncode,'expected_exit_code':expected,'status':'pass' if result.returncode==expected else 'fail','elapsed_seconds':round(time.monotonic()-start,3),'log':log.name})
    (EVIDENCE/'builds.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(name,result.returncode,flush=True)
    if result.returncode!=expected:print('\n'.join(log.read_text(errors='replace').splitlines()[-22:]),flush=True)
    return result.returncode==expected

clang=PREFIX/'bin'/'clang.exe'
flags=['-fobjc-runtime=gnustep-2.0','-fexceptions','-fobjc-exceptions','-fblocks','-fconstant-string-class=NSConstantString','-DSTRICT_APPLE_COMPATIBILITY=1','-D_NATIVE_OBJC_EXCEPTIONS','-D_FILE_OFFSET_BITS=64','-I'+str(PREFIX/'include'),'-L'+str(PREFIX/'lib')]
probe=BASE/'foundation-probe.exe'
shutil.copy2(COMPAT/'bin'/'libstdc++-6.dll',BASE/'libstdc++-6.dll')
if not run('foundation-build',[clang,'-L'+str(COMPAT/'lib'),*flags,'-fuse-ld=lld',ROOT/'scripts'/'windows_foundation_probe.m','-lgnustep-base','-lobjc','-lstdc++','-o',probe]):raise SystemExit(1)
if not run('foundation-run',[probe]):raise SystemExit(1)
negative=BASE/'foundation-without-abi-flag.exe'
if not run('foundation-negative-build',[clang,'-L'+str(COMPAT/'lib'),*[f for f in flags if f!='-DSTRICT_APPLE_COMPATIBILITY=1'],'-fuse-ld=lld',ROOT/'scripts'/'windows_foundation_probe.m','-lgnustep-base','-lobjc','-lstdc++','-o',negative]):raise SystemExit(1)
if not run('foundation-negative-run',[negative],expected=1):raise SystemExit(1)

src=BASE/'XADMaster';detector=BASE/'UniversalDetector'
for dest,ref in ((src,'xad-head'),(detector,'detector')):
    if not dest.exists():shutil.copytree(ROOT/'references'/ref,dest,ignore=shutil.ignore_patterns('.git'))

original=(ROOT/'references'/'xad-head'/'XADUnarchiver.m').read_text()
old='unlink([destpath fileSystemRepresentation]);'
if original.count(old)!=1:raise RuntimeError('Unexpected upstream unlink call')
replacement='#ifdef _WIN32\n\t\t\t_wunlink((const wchar_t *)[destpath fileSystemRepresentation]);\n#else\n\t\t\tunlink([destpath fileSystemRepresentation]);\n#endif'
patched=original.replace(old,replacement)
(src/'XADUnarchiver.m').write_text(patched)
(EVIDENCE/'windows-wide-unlink.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),patched.splitlines(True),fromfile='a/XADUnarchiver.m',tofile='b/XADUnarchiver.m')))
encoding_original=(ROOT/'references'/'xad-head'/'XADStringWindows.m').read_text()
encoding_patched=encoding_original.replace('int numbytes=WideCharToMultiByte(codepage,MB_ERR_INVALID_CHARS,','DWORD flags=(codepage==CP_UTF8||codepage==54936)?WC_ERR_INVALID_CHARS:0;\n\tint numbytes=WideCharToMultiByte(codepage,flags,')
encoding_patched=encoding_patched.replace('WideCharToMultiByte(codepage,MB_ERR_INVALID_CHARS,charbuf,numchars,bytebuf,numbytes,NULL,NULL);','if(WideCharToMultiByte(codepage,flags,charbuf,numchars,bytebuf,numbytes,NULL,NULL)!=numbytes)\n\t{\n\t\tfree(bytebuf);\n\t\treturn nil;\n\t}')
encoding_patched=encoding_patched.replace('return [NSData dataWithBytesNoCopy:bytebuf length:numbytes freeWhenDone:YES];','NSData *data=[NSData dataWithBytesNoCopy:bytebuf length:numbytes freeWhenDone:YES];\n\tif(![[self stringForData:data encodingName:encoding] isEqualToString:string]) return nil;\n\treturn data;')
if encoding_patched==encoding_original:raise RuntimeError('Unexpected upstream encoding implementation')
(src/'XADStringWindows.m').write_text(encoding_patched)
(EVIDENCE/'windows-encoding.patch').write_text(''.join(difflib.unified_diff(encoding_original.splitlines(True),encoding_patched.splitlines(True),fromfile='a/XADStringWindows.m',tofile='b/XADStringWindows.m')))
compat_include=BASE/'compat-include';compat_include.mkdir(exist_ok=True)
shutil.copy2(src/'Windows'/'include'/'regex.h',compat_include/'regex.h')
def sources(path):
    text=(path/'Makefile.common').read_text().replace('\\\n',' ')
    found=[]
    for kind in ('OBJC','C','CXX'):
        match=re.search(r'^LIBRARY_'+kind+r'_FILES\s*=([^\n]*)',text,re.M)
        found += [path/name for name in match.group(1).split()] if match else []
    return found
def quoted(path):return '"'+str(path).replace('\\','/')+'"'

project=BASE/'project';project.mkdir(exist_ok=True)
cmake='''cmake_minimum_required(VERSION 3.20)
project(XADWindowsProbe LANGUAGES C CXX OBJC)
set(CMAKE_C_STANDARD 99)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_OBJC_FLAGS "${CMAKE_OBJC_FLAGS} -fobjc-runtime=gnustep-2.0 -fobjc-exceptions -fblocks -fconstant-string-class=NSConstantString")
add_compile_definitions(STRICT_APPLE_COMPATIBILITY=1 _NATIVE_OBJC_EXCEPTIONS _FILE_OFFSET_BITS=64)
add_compile_options(-fexceptions -Wno-multichar -Wno-import)
add_link_options(-fuse-ld=lld)
'''
cmake+='include_directories('+quoted(PREFIX/'include')+' '+quoted(src)+' '+quoted(compat_include)+')\n'
cmake+='link_directories('+quoted(COMPAT/'lib')+' '+quoted(PREFIX/'lib')+')\n'
cmake+='add_library(detector STATIC\n'+'\n'.join(quoted(p) for p in sources(detector))+'\n)\n'
cmake+='add_library(xad STATIC\n'+'\n'.join(quoted(p) for p in [*sources(src),src/'XADPlatformWindows.m',src/'XADStringWindows.m',src/'Windows'/'regex.c'])+'\n)\n'
cmake+='add_executable(xad-worker '+quoted(ROOT/'scripts'/'xad_probe.m')+')\n'
cmake+='set_property(TARGET xad-worker PROPERTY LINKER_LANGUAGE CXX)\n'
cmake+='target_link_libraries(xad-worker PRIVATE "-Wl,--whole-archive" xad detector "-Wl,--no-whole-archive" gnustep-base objc z bz2 wavpack winmm gdi32)\n'
cmake+='target_link_options(xad-worker PRIVATE -municode)\n'
cmake+='add_executable(lsar '+ ' '.join(quoted(src/name) for name in ('lsar.m','CSJSONPrinter.m','CSCommandLineParser.m','CommandLineCommon.m','NSStringPrinting.m'))+')\n'
cmake+='set_property(TARGET lsar PROPERTY LINKER_LANGUAGE CXX)\n'
cmake+='target_link_libraries(lsar PRIVATE "-Wl,--whole-archive" xad detector "-Wl,--no-whole-archive" gnustep-base objc z bz2 wavpack winmm gdi32 shell32)\n'
cmake+='add_executable(xad-diagnose '+quoted(ROOT/'scripts'/'windows_xad_diagnose.m')+')\n'
cmake+='set_property(TARGET xad-diagnose PROPERTY LINKER_LANGUAGE CXX)\n'
cmake+='target_link_options(xad-diagnose PRIVATE -municode)\n'
cmake+='target_link_libraries(xad-diagnose PRIVATE "-Wl,--whole-archive" xad detector "-Wl,--no-whole-archive" gnustep-base objc z bz2 wavpack winmm gdi32)\n'
cmake+='add_executable(encoding-probe '+quoted(ROOT/'scripts'/'windows_encoding_probe.m')+')\n'
cmake+='set_property(TARGET encoding-probe PROPERTY LINKER_LANGUAGE CXX)\n'
cmake+='target_link_libraries(encoding-probe PRIVATE "-Wl,--whole-archive" xad detector "-Wl,--no-whole-archive" gnustep-base objc z bz2 wavpack winmm gdi32)\n'
(project/'CMakeLists.txt').write_text(cmake)
build=BASE/'build-clang22'
if not run('xad-configure',['C:/msys64/mingw64/bin/cmake.exe','-S',project,'-B',build,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release','-DCMAKE_C_COMPILER='+str(clang),'-DCMAKE_OBJC_COMPILER='+str(clang),'-DCMAKE_CXX_COMPILER='+str(PREFIX/'bin'/'clang++.exe'),'-DCMAKE_CXX_FLAGS=','-DCMAKE_MAKE_PROGRAM=C:/msys64/mingw64/bin/ninja.exe']):raise SystemExit(1)
if not run('xad-build',['C:/msys64/mingw64/bin/cmake.exe','--build',build,'-j','4']):raise SystemExit(1)
