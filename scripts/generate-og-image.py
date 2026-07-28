#!/usr/bin/env python3
"""Render the Open Graph share image with correct Persian text shaping.

Why this exists
---------------
`next/og` (Satori) has no Arabic/Persian shaping engine: it renders Persian
letters in isolated form, left-to-right, which looks broken. Pillow compiled
with **raqm** delegates to HarfBuzz + FriBiDi, producing correctly joined and
correctly ordered text.

The image is generated once and committed to `frontend/public/og.png`, so the
deployment has no runtime font or shaping dependency.

    python scripts/generate-og-image.py [--font-dir DIR] [--out PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, features

W, H = 1200, 630

BG_TOP = (15, 20, 32)
BG_BOTTOM = (30, 39, 64)
TEXT = (232, 237, 247)
MUTED = (150, 163, 191)
PRIMARY = (79, 140, 255)
CHIP_BG = (28, 38, 62)
CHIP_BORDER = (42, 53, 80)

EYEBROW = "GOZARESH  ·  ENTERPRISE REPORTING"
TITLE = "سامانه گزارش‌گیری سازمانی"
SUBTITLE = "محاسبات چندارزی زیر ۵۰ میلی‌ثانیه · گردش‌کار تأیید امضاشده · حسابرسی تغییرناپذیر"
CHIPS = ["Decimal 16dp", "RSA Signatures", "Hash-chained Audit", "FastAPI + Next.js"]


def load_font(font_dir: Path, name: str, size: int) -> ImageFont.FreeTypeFont:
    path = font_dir / name
    if not path.exists():
        sys.exit(
            f"✗ Font not found: {path}\n"
            "  Download Vazirmatn: https://github.com/rastikerdar/vazirmatn/releases\n"
            "  then pass --font-dir pointing at the extracted ttf folder."
        )
    return ImageFont.truetype(str(path), size)


def gradient_background() -> Image.Image:
    base = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(base)
    for y in range(H):
        t = y / H
        draw.line(
            [(0, y), (W, y)],
            fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM, strict=True)),
        )
    return base


def draw_centered(draw: ImageDraw.ImageDraw, y: int, text: str, font, fill, rtl: bool = False) -> int:
    """Draw horizontally centred text; returns the bottom y coordinate."""
    direction = "rtl" if rtl else "ltr"
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, direction=direction)
    draw.text(((W - (right - left)) / 2 - left, y - top), text, font=font, fill=fill, direction=direction)
    return y + (bottom - top)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--font-dir", type=Path, default=Path("/tmp"), help="folder containing Vazirmatn *.ttf")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "frontend" / "public" / "og.png",
        help="output PNG path",
    )
    args = parser.parse_args()

    if not features.check("raqm"):
        sys.exit(
            "✗ Pillow was built without raqm; Persian text would render unshaped.\n"
            "  Install libraqm (e.g. `apt-get install libraqm0`) and reinstall Pillow."
        )

    font_eyebrow = load_font(args.font_dir, "Vazirmatn-Medium.ttf", 30)
    font_title = load_font(args.font_dir, "Vazirmatn-Bold.ttf", 78)
    font_sub = load_font(args.font_dir, "Vazirmatn-Regular.ttf", 29)
    font_chip = load_font(args.font_dir, "Vazirmatn-Medium.ttf", 24)

    image = gradient_background()
    draw = ImageDraw.Draw(image)

    # Accent bar along the top edge
    draw.rectangle([0, 0, W, 6], fill=PRIMARY)

    draw_centered(draw, 96, EYEBROW, font_eyebrow, PRIMARY)
    draw_centered(draw, 178, TITLE, font_title, TEXT, rtl=True)
    draw_centered(draw, 322, SUBTITLE, font_sub, MUTED, rtl=True)

    # Feature chips, centred as one row
    gap, pad_x, chip_h = 18, 26, 52
    widths = []
    for label in CHIPS:
        left, _, right, _ = draw.textbbox((0, 0), label, font=font_chip)
        widths.append(right - left + pad_x * 2)

    x = (W - (sum(widths) + gap * (len(CHIPS) - 1))) / 2
    y = 430
    for label, width in zip(CHIPS, widths, strict=True):
        draw.rounded_rectangle([x, y, x + width, y + chip_h], radius=chip_h // 2, fill=CHIP_BG, outline=CHIP_BORDER)
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font_chip)
        draw.text(
            (x + (width - (right - left)) / 2 - left, y + (chip_h - (bottom - top)) / 2 - top),
            label,
            font=font_chip,
            fill=TEXT,
        )
        x += width + gap

    draw_centered(draw, 542, "github.com/mamadiezad/gozaresh-reporting-system  ·  made by Mohammad", font_sub, MUTED)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out, "PNG", optimize=True)
    print(f"✓ Wrote {args.out} ({args.out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
