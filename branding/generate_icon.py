"""Generate the Babarify Frame app icon set from the source artwork.

Source: branding/source/babarify-frame-source.webp (1254 x 1254, full-bleed
dark background around a rounded, glowing tile). The script crops to the
tile, makes the area outside its rounded corners transparent, and writes
PNG sizes plus a multi-size Windows .ico.

Usage:  python branding/generate_icon.py   (requires Pillow)
"""

import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent
SOURCE = ROOT / "source" / "babarify-frame-source.webp"
OUT = ROOT / "icon"
APP_RESOURCES = ROOT.parent / "src" / "babarify_frame" / "resources" / "icons"
APP_PNG_SIZES = [16, 32, 64, 256]

# Tile geometry measured on the 1254 px source (glowing border line included).
CROP = (70, 59, 1170, 1159)  # square crop centred on the tile
TILE = (18, 19, 1082, 1080)  # border-line centre +5 px, inside the crop
TILE_RADIUS = 260
FEATHER = 1.5  # soften the mask edge (crop pixels)

PNG_SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
SHARPEN_MAX = 48  # light unsharp mask at small sizes


def master():
    art = Image.open(SOURCE).convert("RGBA").crop(CROP)
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(TILE, radius=TILE_RADIUS, fill=255)
    art.putalpha(mask.filter(ImageFilter.GaussianBlur(FEATHER)))
    return art


def sized(art, px):
    im = art.resize((px, px), Image.LANCZOS)
    if px <= SHARPEN_MAX:
        im = im.filter(ImageFilter.UnsharpMask(radius=0.6, percent=60, threshold=0))
    return im


def main():
    (OUT / "png").mkdir(parents=True, exist_ok=True)
    art = master()
    images = {px: sized(art, px) for px in PNG_SIZES}
    for px, im in images.items():
        im.save(OUT / "png" / f"babarify-frame-{px}.png")

    ico = [images[px] for px in ICO_SIZES]
    ico[-1].save(OUT / "babarify-frame.ico", sizes=[(p, p) for p in ICO_SIZES], append_images=ico[:-1])

    # Copies bundled with the application package.
    APP_RESOURCES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT / "babarify-frame.ico", APP_RESOURCES / "babarify-frame.ico")
    for px in APP_PNG_SIZES:
        shutil.copy2(OUT / "png" / f"babarify-frame-{px}.png", APP_RESOURCES / f"babarify-frame-{px}.png")
    print(f"Wrote icon set to {OUT} and {APP_RESOURCES}")


if __name__ == "__main__":
    main()
