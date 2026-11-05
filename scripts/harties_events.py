#!/usr/bin/env python3
"""Turn the researched events into promos for Harties Board.

Input : outputs/community-app/events/raw/*.json   (one array of event records per research helper)
Output: outputs/community-app/events/events-promos.json   {businesses, promos}
        outputs/community-app/events/events-report.md      what went in, what was left out and why
        and, with `merge`, the same promos inside the app's seed file.

Rules, all of them so a wrong date never looks right:
  - Only events from today to the end of the window; anything finished is dropped.
  - An event with no usable date is NOT put on the board; it goes in the report's watch list.
  - A date that only a listing site gave, or that is inferred from earlier years, carries a note
    ("Date to be confirmed by the organiser") on the card and the page.
  - "Members only" events are left out: this is a public board.
  - The same event found by two helpers is one event; the better source wins and the sources are kept.
  - Monthly events ("last Saturday of the month") become one dated promo per coming month, because
    the board's schedules know weekly, range and once.

  python scripts/harties_events.py build
  python scripts/harties_events.py merge --seed C:/Users/gamin/BoschAI/harties-board/data/seed.local.json
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harties_places as hp  # noqa: E402
from harties_directory import app_area, sa_number, slugify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "outputs" / "community-app" / "events"
RAW = EVENTS / "raw"
SKIP_FILES = {"feeds.json", "calendar-context.json", "useful-numbers.json"}
TODAY = dt.date(2026, 11, 5)
WINDOW_END = dt.date(2027, 5, 5)
DAYS = {"monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6, "sunday": 7,
        "mondays": 1, "tuesdays": 2, "wednesdays": 3, "thursdays": 4, "fridays": 5, "saturdays": 6, "sundays": 7,
        "mon": 1, "tue": 2, "tues": 2, "wed": 3, "thu": 4, "thur": 4, "thurs": 4, "fri": 5, "sat": 6, "sun": 7}
ORDINALS = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "last": -1}
NOTE_LISTING = "Date from a listing, check with the organiser"
NOTE_TYPICAL = "Date to be confirmed by the organiser"


def parse_date(text):
    try:
        return dt.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def https(url):
    url = (url or "").strip()
    if not url:
        return ""
    if url.lower().startswith("http://"):
        url = "https://" + url[7:]
    elif not url.lower().startswith("https://") and "." in url and " " not in url:
        url = "https://" + url
    return url if url.lower().startswith("https://") and " " not in url and len(url) <= 300 else ""


def clock(text):
    m = re.match(r"^(\d{1,2}):(\d{2})$", (text or "").strip())
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m and int(m.group(1)) < 24 else None


def weekdays_in(text):
    found = []
    for word in re.findall(r"[a-z]+", (text or "").lower()):
        d = DAYS.get(word)
        if d and d not in found:
            found.append(d)
    return sorted(found)


def nth_weekday(year, month, weekday, n):
    """The n-th (or last, n = -1) given ISO weekday of a month."""
    first = dt.date(year, month, 1)
    days = [first + dt.timedelta(days=i) for i in range(31)]
    days = [d for d in days if d.month == month and d.isoweekday() == weekday]
    return days[n - 1] if n > 0 and len(days) >= n else (days[-1] if n == -1 else None)


def monthly_dates(repeat):
    """Dates in the window for 'last Saturday of the month' style rules, or []."""
    text = (repeat or "").lower()
    ordinal = next((ORDINALS[w] for w in re.findall(r"[a-z0-9]+", text) if w in ORDINALS), None)
    days = weekdays_in(text)
    if ordinal is None or len(days) != 1:
        return []
    out, y, m = [], TODAY.year, TODAY.month
    for _ in range(8):
        d = nth_weekday(y, m, days[0], ordinal)
        if d and TODAY <= d <= WINDOW_END:
            out.append(d)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


SUBS = [
    (r"marathon|trail|run\b|running|parkrun|fun run|hike|hiking|walk", "sport", "running"),
    (r"cycl|bike|mtb|gravel|mountain bik", "sport", "outdoors"),
    (r"golf", "sport", "golf"),
    (r"padel|tennis|squash|pickle|racket", "sport", "racket"),
    (r"sail|regatta|boat|yacht|fishing|bass|kayak|paddle|swim|triathl", "sport", "water"),
    (r"horse|equestrian|riding", "sport", "outdoors"),
    (r"market|bazaar|stalls|craft fair", "events", "markets"),
    (r"music|concert|festival|karaoke|quiz|band|live|comedy|dj\b|show|theatre|party|new year|nye", "events", "music"),
    (r"church|carol|service|prayer|retreat|faith", "events", "community"),
    (r"kids|children|holiday programme|santa", "kids", "classes"),
    (r"dinner|lunch|breakfast|roast|wine|tasting|brunch|braai|food|restaurant|happy hour", "food", "restaurants"),
]
SUBS = [(re.compile(p, re.I), c, s) for p, c, s in SUBS]
RECORD_CATEGORY = {"sport": ("sport", "running"), "market": ("events", "markets"), "music": ("events", "music"),
                   "community": ("events", "community"), "kids": ("kids", "classes"), "food": ("food", "restaurants"),
                   "faith": ("events", "community"), "charity": ("events", "community"), "outdoors": ("sport", "outdoors"),
                   "other": ("events", "community")}


def category_for(rec):
    blob = f"{rec.get('title', '')} {rec.get('description', '')}"
    title_hit = next(((c, s) for rx, c, s in SUBS if rx.search(rec.get("title", ""))), None)
    if title_hit:
        return title_hit
    base = RECORD_CATEGORY.get((rec.get("category") or "other").lower(), ("events", "community"))
    hit = next(((c, s) for rx, c, s in SUBS if rx.search(blob) and c == base[0]), None)
    return hit or base


# Events a person should decide on before they appear on a community board.
HOLD_TITLES = ("hookah",)

# A researcher's own warning in the notes means the event waits until a person has checked it.
CHECK_MARKERS = ("low confidence", "conflict:", "verify the venue", "venue is unverified", "verify before", "unverified")


def needs_check(rec):
    notes = (rec.get("notes") or "").lower()
    return any(marker in notes for marker in CHECK_MARKERS)


def title_key(title):
    t = re.sub(r"\b(20\d\d|annual|the|at|in|of|and|&)\b", " ", (title or "").lower())
    return " ".join(sorted(set(re.findall(r"[a-z0-9]{3,}", t))))


def load_records():
    records = []
    for path in sorted(RAW.glob("*.json")):
        if path.name in SKIP_FILES:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"! {path.name}: not valid JSON ({exc})")
            continue
        for rec in data if isinstance(data, list) else []:
            if isinstance(rec, dict) and rec.get("title"):
                rec["_file"] = path.stem
                records.append(rec)
    return records


STATUS_RANK = {"confirmed": 3, "listing": 2, "typical": 1, "unknown": 0}


def same_event(a, b):
    """Two records name the same event: same day, and one title's words are inside the other's (or most are shared)."""
    ta, tb = set(title_key(a["title"]).split()), set(title_key(b["title"]).split())
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    return inter >= 2 and (ta <= tb or tb <= ta or inter / len(ta | tb) >= 0.5) or ta == tb


def merge_duplicates(records):
    """The same event found twice is one event: keep the best-sourced record and every source."""
    groups = []
    for r in sorted(records, key=lambda r: -STATUS_RANK.get(r.get("date_status") or "unknown", 0)):
        repeating = (r.get("kind") or "") in ("weekly", "monthly")
        for g in groups:
            first = g[0]
            if (first.get("start_date") or "") == (r.get("start_date") or "") and ((first.get("kind") or "") in ("weekly", "monthly")) == repeating and same_event(first, r):
                g.append(r)
                break
        else:
            groups.append([r])
    out = []
    for group in groups:
        best = dict(group[0])
        best["sources"] = list(dict.fromkeys(s for r in group for s in (r.get("sources") or [])))
        best["_found_by"] = sorted({r["_file"] for r in group})
        if len(group) > 1:
            best["description"] = max((r.get("description") or "" for r in group), key=len)
            contact = dict(best.get("organiser_contact") or {})
            for r in group[1:]:
                for key, value in (r.get("organiser_contact") or {}).items():
                    contact.setdefault(key, value) if not contact.get(key) else None
                    if not contact.get(key):
                        contact[key] = value
            best["organiser_contact"] = contact
        out.append(best)
    return out


def schedule_for(rec):
    """-> list of (schedule dict, id suffix, extra note) or [] when the event has no usable date."""
    kind = (rec.get("kind") or "once").lower()
    start, end = parse_date(rec.get("start_date")), parse_date(rec.get("end_date"))
    t0, t1 = clock(rec.get("start_time")), clock(rec.get("end_time"))
    times = {**({"start": t0} if t0 else {}), **({"end": t1} if t1 else {})}
    repeat = rec.get("repeat") or ""
    if kind in ("weekly", "league"):
        days = weekdays_in(repeat) or ([start.isoweekday()] if start else [])
        if not days:
            return []
        until = {"until": WINDOW_END.isoformat()}
        return [({"type": "weekly", "days": days, **times, **({"from": start.isoformat()} if start and start > TODAY else {}), **until}, "weekly", "")]
    if kind == "monthly":
        dates = monthly_dates(repeat)
        return [({"type": "once", "date": d.isoformat(), **times}, d.isoformat(), f"Repeats: {repeat}"[:60]) for d in dates]
    if not start:
        return []
    if end and end > start:
        if end < TODAY or start > WINDOW_END:
            return []
        return [({"type": "range", "from": start.isoformat(), "to": end.isoformat(), **times}, start.isoformat(), "")]
    if start < TODAY or start > WINDOW_END:
        return []
    return [({"type": "once", "date": start.isoformat(), **times}, start.isoformat(), "")]


def find_business(name, businesses):
    n = hp.norm(name)
    if not n:
        return None
    for b in businesses:
        bn = hp.norm(b["name"])
        # The same name, or one name is the other plus whole extra words ("Welwitschia Country Market" and "Welwitschia Country Market Damdoryn").
        # Never a bare prefix: "Hartbees" is not "Hartbeespoort High School".
        if bn == n or (len(min(n, bn, key=len)) >= 10 and (bn.startswith(n + " ") or n.startswith(bn + " "))):
            return b
    return None


def build(seed_businesses=()):
    records = merge_duplicates(load_records())
    existing = list(seed_businesses)
    new_businesses, promos, skipped, watch = [], [], [], []
    used_slugs = {b["slug"] for b in existing}
    used_ids = set()
    for rec in sorted(records, key=lambda r: (r.get("start_date") or "9999", r["title"])):
        title = re.sub(r"\s+", " ", rec["title"]).strip()[:90]
        if (rec.get("audience") or "").lower() == "members only":
            skipped.append((title, "members only"))
            continue
        if (rec.get("distance") or "core").lower() not in ("core", "extended"):
            skipped.append((title, "too far"))
            continue
        if any(word in title.lower() for word in HOLD_TITLES):
            skipped.append((title, "left for Heinrich to decide"))
            continue
        if needs_check(rec):
            skipped.append((title, "held back until checked: " + (rec.get("notes") or "")[:110]))
            continue
        scheds = schedule_for(rec)
        if not scheds:
            watch.append(rec)
            continue
        cat, sub = category_for(rec)
        area = app_area(f"{rec.get('area', '')} {rec.get('venue', '')}", rec.get("organiser", ""))
        organiser = re.sub(r"\s+", " ", rec.get("organiser") or rec.get("venue") or title).strip()[:80]
        contact = rec.get("organiser_contact") or {}
        biz = find_business(organiser, existing + new_businesses)
        if biz is None:
            slug = slugify(organiser)
            base, n = slug, 2
            while slug in used_slugs:
                slug, n = f"{base}-{n}", n + 1
            used_slugs.add(slug)
            phone = sa_number(contact.get("phone"))
            biz = {"slug": slug, "name": organiser, "category": cat, "subcategory": sub, "area": area, "deliversTo": [],
                   "about": f"Organiser of {title}.", "backedBy": 0, "alwaysAvailable": [], "unclaimed": True, "origin": "events"}
            if phone:
                biz["phone"] = phone
            if https(contact.get("website")):
                biz["website"] = https(contact.get("website"))
            if "@" in (contact.get("email") or "") and len(contact["email"]) <= 80:
                biz["email"] = contact["email"]
            new_businesses.append(biz)
        url = https(contact.get("booking_url")) or https(contact.get("website"))
        sources = [s for s in (rec.get("sources") or []) if https(s)]
        status = (rec.get("date_status") or "unknown").lower()
        note = "" if status == "confirmed" else (NOTE_TYPICAL if status in ("typical", "unknown") else NOTE_LISTING)
        price = (rec.get("price_text") or "").strip()
        details = (rec.get("description") or "").strip()
        if len(price) > 60:
            details = f"{details} Price: {price}".strip()
            price = ""
        phone = sa_number(contact.get("phone"))
        for sched, suffix, extra in scheds:
            pid = f"evt-{slugify(title)[:44]}-{suffix}".strip("-")
            n = 2
            while pid in used_ids:
                pid, n = f"{pid}-{n}", n + 1
            used_ids.add(pid)
            promo = {"id": pid, "businessSlug": biz["slug"], "kind": "event", "title": title, "category": cat, "subcategory": sub,
                     "area": area, "schedule": sched, "cta": "none", "origin": "events"}
            if details:
                promo["details"] = details[:400]
            if price:
                promo["priceText"] = price
            if rec.get("venue"):
                promo["venue"] = rec["venue"][:80]
            if url:
                promo.update(cta="link", ctaUrl=url, ctaLabel="Book or find out more")
            elif phone:
                promo["cta"] = "call"
            if note and extra:
                promo["dateNote"] = f"{extra[:48].rstrip('. ')}. Check first."
            elif note or extra:
                promo["dateNote"] = (extra or note)[:80]
            if sources:
                promo["sourceUrl"] = sources[0]
            promos.append(promo)
    return new_businesses, promos, skipped, watch, records


def month_name(iso):
    return dt.date.fromisoformat(iso).strftime("%B %Y")


def report(businesses, promos, skipped, watch, records):
    lines = ["# Events for Harties Board, built " + TODAY.isoformat(), "",
             f"{len(promos)} events on the board from {len(records)} researched records ({len(businesses)} new organisers).", ""]
    by_month = {}
    for p in promos:
        s = p["schedule"]
        key = s.get("date") or s.get("from") or "weekly"
        by_month.setdefault(month_name(key) if key != "weekly" else "Every week", []).append(p)
    for month, items in by_month.items():
        lines.append(f"## {month}")
        for p in sorted(items, key=lambda x: x["schedule"].get("date") or x["schedule"].get("from") or ""):
            s = p["schedule"]
            when = s.get("date") or (f"{s['from']} to {s['to']}" if s["type"] == "range" else "every " + ", ".join(str(d) for d in s["days"]))
            lines.append(f"- {when}: {p['title']}" + (f" ({p['dateNote']})" if p.get("dateNote") else ""))
        lines.append("")
    lines.append("## Left off the board")
    lines += [f"- {t}: {why}" for t, why in skipped]
    lines.append("")
    lines.append("## Watch list: real events, no usable date yet")
    lines += [f"- {w['title']} ({w.get('repeat') or w.get('date_status')}): {w.get('notes', '')[:140]}" for w in watch]
    return "\n".join(lines) + "\n"


def write_outputs(seed_businesses=()):
    businesses, promos, skipped, watch, records = build(seed_businesses)
    EVENTS.mkdir(parents=True, exist_ok=True)
    (EVENTS / "events-promos.json").write_text(json.dumps({"businesses": businesses, "promos": promos}, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    (EVENTS / "events-report.md").write_text(report(businesses, promos, skipped, watch, records), encoding="utf-8", newline="\n")
    print(f"{len(records)} records -> {len(promos)} promos, {len(businesses)} new organisers, {len(skipped)} left off, {len(watch)} on the watch list")
    return businesses, promos


def merge(seed_path):
    path = Path(seed_path)
    seed = json.loads(path.read_text(encoding="utf-8"))
    keep_b = [b for b in seed["businesses"] if b.get("origin") != "events"]
    keep_p = [p for p in seed["promos"] if p.get("origin") != "events" and not str(p.get("id", "")).startswith("evt-")]
    businesses, promos = write_outputs(keep_b)
    seed["businesses"] = keep_b + businesses
    seed["promos"] = keep_p + promos
    path.write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    print(f"seed now has {len(seed['businesses'])} businesses and {len(seed['promos'])} promos")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["build", "merge"])
    ap.add_argument("--seed", default="C:/Users/gamin/BoschAI/harties-board/data/seed.local.json")
    args = ap.parse_args()
    if args.stage == "build":
        seed = json.loads(Path(args.seed).read_text(encoding="utf-8")) if Path(args.seed).exists() else {"businesses": []}
        write_outputs([b for b in seed["businesses"] if b.get("origin") != "events"])
    else:
        merge(args.seed)
