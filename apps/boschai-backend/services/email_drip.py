"""
Email drip — sends queued outreach emails one at a time with random gaps.

The scheduler calls tick() every minute. Most ticks do nothing: outside the
07:30-18:30 SAST window it sleeps, and between sends it waits out a random
3-9 minute gap so the pattern never looks like a burst. A hard daily cap
(EMAIL_DRIP_DAILY_CAP, default 25) protects Gmail deliverability.

Queue rows live in Supabase (email_queue, migration 010) and are loaded from
Heinrich's local CRM by scripts/crm_cloud_sync.py. Sending goes through the
same Gmail OAuth connection as the rest of the backend (services.email).
"""
import random
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from config import EMAIL_DRIP_DAILY_CAP
from db.client import supabase
from services import email as email_service

TZ = ZoneInfo("Africa/Johannesburg")
WINDOW_START = dtime(7, 30)
WINDOW_END = dtime(18, 30)
GAP_SECONDS = (180, 540)  # 3 to 9 minutes between sends

_next_send_at: datetime | None = None  # in-process pacing gate


def _now():
    return datetime.now(TZ)


def _in_window(now: datetime) -> bool:
    return WINDOW_START <= now.time() <= WINDOW_END


def _sent_today(now: datetime) -> int:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    res = (supabase.table("email_queue")
           .select("id", count="exact")
           .eq("status", "sent")
           .gte("sent_at", day_start.isoformat())
           .execute())
    return res.count or 0


def tick():
    """One scheduler heartbeat: send at most one email, if it's time."""
    global _next_send_at
    now = _now()
    if not _in_window(now):
        return
    if _next_send_at and now < _next_send_at:
        return

    if _sent_today(now) >= EMAIL_DRIP_DAILY_CAP:
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
        email_service.send_new(row["to_email"], row["subject"], row["body"])
        supabase.table("email_queue").update({
            "status": "sent",
            "sent_at": now.isoformat(),
        }).eq("id", row["id"]).execute()
        gap = random.randint(*GAP_SECONDS)
        _next_send_at = now + timedelta(seconds=gap)
        print(f"[drip] sent -> {row['to_email']} ({row['subject'][:50]}), "
              f"next in {gap // 60}m{gap % 60:02d}s", flush=True)
    except Exception as exc:
        supabase.table("email_queue").update({
            "status": "failed",
            "error": str(exc)[:300],
        }).eq("id", row["id"]).execute()
        _next_send_at = now + timedelta(seconds=120)
        print(f"[drip] FAILED -> {row['to_email']}: {exc}", flush=True)
