"""
IntelOS — Meeting classifier.

Classifies meetings by department/stream based on participant emails
matched against the staff registry.

Usage:
    python scripts/intel/classify.py
    python scripts/intel/classify.py --reclassify
"""

import json
import argparse
from pathlib import Path
from datetime import datetime, timezone
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import get_connection


def classify_meeting(conn, meeting: dict, department_streams: dict) -> dict:
    participants_json = meeting.get("participants", "")
    title = (meeting.get("title") or "").strip()

    try:
        participants = json.loads(participants_json) if participants_json else []
    except (json.JSONDecodeError, TypeError):
        participants = []

    staff_found = []
    external_found = []

    for p in participants:
        email = name = None
        if isinstance(p, dict):
            email = p.get("email", "")
            name = p.get("name", "")
        elif isinstance(p, str):
            if "@" in p:
                email = p
            else:
                name = p

        if email:
            row = conn.execute(
                "SELECT * FROM staff_registry WHERE LOWER(email) = LOWER(?)",
                (email.strip(),)
            ).fetchone()
            if row:
                staff_found.append(dict(row))
            else:
                external_found.append({"email": email, "name": name or email})
        elif name:
            row = conn.execute(
                "SELECT * FROM staff_registry WHERE LOWER(name) = LOWER(?)",
                (name.strip(),)
            ).fetchone()
            if row:
                staff_found.append(dict(row))
            else:
                external_found.append({"name": name})

    if not department_streams:
        call_type = "meeting"
        if len(staff_found) >= 2 and len(external_found) == 0:
            call_type = "team_meeting"
        elif len(staff_found) >= 1 and len(external_found) >= 1:
            call_type = "one_on_one"
        return {"stream": "general", "call_type": call_type, "reason": "no_departments_configured"}

    staff_count = len(staff_found)
    external_count = len(external_found)

    if staff_count >= 2 and external_count == 0:
        call_type = "team_meeting"
    elif staff_count >= 1 and external_count >= 1:
        call_type = "one_on_one"
    elif staff_count == 0 and external_count >= 2:
        call_type = "external"
    else:
        call_type = "meeting"

    if staff_found:
        dept = staff_found[0].get("department", "general")
        stream = department_streams.get(dept, dept)
        reason = f"department:{dept}"
    elif title:
        stream = _classify_by_title(title, department_streams)
        reason = f"title_heuristic:{title[:60]}"
    else:
        stream = "general"
        reason = "no_participants_no_title"

    return {"stream": stream, "call_type": call_type, "reason": reason}


def _classify_by_title(title: str, department_streams: dict) -> str:
    title_lower = title.lower()
    for dept in department_streams:
        if dept.lower() in title_lower:
            return department_streams[dept]
    for keyword in ["sales", "demo", "discovery", "qualification"]:
        if keyword in title_lower:
            return department_streams.get("sales", "sales")
    for keyword in ["standup", "sync", "team", "internal", "weekly"]:
        if keyword in title_lower:
            return "team_meeting"
    return "general"


def get_department_streams(conn) -> dict:
    rows = conn.execute(
        "SELECT DISTINCT department FROM staff_registry WHERE is_active = 1"
    ).fetchall()
    if not rows:
        return {}
    return {row["department"]: row["department"] for row in rows}


def classify_all(conn, reclassify: bool = False) -> int:
    department_streams = get_department_streams(conn)

    if reclassify:
        cursor = conn.execute("SELECT meeting_id, title, participants FROM meetings")
    else:
        cursor = conn.execute(
            "SELECT meeting_id, title, participants FROM meetings WHERE stream IS NULL"
        )

    meetings = [dict(row) for row in cursor.fetchall()]
    if not meetings:
        print("No meetings to classify.")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    count = 0

    for meeting in meetings:
        result = classify_meeting(conn, meeting, department_streams)
        conn.execute(
            "UPDATE meetings SET stream = ?, call_type = ?, classified_at = ? "
            "WHERE meeting_id = ?",
            (result["stream"], result["call_type"], now, meeting["meeting_id"])
        )
        count += 1

    conn.commit()
    print(f"Classified {count} meetings.")
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reclassify", action="store_true")
    args = parser.parse_args()

    conn = get_connection()
    classify_all(conn, reclassify=args.reclassify)
    conn.close()
