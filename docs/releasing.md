# Windows beta packaging and source materials

The Windows beta is a portable x64 ZIP. Extract the entire folder and run `Packsmith.exe`; keep the workers and private legacy runtime directories together. The executables are unsigned. No installer, file association, administrative privilege, activation key or signature enforcement is required. A replacement Qt DLL or rebuilt legacy helper can be run normally.

Each release provides the binary ZIP, a corresponding-source materials ZIP, a release manifest and SHA-256 checksums. The source-materials ZIP contains:

- The complete authored repository snapshot at the release commit (`Packsmith-source.tar.gz`).
- Exact patched XADMaster and UniversalDetector source trees and the original Windows patches.
- Official 7-Zip 26.03 and Qt Base 6.10.2 source archives. Qt Base includes all the Qt modules/plugins shipped here, including the ICO plugin.
- Exact MSYS2 source packages for each runtime DLL, with upstream source payloads, distribution patches, licenses and PKGBUILD recipes. `source-materials.json` maps exact DLL content to source-package versions. Extract these `.src.tar.zst` archives with a current 7-Zip/MSYS2 tar, then follow the included PKGBUILD for a modified library build.
- Matching XAD/UniversalDetector static libraries, GNUstep/runtime import libraries, public/generated headers, compatibility headers and a helper relinking script. Sources for all these materials accompany them.

## Relink or modify the legacy helper

Use a MinGW-targeting Clang/lld toolchain; the observed build uses 22.1.8 with GNUstep 2.0 Objective-C ABI. Keep `STRICT_APPLE_COMPATIBILITY=1`: omitting it changes GNUstep's Foundation string ABI. The full observed compiler flags and engine CMake recipe are in the materials. Their recorded absolute paths document the build machine; substitute your extracted source and toolchain paths when rebuilding the engine libraries. The repository's `assessment/scripts/build_xad_windows.py` constructs the source lists and CMake recipe from each engine's `Makefile.common`.

From the authored repository, after extracting the source materials:

```powershell
python scripts/relink_legacy.py --materials C:/path/Packsmith-0.1.0-beta.1-source-materials --compiler C:/path/mingw64/bin/clang.exe --output C:/path/xad-stream.exe
```

To rebuild changed helper code, also pass `--source C:/path/modified-xad_stream.m`. To change an engine, build its matching replacement `.a` library and substitute it under `relink/lib` before running the same command. Copy the resulting helper over `workers/legacy/xad-stream.exe` in an extracted binary package. Leave the legacy DLLs in that directory. The helper deliberately uses the GNUstep-compatible GCC 16.1 runtime, while the Qt application uses GCC 15.2; the newer GCC 16.2 runtime failed the recorded GNUstep loader tests.

The desktop/worker can be rebuilt using the repository CMake target, Qt 6.10.2 MinGW x64 SDK and 7-Zip headers from the supplied source. Supply the extracted 7-Zip source with `-DSEVENZIP_SOURCE=C:/path/7zip` and Qt with `-DCMAKE_PREFIX_PATH=C:/path/Qt/6.10.2/mingw_64`. The build scripts currently require locally provisioned toolchains; this release does not claim a fresh-machine bootstrap build.

## Maintainer sequence

1. Update `app/version.h`; the Qt version string and Windows resource metadata use it.
2. Run `python scripts/prepare_release_sources.py` to match every shipped runtime DLL to its exact source package, then `python scripts/build_windows.py`.
3. Run the worker, legacy, native GUI and branding tests listed in the root README, then `python assessment/scripts/verify_assessment.py`.
4. Run `python scripts/package_beta.py --prepare-only`, relink the helper from those materials and verify listing/test/extraction with the generated fork fixtures. Check that the relinked process runs with only its private runtime directory.
5. Commit the source, packaging scripts and test receipts; push without force. Run `python scripts/package_beta.py` against the clean commit to assemble the versioned release assets.
6. Create an annotated version tag at that commit. Upload the binary, source-materials, release manifest and checksum assets to a draft GitHub prerelease, verify the uploaded SHA-256 digests and tag target, then publish it as a prerelease.

Release notes must keep the demonstrated format/operation scope and outstanding qualification gates visible. The original assessment's failed or unverified checks are retained as evidence. A beta publication does not mark them passed.

## Unpublished candidates

Run `python scripts/package_beta.py --candidate` to package the exact current workspace without committing, tagging, uploading or publishing. It writes versioned assets under `dist/candidates/`, includes a tarball of non-ignored authored workspace files, and records every snapshot hash, the base commit and dirty state. It validates the binary package and authored-source hashes before assembly. Private corpus inputs/outputs remain excluded by Git's ignore rules. This snapshot receipt is not a release-commit claim; the normal tagged-release command still requires a clean commit.

Beta 2 checks also include `python tests/run_beta2.py` and the local corpus qualification described in the root README. New receipts live under `assessment/evidence/beta2/`. Preserve published beta 1 assets, tags and historical receipts.

Beta 3 uses `tests/run_beta3.py`, `tests/classic_test.py`, the existing smoke/recovery/branding checks, and original/modified relink checks. Receipts live under `assessment/evidence/beta3/`; preserve beta 1/beta 2 artifacts. The classic Mac oracle requires isolated disk copies, explicit UI expansion/shutdown and independent HFS inspection. Never include private inventories, disk images, ROMs, proprietary tools or user archives in Git/assets. The candidate remains unpublished; signing, clean-machine certification and publishing are separate tasks.
