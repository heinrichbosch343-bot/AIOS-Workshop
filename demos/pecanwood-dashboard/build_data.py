"""
build_data.py — merge the scraped Seeff/Property24 datasets into data/portfolio.json.

Everything in the output is REAL scraped public data except the `sample` block on
each listing (portal activity we cannot see from outside), which is generated
deterministically from the web ref so the demo is stable between reloads, and is
labeled as sample throughout the UI.

Run once (or re-run after a fresh scrape):
    python build_data.py
"""
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

CAPTURED = "2026-07-06"

# Property24 estate-agency counts for Pecanwood, captured 2026-07-06 (real).
COMPETITORS = [
    {"name": "Pam Golding", "listings": 44},
    {"name": "Seeff Pecanwood", "listings": 42, "us": True},
    {"name": "RE/MAX Horizon", "listings": 35},
    {"name": "Property Active", "listings": 22},
    {"name": "15 smaller agencies", "listings": 43},
]

# The three pre-built Monday seller updates (real listings, PDFs in static/reports/).
REPORTS = {
    "3001224": "seller-update-8-forest-crescent.pdf",
    "2988115": "seller-update-202-jack-nicklaus-drive.pdf",
    "1958094": "seller-update-6-mountain-view-drive.pdf",
}


def pretty_address(slug: str | None, title: str | None) -> str | None:
    if not slug:
        return None
    words = slug.replace("-", " ").title()
    return words


def sample_activity(ref: str) -> dict:
    """Deterministic pseudo-activity per listing. Clearly labeled SAMPLE in the UI."""
    n = int(ref)
    return {
        "views_week": 90 + (n * 37) % 220,
        "enquiries_week": (n * 7) % 5,
        "viewings_booked": (n * 13) % 3,
        "days_listed": 21 + (n * 11) % 180,
    }


def main() -> None:
    listings_raw = json.loads((DATA / "pecanwood_listings.json").read_text(encoding="utf-8"))
    deals_raw = json.loads((DATA / "louise_deals.json").read_text(encoding="utf-8"))

    sale = [l for l in listings_raw if not l["rental"]]
    priced = [l for l in sale if l.get("size") and l["price"] > 1_000_000]
    med = median(l["price"] / l["size"] for l in priced)

    listings = []
    for l in sorted(sale, key=lambda x: -x["price"]):
        rpm2 = round(l["price"] / l["size"]) if l.get("size") else None
        listings.append({
            "ref": l["ref"],
            "url": l["url"],
            "title": l.get("title") or "Listing",
            "address": pretty_address(l.get("slug"), l.get("title")),
            "price": l["price"],
            "size": l.get("size"),
            "beds": l.get("beds"),
            "baths": l.get("baths"),
            "mandate": l.get("mandate"),
            "rpm2": rpm2,
            "vs_median_pct": round((rpm2 / med - 1) * 100) if rpm2 and l["price"] > 1_000_000 else None,
            "report": REPORTS.get(l["ref"]),
            "sample": sample_activity(l["ref"]),
        })

    solds = [d for d in deals_raw if d.get("status") == "Sold" and not d["rental"]]
    rented = [d for d in deals_raw if d.get("status") == "Rented"]

    portfolio = {
        "captured": CAPTURED,
        "agent": {"name": "Louise Cawood", "office": "Seeff Pecanwood", "office_deals_public": 139},
        "estate": {"name": "Pecanwood Golf Estate", "homes": 880},
        "stats": {
            "active_sale": len(sale),
            "book_value": sum(l["price"] for l in sale),
            "median_rpm2": round(med),
            "priced_listings": len(priced),
            "pct_estate_on_market": round(len(sale) / 880 * 100, 1),
        },
        "competitors": COMPETITORS,
        "recent_solds": [{"price": d["price"], "title": d.get("title", "")} for d in solds],
        "recent_rented": [{"price": d["price"], "title": d.get("title", "")} for d in rented],
        "listings": listings,
    }

    out = DATA / "portfolio.json"
    out.write_text(json.dumps(portfolio, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[build] {len(listings)} listings, median R{med:,.0f}/m2, "
          f"book R{portfolio['stats']['book_value']/1e6:,.1f}M -> {out.name}")


if __name__ == "__main__":
    main()
