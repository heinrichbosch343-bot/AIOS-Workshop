"""
harties_status.py - what the Harties Board page inside Twenty reads, with no Streamlit in it (harties_view.py draws it).

The Harties Board app (hartisboard.up.railway.app, its own Railway service) counts visitors, home-screen installs and the
businesses and promos people send in. Its /api/stats feed, guarded by the same key as its /stats page, hands those counts
over as JSON: counts only, never a phone's code or anything a visitor typed. Where the app lives and the key are saved by
`python3 scripts/hartisboard_deploy.py --save-stats-feed` in outputs/community-app/hartisboard-stats.json (gitignored).

Every network call goes through reply_status, so it has a short timeout and a failure becomes a plain sentence.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import quote

import reply_status as R

ROOT = Path(__file__).resolve().parents[1]
FEED_FILE = ROOT / "outputs" / "community-app" / "hartisboard-stats.json"
TIMEOUT = 20      # the app reads its saved files before it answers
NOT_TOLD = ("this PC does not know where Harties Board runs yet. Ask Claude to run "
            "`python3 scripts/hartisboard_deploy.py --save-stats-feed`")
NOT_UPDATED = "the Harties Board app has not been updated yet to share its numbers with Twenty. Ask Claude to ship it"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"]   # as the app's own page writes them
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def target(path: Path | None = None, env=None) -> tuple[str, str]:
    """(address, key) of the Harties Board app, or ("", "") when this PC has never been told."""
    env = os.environ if env is None else env
    p = path or FEED_FILE
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("url") and data.get("key"):
                return str(data["url"]).rstrip("/"), str(data["key"])
        except (OSError, ValueError):
            pass
    return (env.get("HARTIES_STATS_URL") or "").rstrip("/"), env.get("HARTIES_STATS_KEY") or ""


def report(where: tuple[str, str] | None = None) -> dict:
    """The app's numbers. Raises reply_status.Unreachable with a plain sentence when they can't be read."""
    url, key = where or target()
    if not url or not key:
        raise R.Unreachable(NOT_TOLD)
    try:
        data = R.get_json(f"{url}/api/stats?key={quote(key, safe='')}", TIMEOUT)
    except R.Unreachable as e:
        if "older build" in str(e):          # a 404: the app is running a version from before the feed existed
            raise R.Unreachable(NOT_UPDATED)
        raise
    if not isinstance(data.get("stats"), dict) or not isinstance(data.get("listing"), dict):
        raise R.Unreachable("it answered with something that is not the numbers")
    return data


# ---------------------------------------------------------------- reading the answer safely

def dig(data, *path):
    for step in path:
        data = data.get(step) if isinstance(data, dict) else None
    return data


def num(value) -> int:
    """A whole number from whatever the feed holds; anything else is 0, so one odd field can't break the page."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def n(value) -> str:
    return f"{num(value):,}"


def day_label(value) -> str:
    """2026-11-02 as 2 Nov; anything that isn't a date comes back as it is (the page escapes it)."""
    try:
        d = date.fromisoformat(str(value))
    except ValueError:
        return str(value)
    return f"{d.day} {MONTHS[d.month - 1]}"


def month_label(key) -> str:
    try:
        year, month = str(key).split("-")
        return f"{MONTHS[int(month) - 1]} {int(year)}"
    except (ValueError, IndexError):
        return str(key)


def week_label(key) -> str:
    try:
        d = date.fromisoformat(str(key))
    except ValueError:
        return str(key)
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def cards(data: dict) -> list[tuple[str, str]]:
    """(big number, label) for the strip at the top."""
    return [
        (n(dig(data, "stats", "active", "today")), "Using it today"),
        (n(dig(data, "stats", "active", "week")), "Using it this week"),
        (n(dig(data, "stats", "installed", "all")), "Have it on their phone"),
        (n(dig(data, "stats", "appUsers", "month")), "Opened it from the icon, 30 days"),
        (n(dig(data, "board", "listedThemselves")), "Businesses that listed themselves"),
        (n(data.get("waiting")), "Waiting for you to check"),
    ]


def period_rows(data: dict, which: str) -> list[list[str]]:
    """Month or week rows: label, opens, people, icon, added, listed. Listings are matched by period, not by position."""
    listed = {r.get("key"): r.get("listings") for r in (dig(data, "listing", which) or []) if isinstance(r, dict)}
    label = month_label if which == "months" else week_label
    rows = []
    for r in (dig(data, "stats", which) or []):
        if not isinstance(r, dict):
            continue
        rows.append([label(r.get("key")), n(r.get("opens")), n(r.get("people")), n(r.get("appPeople")), n(r.get("added")),
                     n(listed.get(r.get("key")))])
    return rows


