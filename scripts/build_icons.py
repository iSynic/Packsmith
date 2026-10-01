"""Convert generated RGBA masters into native icon formats without changing the artwork."""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ICONS = ROOT / "assets/icons"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256, 512)


def main():
    records = []
    for name in ("packsmith", "packsmith-archive"):
        source = ICONS / (name + "-master.png")
        with Image.open(source) as master:
            if master.mode != "RGBA" or master.width != master.height:
                raise RuntimeError("Icon master must be square RGBA: " + str(source))
            if master.getextrema()[3] != (0, 255):
                raise RuntimeError("Icon master needs transparent and opaque pixels")
            for size in SIZES:
                master.resize((size, size), Image.Resampling.LANCZOS).save(ICONS / f"{name}-{size}.png")
            master.save(ICONS / (name + ".ico"), sizes=[(size, size) for size in SIZES if size <= 256])
        with Image.open(ICONS / (name + ".ico")) as icon:
            if icon.ico.sizes() != {(size, size) for size in SIZES if size <= 256}:
                raise RuntimeError("ICO size directory differs from requested sizes")
        records.append({"name": name, "source": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                        "png_sizes": SIZES, "ico_sizes": [size for size in SIZES if size <= 256]})
    (ICONS / "formats.json").write_text(json.dumps({"conversion": "Pillow RGBA downsampling/ICO encoding; generated artwork and alpha preserved",
                                                  "icons": records}, indent=2) + "\n", encoding="utf-8")
    print("Built Packsmith PNG sizes and multi-resolution ICOs")


if __name__ == "__main__":
    main()
