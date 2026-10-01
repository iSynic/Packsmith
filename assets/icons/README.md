# Packsmith icons

Two transparent raster masters were generated with the built-in image_gen tool for this project:

* `packsmith-master.png`: the application mark, a golden archive box and zipper on a forged-metal base.
* `packsmith-archive-master.png`: a matching archive-document icon, derived from the application mark.

The exact final prompts and reference relationship are recorded in [generation.json](generation.json). The original generated artwork and alpha remain in both masters. [formats.json](formats.json) records master SHA-256 hashes and converted sizes.

`packsmith.ico` and `packsmith-archive.ico` contain 16, 20, 24, 32, 40, 48, 64, 96, 128 and 256-pixel frames. Corresponding PNGs also include 512 pixels. Regenerate format/size variants using Pillow:

```powershell
python scripts/build_icons.py
```

The application icon is embedded in the Windows executable as icon group 101 and loaded into Qt for the window/taskbar and in-app header. The archive-document icon is group 102, used by Open and supplied as a separate ICO for future file associations. Associations are not registered by this preview. Qt resources embed both icons; the portable package includes the ICO image plugin and standalone ICO/256-pixel PNG assets.
