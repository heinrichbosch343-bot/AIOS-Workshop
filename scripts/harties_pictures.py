#!/usr/bin/env python3
"""Find pictures for the businesses on Harties Board, from the businesses' OWN websites.

Stage `collect`: for every listing with a website and no picture yet, read its home page the way a link
preview does (the picture the business itself offers for sharing: og:image, twitter:image), then the
large pictures on the page, and keep up to three that pass the checks below. Nothing is taken from
social media, and no Google Maps photos are collected here (those belong to Google and the people who
uploaded them; the listing links to Google Maps instead).

Stage `sheets`: contact sheets (30 pictures each, labelled) for the reviewers.
Stage `apply`: copy the pictures the reviewers kept into the app's media folder and the seed.

Checks (all automatic, no cost): a real picture of at least 480 x 300, not an icon or a blank, a sensible
shape, not a copy of another picture of the same business, and NOT a picture that three or more different
businesses all show (site-builder templates, stock defaults and platform logos).

  uv run --no-project --system-certs --with pillow --with truststore python scripts/harties_pictures.py collect [--limit N] [--only slug,slug]
  uv run --no-project --system-certs --with pillow --with truststore python scripts/harties_pictures.py sheets
  uv run --no-project --system-certs --with pillow --with truststore python scripts/harties_pictures.py apply --seed PATH --media PATH
"""
import argparse
import concurrent.futures as cf
import hashlib
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from PIL import Image, ImageDraw, ImageStat  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "community-app" / "pictures"
SEED = Path("C:/Users/gamin/BoschAI/harties-board/data/seed.local.json")
MEDIA = Path("C:/Users/gamin/BoschAI/harties-board/public/media")
UA = "Mozilla/5.0 (compatible; HartiesBoardLinkPreview/1.0; +https://hartisboard.up.railway.app)"
MAX_PAGE = 1_500_000
MAX_IMAGE = 6_000_000
KEEP = 3
LOGOISH = re.compile(r"logo|favicon|icon|sprite|avatar|badge|payment|flag|emoji|placeholder|blank|spacer|pixel|loading|banner-ad|trust|seal|badge", re.I)
SKIP_URL = re.compile(r"\.(svg|gif|ico)(\?|$)|^data:|gravatar|facebook\.com/tr|googletagmanager|doubleclick", re.I)


def get(url, limit):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,image/*;q=0.9,*/*;q=0.5", "Accept-Language": "en"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read(limit + 1)
            return (data if len(data) <= limit else None), resp.headers.get("Content-Type", ""), resp.geturl()
    except Exception:
        return None, "", url


class Finder(HTMLParser):
    """Collects picture addresses from a page, best-offered first."""

    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.found = []  # (rank, url, label)

    def add(self, rank, raw, label=""):
        if not raw or raw.strip().startswith("data:"):
            return
        url = urllib.parse.urljoin(self.base, raw.strip().split(" ")[0])
        if url.startswith("http") and not SKIP_URL.search(url):
            self.found.append((rank, url, label))

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            if key in ("og:image", "og:image:secure_url"):
                self.add(0, a.get("content"), "og")
            elif key in ("twitter:image", "twitter:image:src"):
                self.add(1, a.get("content"), "twitter")
        elif tag == "link" and "image_src" in a.get("rel", "").lower():
            self.add(1, a.get("href"), "image_src")
        elif tag == "img":
            label = " ".join([a.get("alt", ""), a.get("class", ""), a.get("id", ""), a.get("src", "")])
            try:
                w, h = int(re.sub(r"\D", "", a.get("width", "") or "0") or 0), int(re.sub(r"\D", "", a.get("height", "") or "0") or 0)
            except ValueError:
                w = h = 0
            if (w and w < 200) or (h and h < 120):
                return
            srcset = a.get("srcset") or a.get("data-srcset") or ""
            best = None
            if srcset:
                parts = [p.strip().split(" ") for p in srcset.split(",") if p.strip()]
                sized = [(int(re.sub(r"\D", "", p[1]) or 0) if len(p) > 1 else 0, p[0]) for p in parts]
                best = max(sized)[1] if sized else None
            self.add(3, best or a.get("data-src") or a.get("data-lazy-src") or a.get("data-original") or a.get("src"), label)
        style = a.get("style", "")
        for m in re.finditer(r"url\(['\"]?([^'\")]+)", style):
            self.add(2, m.group(1), "background")


def ahash(im):
    small = im.convert("L").resize((8, 8))
    px = list(small.getdata())
    avg = sum(px) / 64
    return sum(1 << i for i, p in enumerate(px) if p > avg)


def ham(a, b):
    return bin(a ^ b).count("1")