def listing_rows(data: dict) -> list[list[str]]:
    """Rows for the "Who is listing" table, businesses next to promos."""
    b, p = dig(data, "listing", "listings") or {}, dig(data, "listing", "promos") or {}
    both = lambda label, *path: [label, n(dig(b, *path)), n(dig(p, *path))]
    return [
        both("Sent in, ever", "sent"),
        both("Sent in the last 7 days", "when", "week"),
        both("Sent in the last 30 days", "when", "month"),
        both("On the board (you approved)", "approved"),
        both("Waiting for you to check", "waiting"),
        both("Turned down", "rejected"),
        ["Phones that opened the page", n(dig(data, "stats", "opened", "list")), n(dig(data, "stats", "opened", "post"))],
    ]


# ---------------------------------------------------------------- the visitor dashboard (Plausible's layout)

RANGES = (7, 28, 90)
NO_TRAFFIC = ("The full visitor dashboard appears once the app update that counts visits, sources and pages is live. "
              "Until then, the numbers below are what the app already counts.")
# Each tile: the field in the feed, its label, how it is written, and whether a rise is good news (bounce rate is not).
TILES = (
    ("visitors", "Unique visitors", "count", True),
    ("visits", "Total visits", "count", True),
    ("pageviews", "Page views", "count", True),
    ("viewsPerVisit", "Views per visit", "decimal", True),
    ("bounceRate", "Bounce rate", "percent", False),
    ("visitSeconds", "Visit length", "duration", True),
    ("added", "Added to phone", "count", True),
)
CHART_METRICS = {"Visitors": "visitors", "Visits": "visits", "Page views": "pageviews"}


def traffic_range(data: dict, days: int) -> dict | None:
    """The 7, 28 or 90 day block of the dashboard, or None when the app does not send one yet."""
    block = dig(data, "traffic", "ranges", str(days))
    return block if isinstance(block, dict) and isinstance(block.get("current"), dict) else None


def value(field: str, kind: str, raw) -> str:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raw = 0
    if kind == "decimal":
        return f"{raw:.1f}"
    if kind == "percent":
        return f"{round(raw)}%"
    if kind == "duration":
        return duration(raw)
    return compact(raw)


def compact(raw) -> str:
    """1234 as 1.2k, the way the dashboard writes big numbers; small ones stay whole."""
    x = num(raw)
    if x >= 1_000_000:
        return f"{x / 1_000_000:.1f}M".replace(".0M", "M")
    if x >= 10_000:
        return f"{round(x / 1000)}k"
    if x >= 1000:
        return f"{x / 1000:.1f}k".replace(".0k", "k")
    return str(x)


def duration(seconds) -> str:
    s = max(0, num(seconds))
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def change(current, previous, rise_is_good: bool = True) -> tuple[str, str]:
    """("12%", "good"|"bad"|"flat"|"new") for the small arrow under a tile. Nothing before is "new", not +infinity."""
    cur, prev = (c if isinstance(c, (int, float)) and not isinstance(c, bool) else 0 for c in (current, previous))
    if prev == 0:
        return ("new", "flat") if cur else ("0%", "flat")
    pct = round((cur - prev) / prev * 100)
    if pct == 0:
        return "0%", "flat"
    up = pct > 0
    return f"{abs(pct)}%", ("good" if up == rise_is_good else "bad") + ("-up" if up else "-down")


def tiles(block: dict) -> list[dict]:
    cur, prev = block.get("current") or {}, block.get("previous") or {}
    out = []
    for field, label, kind, rise_good in TILES:
        text, mood = change(cur.get(field), prev.get(field), rise_good)
        out.append({"label": label, "value": value(field, kind, cur.get(field)), "change": text, "mood": mood})
    return out


def series(block: dict, metric: str) -> list[tuple[str, int]]:
    """(day, number) for the chart, oldest first."""
    return [(str(p.get("day")), num(p.get(metric))) for p in (block.get("series") or []) if isinstance(p, dict) and p.get("day")]


def list_rows(block: dict, which: str, names: dict | None = None) -> list[dict]:
    """Rows for a Sources or Pages list: name, a second line (the page address when it has a name), count, bar width."""
    rows = [r for r in (block.get(which) or []) if isinstance(r, dict) and r.get("name")]
    top = max([num(r.get("visitors")) for r in rows] or [0]) or 1
    names = names or {}
    out = []
    for r in rows:
        raw = str(r.get("name"))
        nice = names.get(raw) if isinstance(names.get(raw), str) else None
        out.append({"name": nice or raw, "sub": raw if nice else "", "count": compact(r.get("visitors")),
                    "width": max(2, round(100 * num(r.get("visitors")) / top))})
    return out


def range_label(block: dict) -> str:
    return f"{day_label(block.get('from'))} to {day_label(block.get('to'))}"

