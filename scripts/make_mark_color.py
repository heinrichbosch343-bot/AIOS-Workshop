"""
Render the Boschly swirl mark as a high-res transparent PNG
with the full blue radial gradient (white core → sky blue → brand blue → deep blue tips).
Output: outputs/branding/boschly-mark-color.png
"""
from __future__ import annotations
import os, math
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs", "branding", "boschly-mark-color.png")
SIZE = 1200   # output px — high-res, scale down as needed
SS   = 8      # internal supersample for clean antialiasing

# Blade path in a 120×120 logical box, centre (60,60)
# Two cubic-bezier segments that form one comma-shaped blade.
BLADE_SEGS = [
    ((60,60),(64,41),(81,33),(99,41)),
    ((99,41),(90,51),(76,55),(60,60)),
]

# Radial gradient stops: (radius_fraction, R, G, B)
STOPS = [
    (0.00, 255, 255, 255),   # white core
    (0.18, 255, 255, 255),   # hold white a bit
    (0.36, 191, 219, 254),   # blue-200
    (0.62, 59,  130, 246),   # blue-500  (#3b82f6)
    (1.00, 29,  78,  216),   # blue-700  (#1d4ed8)
]


def cubic(p0, p1, p2, p3, n=60):
    pts = []
    for i in range(n + 1):
        t = i / n; u = 1 - t
        x = u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0]
        y = u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1]
        pts.append((x, y))
    return pts


def blade_pts():
    pts = []
    for seg in BLADE_SEGS:
        pts.extend(cubic(*seg))
    return pts


def rotate(pts, deg, cx=60, cy=60):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(cx+(x-cx)*ca-(y-cy)*sa, cy+(x-cx)*sa+(y-cy)*ca) for x,y in pts]


def lerp_stop(t, stops):
    for i in range(len(stops)-1):
        t0, *c0 = stops[i]
        t1, *c1 = stops[i+1]
        if t0 <= t <= t1:
            f = (t-t0)/(t1-t0) if t1>t0 else 0
            return tuple(int(c0[j]+(c1[j]-c0[j])*f) for j in range(3))
    return tuple(stops[-1][1:])


def make_gradient(size):
    """Radial gradient image (RGBA, alpha=255 everywhere — mask applied later)."""
    cx = cy = size // 2
    r_max = size * 0.5
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - cx, y - cy) / r_max
            col = lerp_stop(min(d, 1.0), STOPS)
            px[x, y] = col + (255,)
    return img


def make_mask(big):
    """White-on-black mask of all 6 blades + core at `big` px."""
    mask = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(mask)
    scale = big / 120.0
    base = blade_pts()
    for i in range(6):
        poly = [(x*scale, y*scale) for x,y in rotate(base, i*60)]
        d.polygon(poly, fill=255)
    # core circle
    r = 9 * scale
    cx = cy = big // 2
    d.ellipse([cx-r, cy-r, cx+r, cy+r], fill=255)
    return mask


def main():
    big = SIZE * SS
    print(f"Rendering {big}×{big} supersample …")

    mask = make_mask(big)
    print("Mask done. Building gradient …")
    grad = make_gradient(big)

    # apply mask as alpha channel
    grad.putalpha(mask)

    print("Downsampling …")
    out = grad.resize((SIZE, SIZE), Image.LANCZOS)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.save(OUT)
    print("wrote", os.path.relpath(OUT, ROOT), out.size)


if __name__ == "__main__":
    main()