def judge(data):
    """-> (Image, reason) : the picture when it passes the checks, else None and why."""
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return None, "not a readable picture"
    im = im.convert("RGB")
    w, h = im.size
    if w < 480 or h < 300:
        return None, f"too small ({w}x{h})"
    if not 0.4 <= w / h <= 3.5:
        return None, f"odd shape ({w}x{h})"
    if sum(ImageStat.Stat(im).stddev) / 3 < 12:
        return None, "nearly blank"
    return im, ""


def collect_one(item):
    slug, name, site = item["slug"], item["name"], item["website"]
    result = {"slug": slug, "name": name, "website": site, "pictures": [], "tried": 0, "note": ""}
    page, ctype, final = get(site, MAX_PAGE)
    if page is None or "html" not in ctype.lower() and b"<html" not in page[:2000].lower():
        result["note"] = "site did not load"
        return result
    finder = Finder(final)
    try:
        finder.feed(page.decode("utf-8", "replace"))
    except Exception:
        pass
    seen, ordered = set(), []
    for rank, url, label in sorted(finder.found, key=lambda x: (bool(LOGOISH.search(x[1] + " " + x[2])) and x[0] > 0, x[0])):
        if url not in seen:
            seen.add(url)
            ordered.append((rank, url, label))
    folder = OUT / "raw" / slug
    folder.mkdir(parents=True, exist_ok=True)
    hashes = []
    start = time.time()
    for rank, url, label in ordered[:12]:
        if len(result["pictures"]) >= KEEP or time.time() - start > 70:
            break
        result["tried"] += 1
        data, ctype, _ = get(url, MAX_IMAGE)
        if data is None or "image" not in ctype.lower() and not re.search(r"\.(jpe?g|png|webp)", url, re.I):
            continue
        im, why = judge(data)
        if im is None:
            continue
        h = ahash(im)
        if any(ham(h, k) <= 4 for k in hashes):
            continue
        hashes.append(h)
        im.thumbnail((1000, 1000))
        n = len(result["pictures"]) + 1
        path = folder / f"{n}.jpg"
        im.save(path, "JPEG", quality=76, optimize=True)
        result["pictures"].append({
            "file": f"{slug}/{n}.jpg", "source": url, "page": final, "how": label if label in ("og", "twitter", "image_src", "background") else "page",
            "logoish": bool(LOGOISH.search(url + " " + label)), "w": im.size[0], "h": im.size[1], "bytes": path.stat().st_size, "ahash": h,
        })
    if not result["pictures"]:
        result["note"] = f"no usable picture among {len(ordered)} found"
    return result


def listings(only=None):
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    out = []
    for b in seed["businesses"]:
        if b.get("home") or not b.get("website") or b.get("image") or b.get("origin") == "numbers":
            continue
        if only and b["slug"] not in only:
            continue
        out.append({"slug": b["slug"], "name": b["name"], "website": b["website"]})
    return out


def collect(limit, only):
    import truststore  # Norton re-signs web traffic here: trust the Windows certificate store

    truststore.inject_into_ssl()
    (OUT / "results").mkdir(parents=True, exist_ok=True)
    todo = [i for i in listings(only) if not (OUT / "results" / f"{i['slug']}.json").exists()]
    if limit:
        todo = todo[:limit]
    print(f"{len(todo)} sites to read")
    done = 0
    with cf.ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(collect_one, i): i for i in todo}
        for fut in cf.as_completed(futures):
            item = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # one site must never stop the run
                res = {"slug": item["slug"], "name": item["name"], "website": item["website"], "pictures": [], "note": f"error: {exc}"[:120]}
            (OUT / "results" / f"{res['slug']}.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8", newline="\n")
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(todo)}")
    summarise()


def load_results():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((OUT / "results").glob("*.json"))]


def summarise():
    results = load_results()
    with_pic = [r for r in results if r["pictures"]]
    print(f"{len(results)} sites read, {len(with_pic)} gave a picture, {sum(len(r['pictures']) for r in results)} pictures")
    notes = {}
    for r in results:
        if not r["pictures"]:
            key = (r.get("note") or "")[:30]
            notes[key] = notes.get(key, 0) + 1
    print("no picture because:", sorted(notes.items(), key=lambda x: -x[1])[:6])


def shared_hashes(results):
    """Pictures that three or more different businesses all show are templates or platform defaults, never the business."""
    seen = {}
    for r in results:
        for p in r["pictures"]:
            seen.setdefault(p["ahash"], set()).add(r["slug"])
    bad = set()
    keys = list(seen)
    for i, a in enumerate(keys):
        group = set(seen[a])
        for b in keys[i + 1:]:
            if ham(a, b) <= 3:
                group |= seen[b]
        if len(group) >= 3:
            bad.add(a)
            bad.update(b for b in keys if ham(a, b) <= 3)
    return bad


