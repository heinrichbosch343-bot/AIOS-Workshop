#!/usr/bin/env python3
"""Turn the Google Maps scrapes into directory listings for Harties Board.

Stage 1 (this file, `prepare`): read every raw Maps file, drop duplicates, closed places, places outside
the Harties area, businesses already in the app and things that are not a business a resident can use
(houses, substations, ...), map each place to the app's categories (lib/categories.ts, 5 Nov 2026
version) and write compact rows for a reviewer to check.

Stage 2 (`apply`): read the reviewers' decisions (keep, category, sub-group, cleaned name), build the
final listings (name, short factual about line, search tags, a busyness number used only to order lists,
contacts as the business published them) and write them to outputs/community-app/directory/.

Stage 3 (`merge`): put the listings into the app's seed file. Idempotent: listings from a earlier run
(the ones marked "unclaimed") are replaced, everything else in the seed is left alone.

Facts only. Nothing in a listing is invented: the "about" line is the place's own Google type, its area
and its opening days, and the tags are its Google type and its name's words.

  python scripts/harties_directory.py prepare
  python scripts/harties_directory.py apply
  python scripts/harties_directory.py merge --seed C:/Users/gamin/BoschAI/harties-board/data/seed.local.json
"""
import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harties_places as hp  # noqa: E402  (reuse the area box, closed test and chain list)

ROOT = Path(__file__).resolve().parent.parent
MAPS = ROOT / "outputs" / "community-app" / "maps"
OUT = ROOT / "outputs" / "community-app" / "directory"
SEED = Path("C:/Users/gamin/BoschAI/harties-board/data/seed.local.json")
RAW_FILES = ["places.csv", "places-sweep2.csv"]

