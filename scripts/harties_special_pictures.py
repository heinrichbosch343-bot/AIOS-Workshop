#!/usr/bin/env python3
"""Find a picture of the SPECIAL itself (the sirloin, the pizza, the poster) for the specials on Harties Board.

A special used to borrow its restaurant's photo, so "350g sirloin & chips" showed the building. This looks for the
picture the business shows for that special on its own pages, then lets a reviewer confirm it.

Stages (all free, no keys):
  collect  open each business's special pages in a real browser (so lazy-loaded pictures appear), save every picture
           of a useful size with the words around it (alt text, nearby text, file name)
  rank     CLIP (OpenAI's open image-and-text matching model, run here on this PC) scores every picture against the
           words of each special, together with how well the page's own words match; keeps the best few per special
  sheets   contact sheets for the reviewers: one strip per special, its words, its best candidates
  apply    copy the pictures the reviewers picked into the app's media folder and set them on the specials

  Add --set events to do the same for the events (pictures from the organisers' own pages); --part i/n shares `collect` between runs.
  uv run --no-project --system-certs --python 3.12 --with playwright --with pillow python scripts/harties_special_pictures.py collect [--only slug,slug]
  HF_HOME=Z:/aios-models/hf uv run --no-project --system-certs --python 3.12 --with torch --with transformers --with pillow --with truststore python scripts/harties_special_pictures.py rank
  uv run --no-project --system-certs --python 3.12 --with pillow python scripts/harties_special_pictures.py sheets
  uv run --no-project --system-certs --python 3.12 --with pillow python scripts/harties_special_pictures.py apply [--seed PATH] [--media PATH]

Only pictures from the business's own website are used, and the page says where each came from.
"""
import argparse
import hashlib
import io
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "outputs" / "community-app"
# Two sets of promos get pictures this way. `specials`: the food specials. `events`: the events from organisers' pages.
SETS = {
    "specials": {"dir": "specials", "prefix": "spec", "pick": lambda p: p.get("origin") == "food-specials"},
    "events": {"dir": "event-pictures", "prefix": "ev", "pick": lambda p: p.get("origin") == "events"},
}
SET = "specials"
OG_ONLY = False
OUT = BASE / SETS[SET]["dir"]
SKIP_PAGES = re.compile(r"[.]pdf($|[?])|facebook[.]com|instagram[.]com|fb[.]me|wa[.]me", re.I)
SEED = Path("C:/Users/gamin/BoschAI/harties-board/data/seed.local.json")
MEDIA = Path("C:/Users/gamin/BoschAI/harties-board/public/media")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
LOGOISH = re.compile(r"logo|favicon|icon|sprite|avatar|badge|payment|flag|emoji|placeholder|blank|spacer|pixel|loading|trust|seal|whatsapp|facebook|instagram|tripadvisor|google|visa|master", re.I)
SKIP_URL = re.compile(r"\.(svg|gif|ico)(\?|$)|^data:|gravatar|googletagmanager|doubleclick|/emoji/|wp-includes", re.I)
MAX_PER_PAGE = 60
TOP = 5
STOP = set("the and with for from our your are you all day every special specials deal deals only per eat in dine takeaway delivery lunch dinner menu price prices confirm store branch page national weekday weekdays monday tuesday wednesday thursday friday saturday sunday on off at of a an to is it this that".split())

# Read every picture on the page with the words around it. Runs inside the page.
PAGE_JS = """
() => {
  const text = (el) => (el.innerText || "").replace(/\\s+/g, " ").trim();
  const near = (el) => { let n = el; for (let i = 0; i < 6 && n.parentElement; i++) { n = n.parentElement; const t = text(n); if (t.length >= 25) return t.slice(0, 360); } return ""; };
  const out = [];
  for (const img of document.images) {
    const src = img.currentSrc || img.src;
    if (!src || src.startsWith("data:")) continue;
    const r = img.getBoundingClientRect();
    out.push({ src, nw: img.naturalWidth, nh: img.naturalHeight, w: r.width, h: r.height, alt: img.alt || "", title: img.title || "", ctx: near(img), y: Math.round(r.top + scrollY) });
    // the largest picture the page offers for this spot (srcset), when it is not the one already read
    const sets = (img.srcset || "").split(",").map((x) => x.trim().split(" ")).filter((x) => x[0]);
    const big = sets.map((x) => ({ url: new URL(x[0], location.href).href, w: parseInt(x[1]) || 0 })).sort((a, b) => b.w - a.w)[0];
    if (big && big.url !== src) out.push({ src: big.url, nw: 0, nh: 0, w: r.width, h: r.height, alt: img.alt || "", title: img.title || "", ctx: near(img), y: Math.round(r.top + scrollY) });
  }
  for (const el of document.querySelectorAll("div,section,a,li,figure,span")) {
    const bg = getComputedStyle(el).backgroundImage;
    const m = bg && bg.match(/url\\(["']?([^"')]+)/);
    if (!m || m[1].startsWith("data:")) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 200 || r.height < 120) continue;
    out.push({ src: new URL(m[1], location.href).href, nw: 0, nh: 0, w: r.width, h: r.height, alt: "", title: "", ctx: near(el), y: Math.round(r.top + scrollY), bg: true });
  }
  const og = document.querySelector('meta[property="og:image"]');
  if (og && og.content) out.push({ src: new URL(og.content, location.href).href, nw: 0, nh: 0, w: 0, h: 0, alt: "og", title: "", ctx: document.title, y: -1 });
  return out;
}
"""


