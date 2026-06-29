"""
seed_demo_meetings.py — load the demo transcripts into the CRM store.

Reads each file in demo_transcripts/, summarises it with Claude (same as the live
dashboard), and logs it against the right client with the right date. After running,
the "Ask the AI" tab is pre-populated so you can demo recall immediately.

Usage:
    ../../.venv/Scripts/python seed_demo_meetings.py            # add the demo meetings
    ../../.venv/Scripts/python seed_demo_meetings.py --reset    # wipe the demo DB first (clean slate)

The .txt files double as upload material: drag one into the Capture tab on camera to
demo the "upload transcript -> log to CRM" flow live.
"""
import argparse
from pathlib import Path

import store
import transcribe as tx

HERE = Path(__file__).resolve().parent
TDIR = HERE / "demo_transcripts"

# Spread across June 2026, multiple clients, two Osun meetings (so date-within-client
# questions work), and Hartley as a client not in the seed roster (added on log).
MEETINGS = [
    {"file": "osun-2026-06-12-annual-reports.txt",      "client": "Osun Consulting Group", "date": "2026-06-12", "title": "Annual report automation — kickoff"},
    {"file": "cape-agri-2026-06-18-forecasting.txt",     "client": "Cape Agri Cooperative", "date": "2026-06-18", "title": "Demand forecasting — scoping"},
    {"file": "sandstone-2026-06-20-hr-compliance.txt",   "client": "Sandstone Medical Group", "date": "2026-06-20", "title": "HR compliance automation"},
    {"file": "hartley-2026-06-22-customer-intel.txt",    "client": "Hartley Retail Group",  "date": "2026-06-22", "title": "Customer intelligence — intro"},
    {"file": "brightpath-2026-06-23-fleet-intelligence.txt", "client": "BrightPath Logistics", "date": "2026-06-23", "title": "Fleet intelligence — scoping"},
    {"file": "osun-2026-06-25-rfp-demo.txt",            "client": "Osun Consulting Group", "date": "2026-06-25", "title": "Follow-up — RFP module demo"},
]


def main(reset: bool) -> None:
    if reset and store.DB_PATH.exists():
        store.DB_PATH.unlink()
        print(f"reset: removed {store.DB_PATH.name}")
    store.ensure_db()

    for m in MEETINGS:
        path = TDIR / m["file"]
        if not path.exists():
            print(f"  SKIP (missing): {m['file']}")
            continue
        text = path.read_text(encoding="utf-8")
        print(f"summarising {m['file']} …")
        summary = tx.summarise(text)
        store.log_meeting(
            client=m["client"],
            transcript_text=text,
            meeting_date=m["date"],
            title=m["title"],
            summary=summary.summary,
            action_items=summary.action_items,
            source="transcript",
        )
        print(f"  logged {m['client']} · {m['date']} · {len(summary.action_items)} action items")

    total = len(store.get_meetings())
    print(f"\nDone. {total} meeting(s) in the store across {len(store.list_clients())} clients.")
    print("Open the dashboard's “Ask the AI” tab and try:")
    print('  • "What happened in the meeting with Osun on 25 June? Give me a full review."')
    print('  • "What was recorded on 18 June, with who, and what was it about?"')
    print('  • "Which clients have follow-ups coming up and when?"')


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="wipe the demo DB before seeding")
    main(ap.parse_args().reset)
