"""
IntelOS — Master collection script.

Runs all configured collectors (meetings), writes to the database,
and classifies new meetings. This is the script that gets scheduled daily.

Usage:
    python scripts/intel/collect_all.py
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import init_db, write_meetings, get_meeting_stats


def run():
    print(f"IntelOS collection starting at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    conn = init_db()
    meeting_records = []

    # Collect from Fathom
    try:
        from collect_fathom import collect as collect_fathom
        fathom_meetings = collect_fathom()
        if fathom_meetings:
            meeting_records.extend(fathom_meetings)
    except Exception as e:
        print(f"Fathom error: {e}")

    # Write to database
    if meeting_records:
        count = write_meetings(conn, meeting_records)
        print(f"Meetings: {count} records written to database")
    else:
        print("Meetings: no new records collected")

    # Classify new meetings
    try:
        from classify import classify_all
        classified = classify_all(conn)
        if classified:
            print(f"Classifier: {classified} meetings classified")
    except Exception as e:
        print(f"Classifier error: {e}")

    # Summary
    print("\n" + "=" * 60)
    stats = get_meeting_stats(conn)
    print(f"Database totals:")
    print(f"  Meetings:     {stats['total_meetings']}")
    print(f"  Team members: {stats['team_members']}")
    if stats['latest_meeting_date']:
        print(f"  Latest meeting: {stats['latest_meeting_date']}")
    print("=" * 60)

    conn.close()
    print("Done.")


if __name__ == "__main__":
    run()
