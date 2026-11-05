#!/usr/bin/env python3
"""Put the verified help and useful numbers into Harties Board.

Input : outputs/community-app/events/raw/useful-numbers.json  (every number read on an official page, with its URL)
Output: community listings in the seed ("Community & help"), tagged origin "numbers" so a re-run replaces them.

Only numbers with the confidence "official page" go in. The page the number was read from is the listing's website,
so anyone can check it, and every listing says when it was checked. Nothing here is an advertisement.

  python scripts/harties_numbers.py merge --seed C:/Users/gamin/BoschAI/harties-board/data/seed.local.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harties_directory import slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "outputs" / "community-app" / "events" / "raw" / "useful-numbers.json"

GROUP_TO_SUB = {"emergency": "emergency", "police": "emergency", "medical": "emergency", "council": "council",
                "utilities": "council", "estate": "estates", "animals": "clubs"}
POPULARITY = {"emergency": 100, "police": 95, "medical": 92, "council": 70, "utilities": 70, "services": 60, "estate": 50, "animals": 40}
ESTATE_AREA = [("pecanwood", "pecanwood"), ("islands", "islands"), ("coves", "coves"), ("xanadu", "harties"), ("leloko", "leloko")]
TAGS = {"emergency": ["emergency", "help", "urgent"], "police": ["police", "saps", "crime", "emergency"], "medical": ["hospital", "emergency", "poison"],
        "council": ["municipality", "council", "madibeng"], "utilities": ["eskom", "electricity", "power"],
        "estate": ["estate", "security", "hoa", "office"], "animals": ["animals", "rescue", "welfare"],
        "services": ["help", "helpline", "counselling"]}
# The helplines and the water authority are services, not the council.
SERVICE_SUBS = {"gbv": "emergency", "childline": "emergency", "lifeline": "emergency", "sadag": "emergency", "department of water": "council"}


def sub_for(item):
    name = item["name"].lower()
    for key, sub in SERVICE_SUBS.items():
        if key in name:
            return sub
    return GROUP_TO_SUB.get(item["group"], "council")


def local_number(text):
    """The number as digits and spaces, or '' when it is not a number we can show as a Call row."""
    t = re.sub(r"[^0-9]", "", text or "")
    if t in ("112", "10111", "10177", "107", "082911", "084124"):
        return t
    if t.startswith("27") and len(t) == 11:
        t = "0" + t[2:]
    return t if len(t) == 10 and t.startswith("0") else ""


def digits_show(t):
    return t if len(t) <= 6 else f"{t[:3]} {t[3:6]} {t[6:]}"


def area_for(item):
    blob = (item["name"] + " " + (item.get("area") or "")).lower()
    for word, area in ESTATE_AREA:
        if word in blob:
            return area
    return "harties"


def build(items):
    out, used = [], set()
    for it in items:
        if (it.get("confidence") or "").lower() != "official page":
            continue
        phone = local_number(it.get("phone"))
        alt = local_number(it.get("alt_phone"))
        web = (it.get("website") or it.get("source") or "").strip()
        if web.startswith("http://"):
            web = "https://" + web[7:]
        if not phone and not web.startswith("https://"):
            continue
        sub = sub_for(it)
        slug = slugify(it["name"])
        base, n = slug, 2
        while slug in used:
            slug, n = f"{base}-{n}", n + 1
        used.add(slug)
        area = area_for(it)
        about = f"{it['name']}. Checked on the official page on 5 Nov 2026." + (" A second number is shown too." if alt else "")
        if it.get("hours"):
            about += f" {it['hours']}"
        listing = {
            "slug": slug, "name": it["name"][:70], "category": "community", "subcategory": sub, "area": area,
            "deliversTo": ["all"] if area == "harties" else [], "about": about[:300], "backedBy": 0, "alwaysAvailable": [],
            "popularity": POPULARITY.get(it["group"], 50), "tags": TAGS.get(it["group"], []), "origin": "numbers",
        }
        if phone:
            listing["phone"] = phone if len(phone) <= 6 else digits_show(phone)
        if alt and alt != phone:
            listing["whatsapp"] = alt if len(alt) <= 6 else digits_show(alt)
        if web.startswith("https://") and " " not in web:
            listing["website"] = web
        if it.get("address"):
            listing["address"] = it["address"][:160]
        if "@" in (it.get("email") or "") and len(it["email"]) <= 80:
            listing["email"] = it["email"]
        out.append(listing)
    return out


def merge(seed_path):
    data = json.loads(SRC.read_text(encoding="utf-8"))
    listings = build(data["items"])
    path = Path(seed_path)
    seed = json.loads(path.read_text(encoding="utf-8"))
    keep = [b for b in seed["businesses"] if b.get("origin") != "numbers"]
    taken = {b["slug"] for b in keep}
    for l in listings:
        base, n = l["slug"], 2
        while l["slug"] in taken:
            l["slug"], n = f"{base}-{n}", n + 1
        taken.add(l["slug"])
    seed["businesses"] = keep + listings
    path.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"{len(listings)} help listings (of {len(data['items'])} researched); seed has {len(seed['businesses'])} businesses")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["merge"])
    ap.add_argument("--seed", default="C:/Users/gamin/BoschAI/harties-board/data/seed.local.json")
    merge(ap.parse_args().seed)