# --- Google type -> (category, sub-group). First match wins. None = not a listing. -----------------
RULES = [
    # Not something a resident looks up (or not a business at all).
    (r"^(house|villa|apartment|cottage|condominium complex|townhouse complex|housing complex|housing development|housing society|"
     r"gated community|furnished apartment building|real estate developer|electrical substation|tunnel|reservoir|dam|"
     r"warehouse|warehouse store|corporate office|mining company|sand plant|slaughterhouse|manufacturer|food manufacturer|"
     r"food producer|industrial equipment supplier|furniture wholesaler|household goods wholesaler|meat wholesaler|"
     r"alcoholic beverage wholesaler|computer wholesaler|wholesale plant nursery|fruit and vegetable wholesaler|"
     r"cannabis club|cannabis store|gun shop|taxidermist|rock shop|crane rental agency|plant and machinery hire|"
     r"architectural and engineering model maker|information services|e-commerce service|truck stop|"
     r"alcohol retail monopoly|fish farm|scenic spot|picnic ground|park|garden|historical landmark|tourist information center)$", "!", ""),
    # Stay & visit
    (r"guest ?house|bed ?& ?breakfast|\bb&b\b|homestay|lodge\b|lodging|hotel|resort|inn\b|camp|caravan|serviced accommodation|indoor lodging", "stay", "lodges"),
    (r"self-catering|holiday (rental|home|apartment)|vacation (home|rental)", "stay", "self-catering"),
    (r"wedding venue|event venue|banquet|function|conference|reception", "stay", "venues"),
    (r"boat tour|cruise|tour (agency|operator)|travel agency|canoe|kayak|boat rental|boat hire", "stay", "tours"),
    (r"tourist attraction|wildlife|zoo|safari|sanctuary|adventure|zip|balloon|aerial|cable|museum|nature preserve|bird watching|hiking area|"
     r"outdoor activity|park$", "stay", "attractions"),
    # Food
    (r"coffee|cafe|café|espresso|tea (house|room|store)|bakery|cake|pastry|pie shop|donut|dessert|ice cream|confection|chocolate|patisserie", "food", "home-kitchens"),
    (r"fast food|take ?(out|away)|pizza takeaway|hamburger|burger|fried chicken|food court|sandwich|kebab", "food", "takeaways"),
    (r"restaurant|steak house|bistro|diner|eatery|gastropub|brewpub|tapas|sushi|grill|dinner theater|pub & grill|bar & grill|bar and grill", "food", "restaurants"),
    (r"liquor|wine|winery|brewery|distillery|\bbar$|^bar$|sports bar|pub$|^pub$|bartending|club$|cocktail|beer", "food", "wine-bars"),
    (r"butcher|meat|grocery|supermarket|convenience|farm shop|farm$|fruit and vegetable|health food|market$|farmers|baking supply|deli$|^deli|discount supermarket|food products|animal feed", "food", "produce"),
    # Health
    (r"pharmac|drug ?store|chemist", "health", "pharmacies"),
    (r"orthodont", "health", "orthodontists"),
    (r"dent(ist|al)|oral and maxillofacial", "health", "dentists"),
    (r"optomet|optician|audiolog|hearing|eye care|ophthalm", "health", "eyes"),
    (r"physio|physical therap|physical rehab|chiropract|occupational therap|psycholog|psychiat|counsel|speech|biokinet|dietic|nutrition|"
     r"health consultant|homeopath|naturopath|wellness|massage therapist", "health", "therapy"),
    (r"nurs|home care|frail|caregiver|care home|old age|retirement", "health", "care"),
    (r"doctor|medical|clinic|general practi|family practice|physician|radiolog|patholog|hospital|surgeon|paediatric|pediatric|"
     r"gynae|dermatolog|urgent care|blood|laborator", "health", "clinics"),
    # Beauty & fitness
    (r"skin care|cosmetic|aesthetic|medical spa|laser|permanent make|botox|beauty clinic", "beauty", "aesthetics"),
    (r"gym|fitness|yoga|pilates|personal trainer|martial arts|kickboxing|crossfit|physical fitness|boxing|sports club$|tennis instructor|gymnastics", "beauty", "fitness"),
    (r"beauty|hair|barber|nail|spa\b|waxing|make-up|makeup|beautician|tanning|lash|brow|massage|salon|health spa|health and beauty", "beauty", "spa-nails"),
    # Sport
    (r"golf", "sport", "golf"),
    (r"tennis|padel|squash|bowling|racquet|racket", "sport", "racket"),
    (r"marina|yacht|sailing|boat (club|ramp|repair|builder)|fishing|marine supply|swimming (school|instructor)|water sport", "sport", "water"),
    (r"horse|equestrian|riding|stable|bicycle|cycling|mountain bike|running|trail|sports complex|outdoor (clothing|equipment)", "sport", "outdoors"),
    (r"dance|swimming|sports (club|association)", "sport", "dance"),
    # Property
    (r"real estate (agency|agent|consultant|attorney)|estate agen|property (management|consultant)|letting|realtor", "property", "agents"),
    # Business & professional
    (r"accountant|accounting|bookkeep|tax|audit", "business", "accounting"),
    (r"law firm|lawyer|attorney|legal|notary|advocate", "business", "legal"),
    (r"insurance|financial|bank$|^bank|mortgage|investment|loan|credit", "business", "finance"),
    (r"software|website|web design|computer (service|support|security)|it (support|services)|internet service|graphic design|recording studio|"
     r"computer repair|cell phone repair|phone repair|electronics repair", "business", "it"),
    (r"print|sign shop|copy|signage|embroider|digital printing", "business", "print"),
    (r"architect|engineer|surveyor|consultant|management consultant|business (management|center)|employment|recruit|hr |marketing|advertis|"
     r"interior design|photograph|videograph", "", ""),  # sorted by the reviewer
    # Trades
    (r"plumb|geyser|drain|water treatment|septic|rainwater", "trades", "plumbing-electrical"),
    (r"electric|generator|solar|inverter|battery|energy", "trades", "solar"),
    (r"security|alarm|cctv|fence|fencing|locksmith|guard|gate", "trades", "security"),
    (r"pool|landscap|garden|plant nursery|tree|irrigation|lawn|pest", "trades", "pool-garden"),
    (r"clean|laundry|dry cleaner|cleaners|carpet", "trades", "cleaning"),
    (r"hardware|building materials|paint store|plumbing supply|electrical supply|timber|door shop|aluminum window|natural stone|tile store|"
     r"swimming pool supply|window", "trades", "supplies"),
    (r"contractor|builder|home builder|construction|painter|painting|roof|carpent|weld|steel|glass|kitchen|cabinet|plaster|paving|waterproof|"
     r"deck|tiling|flooring|civil|property maintenance|building firm|upholster|furniture (maker|repair)|curtain|blind", "trades", "building"),
    (r"appliance|repair|handyman|handywoman|air conditioning|hvac|refrigerator|garage door|mattress repair|maintenance", "trades", "repairs"),
    # Cars
    (r"tire|tyre|auto|car (repair|wash|dealer)|mechanic|panel|body shop|garage|motor|vehicle|towing|used car|engine|machine shop", "cars", "garages"),
    (r"golf cart|motorcycle|dealer", "cars", "cars"),
    (r"gas station|fuel|petrol|filling", "cars", "garages"),
    (r"transport|taxi|shuttle|courier|removal|moving|bus", "cars", "transport"),
    # Kids & schools
    (r"preschool|pre-school|nursery school|day ?care|child care|kindergarten|playgroup|after school|montessori|crèche|creche", "kids", "preschools"),
    (r"school|college|educational institution|education center|learning center|charter|university|academy", "kids", "schools"),
    (r"tutor|educational consultant|private tutor|driving school|language", "kids", "learning"),
    (r"children'?s party|party (equipment|service)|jumping castle", "kids", "parties"),
    # Shops
    (r"pet |pets|veterinar|animal (clinic|hospital|rescue)|kennel|dog|groom", "shops", "pets"),
    (r"clothing|shoe|boutique|fashion|apparel|jewel|bridal|uniform", "shops", "clothing"),
    (r"furniture|home goods|home decor|decor|mattress|carpet store|lighting|kitchenware|appliance store", "shops", "furniture"),
    (r"book|stationery|toy|baby store|hobby|craft store|art supply|fabric|candle|game", "shops", "hobbies"),
    (r"gift|art gallery|artist|art studio|picture frame|pottery|souvenir|photo shop|florist", "shops", "gifts"),
    (r"shopping mall|store|shop|electronics|computer|cell phone", "shops", "gifts"),
    # Community
    (r"church|chapel|mosque|temple|place of worship|ministr|christian", "community", "faith"),
    (r"police|fire station|ambulance|emergency|rescue", "community", "emergency"),
    (r"municipal|council|post office|government|public", "community", "council"),
    (r"atm|bank", "community", "banks"),
    (r"non-profit|ngo|association|community|club|society|cultural|residents|charity", "community", "clubs"),
    (r"market|flea", "events", "markets"),
]
RULES = [(re.compile(p, re.I), c, s) for p, c, s in RULES]