SIZED = re.compile(r"-\d{2,4}x\d{2,4}(?=\.[a-z0-9]+$)", re.I)


def full_size(url):
    """WordPress and others serve a resized copy ('poster-300x300.jpg') beside the original ('poster.jpg'): try the original."""
    path = urllib.parse.urlparse(url).path
    return SIZED.sub("", url) if SIZED.search(path) else url


def host_of(url):
    return urllib.parse.urlparse(url).netloc.lower().replace("www.", "")


def clean_url(url):
    p = urllib.parse.urlparse(url.strip())
    return urllib.parse.urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def specials(seed):
    """The promos of the chosen set."""
    return [p for p in seed["promos"] if SETS[SET]["pick"](p)]


def pages_by_business(seed, only=None):
    biz = {b["slug"]: b for b in seed["businesses"]}
    out = {}
    for p in specials(seed):
        if only and p["businessSlug"] not in only:
            continue
        b = biz.get(p["businessSlug"])
        if not b:
            continue
        pages = out.setdefault(p["businessSlug"], {"name": b["name"], "pages": []})["pages"]
        for u in (p.get("sourceUrl"), b.get("website")):
            if u and not SKIP_PAGES.search(u) and clean_url(u) not in pages:
                pages.append(clean_url(u))
    return out


def judge(data):
    from PIL import Image, ImageStat
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return None
    im = im.convert("RGB")
    w, h = im.size
    if w < 360 or h < 240 or not 0.35 <= w / h <= 3.5 or sum(ImageStat.Stat(im).stddev) / 3 < 10:
        return None
    return im


def ahash(im):
    px = list(im.convert("L").resize((8, 8)).getdata())
    avg = sum(px) / 64
    return sum(1 << i for i, p in enumerate(px) if p > avg)


def ham(a, b):
    return bin(a ^ b).count("1")


def cand_files():
    return sorted(OUT.glob("candidates*.json"))


def load_candidates():
    """Every candidates*.json laid together; a business in two files gets both lists."""
    merged = {}
    for path in cand_files():
        for slug, v in json.loads(path.read_text(encoding="utf-8")).items():
            if slug in merged:
                merged[slug]["candidates"] = merged[slug]["candidates"] + v["candidates"]
                merged[slug]["texts"] = {**merged[slug].get("texts", {}), **v.get("texts", {})}
                merged[slug]["pages"] = list(dict.fromkeys(merged[slug]["pages"] + v["pages"]))
            else:
                merged[slug] = v
    return merged


OG_META = re.compile(r"<meta[^>]+(?:property|name)=['\"]og:image['\"][^>]*>", re.I)
OG_CONTENT = re.compile(r"content=['\"]([^'\"]+)['\"]", re.I)


def og_images(html, base):
    """The share pictures a page offers, as full addresses (a plain page fetch: it sees what a link preview sees)."""
    out = []
    for tag in OG_META.findall(html):
        m = OG_CONTENT.search(tag)
        if m:
            out.append(urllib.parse.urljoin(base, m.group(1).strip()))
    return out


