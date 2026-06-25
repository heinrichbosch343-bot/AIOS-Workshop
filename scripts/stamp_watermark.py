"""
Stamp the Boschly watermark onto an image.

Usage:
  python scripts/stamp_watermark.py --image path/to/photo.png
  python scripts/stamp_watermark.py --image in.png --out out.png \
      --variant white --corner br --width 0.20 --pad 0.04 --opacity 0.92

Options:
  --image     source image (required)
  --out       output path (default: <image>-wm.png)
  --variant   white | ink            (default white  — use ink on light photos)
  --corner    br bl tr tl bc tc      (default br = bottom-right)
  --width     watermark width as fraction of image width (default 0.20)
  --pad       edge padding as fraction of image width    (default 0.04)
  --opacity   0..1                                        (default 0.92)
"""
from __future__ import annotations
import argparse
import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRAND = os.path.join(ROOT, "outputs", "branding")
WATERMARKS = {
    "white": os.path.join(BRAND, "boschly-watermark-white.png"),
    "ink": os.path.join(BRAND, "boschly-watermark-ink.png"),
    "mark": os.path.join(BRAND, "boschly-mark-white.png"),
}


def stamp(image, out, variant="white", corner="br", width=0.20, pad=0.04, opacity=0.92):
    base = Image.open(image).convert("RGBA")
    wm = Image.open(WATERMARKS[variant]).convert("RGBA")

    W, H = base.size
    target_w = int(W * width)
    target_h = int(wm.height * target_w / wm.width)
    wm = wm.resize((target_w, target_h), Image.LANCZOS)

    if opacity < 1.0:
        alpha = wm.split()[3].point(lambda a: int(a * opacity))
        wm.putalpha(alpha)

    px = int(W * pad)
    py = int(W * pad)  # use width-based pad both axes for visual consistency
    x = px if corner[1] == "l" else (W - target_w) // 2 if corner[1] == "c" else W - target_w - px
    y = py if corner[0] == "t" else (H - target_h) // 2 if corner[0] == "m" else H - target_h - py

    base.alpha_composite(wm, (x, y))
    base.convert("RGB").save(out, quality=95) if out.lower().endswith((".jpg", ".jpeg")) else base.save(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out")
    ap.add_argument("--variant", default="white", choices=list(WATERMARKS))
    ap.add_argument("--corner", default="br")
    ap.add_argument("--width", type=float, default=0.20)
    ap.add_argument("--pad", type=float, default=0.04)
    ap.add_argument("--opacity", type=float, default=0.92)
    a = ap.parse_args()
    out = a.out or os.path.splitext(a.image)[0] + "-wm.png"
    path = stamp(a.image, out, a.variant, a.corner, a.width, a.pad, a.opacity)
    print("wrote", path)


if __name__ == "__main__":
    main()
