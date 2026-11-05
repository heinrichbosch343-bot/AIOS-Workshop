"""Gives the Harties Board's businesses and events a point on the map.

The board filters by distance ("within 5 km of Pecanwood"), so every business and every event with its
own venue needs a latitude and longitude. They come from the Google Maps scrape already on disk
(outputs/community-app/maps/places.csv, built by harties_places.py); nothing is fetched here.

A business gets a point when it matches a scraped place by phone number, by website address or by name.
When several places share a name (a chain with branches) the one nearest the business's own area wins.
An event whose venue is named ("Aviators Harties") gets that venue's point, even when the organiser is
another business. Everything else keeps no point and the board falls back to the middle of its area.

  python scripts/harties_geo.py --seed <app>/data/seed.local.json            # fill in what is missing
  python scripts/harties_geo.py --seed <seed> --dry                          # say what would change, write nothing
  python scripts/harties_geo.py --seed <seed> --centres                      # print the area centres

Safe to run again: a point already in the seed is kept unless --force. A backup of the seed is kept once a day.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import statistics
import sys
import unicodedata
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACES = ROOT / "outputs" / "community-app" / "maps" / "places.csv"

# The box the board accepts (lib/geo.ts says the same): a point outside it is a bad match, not a place.
LAT_MIN, LAT_MAX, LNG_MIN, LNG_MAX = -26.6, -25.2, 27.4, 28.6
# A match further than this from the middle of its own area is almost certainly a namesake elsewhere.
MAX_FROM_AREA_KM = 25.0

# The middle of each area, read off landmarks in the scrape (a clubhouse, a shopping centre, a crossroads),
# not the average of its businesses: many businesses are filed under an area they only serve. Here they only
# pick between same-named places; the board has its own copy in lib/geo.ts, and the two must agree.
FALLBACK_CENTRES = {
    "harties": (-25.7360, 27.8950),
    "pecanwood": (-25.7650, 27.8560),
    "coves": (-25.7716, 27.7966),
    "islands": (-25.7720, 27.8500),
    "westlake": (-25.7804, 27.8042),
    "r512": (-25.7770, 27.8580),
    "schoemansville": (-25.7310, 27.8780),
    "ifafi": (-25.7435, 27.9000),
    "kosmos": (-25.7430, 27.8470),
    "broederstroom": (-25.8005, 27.8768),
    "leloko": (-25.7497, 27.7940),
    "damdoryn": (-25.7251, 27.8301),
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(pty|ltd|cc|the|and|in|at|hartbeespoort|hartbeespoortdam|harties|hartbeespoort dam)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def digits(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    return d[-9:] if len(d) >= 9 else ""


def host(url: str) -> str:
    m = re.match(r"^(?:https?://)?(?:www\.)?([^/?#]+)", (url or "").strip().lower())
    return m.group(1) if m else ""


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat, dlng = radians(b[0] - a[0]), radians(b[1] - a[1])
    h = sin(dlat / 2) ** 2 + cos(radians(a[0])) * cos(radians(b[0])) * sin(dlng / 2) ** 2
    return 12742 * asin(sqrt(h))


def in_box(lat: float, lng: float) -> bool:
    return LAT_MIN <= lat <= LAT_MAX and LNG_MIN <= lng <= LNG_MAX


class Places:
    """The scraped places, indexed three ways."""

    def __init__(self, path: Path):
        self.rows = []
        with open(path, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    lat, lng = float(r["latitude"]), float(r["longitude"])
                except (KeyError, ValueError):
                    continue
                if not in_box(lat, lng):
                    continue
                self.rows.append({"title": r.get("title", ""), "lat": lat, "lng": lng, "phone": digits(r.get("phone", "")), "host": host(r.get("website", ""))})
        self.by_phone: dict[str, list[dict]] = {}
        self.by_host: dict[str, list[dict]] = {}
        self.by_name: dict[str, list[dict]] = {}
        for p in self.rows:
            if p["phone"]:
                self.by_phone.setdefault(p["phone"], []).append(p)
            if p["host"]:
                self.by_host.setdefault(p["host"], []).append(p)
            n = norm(p["title"])
            if n:
                self.by_name.setdefault(n, []).append(p)

    def find(self, business: dict, centre: tuple[float, float]) -> tuple[dict, str] | None:
        for how, pool in (
            ("phone", self.by_phone.get(digits(business.get("phone") or business.get("whatsapp") or ""), [])),
            ("website", self.by_host.get(host(business.get("website") or ""), []) if host(business.get("website") or "") not in COMMON_HOSTS else []),
            ("name", self.by_name.get(norm(business.get("name") or ""), [])),
        ):
            if not pool:
                continue
            best = min(pool, key=lambda p: km((p["lat"], p["lng"]), centre))
            if km((best["lat"], best["lng"]), centre) <= MAX_FROM_AREA_KM:
                return best, how
        return None

    def venue(self, text: str) -> dict | None:
        want = norm(text)
        if len(want) < 5:
            return None
        pool = self.by_name.get(want)
        if pool:
            return pool[0]
        # "Aviators" in "Aviators Harties", "The Wine Shed" in "Wine Shed at Pecanwood": one name inside the other.
        hits = [p for n, ps in self.by_name.items() for p in ps if len(n) >= 6 and (n in want or want in n)]
        return hits[0] if len(hits) == 1 else None


# Websites many unrelated businesses share (a page on Facebook is not the business's own site).
COMMON_HOSTS = {"", "facebook.com", "m.facebook.com", "instagram.com", "linktr.ee", "wa.me", "google.com", "business.site"}


def business_point(b: dict) -> tuple[float, float] | None:
    if isinstance(b.get("lat"), (int, float)) and isinstance(b.get("lng"), (int, float)):
        return float(b["lat"]), float(b["lng"])
    return None


def fill(seed: dict, places: Places, force: bool = False) -> dict:
    report = {"businesses": 0, "kept": 0, "no_match": 0, "promos": 0, "promo_no_venue": [], "by": {}}
    named: dict[str, tuple[float, float]] = {}
    for b in seed["businesses"]:
        if b.get("home"):  # a home is never placed exactly
            b.pop("lat", None)
            b.pop("lng", None)
            continue
        if business_point(b) and not force:
            report["kept"] += 1
            continue
        centre = FALLBACK_CENTRES.get(b.get("area", "harties"), FALLBACK_CENTRES["harties"])
        hit = places.find(b, centre)
        if not hit:
            report["no_match"] += 1
            continue
        place, how = hit
        b["lat"], b["lng"] = round(place["lat"], 5), round(place["lng"], 5)
        report["businesses"] += 1
        report["by"][how] = report["by"].get(how, 0) + 1
    for b in seed["businesses"]:
        pt = business_point(b)
        if pt:
            named[norm(b["name"])] = pt
    for p in seed["promos"]:
        if not p.get("venue"):
            continue
        if business_point(p) and not force:
            continue
        pt = venue_point(p["venue"], named, places)
        if pt is None:
            report["promo_no_venue"].append(f'{p["id"]}: {p["venue"]}')
            continue
        p["lat"], p["lng"] = round(pt[0], 5), round(pt[1], 5)
        report["promos"] += 1
    return report


def venue_point(venue: str, named: dict[str, tuple[float, float]], places: Places) -> tuple[float, float] | None:
    """The point of a venue written the way an advert writes it: "Aviators Harties", "Boatersworld, Simon Bekker Avenue"."""
    # The whole text first, then each part before a comma or an "at" ("The Boat House Restaurant at Pecanwood, 1 The Peninsula Street").
    parts = [venue] + [x for x in re.split(r",| at | \(", venue) if x.strip()]
    for part in parts:
        want = norm(part)
        if len(want) < 5:
            continue
        if want in named:
            return named[want]
        hits = [v for n, v in named.items() if len(n) >= 6 and (n in want or want in n)]
        if len(hits) == 1:
            return hits[0]
        place = places.venue(part)
        if place:
            return place["lat"], place["lng"]
    return None


def centres(seed: dict) -> dict[str, tuple[float, float, int]]:
    by_area: dict[str, list[tuple[float, float]]] = {}
    for b in seed["businesses"]:
        pt = business_point(b)
        if pt and not b.get("home"):
            by_area.setdefault(b["area"], []).append(pt)
    return {
        a: (round(statistics.median(p[0] for p in pts), 4), round(statistics.median(p[1] for p in pts), 4), len(pts))
        for a, pts in sorted(by_area.items())
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", required=True, type=Path, help="the app's data/seed.local.json")
    ap.add_argument("--places", type=Path, default=PLACES)
    ap.add_argument("--force", action="store_true", help="replace points already in the seed")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--centres", action="store_true", help="print the middle of each area and stop")
    args = ap.parse_args(argv)

    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    if args.centres:
        for area, (lat, lng, n) in centres(seed).items():
            print(f"{area:15s} {lat:.4f}, {lng:.4f}   ({n} businesses)")
        return 0
    report = fill(seed, Places(args.places), args.force)
    print(f"businesses placed now: {report['businesses']} {report['by']}, already had a point: {report['kept']}, no match: {report['no_match']}")
    print(f"events placed at their venue: {report['promos']}, venue not found: {len(report['promo_no_venue'])}")
    for line in report["promo_no_venue"][:40]:
        print("  no venue point:", line)
    if args.dry:
        print("dry run: nothing written")
        return 0
    backup = args.seed.with_name(args.seed.name.replace(".local.json", f".before-geo-{date.today().isoformat()}.local.json"))
    if not backup.exists():
        shutil.copyfile(args.seed, backup)
    args.seed.write_text(json.dumps(seed, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"written: {args.seed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