NOT_A_LISTING_HINT = re.compile(r"\b(private|guest cottage|unit \d|room \d)\b", re.I)

AREA_IDS = [
    ("pecanwood", r"pecanwood"),
    ("islands", r"\bislands?\b(?! of)"),
    ("coves", r"\bthe coves\b|\bcoves\b"),
    ("westlake", r"westlake"),
    ("r512", r"\br512\b|mountain lake|oberon"),
    ("schoemansville", r"schoemansville"),
    ("ifafi", r"ifafi"),
    ("kosmos", r"kosmos"),
    ("broederstroom", r"broederstroom"),
    ("leloko", r"leloko"),
    ("damdoryn", r"damdoryn|skeerpoort"),
]


def classify(google_category):
    g = (google_category or "").strip()
    for rx, cat, sub in RULES:
        if rx.search(g):
            return cat, sub
    return "", ""


def app_area(address, name):
    blob = f"{address} {name}"
    for area_id, rx in AREA_IDS:
        if re.search(rx, blob, re.I):
            return area_id
    return "harties"


def clean_name(name):
    n = re.sub(r"\s+", " ", name or "").strip()
    n = re.sub(r"\s*[-–|,]\s*(restaurant|bar|cafe|café|hotel|lodge|guest ?house|spa|salon)?[^-–|,]*\bin (hartbeespoort|hartebeespoort|harties|pecanwood|kosmos|schoemansville|broederstroom|ifafi)\b.*$", "", n, flags=re.I)
    n = re.sub(r"\s*[-–|]\s*(hartbeespoort|hartebeespoort|harties)\s*$", "", n, flags=re.I)
    return n[:80].strip(" -–|,")


PLACE_WORDS = r"(hartbeespoort|hartebeespoort|harties|pecanwood|kosmos|schoemansville|broederstroom|ifafi|meerhof|xanadu|the islands|westlake)"