def collect_og(seed):
    """For promos still without a picture: read each source page like a link preview does and keep its share picture.
    Writes candidates-og.json (the same shape as `collect`), so ranking, review and apply work unchanged."""
    import urllib.request
    have = set()
    for path in cand_files():
        if path.name != "candidates-og.json":
            have |= set(json.loads(path.read_text(encoding="utf-8")))
    biz = {b["slug"]: b for b in seed["businesses"]}
    decided = set()
    for path in (OUT / "decisions").glob("*.json"):
        decided |= {d["id"] for d in json.loads(path.read_text(encoding="utf-8")) if d.get("pick")}
    out_file = OUT / "candidates-og.json"
    results = json.loads(out_file.read_text(encoding="utf-8")) if out_file.exists() else {}
    for p in specials(seed):
        if p.get("image") or p["id"] in decided or not p.get("sourceUrl") or SKIP_PAGES.search(p["sourceUrl"]):
            continue
        slug, url = p["businessSlug"], clean_url(p["sourceUrl"])
        entry = results.setdefault(slug, {"name": biz[slug]["name"], "pages": [], "candidates": [], "texts": {}})
        if url in entry["pages"]:
            continue
        entry["pages"].append(url)
        try:
            req = urllib.request.Request(p["sourceUrl"], headers={"User-Agent": UA, "Accept-Language": "en"})
            html = urllib.request.urlopen(req, timeout=20).read(600000).decode("utf-8", "replace")
        except Exception as e:
            print("   no page", p["id"][:50], str(e)[:50], flush=True)
            continue
        folder = OUT / "raw" / slug
        folder.mkdir(parents=True, exist_ok=True)
        for src in og_images(html, p["sourceUrl"])[:2]:
            for url_try in dict.fromkeys([full_size(src), src]):
                try:
                    data = urllib.request.urlopen(urllib.request.Request(url_try.replace(" ", "%20"), headers={"User-Agent": UA}), timeout=20).read(6_000_000)
                except Exception:
                    continue
                im = judge(data)
                if im is None:
                    continue
                n = len(entry["candidates"]) + 1
                im.thumbnail((1400, 1400))
                im.save(folder / f"og-{n}.jpg", "JPEG", quality=80, optimize=True)
                entry["candidates"].append({"file": f"{slug}/og-{n}.jpg", "src": src, "page": url, "alt": "og", "ctx": p["title"], "y": -1,
                                            "w": im.size[0], "h": im.size[1], "ahash": ahash(im)})
                print("   og picture", p["id"][:50], im.size, flush=True)
                break
    out_file.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8", newline=chr(10))


def collect(only, part=None):
    """`part` = (i, n): this run takes every n-th business, so several runs can share the work (each writes its own file)."""
    from playwright.sync_api import sync_playwright
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    plan = pages_by_business(seed, only)
    if part:
        plan = {k: v for j, (k, v) in enumerate(sorted(plan.items())) if j % part[1] == part[0]}
    (OUT / "raw").mkdir(parents=True, exist_ok=True)
    out_file = OUT / (f"candidates-{part[0]}.json" if part else "candidates.json")
    results = {}
    if out_file.exists():
        results = json.loads(out_file.read_text(encoding="utf-8"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900}, locale="en-ZA")
        for slug, info in plan.items():
            print("==", slug, info["pages"], flush=True)
            cands, hashes, texts = [], [], {}
            folder = OUT / "raw" / slug
            folder.mkdir(parents=True, exist_ok=True)
            for url in info["pages"]:
                page = ctx.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1500)
                    for _ in range(8):  # scroll down so lazy pictures load
                        page.mouse.wheel(0, 900)
                        page.wait_for_timeout(350)
                    page.wait_for_timeout(800)
                    found = page.evaluate(PAGE_JS)
                    texts[url] = page.inner_text("body").strip()[:7000]
                except Exception as e:
                    print("   page failed", url, str(e)[:80], flush=True)
                    page.close()
                    continue
                seen = set()
                ordered = [f for f in found if f["src"].startswith("http") and not SKIP_URL.search(f["src"]) and not (f["src"] in seen or seen.add(f["src"]))]
                for f in ordered[:MAX_PER_PAGE * 2]:
                    if len(cands) >= MAX_PER_PAGE * 2:
                        break
                    if LOGOISH.search(f["src"] + " " + f["alt"]):
                        continue
                    im = None
                    for url_try in dict.fromkeys([full_size(f["src"]), f["src"]]):
                        try:
                            resp = ctx.request.get(url_try, timeout=20000)
                            if resp.ok:
                                im = judge(resp.body())
                        except Exception:
                            im = None
                        if im is not None:
                            break
                    if im is None:
                        continue
                    h = ahash(im)
                    if any(ham(h, k) <= 2 for k in hashes):
                        continue
                    hashes.append(h)
                    im.thumbnail((1400, 1400))
                    n = len(cands) + 1
                    im.save(folder / f"{n}.jpg", "JPEG", quality=80, optimize=True)
                    cands.append({"file": f"{slug}/{n}.jpg", "src": f["src"], "page": url, "alt": f["alt"].strip()[:160], "ctx": f["ctx"], "y": f["y"],
                                  "w": im.size[0], "h": im.size[1], "ahash": h})
                page.close()
            print(f"   {len(cands)} pictures kept", flush=True)
            results[slug] = {"name": info["name"], "pages": info["pages"], "candidates": cands, "texts": texts}
            out_file.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        browser.close()


