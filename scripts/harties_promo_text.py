#!/usr/bin/env python3
"""Put the clearer descriptions on Harties Board's promos.

  python scripts/harties_promo_text.py [--seed PATH] [--text PATH]

outputs/community-app/directory/promo-text.json holds, per promo id, a plain description of what it is (`details`,
written from the organiser's own page or the business's own post, checked for length and tone), a price when the page
states one and the promo had none (`priceText`), and a "check with the organiser" note where the sources disagree
(`dateNote`), and sometimes a photo the business already has (`image`). A data refresh brings the original wording back, so this runs after it, in harties_refresh.py.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = Path("C:/Users/gamin/BoschAI/harties-board/data/seed.local.json")
TEXT = ROOT / "outputs" / "community-app" / "directory" / "promo-text.json"
MAX_DETAILS, MAX_PRICE, MAX_NOTE = 400, 60, 80


def apply_text(seed: dict, text: dict, media_dir: Path | None = None) -> tuple[dict, int]:
    count = 0
    promos = []
    for p in seed["promos"]:
        e = text.get(p["id"]) if p["id"] != "_businesses" else None
        if not e:
            promos.append(p)
            continue
        q = dict(p)
        d = (e.get("details") or "").strip()
        if d and len(d) <= MAX_DETAILS:
            q["details"] = d
        price = (e.get("priceText") or "").strip()
        if price and len(price) <= MAX_PRICE and not q.get("priceText"):
            q["priceText"] = price
        note = (e.get("dateNote") or "").strip()
        if note and len(note) <= MAX_NOTE:
            q["dateNote"] = note
        # a picture the business already has (a photo from its own gallery), chosen by eye for this promo
        pic = (e.get("image") or "").strip()
        if pic and not q.get("image") and media_dir is not None and (media_dir / pic.rsplit("/", 1)[-1]).exists():
            q["image"] = pic
        count += q != p
        promos.append(q)
    # tidier names for organisers that were made from a listing's wording ("Boatersworld (organiser not named)")
    names = text.get("_businesses", {})
    businesses = [{**b, "name": names[b["slug"]]} if b["slug"] in names and b.get("origin") == "events" else b for b in seed["businesses"]]
    return {**seed, "businesses": businesses, "promos": promos}, count


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=str(SEED))
    ap.add_argument("--text", default=str(TEXT))
    args = ap.parse_args()
    seed_path = Path(args.seed)
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    out, count = apply_text(seed, json.loads(Path(args.text).read_text(encoding="utf-8")), seed_path.parent.parent / "public" / "media")
    seed_path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"descriptions updated on {count} promos")


if __name__ == "__main__":
    main()
