"""Rebuild the legacy helper using the source-materials release asset."""
import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--materials', type=Path, required=True)
    parser.add_argument('--compiler', type=Path, required=True, help='MinGW-targeting Clang with lld (tested: 22.1.8)')
    parser.add_argument('--source', type=Path, help='Replacement helper source; defaults to materials/app/xad_stream.m')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    materials, output, compiler = args.materials.resolve(), args.output.resolve(), args.compiler.resolve()
    source = (args.source or materials / 'app/xad_stream.m').resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [str(compiler), '-O2', '-fobjc-runtime=gnustep-2.0', '-fexceptions', '-fobjc-exceptions', '-fblocks',
               '-fconstant-string-class=NSConstantString', '-DSTRICT_APPLE_COMPATIBILITY=1',
               '-D_NATIVE_OBJC_EXCEPTIONS', '-D_FILE_OFFSET_BITS=64',
               '-I' + str(materials / 'relink/include'), '-I' + str(materials / 'sources/XADMaster'),
               '-I' + str(materials / 'relink/compat-include'), '-L' + str(materials / 'relink/lib'),
               '-fuse-ld=lld', str(source), '-Wl,--whole-archive',
               str(materials / 'relink/lib/libxad.a'), str(materials / 'relink/lib/libdetector.a'),
               '-Wl,--no-whole-archive', '-lgnustep-base', '-lobjc', '-lstdc++', '-lz', '-lbz2', '-lwavpack',
               '-lwinmm', '-lgdi32', '-o', str(output)]
    env = os.environ.copy()
    env['PATH'] = str(compiler.parent) + os.pathsep + env['PATH']
    subprocess.run(command, env=env, check=True)
    print('Rebuilt helper: ' + str(output))


if __name__ == '__main__':
    main()
