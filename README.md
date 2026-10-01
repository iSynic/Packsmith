# Packsmith

Packsmith is an archive manager for Windows, with extra care for classic Mac files. It started as a fork of Unarchiver and now has a desktop interface for browsing, extracting, creating and editing archives.

## Download

Get the Windows ZIP from [the latest release](https://github.com/iSynic/Packsmith/releases/latest), extract the whole folder, and run `Packsmith.exe`. There's no installer. The app is unsigned, so Windows may show a SmartScreen warning.

## What it does

- Creates and edits ZIP and 7z archives.
- Opens StuffIt, BinHex, MacBinary, Compact Pro, LhA and Amiga LZX archives through the existing legacy engine. Support varies by compression method; [the support table](assessment/reports/packsmith-beta4.md) shows what we've tested.
- Browses folders, searches the whole archive, and shows file details and separate data/resource-fork sizes.
- Preserves classic Mac resource forks and Finder metadata in AppleDouble sidecars. Keep each extracted file with its matching `._filename` file.
- Exports legacy files as a ZIP of MacBinary files, with a preservation report and instructions for restoring them on a classic Mac.

**Extract** uses your selection, or the current folder if nothing is selected. **Extract All** extracts the whole archive. Search results need a selection. You can also open an archive by dropping one file onto the window.

Recent archive history is off by default. Enable it in the File menu if you want it; disabling it clears the saved paths. Passwords aren't saved.

Extraction is staged and checked before output is committed. Corrupt archives don't leave a published partial extraction. Edits keep a backup of the original. The results panel shows what was written, what was verified, and any filename changes or recovery files.

## Current limits

Windows x64 only for now. Legacy formats are read-only, and StuffIt X is unverified. Classic Mac export targets Mac Roman names and classic HFS limits; names outside that profile need mapping. Some metadata and historical timestamps have limitations.

This is still beta software. Full Narrator testing and fresh-machine source builds are unfinished. See [the support matrix and current-state notes](assessment/reports/packsmith-beta4.md) for the evidence and remaining gaps.

## Building and source

The current build uses Qt 6.10.2 MinGW x64, GCC 15.2.0, CMake and Ninja, plus a separately provisioned Objective-C toolchain for the legacy worker. With those dependencies in place:

```powershell
python scripts/build_windows.py
```

The app is built into `dist/Packsmith-preview/`. [Build and relink details](docs/releasing.md) cover the pinned dependencies; this isn't a one-command setup on a fresh machine.

Each release includes matching source and relink materials. Packsmith retains the original project's LGPL-2.1-or-later license. See [LICENSE](LICENSE) and [third-party notices](NOTICE.md).