def sheets():
    results = load_results()
    bad = shared_hashes(results)
    rows = []
    for r in results:
        for n, p in enumerate(r["pictures"], 1):
            rows.append({"id": f"{r['slug']}#{n}", "slug": r["slug"], "name": r["name"], "file": p["file"], "logoish": p["logoish"], "shared": p["ahash"] in bad, "how": p["how"]})
    rows = [x for x in rows if not x["shared"]]
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    per, cols, cell = 30, 6, 230
    index = []
    for s in range(0, len(rows), per):
        chunk = rows[s:s + per]
        sheet = Image.new("RGB", (cols * cell, ((len(chunk) + cols - 1) // cols) * (cell + 30)), "white")
        draw = ImageDraw.Draw(sheet)
        for i, x in enumerate(chunk):
            im = Image.open(OUT / "raw" / x["file"]).convert("RGB")
            im.thumbnail((cell - 8, cell - 8))
            cx, cy = (i % cols) * cell, (i // cols) * (cell + 30)
            sheet.paste(im, (cx + 4, cy + 4))
            draw.text((cx + 4, cy + cell - 2), f"{s + i + 1:03d} {x['slug'][:28]}#{x['id'].split('#')[1]}", fill="black")
        name = f"sheet-{s // per + 1:02d}.png"
        sheet.save(OUT / "sheets" / name)
        index.append({"sheet": name, "items": [{"n": s + i + 1, **x} for i, x in enumerate(chunk)]})
    (OUT / "sheets" / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"{len(rows)} pictures on {len(index)} sheets ({sum(1 for r in results for p in r['pictures'] if p['ahash'] in bad)} shared ones left out)")


def corners_dark(path):
    im = Image.open(path).convert("L")
    w, h = im.size
    spots = [im.getpixel(p) for p in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]
    return sum(spots) / 4 < 25


def apply(seed_path, media_path):
    seed_file, media = Path(seed_path), Path(media_path)
    seed = json.loads(seed_file.read_text(encoding="utf-8"))
    decisions = {}
    for path in sorted((OUT / "decisions").glob("*.json")):
        for d in json.loads(path.read_text(encoding="utf-8")):
            decisions[d["id"]] = d
    results = {r["slug"]: r for r in load_results()}
    index = {i["id"]: i for sheet in json.loads((OUT / "sheets" / "index.json").read_text(encoding="utf-8")) for i in sheet["items"]}
    by = {}
    left_out = {"dated promo": 0, "black logo": 0}
    for pid, d in decisions.items():
        if not d.get("keep") or pid not in index:
            continue
        what = (d.get("what") or "").lower()
        if re.search(r"promo|flyer|poster|price|special|sale|discount|event", what):
            left_out["dated promo"] += 1  # a date or a price goes stale; the business can post it as a promo itself
            continue
        if "logo" in what and corners_dark(OUT / "raw" / index[pid]["file"]):
            left_out["black logo"] += 1  # a transparent logo saved on black: it would show as a black box
            continue
        by.setdefault(index[pid]["slug"], []).append((pid, d))
    media.mkdir(parents=True, exist_ok=True)
    count = {"main": 0, "gallery": 0}
    for b in seed["businesses"]:
        if b.get("home") or b["slug"] not in by:
            continue
        # a re-run replaces what an earlier run set, never a picture that came from somewhere else
        if b.get("image") and not b.get("imageFrom"):
            continue
        kept = sorted(by[b["slug"]], key=lambda x: (not x[1].get("main"), x[0]))
        picks = [(pid, d) for pid, d in kept]
        if not picks:
            continue
        res = results[b["slug"]]
        host = urllib.parse.urlparse(b["website"]).netloc.replace("www.", "")[:60]
        # The pictures were read from one website: only a business still on that website may show them.
        if urllib.parse.urlparse(res["website"]).netloc.replace("www.", "") != host:
            continue
        gallery = []
        for n, (pid, d) in enumerate(picks[:KEEP]):
            src = OUT / "raw" / index[pid]["file"]
            im = Image.open(src).convert("RGB")
            suffix = "" if n == 0 else f"-g{n}"
            name = f"dir-{b['slug'][:48]}{suffix}.jpg"
            im.save(media / name, "JPEG", quality=76, optimize=True)
            if n == 0:
                sm = im.copy()
                sm.thumbnail((640, 640))
                sm.save(media / f"dir-{b['slug'][:48]}-sm.jpg", "JPEG", quality=72, optimize=True)
                b["image"] = f"/media/{name}"
                b["imageFrom"] = host
                count["main"] += 1
            else:
                gallery.append(f"/media/{name}")
                count["gallery"] += 1
        if gallery:
            b["gallery"] = gallery
    seed_file.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"pictures set: {count['main']} main, {count['gallery']} more; left out {left_out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["collect", "sheets", "apply", "summary"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="")
    ap.add_argument("--seed", default=str(SEED))
    ap.add_argument("--media", default=str(MEDIA))
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s} or None
    if args.stage == "collect":
        collect(args.limit, only)
    elif args.stage == "sheets":
        sheets()
    elif args.stage == "summary":
        summarise()
    else:
        apply(args.seed, args.media)
