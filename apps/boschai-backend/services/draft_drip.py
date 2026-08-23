"""
Drafts-to-drip: Heinrich writes outreach emails as Gmail DRAFTS, imports them
into the drip once, and the scheduler sends them one at a time with random
3-9 minute gaps inside the 07:30-18:30 SAST window (services/email_drip.py).

Sending uses Gmail's drafts.send, so a draft composed as a reply keeps its
thread, and whatever the draft holds at send time (edits, attachments) is
exactly what goes out. After a send, the draft disappears from Gmail's Drafts
folder — Gmail moves it to Sent, same as pressing Send by hand.

Import is always explicit (/dripdrafts on Telegram, or the Import button on
the /crm dashboard). The system never sweeps drafts up on its own, so an
unrelated draft Heinrich happens to be writing can never be sent by accident:
anything drafted AFTER the import stays untouched until the next import.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from db.client import supabase
from services import email as email_service

TZ = ZoneInfo("Africa/Johannesburg")


def import_drafts(query: str = "") -> dict:
    """Stage the account's current Gmail drafts into draft_queue.

    Dedupes on Gmail's draft id, so re-running is always safe. Drafts with no
    recipient are skipped (nothing to send them to). `query` optionally narrows
    the import with a Gmail search filter, e.g. 'label:drip'.
    """
    drafts = email_service.list_drafts(query=query)
    with_recipient = [d for d in drafts if "@" in (d.get("to") or "")]
    skipped = len(drafts) - len(with_recipient)
    if not with_recipient:
        return {"found": len(drafts), "imported": 0, "duplicates": 0,
                "skipped_no_recipient": skipped}

    ids = [d["draft_id"] for d in with_recipient]
    existing = (supabase.table("draft_queue")
                .select("draft_id")
                .in_("draft_id", ids)
                .execute()).data
    known = {r["draft_id"] for r in existing}
    fresh = [d for d in with_recipient if d["draft_id"] not in known]
    if fresh:
        supabase.table("draft_queue").insert([{
            "draft_id": d["draft_id"],
            "to_email": email_service.extract_address(d["to"]),
            "subject": d["subject"],
            "snippet": (d.get("snippet") or "")[:200],
        } for d in fresh]).execute()
    return {"found": len(drafts), "imported": len(fresh),
            "duplicates": len(known), "skipped_no_recipient": skipped}


def next_queued() -> dict | None:
    """Oldest staged draft still waiting to be sent, or None."""
    rows = (supabase.table("draft_queue")
            .select("*")
            .eq("status", "queued")
            .order("queued_at")
            .limit(1)
            .execute()).data
    return rows[0] if rows else None


def send_one(row: dict) -> bool:
    """Send one staged draft via drafts.send. Returns True on success.

    A 404 means the draft no longer exists — Heinrich sent or deleted it by
    hand after the import — so the row is marked 'gone', not retried.
    """
    now = datetime.now(TZ)
    try:
        sent = email_service.send_draft(row["draft_id"])
        supabase.table("draft_queue").update({
            "status": "sent",
            "sent_at": now.isoformat(),
            "sent_message_id": sent.get("sent_id") or "",
            "sent_thread_id": sent.get("thread_id") or "",
        }).eq("id", row["id"]).execute()
        return True
    except Exception as exc:
        msg = str(exc)
        gone = "404" in msg or "not found" in msg.lower()
        supabase.table("draft_queue").update({
            "status": "gone" if gone else "failed",
            "error": msg[:300],
        }).eq("id", row["id"]).execute()
        return False


def queue_counts() -> dict:
    """Status counts for the draft queue (status -> n)."""
    rows = (supabase.table("draft_queue")
            .select("status")
            .execute()).data
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts
