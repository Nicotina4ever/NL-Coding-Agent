"""Generate the NL Code application icons from the product brand palette.

The Code - OSS Windows package uses resources/win32/code.ico for the executable
and file icons, and resources/win32/code_150x150.png / code_70x70.png for the
window assets. This script regenerates those files in a build tree without
requiring an SVG rasterizer.

Usage:
    python scripts/nlcode/make_brand_icon.py <resources-win32-dir>

Brand anchors (assets/theme.tokens.json): electric violet #7531FE, deep purple
#521B8D, magenta #E4469B.
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - build tooling dependency
    raise SystemExit("Pillow is required in the build runtime (python\\python.exe -m pip install Pillow)")

VIOLET = (0x75, 0x31, 0xFE)
DEEP_PURPLE = (0x52, 0x1B, 0x8D)
MAGENTA = (0xE4, 0x46, 0x9B)
WHITE = (255, 255, 255, 255)
MASTER = 1024
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in (
        Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        Path(r"C:\Windows\Fonts\seguisb.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
    ):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def render_master() -> Image.Image:
    image = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Diagonal brand gradient inside a rounded-square badge.
    margin = 34
    badge = [margin, margin, MASTER - margin, MASTER - margin]
    radius = 210
    gradient = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for step in range(256):
        t = step / 255
        if t < 0.55:
            color = _lerp(VIOLET, DEEP_PURPLE, t / 0.55)
        else:
            color = _lerp(DEEP_PURPLE, MAGENTA, (t - 0.55) / 0.45 * 0.35)
        gradient_draw.line([(0, step * 4), (MASTER, step * 4)], fill=color + (255,))
    mask = Image.new("L", (MASTER, MASTER), 0)
    ImageDraw.Draw(mask).rounded_rectangle(badge, radius=radius, fill=255)
    image.paste(gradient, (0, 0), mask)

    # White N monogram.
    font = _font(600)
    draw.text((MASTER / 2, MASTER / 2 - 10), "N", font=font, fill=WHITE, anchor="mm")

    # Restrained accent: a short cyan-magenta underline under the monogram.
    draw.rounded_rectangle([MASTER / 2 - 150, MASTER / 2 + 300, MASTER / 2 + 150, MASTER / 2 + 330],
                           radius=15, fill=(0x46, 0xA3, 0xC0, 255))
    return image


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    target = Path(argv[1])
    if not target.is_dir():
        print("not a directory: " + str(target))
        return 2
    master = render_master()
    ico_path = target / "code.ico"
    master.save(ico_path, format="ICO", sizes=[(size, size) for size in ICON_SIZES])
    master.resize((150, 150), Image.Resampling.LANCZOS).save(target / "code_150x150.png")
    master.resize((70, 70), Image.Resampling.LANCZOS).save(target / "code_70x70.png")
    print("wrote " + str(ico_path) + " (" + str(ico_path.stat().st_size) + " bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