def tidy_name(name):
    """A name the app accepts (79 characters at most) and a resident would say: no 'in Hartbeespoort ...' tail, cut at a word."""
    n = re.sub(r"\s+", " ", name or "").strip()
    short = re.sub(r"\s+(in|at)\s+" + PLACE_WORDS + r"\b.*$", "", n, flags=re.I)
    if len(short) >= 3:
        n = short
    if len(n) > 70:
        n = n[:70].rsplit(" ", 1)[0]
    return n.strip(" -–|,&")


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().replace("é", "e").replace("ê", "e")).strip("-")
    return s[:56].strip("-") or "place"


def popularity(rating, reviews):
    try:
        r, n = float(rating or 0), int(float(reviews or 0))
    except ValueError:
        return 0
    if n <= 0:
        return 0
    adj = (r * n + 3.8 * 5) / (n + 5)  # a few reviews do not move a place far from the middle
    score = max(0.0, (adj - 3.0) / 2.0) * 60 + min(1.0, math.log10(n + 1) / 2.7) * 40
    return max(0, min(100, round(score)))


def load_raw():
    rows, seen = [], set()
    for name in RAW_FILES:
        path = MAPS / name
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                key = r.get("cid") or r.get("place_id") or r.get("link")
                if not key or key in seen:
                    continue
                seen.add(key)
                rows.append(r)
    return rows


def load_seed_without_ours():
    """Names and phones of what is already in the app, not counting what this pipeline itself put there (a re-run must see the same places)."""
    names, phones = set(), set()
    try:
        seed = json.loads(SEED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return names, phones
    for b in seed.get("businesses", []):
        if b.get("origin") in ("directory", "events", "numbers"):
            continue
        names.add(hp.norm(b.get("name", "")))
        for key in ("phone", "whatsapp"):
            digits = hp.digits(b.get(key, ""))
            if digits:
                phones.add(digits)
    return names, phones


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_raw()
    seed_names, seed_phones = load_seed_without_ours()
    kept, drops = [], Counter()
    for r in rows:
        name = (r.get("title") or "").strip()
        if not name:
            drops["no name"] += 1
            continue
        if not hp.in_area(r.get("latitude"), r.get("longitude")):
            drops["outside the Harties box"] += 1
            continue
        if hp.is_closed(r) or (r.get("status") or "").strip().upper().startswith("CLOSED"):
            drops["closed"] += 1
            continue
        phone, website = (r.get("phone") or "").strip(), (r.get("website") or "").strip()
        reviews = int(float(r.get("review_count") or 0))
        gcat = (r.get("category") or "").strip()
        cat, sub = classify(gcat)
        if re.match(r"^(house|villa|apartment|cottage)$", gcat, re.I) and reviews < 25:
            drops["a single house or villa"] += 1
            continue
        if cat == "!":
            drops["not a business residents use"] += 1
            continue
        if not phone and not website and reviews < 30:
            drops["no phone, no website, few reviews"] += 1
            continue
        digits = hp.digits(phone)
        if hp.norm(name) in seed_names or (digits and digits in seed_phones):
            drops["already in the app"] += 1
            continue
        kept.append({
            "id": r.get("cid") or r.get("place_id"),
            "name": clean_name(name), "raw_name": name, "google_category": gcat,
            "category": cat, "sub": sub, "area": app_area(r.get("address", ""), name),
            "address": (r.get("address") or "").strip(), "phone": phone, "website": website,
            "rating": r.get("review_rating", ""), "reviews": reviews,
            "hours": r.get("open_hours", ""), "email": (r.get("emails") or "").split(",")[0].strip() if r.get("emails") else "",
            "lat": r.get("latitude", ""), "lon": r.get("longitude", ""),
            "maps_link": r.get("link", ""), "place_id": r.get("place_id", ""),
            "chain": bool(hp.NOT_LOCAL.search(name + " ")),
        })
    # One place can come back for several searches under slightly different ids: same phone and same name = one place.
    unique, seen_key = [], set()
    for k in kept:
        key = (hp.norm(k["name"]), hp.digits(k["phone"]) or k["address"].lower())
        if key in seen_key:
            drops["same place found twice"] += 1
            continue
        seen_key.add(key)
        unique.append(k)
    (OUT / "prepared.json").write_text(json.dumps(unique, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"raw rows {len(rows)} -> prepared {len(unique)}")
    for reason, n in drops.most_common():
        print(f"  dropped {n:5d}  {reason}")
    mapped = Counter((k["category"] or "(reviewer)", k["sub"]) for k in unique)
    print("by group:", sorted(Counter(k["category"] or "(reviewer)" for k in unique).items(), key=lambda x: -x[1]))
    unmapped = Counter(k["google_category"] for k in unique if not k["category"])
    print("left for the reviewers:", sum(unmapped.values()), unmapped.most_common(12))
    return unique


def hours_line(hours_json):
    """'Open Mon to Sat' style summary from Google's opening hours, or ''. Days only; the times stay on the place's own page."""
    try:
        data = json.loads(hours_json) if isinstance(hours_json, str) else hours_json
    except (TypeError, ValueError):
        return ""
    if not isinstance(data, dict) or not data:
        return ""
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    short = {d: d[:3] for d in order}
    open_days = [d for d in order if data.get(d) and "closed" not in " ".join(data[d]).lower()]
    if not open_days:
        return ""
    if len(open_days) == 7:
        times = {tuple(data[d]) for d in order}
        only = data["Monday"][0] if len(times) == 1 and data["Monday"] else ""
        if re.search(r"24 hours", only, re.I):
            return "Open 24 hours"
        # Clock times only: anything else Google writes there is left out rather than mangled.
        return "Open daily" + (f", {only.replace(' ', '').replace('–', '-')}" if re.fullmatch(r"[0-9:apm. –-]+", only, re.I) else "")
    # runs of consecutive days
    runs, run = [], [open_days[0]]
    for d in open_days[1:]:
        if order.index(d) == order.index(run[-1]) + 1:
            run.append(d)
        else:
            runs.append(run)
            run = [d]
    runs.append(run)
    text = ", ".join(short[r[0]] if len(r) == 1 else f"{short[r[0]]} to {short[r[-1]]}" for r in runs)
    return f"Open {text}"


def hours_text(hours_json):
    """'Mon-Fri 8am-5pm; Sat 9am-1pm' from Google's opening hours, or '' when it does not fit in 80 characters or is not clock times."""
    try:
        data = json.loads(hours_json) if isinstance(hours_json, str) else hours_json
    except (TypeError, ValueError):
        return ""
    if not isinstance(data, dict) or not data:
        return ""
    order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def compact(times):
        text = ", ".join(times)
        if re.search(r"24 hours", text, re.I):
            return "24 hours"
        text = re.sub(r"\s*(am|pm)", lambda m: m.group(1).lower(), text, flags=re.I)
        text = text.replace("–", "-").replace(" ", "")
        return text if re.fullmatch(r"[0-9:apm,.-]+", text) else ""

    rows = []
    for day in order:
        times = data.get(day)
        if not times or "closed" in " ".join(times).lower():
            continue
        shown = compact(times)
        if not shown:
            return ""
        if rows and rows[-1][2] == shown and rows[-1][1] == order.index(day) - 1:
            rows[-1] = (rows[-1][0], order.index(day), shown)
        else:
            rows.append((order.index(day), order.index(day), shown))
    if not rows:
        return ""
    parts = []
    for first, last, shown in rows:
        days = order[first][:3] if first == last else f"{order[first][:3]}-{order[last][:3]}"
        parts.append(f"{days} {shown}")
    text = "; ".join(parts)
    return "Open daily " + text.split(" ", 1)[1] if len(rows) == 1 and rows[0][:2] == (0, 6) else (text if len(text) <= 80 else "")


def sa_number(phone):
    """Digits as a local number with spaces ('064 665 7382'), or '' when it is not a South African number."""
    d = re.sub(r"\D", "", phone or "")
    if d.startswith("27") and len(d) == 11:
        d = "0" + d[2:]
    if len(d) == 10 and d.startswith("0"):
        return f"{d[:3]} {d[3:6]} {d[6:]}"
    return ""


def is_mobile(local):
    d = re.sub(r"\D", "", local)
    return len(d) == 10 and (d[:2] in ("06", "07") or d[:3] in ("081", "082", "083", "084"))


def humanize(gcat):
    g = (gcat or "").strip()
    return g[:1].upper() + g[1:] if g else "Business"


def build_listing(k, decision, used_slugs, extra=None):
    cat = decision.get("category") or k["category"]
    sub = decision.get("sub") or k["sub"]
    name = tidy_name(decision.get("name") or k["name"])
    area_name = {"pecanwood": "Pecanwood", "islands": "The Islands", "coves": "The Coves", "westlake": "Westlake", "r512": "Mountain Lake and the R512",
                 "schoemansville": "Schoemansville", "ifafi": "Ifafi", "kosmos": "Kosmos", "broederstroom": "Broederstroom",
                 "leloko": "Leloko", "damdoryn": "Damdoryn and Skeerpoort", "harties": "Hartbeespoort"}[k["area"]]
    type_words = humanize(k["google_category"])
    hours = hours_line(k["hours"])
    about = f"{type_words} in {area_name}." + (f" {hours}." if hours else "")
    base = slugify(name)
    slug = base
    n = 2
    while slug in used_slugs:
        slug = f"{base}-{n}"
        n += 1
    used_slugs.add(slug)
    local = sa_number(k["phone"])
    tags = []
    for t in [k["google_category"].lower(), *re.findall(r"[a-z]{3,}", name.lower())]:
        if t and t not in tags and t not in ("the", "and", "pty", "ltd"):
            tags.append(t)
    tags.extend(decision.get("tags", []))
    website = k["website"]
    if website and not website.lower().startswith("https://"):
        website = "https://" + re.sub(r"^https?://", "", website, flags=re.I) if website.lower().startswith("http://") or "." in website else ""
    listing = {
        "slug": slug, "name": name, "category": cat, "subcategory": sub, "area": k["area"], "deliversTo": [],
        "about": about[:300], "backedBy": 0, "alwaysAvailable": [], "unclaimed": True, "origin": "directory",
        "popularity": popularity(k["rating"], k["reviews"]), "tags": tags[:24],
    }
    # What the business's own website says about itself (read by the food-specials helpers), when it says it.
    extra = extra or {}
    if extra.get("hours") and len(extra["hours"]) <= 80:
        listing["hours"] = extra["hours"]
    elif hours_text(k["hours"]):
        listing["hours"] = hours_text(k["hours"])
    if re.match(r"^[A-Za-z0-9._]{1,30}$", extra.get("instagram") or ""):
        listing["instagram"] = extra["instagram"]
    if re.match(r"^https://(www\.)?facebook\.com/[^?#\s]{2,}", extra.get("facebook") or ""):
        listing["facebook"] = extra["facebook"].split("?")[0].rstrip("/")
    if local:
        listing["phone"] = local
        if is_mobile(local):
            listing["whatsapp"] = local
    if website:
        listing["website"] = website
    if k.get("email") and "@" in k["email"] and len(k["email"]) <= 80:
        listing["email"] = k["email"]
    if k["address"]:
        listing["address"] = k["address"][:160]
    return listing


def apply():
    prepared = json.loads((OUT / "prepared.json").read_text(encoding="utf-8"))
    decisions = {}
    for path in sorted((OUT / "decisions").glob("*.json")):
        for d in json.loads(path.read_text(encoding="utf-8")):
            decisions[str(d["id"])] = d
    used = set()
    extras = {}
    for path in sorted((OUT / "food").glob("result-*.json")):
        for e in json.loads(path.read_text(encoding="utf-8")).get("extra_info", []):
            extras[str(e.get("business_id"))] = e
    index = {}
    listings, dropped, missing = [], Counter(), 0
    for k in prepared:
        d = decisions.get(str(k["id"]))
        if d is None:
            missing += 1
            if not k["category"]:
                dropped["no decision and no category"] += 1
                continue
            d = {"keep": True}
        if not d.get("keep", True):
            dropped[d.get("reason", "dropped by the reviewer")[:60]] += 1
            continue
        if not (d.get("category") or k["category"]):
            dropped["no category"] += 1
            continue
        listing = build_listing(k, d, used, extras.get(str(k["id"])))
        index[str(k["id"])] = listing["slug"]
        listings.append(listing)
    (OUT / "directory-businesses.json").write_text(json.dumps(listings, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (OUT / "directory-index.json").write_text(json.dumps(index, indent=1), encoding="utf-8", newline="\n")
    print(f"{len(listings)} listings ({missing} had no reviewer decision)")
    for reason, n in dropped.most_common(15):
        print(f"  dropped {n:4d}  {reason}")
    print(sorted(Counter(l["category"] for l in listings).items(), key=lambda x: -x[1]))


def specials_promos(listings, index):
    """Promos for the weekly specials and nights the helpers read on the places' own websites."""
    import harties_events as ev  # noqa: E402
    by_slug = {l["slug"]: l for l in listings}
    promos, seen = [], set()
    for path in sorted((OUT / "food").glob("result-*.json")):
        for r in json.loads(path.read_text(encoding="utf-8")).get("records", []):
            slug = index.get(str(r.get("business_id")))
            biz = by_slug.get(slug)
            title = re.sub(r"\s+", " ", r.get("title") or "").strip()[:90]
            if not biz or not title:
                continue
            t0, t1 = ev.clock(r.get("start_time")), ev.clock(r.get("end_time"))
            if t1 and not t0:
                t1 = None  # "until 11am" with no start is not a time range the board can show
            times = {**({"start": t0} if t0 else {}), **({"end": t1} if t1 else {})}
            schedules = []
            if r.get("monthly"):
                schedules = [({"type": "once", "date": d.isoformat(), **times}, d.isoformat()) for d in ev.monthly_dates(r["monthly"])]
            elif r.get("date"):
                d = ev.parse_date(r["date"])
                if d and ev.TODAY <= d <= ev.WINDOW_END:
                    schedules = [({"type": "once", "date": d.isoformat(), **times}, d.isoformat())]
            elif r.get("days"):
                days = sorted({int(x) for x in r["days"] if str(x).isdigit() and 1 <= int(x) <= 7})
                if days:
                    schedules = [({"type": "weekly", "days": days, **times}, "weekly")]
            for sched, suffix in schedules:
                key = (slug, sched.get("date") or "weekly", t0 or "", hp.norm(title)[:20])
                dup = (slug, sched.get("date"), t0 or "")
                if key in seen or (sched.get("date") and dup in seen):
                    continue
                seen.add(key)
                seen.add(dup)
                promo = {
                    "id": f"spec-{slug[:22]}-{slugify(title)[:20]}-{suffix}".strip("-")[:60].strip("-"), "businessSlug": slug,
                    "kind": "special" if r.get("kind") == "special" else "event", "title": title,
                    "category": biz["category"], "subcategory": biz["subcategory"], "area": biz["area"],
                    "schedule": sched, "cta": "call" if biz.get("phone") else ("link" if biz.get("website") else "none"),
                    "origin": "food-specials",
                }
                if promo["cta"] == "link":
                    promo["ctaUrl"], promo["ctaLabel"] = biz["website"], "Website"
                if r.get("details"):
                    promo["details"] = r["details"][:400]
                price = (r.get("price_text") or "").strip()
                if price and len(price) <= 60:
                    promo["priceText"] = price
                src = (r.get("source") or "").strip()
                if src.startswith("http://"):
                    src = "https://" + src[7:]
                if src.startswith("https://") and " " not in src:
                    promo["sourceUrl"] = src
                if r.get("monthly"):
                    promo["dateNote"] = (r["monthly"][:1].upper() + r["monthly"][1:])[:80]
                promos.append(promo)
    ids = Counter(p["id"] for p in promos)
    return [p for p in promos if ids[p["id"]] == 1] + [p for p in promos if ids[p["id"]] > 1][:0]


def merge(seed_path):
    seed = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    listings = json.loads((OUT / "directory-businesses.json").read_text(encoding="utf-8"))
    index = json.loads((OUT / "directory-index.json").read_text(encoding="utf-8"))
    keep = [b for b in seed["businesses"] if b.get("origin") != "directory"]
    taken = {b["slug"] for b in keep}
    out, remap = [], {}
    for l in listings:
        slug, n = l["slug"], 2
        while slug in taken:
            slug = f"{l['slug']}-{n}"
            n += 1
        taken.add(slug)
        remap[l["slug"]] = slug
        out.append({**l, "slug": slug})
    index = {k: remap.get(v, v) for k, v in index.items()}
    specials = specials_promos(out, index)
    seed["businesses"] = keep + out
    seed["promos"] = [p for p in seed["promos"] if p.get("origin") != "food-specials"] + specials
    Path(seed_path).write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"seed now has {len(seed['businesses'])} businesses ({len(out)} from the directory, {len(keep)} others) and {len(specials)} food specials")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["prepare", "apply", "merge"])
    ap.add_argument("--seed", default=str(SEED))
    args = ap.parse_args()
    {"prepare": prepare, "apply": apply, "merge": lambda: merge(args.seed)}[args.stage]()
