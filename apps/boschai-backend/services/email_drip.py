"""
Email drip — sends queued outreach emails one at a time with random gaps.

The scheduler calls tick() every minute. Most ticks do nothing: outside the
07:30-15:00 SAST window it sleeps, and between sends it waits out a random
3-9 minute gap so the pattern never looks like a burst. A hard daily cap
(EMAIL_DRIP_DAILY_CAP, default 25) protects Gmail deliverability.

Two queues feed it, drained in this order:
  1. draft_queue — Heinrich's own Gmail drafts, staged by services/draft_drip.py
     and sent via Gmail drafts.send (threading and attachments preserved).
  2. email_queue — CSV-drafted outreach, loaded from the local CRM by
     scripts/crm_cloud_sync.py and sent as fresh mail (services.email.send_new).

The daily cap counts sends across BOTH queues.
"""
import random
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from config import EMAIL_DRIP_DAILY_CAP
from db.client import supabase
from services import draft_drip
from services import email as email_service

TZ = ZoneInfo("Africa/Johannesburg")
WINDOW_START = dtime(7, 30)
WINDOW_END = dtime(15, 0)
GAP_SECONDS = (180, 540)  # 3 to 9 minutes between sends

_next_send_at: datetime | None = None  # in-process pacing gate


def _now():
    return datetime.now(TZ)


def _in_window(now: datetime) -> bool:
    return WINDOW_START <= now.time() <= WINDOW_END


def sent_today(now: datetime | None = None) -> int:
    """Sends so far today across both queues (draft_queue + email_queue)."""
    now = now or _now()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    total = 0
    for table in ("email_queue", "draft_queue"):
        res = (supabase.table(table)
               .select("id", count="exact")
               .eq("status", "sent")
               .gte("sent_at", day_start.isoformat())
               .execute())
        total += res.count or 0
    return total


def _set_gap(now: datetime, seconds: int | None = None) -> int:
    global _next_send_at
    gap = seconds if seconds is not None else random.randint(*GAP_SECONDS)
    _next_send_at = now + timedelta(seconds=gap)
    return gap


def tick():
    """One scheduler heartbeat: send at most one email, if it's time."""
    now = _now()
    if not _in_window(now):
        return
    if _next_send_at and now < _next_send_at:
        return

    if sent_today(now) >= EMAIL_DRIP_DAILY_CAP:
        return

    # Gmail drafts first (the warm re-engagement list), then the CSV queue.
    draft_row = draft_drip.next_queued()
    if draft_row:
        if draft_drip.send_one(draft_row):
            gap = _set_gap(now)
            print(f"[drip] sent draft -> {draft_row['to_email']} "
                  f"({draft_row['subject'][:50]}), next in {gap // 60}m{gap % 60:02d}s",
                  flush=True)
        else:
            _set_gap(now, 120)
            print(f"[drip] draft FAILED -> {draft_row['to_email']}", flush=True)
        return

    rows = (supabase.table("email_queue")
            .select("*")
            .eq("status", "queued")
            .order("queued_at")
            .limit(1)
            .execute()).data
    if not rows:
        return
    row = rows[0]

    try:
        sent = email_service.send_new(row["to_email"], row["subject"], row["body"])
        supabase.table("email_queue").update({
            "status": "sent",
            "sent_at": now.isoformat(),
            "sent_thread_id": sent.get("thread_id") or "",
        }).eq("id", row["id"]).execute()
        gap = _set_gap(now)
        print(f"[drip] sent -> {row['to_email']} ({row['subject'][:50]}), "
              f"next in {gap // 60}m{gap % 60:02d}s", flush=True)
    except Exception as exc:
        supabase.table("email_queue").update({
            "status": "failed",
            "error": str(exc)[:300],
        }).eq("id", row["id"]).execute()
        _set_gap(now, 120)
        print(f"[drip] FAILED -> {row['to_email']}: {exc}", flush=True)
