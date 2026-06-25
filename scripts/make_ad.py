"""
Compose a finished Boschly ad: headline text + watermark on a photo.

Handles legibility scrims automatically so white text/marks stay readable on
busy or partly-bright photos.

Usage:
  python scripts/make_ad.py --image photo.png --headline "One system.\nThe whole team aligned." \
      --pos tl --wm-corner br

Key options:
  --image        source photo (required)
  --out          output (default <image>-ad.png)
  --headline     headline text; use \n for line breaks (auto-wraps too)
  --kicker       small uppercase line above the headline (optional)
  --pos          headline anchor: tl tc tr bl bc br ml mc mr   (default tl)
  --hl-color     white | ink                                   (default white)
  --hl-size      headline size as fraction of image width      (default 0.072)
  --wm-variant   white | ink | mark                            (default white)
  --wm-corner    watermark anchor: br bl bc tr tl tc           (default br)
  --wm-width     watermark width as fraction of image width    (default 0.22)
  --scrim        auto | top | bottom | both | none             (default auto)
"""
from __future__ import annotations
import argparse
import os
import textwrap
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "assets", "fonts", "SpaceGrotesk-SemiBold.ttf")
BRAND = os.path.join(ROOT, "outputs", "branding")
WATERMARKS = {
    "white": os.path.join(BRAND, "boschly-watermark-white.png"),
    "ink": os.path.join(BRAND, "boschly-watermark-ink.png"),
    "mark": os.path.join(BRAND, "boschly-mark-white.png"),
}
WHITE = (255, 255, 255, 255)
INK = (10, 16, 32, 255)


def _font(px, weight=600):
    f = ImageFont.truetype(FONT, px)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def _vgrad(size, top_alpha, bottom_alpha):
    """Vertical black gradient as RGBA, alpha lerps top->bottom."""
    W, H = size
    grad = Image.new("L", (1, H))
    for y in range(H):
        grad.putpixel((0, y), int(top_alpha + (bottom_alpha - top_alpha) * y / max(1, H - 1)))
    alpha = grad.resize((W, H))
    layer = Image.new("RGBA", (W, H), (4, 6, 12, 255))
    layer.putalpha(alpha)
    return layer


def add_scrims(base, mode):
    W, H = base.size
    if mode in ("top", "both"):
        top = _vgrad((W, int(H * 0.42)), 200, 0)
        base.alpha_composite(top, (0, 0))
    if mode in ("bottom", "both"):
        bh = int(H * 0.40)
        bot = _vgrad((W, bh), 0, 225)
        base.alpha_composite(bot, (0, H - bh))
    return base


def _wrap(draw, text, font, max_w):
    """Wrap respecting explicit \n, then by width."""
    lines = []
    for block in text.split("\n"):
        words = block.split()
        if not words:
            lines.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            test = cur + " " + w
            if draw.textlength(test, font=font) <= max_w:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def draw_headline(base, text, pos, color, size_frac, kicker=None):
    W, H = base.size
    d = ImageDraw.Draw(base)
    fpx = int(W * size_frac)
    font = _font(fpx, 600)
    max_w = W * 0.80
    lines = _wrap(d, text, font, max_w)
    lh = int(fpx * 1.12)
    block_w = max(d.textlength(ln, font=font) for ln in lines) if lines else 0

    kfont = _font(max(11, int(fpx * 0.30)), 500)
    ksp = int(fpx * 0.5) if kicker else 0
    kh = (kfont.getbbox("Ag")[3] - kfont.getbbox("Ag")[1] + ksp) if kicker else 0
    block_h = kh + lh * len(lines)

    pad = int(W * 0.06)
    # horizontal anchor
    if pos[1] == "l":
        x0 = pad; align = "l"
    elif pos[1] == "r":
        x0 = W - pad - block_w; align = "r"
    else:
        x0 = (W - block_w) // 2; align = "c"
    # vertical anchor
    if pos[0] == "t":
        y = pad
    elif pos[0] == "b":
        y = H - pad - block_h
    else:
        y = (H - block_h) // 2

    accent = (96, 165, 250, 255)  # brand blue for kicker
    if kicker:
        # tracked uppercase kicker
        kx = x0
        d.text((kx, y), kicker.upper(), font=kfont, fill=accent)
        y += kh

    for ln in lines:
        lw = d.textlength(ln, font=font)
        lx = x0 if align == "l" else (W - pad - lw if align == "r" else (W - lw) // 2)
        # soft shadow for legibility
        if color == "white":
            d.text((lx + max(1, fpx // 40), y + max(1, fpx // 40)), ln, font=font, fill=(0, 0, 0, 110))
        d.text((lx, y), ln, font=font, fill=WHITE if color == "white" else INK)
        y += lh
    return base


def stamp_watermark(base, variant, corner, width):
    W, H = base.size
    wm = Image.open(WATERMARKS[variant]).convert("RGBA")
    tw = int(W * width)
    th = int(wm.height * tw / wm.width)
    wm = wm.resize((tw, th), Image.LANCZOS)
    pad = int(W * 0.045)
    x = pad if corner[1] == "l" else (W - tw) // 2 if corner[1] == "c" else W - tw - pad
    y = pad if corner[0] == "t" else (H - th) // 2 if corner[0] == "m" else H - th - pad
    base.alpha_composite(wm, (x, y))
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out")
    ap.add_argument("--headline", default="")
    ap.add_argument("--kicker", default=None)
    ap.add_argument("--pos", default="tl")
    ap.add_argument("--hl-color", dest="hl_color", default="white", choices=["white", "ink"])
    ap.add_argument("--hl-size", dest="hl_size", type=float, default=0.072)
    ap.add_argument("--wm-variant", dest="wm_variant", default="white", choices=list(WATERMARKS))
    ap.add_argument("--wm-corner", dest="wm_corner", default="br")
    ap.add_argument("--wm-width", dest="wm_width", type=float, default=0.22)
    ap.add_argument("--scrim", default="auto", choices=["auto", "top", "bottom", "both", "none"])
    a = ap.parse_args()

    base = Image.open(a.image).convert("RGBA")
    scrim = a.scrim
    if scrim == "auto":
        top = a.pos[0] == "t" and bool(a.headline)
        bottom = a.wm_corner[0] == "b" or (a.pos[0] == "b" and bool(a.headline))
        scrim = "both" if (top and bottom) else "top" if top else "bottom" if bottom else "none"
    add_scrims(base, scrim)

    if a.headline:
        draw_headline(base, a.headline, a.pos, a.hl_color, a.hl_size, a.kicker)
    stamp_watermark(base, a.wm_variant, a.wm_corner, a.wm_width)

    out = a.out or os.path.splitext(a.image)[0] + "-ad.png"
    base.save(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
