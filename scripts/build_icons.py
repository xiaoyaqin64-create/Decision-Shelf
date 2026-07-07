from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "build-assets"


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = (
        ["C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/arialbd.ttf"]
        if bold
        else ["C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/arial.ttf"]
    )
    candidates += [
        "/System/Library/Fonts/NewYork.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def render(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), "#f4efe6")
    draw = ImageDraw.Draw(image)
    margin = round(size * 0.14)
    radius = round(size * 0.18)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=radius,
        fill="#b64d35",
    )
    # A small shelf edge makes the existing DS brand mark read as a book.
    shelf_y = round(size * 0.77)
    draw.rounded_rectangle(
        (round(size * 0.19), shelf_y, round(size * 0.81), round(size * 0.84)),
        radius=max(1, round(size * 0.018)),
        fill="#70442e",
    )
    label = "DS"
    label_font = font(round(size * 0.33), bold=True)
    box = draw.textbbox((0, 0), label, font=label_font)
    width, height = box[2] - box[0], box[3] - box[1]
    draw.text(
        ((size - width) / 2, (size - height) / 2 - size * 0.04),
        label,
        font=label_font,
        fill="#fffaf2",
        stroke_width=max(0, round(size * 0.002)),
    )
    return image


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    master = render(1024)
    master.save(OUTPUT / "decision-shelf.png")
    master.save(
        OUTPUT / "decision-shelf.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )

    if sys.platform == "darwin":
        iconset = OUTPUT / "DecisionShelf.iconset"
        iconset.mkdir(exist_ok=True)
        variants = {
            "icon_16x16.png": 16,
            "icon_16x16@2x.png": 32,
            "icon_32x32.png": 32,
            "icon_32x32@2x.png": 64,
            "icon_128x128.png": 128,
            "icon_128x128@2x.png": 256,
            "icon_256x256.png": 256,
            "icon_256x256@2x.png": 512,
            "icon_512x512.png": 512,
            "icon_512x512@2x.png": 1024,
        }
        for name, dimension in variants.items():
            master.resize((dimension, dimension), Image.Resampling.LANCZOS).save(iconset / name)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUTPUT / "decision-shelf.icns")],
            check=True,
        )


if __name__ == "__main__":
    main()
