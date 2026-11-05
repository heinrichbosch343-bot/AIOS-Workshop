#!/usr/bin/env python3
"""Remove businesses that are in Harties Board's seed twice, keeping the better listing.

  python scripts/harties_dedupe.py [--seed PATH] [--dupes PATH] [--dry]

The groups come from outputs/community-app/directory/dupes.json ({"groups": [{"same": [slug, ...], "why": ...}]}),
which a person checked: a business on Google Maps and in the WhatsApp group, a help number that is also a maps row,
a doctor's own row and their practice's row. Branches of a chain are never in it.

Which one stays: a listing with a picture first, then the group's own row, then a help number, then a maps row, then an
events-organiser row, then a practice's name over one doctor's own row, then the one with the most filled in. The one that stays takes any contact detail it lacks from the
others (never their pictures: the page says where its pictures came from), and their promos move over to it.
Runs last in harties_refresh.py, so a refresh that brings a removed row back removes it again. A slug no longer in the seed is skipped.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = Path("C:/Users/gamin/BoschAI/harties-board/data/seed.local.json")
DUPES = ROOT / "outputs/community-app/directory/dupes.json"

# Lower comes first. No origin = the group's own row (from the WhatsApp group), the best-checked kind.
ORIGIN_RANK = {None: 0, "numbers": 1, "directory": 2, "events": 3}
FILL = ("phone", "whatsapp", "website", "email", "address", "hours", "instagram", "facebook")
PICTURE_KEYS = ("image", "gallery", "imageFrom")


def filled(row: dict) -> int:
    return sum(1 for k in FILL if row.get(k))


def keeper_key(row: dict) -> tuple:
    # A practice's name ("The Dental Studio") over one doctor's own row ("Dr A J de Jager"): people look for the practice.
    doctor = 1 if row["name"].lower().startswith("dr ") else 0
    return (0 if row.get("image") else 1, ORIGIN_RANK.get(row.get("origin"), 4), doctor, -filled(row), -int(row.get("popularity") or 0), row["slug"])


def merged(keep: dict, others: list[dict]) -> dict:
    out = dict(keep)
    for other in others:
        for key in FILL:
            if not out.get(key) and other.get(key):
                out[key] = other[key]
        if other.get("tags"):
            out["tags"] = list(dict.fromkeys([*(out.get("tags") or []), *other["tags"]]))[:24]
        out["backedBy"] = max(int(out.get("backedBy") or 0), int(other.get("backedBy") or 0))
        if other.get("popularity") is not None:
            out["popularity"] = max(int(out.get("popularity") or 0), int(other["popularity"]))
    return out


def dedupe(seed: dict, groups: list[dict]) -> tuple[dict, list[str]]:
    by_slug = {b["slug"]: b for b in seed["businesses"]}
    replace: dict[str, dict] = {}
    gone: dict[str, str] = {}
    log = []
    for group in groups:
        rows = [by_slug[s] for s in dict.fromkeys(group["same"]) if s in by_slug and s not in gone and s not in replace]
        if len(rows) < 2:
            continue
        rows.sort(key=keeper_key)
        keep, rest = rows[0], rows[1:]
        replace[keep["slug"]] = merged(keep, rest)
        for r in rest:
            gone[r["slug"]] = keep["slug"]
        log.append(f"kept {keep['slug']}, removed {', '.join(r['slug'] for r in rest)} ({group.get('why', '')})")
    businesses = [replace.get(b["slug"], b) for b in seed["businesses"] if b["slug"] not in gone]
    promos = [{**p, "businessSlug": gone[p["businessSlug"]]} if p.get("businessSlug") in gone else p for p in seed["promos"]]
    return {**seed, "businesses": businesses, "promos": promos}, log


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=str(SEED))
    ap.add_argument("--dupes", default=str(DUPES))
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    seed_path = Path(args.seed)
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    groups = json.loads(Path(args.dupes).read_text(encoding="utf-8"))["groups"]
    out, log = dedupe(seed, groups)
    print("\n".join(log))
    print(f"duplicates removed: {len(seed['businesses']) - len(out['businesses'])}")
    if not args.dry:
        seed_path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
