"""
Generate the Boschly watermark as transparent PNGs.

Rebuilds the vector swirl mark (6 rotated bezier blades + glowing core) and pairs it
with the "Boschly" wordmark in the real brand font (Space Grotesk SemiBold).

Outputs to outputs/branding/:
  boschly-watermark-white.png   horizontal lockup, white  (for dark / busy photos)
  boschly-watermark-ink.png     horizontal lockup, ink    (for light photos)
  boschly-mark-white.png        mark only, white          (tight corners / favicons)

Run:  python scripts/make_watermark.py
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = os.path.join(ROOT, "assets", "fonts", "SpaceGrotesk-SemiBold.ttf")
OUT = os.path.join(ROOT, "outputs", "branding")
os.makedirs(OUT, exist_ok=True)

SS = 8  # supersample factor for clean antialiasing

# one blade = two cubic bezier segments, in a 120x120 logical box, centre (60,60)
BLADE = [
    ((60, 60), (64, 41), (81, 33), (99, 41)),
    ((99, 41), (90, 51), (76, 55), (60, 60)),
]


def _cubic(p0, p1, p2, p3, n=40):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        pts.append((x, y))
    return pts


def _blade_points():
    pts = []
    for seg in BLADE:
        pts.extend(_cubic(*seg))
    return pts


def _rotate(pts, deg, cx=60, cy=60):
    import math
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        out.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
    return out


def render_mark(size, color=(255, 255, 255, 255), core=(255, 255, 255, 255)):
    """Return an RGBA Image of the swirl mark at `size` px."""
    big = size * SS
    scale = big / 120.0
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    base = _blade_points()
    for i in range(6):
        poly = [(x * scale, y * scale) for x, y in _rotate(base, i * 60)]
        d.polygon(poly, fill=color)
    r = 9 * scale
    d.ellipse([60 * scale - r, 60 * scale - r, 60 * scale + r, 60 * scale + r], fill=core)
    return img.resize((size, size), Image.LANCZOS)


def _font(px):
    f = ImageFont.truetype(FONT, px)
    try:
        f.set_variation_by_axes([600])  # SemiBold weight on the variable font
    except Exception:
        pass
    return f


def render_lockup(text_color, mark_color, fname, mark_h=120):
    """Horizontal lockup: swirl mark + Boschly wordmark, transparent."""
    big_h = mark_h * SS
    font = _font(int(big_h * 0.86))
    # measure wordmark
    tmp = Image.new("RGBA", (10, 10))
    box = ImageDraw.Draw(tmp).textbbox((0, 0), "Boschly", font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    gap = int(big_h * 0.30)
    pad = int(big_h * 0.10)
    W = big_h + gap + tw + pad * 2
    H = big_h + pad * 2
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mark = render_mark(big_h, color=mark_color, core=mark_color)
    canvas.alpha_composite(mark, (pad, pad))
    d = ImageDraw.Draw(canvas)
    ty = (H - th) // 2 - box[1]
    d.text((pad + big_h + gap, ty), "Boschly", font=font, fill=text_color)
    canvas = canvas.resize((W // SS, H // SS), Image.LANCZOS)
    path = os.path.join(OUT, fname)
    canvas.save(path)
    print("wrote", os.path.relpath(path, ROOT), canvas.size)


def main():
    white = (255, 255, 255, 255)
    ink = (10, 16, 32, 255)  # #0a1020
    render_lockup(white, white, "boschly-watermark-white.png")
    render_lockup(ink, ink, "boschly-watermark-ink.png")
    render_mark(256, color=white, core=white).save(os.path.join(OUT, "boschly-mark-white.png"))
    print("wrote", os.path.relpath(os.path.join(OUT, "boschly-mark-white.png"), ROOT))


if __name__ == "__main__":
    main()