def words(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP and not w.isdigit()]


def dish_text(promo):
    """What the picture should show, as plain words: the title after any 'Day:' lead-in, plus the first sentence of the details."""
    title = promo["title"].split(":", 1)[-1].strip()
    first = re.split(r"(?<=[.!?])\s", promo.get("details", "") or "")[0]
    return title, first


def rank():
    import torch
    import truststore
    truststore.inject_into_ssl()
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    cand = load_candidates()
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").eval()
    proc = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    negatives = ["a logo", "the outside of a restaurant building", "the inside of an empty restaurant", "a group of smiling people", "a map", "a page of text", "a landscape with water and hills"]
    if SET == "events":
        negatives = ["a logo", "a map", "a page of text", "a screenshot of a website", "a ticket office window"]
    lead = "a photo of" if SET == "specials" else "a poster or photo for the event"
    ranked = {}
    for slug, info in cand.items():
        promos = [p for p in specials(seed) if p["businessSlug"] == slug]
        files = info["candidates"]
        if not files or not promos:
            continue
        images = [Image.open(OUT / "raw" / c["file"]).convert("RGB") for c in files]
        prompts = []
        for p in promos:
            title, first = dish_text(p)
            prompts.append(f"{lead} {title}")
        texts = prompts + negatives
        with torch.no_grad():
            inputs = proc(text=texts, images=images, return_tensors="pt", padding=True, truncation=True)
            logits = model(**inputs).logits_per_image  # images x texts
            probs = logits.softmax(dim=1)
        for pi, p in enumerate(promos):
            title, first = dish_text(p)
            want = set(words(title)) | set(words(first))
            scored = []
            for ci, c in enumerate(files):
                around = set(words(c["alt"] + " " + c["ctx"] + " " + Path(urllib.parse.urlparse(c["src"]).path).stem.replace("-", " ").replace("_", " ")))
                hit = len(want & around)
                kw = min(1.0, hit / max(1, min(3, len(want))))
                clip_p = float(probs[ci, pi])
                clip_raw = float(logits[ci, pi])
                bad = float(probs[ci, len(promos):].sum())
                # a page's own share picture (og:image) on this event's own page is usually its poster
                own_page = clean_url(p["sourceUrl"]) == c["page"] if p.get("sourceUrl") else False
                bonus = (0.5 if c["alt"] == "og" and own_page else 0) + (0.15 if own_page else 0)
                scored.append({"file": c["file"], "clip": round(clip_p, 3), "clipRaw": round(clip_raw, 1), "notFood": round(bad, 3), "words": hit,
                               "score": round(clip_p + 0.6 * kw - 0.3 * bad + bonus, 3), "alt": c["alt"], "ctx": c["ctx"][:140], "w": c["w"], "h": c["h"], "src": c["src"], "page": c["page"]})
            scored.sort(key=lambda s: -s["score"])
            ranked[p["id"]] = {"slug": slug, "business": info["name"], "title": p["title"], "details": p.get("details", ""), "candidates": scored[:TOP]}
        print(slug, len(files), "pictures,", len(promos), "specials", flush=True)
    (OUT / "ranked.json").write_text(json.dumps(ranked, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print("ranked", len(ranked), "specials")


def sheets():
    from PIL import Image, ImageDraw, ImageFont
    ranked = json.loads((OUT / "ranked.json").read_text(encoding="utf-8"))
    (OUT / "sheets").mkdir(parents=True, exist_ok=True)
    for old in (OUT / "sheets").glob("*"):
        old.unlink()
    try:
        font = ImageFont.truetype("arial.ttf", 17)
        small = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font = small = ImageFont.load_default()
    ids = list(ranked)
    if OG_ONLY:  # only the promos that gained a share picture in the `og` pass
        ids = [i for i in ids if any("/og-" in c["file"] for c in ranked[i]["candidates"])]
    per, cell_w, cell_h = 5, 300, 220
    index = []
    for s in range(0, len(ids), per):
        chunk = ids[s:s + per]
        sheet = Image.new("RGB", (TOP * cell_w + 10, len(chunk) * (cell_h + 78) + 10), "white")
        d = ImageDraw.Draw(sheet)
        y = 6
        items = []
        for pid in chunk:
            r = ranked[pid]
            d.text((8, y), f"{r['business']}: {r['title']}"[:110], fill="black", font=font)
            d.text((8, y + 22), (r["details"] or "")[:150], fill=(80, 80, 80), font=small)
            for k, c in enumerate(r["candidates"], 1):
                im = Image.open(OUT / "raw" / c["file"]).convert("RGB")
                im.thumbnail((cell_w - 8, cell_h - 8))
                x = 5 + (k - 1) * cell_w
                sheet.paste(im, (x, y + 44))
                d.text((x + 2, y + 44 + cell_h - 4), f"{k}  clip {c['clip']}  words {c['words']}", fill=(0, 90, 160), font=small)
                d.text((x + 2, y + 44 + cell_h + 12), (c["alt"] or c["ctx"])[:42], fill=(60, 60, 60), font=small)
            items.append({"id": pid, "business": r["business"], "title": r["title"], "details": r["details"],
                          "candidates": [{"n": k, "file": c["file"], "alt": c["alt"], "ctx": c["ctx"]} for k, c in enumerate(r["candidates"], 1)]})
            y += cell_h + 78
        name = f"sheet-{s // per + 1:02d}.png"
        sheet.save(OUT / "sheets" / name)
        index.append({"sheet": name, "items": items})
    (OUT / "sheets" / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(len(index), "sheets for", len(ids), "specials")


def apply(seed_path, media_path):
    from PIL import Image
    seed_file, media = Path(seed_path), Path(media_path)
    seed = json.loads(seed_file.read_text(encoding="utf-8"))
    ranked = json.loads((OUT / "ranked.json").read_text(encoding="utf-8"))
    cands = load_candidates()
    decisions = {}
    for path in sorted((OUT / "decisions").glob("*.json")):  # later files win, so a fixes file can overrule a review
        for d in json.loads(path.read_text(encoding="utf-8")):
            decisions[d["id"]] = d
    media.mkdir(parents=True, exist_ok=True)
    set_count = 0
    for p in seed["promos"]:
        d = decisions.get(p["id"])
        if not d or not d.get("pick") or p["id"] not in ranked:
            # a re-run replaces what an earlier run set, never a picture that came from somewhere else
            if SETS[SET]["pick"](p) and p.get("imageFrom"):
                p.pop("image", None)
                p.pop("imageFrom", None)
            continue
        # a decision may name a picture by hand ("file") when the right one was not among the top five
        wanted = d.get("file")
        c = next((x for x in cands.get(wanted.split("/")[0], {}).get("candidates", []) if x["file"] == wanted), None) if wanted else ranked[p["id"]]["candidates"][int(d["pick"]) - 1]
        if c is None:
            print("picture not found for", p["id"], wanted)
            continue
        src = OUT / "raw" / c["file"]
        im = Image.open(src).convert("RGB")
        key = hashlib.sha1(src.read_bytes()).hexdigest()[:10]
        prefix = SETS[SET]["prefix"]
        name = f"{prefix}-{key}.jpg"
        im.save(media / name, "JPEG", quality=78, optimize=True)
        sm = im.copy()
        sm.thumbnail((640, 640))
        sm.save(media / f"{prefix}-{key}-sm.jpg", "JPEG", quality=72, optimize=True)
        p["image"] = f"/media/{name}"
        p["imageFrom"] = host_of(c["page"])[:60]
        set_count += 1
    seed_file.write_text(json.dumps(seed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"special pictures set: {set_count} of {len(specials(seed))}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["collect", "og", "rank", "sheets", "apply"])
    ap.add_argument("--set", default="specials", choices=list(SETS))
    ap.add_argument("--part", default="", help="i/n: take every n-th business (for parallel collect runs)")
    ap.add_argument("--og-only", action="store_true", help="sheets: only the promos that gained a share picture")
    ap.add_argument("--only", default="")
    ap.add_argument("--seed", default=str(SEED))
    ap.add_argument("--media", default=str(MEDIA))
    args = ap.parse_args()
    only = {s for s in args.only.split(",") if s} or None
    SET = args.set
    OG_ONLY = args.og_only
    OUT = BASE / SETS[SET]["dir"]
    part = tuple(int(x) for x in args.part.split("/")) if args.part else None
    if args.stage == "collect":
        collect(only, part)
    elif args.stage == "og":
        collect_og(json.loads(Path(args.seed).read_text(encoding="utf-8")))
    elif args.stage == "rank":
        rank()
    elif args.stage == "sheets":
        sheets()
    else:
        apply(args.seed, args.media)
