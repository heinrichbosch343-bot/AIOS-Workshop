"""
Daily Brief — a short, one-paragraph morning summary for Heinrich, sent to Telegram.

Pulls live data from what's connected: today's real emails, the ones still awaiting
his reply, drafts waiting in Gmail, and sign-offs (waiting on + replies just received).
Synthesises ONE tight paragraph with Claude Haiku and pushes it to Telegram.

Run on a morning schedule (Railway) or on-demand via POST /daily-brief.
"""
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

import anthropic
from googleapiclient.discovery import build as gbuild

from config import ANTHROPIC_API_KEY, TELEGRAM_BRIEF_CHAT_ID, TELEGRAM_BRIEF_TOPIC_ID
from db.client import supabase
from services import context_store as cs
from services import email as email_service
from services.drive import get_credentials
from services.notify import send_telegram

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-haiku-4-5-20251001"
SAST = ZoneInfo("Africa/Johannesburg")

_TODAY_Q = "in:inbox category:primary newer_than:2d"
# Clients with work in motion (not raw leads, not lost) belong in Builds & deadlines.
_BUILD_STAGES = {"won", "meeting_booked", "proposal", "follow_up_meeting", "contact_again"}


def _today_start_iso() -> str:
    """Start of today in SAST, as a UTC ISO string — for 'today' DB filters."""
    start = datetime.now(SAST).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).isoformat()


def _count_campaign_replies_today() -> int:
    """Total inbound replies that landed in the campaign accounts today (any category)."""
    try:
        return supabase.table("campaign_replies").select("id", count="exact") \
            .gte("replied_at", _today_start_iso()).execute().count or 0
    except Exception:
        return 0


def _new_leads_today() -> int:
    """New interested leads today, from BOTH sources:
      - campaign replies classified 'interested'
      - clients newly added to the pipeline (covers leads off Heinrich's personal email)."""
    interested = 0
    try:
        interested = supabase.table("campaign_replies").select("id", count="exact") \
            .eq("category", "interested").gte("replied_at", _today_start_iso()).execute().count or 0
    except Exception:
        interested = 0
    added = 0
    try:
        since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        added = supabase.table("business_events").select("id", count="exact") \
            .eq("event_type", "client_added").gte("created_at", since).execute().count or 0
    except Exception:
        added = 0
    return interested + added


def _builds() -> list[dict]:
    """Active client builds — what's being built for whom, with an optional deadline.
    Pulled straight from client records; soonest deadline first, undated builds last."""
    try:
        rows = supabase.table("clients") \
            .select("name, pipeline_stage, next_step, deadline, active").execute().data
    except Exception:
        # 'deadline' column not migrated yet — fall back to records without it.
        try:
            rows = supabase.table("clients") \
                .select("name, pipeline_stage, next_step, active").execute().data
        except Exception:
            return []
    builds = [
        r for r in rows
        if (r.get("pipeline_stage") in _BUILD_STAGES or r.get("active"))
        and (r.get("next_step") or r.get("deadline"))
    ]
    builds.sort(key=lambda r: (r.get("deadline") is None, r.get("deadline") or ""))
    return builds[:8]


def _name(addr: str) -> str:
    import re
    m = re.match(r'^\s*"?([^"<]+?)"?\s*<', addr or "")
    return m.group(1).strip() if m else (addr or "").split("@")[0]


def gather() -> dict:
    """Collect the facts for the brief. Each source fails soft to empty."""
    try:
        received = email_service.list_inbox(max_results=10, q=_TODAY_Q, people_only=True, today_only=True)
    except Exception:
        received = []
    try:
        outstanding = email_service.list_inbox(
            max_results=10, q=_TODAY_Q, people_only=True, today_only=True, exclude_replied=True
        )
    except Exception:
        outstanding = []
    try:
        gmail = gbuild("gmail", "v1", credentials=get_credentials())
        drafts = gmail.users().drafts().list(userId="me").execute().get("drafts", [])
    except Exception:
        drafts = []
    try:
        open_sos = supabase.table("signoffs").select("*").is_("resolved_at", "null").execute().data
    except Exception:
        open_sos = []
    try:
        from services import calendar as calendar_service
        meetings = calendar_service.today_events()
    except Exception:
        meetings = []
    try:
        from services.pipeline import pipeline_brief_block, check_nudges
        pipeline = cs.pipeline_summary()
        pipeline_text = pipeline_brief_block()
        pipeline_nudges = check_nudges()
    except Exception:
        pipeline = {"counts": {}, "won": 0, "clients": []}
        pipeline_text = ""
        pipeline_nudges = []
    try:
        since_iso = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        new_events = cs.recent_events(limit=8, since=since_iso)
    except Exception:
        new_events = []

    replied = [s for s in open_sos if s.get("reply_detected_at")]
    waiting = [s for s in open_sos if not s.get("reply_detected_at")]
    return {
        "received": received,
        "outstanding": outstanding,
        "drafts": drafts,
        "replied": replied,
        "waiting": waiting,
        "meetings": meetings,
        "pipeline": pipeline,
        "pipeline_text": pipeline_text,
        "pipeline_nudges": pipeline_nudges,
        "new_events": new_events,
        "campaign_replies": _count_campaign_replies_today(),
        "new_leads": _new_leads_today(),
        "builds": _builds(),
    }


def _scoreboard_block(d: dict, html: bool = True) -> str:
    """The morning scoreboard — four fixed lines, always shown (a 0 is informative too).
    Inbox = personal Gmail today; Campaign replies = inbound to the outreach accounts;
    New leads = interested replies + leads added; Meetings = today's calendar count."""
    def n(x) -> str:
        return f"<b>{x}</b>" if html else str(x)

    return "\n".join([
        f"📥 Inbox: {n(len(d['received']))}",
        f"📨 Campaign replies: {n(d.get('campaign_replies', 0))}",
        f"🌱 New leads: {n(d.get('new_leads', 0))}",
        f"📅 Meetings today: {n(len(d['meetings']))}",
    ])


def _nudges_block(d: dict, html: bool = True) -> str:
    """Where to follow up — one bullet per nudge-worthy lead. Empty string if none."""
    nudges = d.get("pipeline_nudges", [])
    if not nudges:
        return ""
    head = "🔔 <b>Nudges:</b>" if html else "🔔 Nudges:"
    lines = [head]
    for nud in nudges[:6]:
        msg = nud.get("message", "")
        lines.append(f"• {escape(msg, quote=False) if html else msg}")
    return "\n".join(lines)


def _builds_block(d: dict, html: bool = True) -> str:
    """What's being built for which client, with deadlines. Empty string if none."""
    builds = d.get("builds", [])
    if not builds:
        return ""
    head = "🏗 <b>Builds &amp; deadlines:</b>" if html else "🏗 Builds & deadlines:"
    lines = [head]
    for b in builds:
        what = b.get("next_step") or "in progress"
        line = f"• {b['name']} — {what}"
        if b.get("deadline"):
            line += f" · due {b['deadline']}"
        lines.append(escape(line, quote=False) if html else line)
    return "\n".join(lines)


def _meetings_block(d: dict, html: bool = True) -> str:
    """Today's meetings, listed out (time, title, who + their email). Empty if none."""
    meetings = d.get("meetings", [])
    if not meetings:
        return ""
    head = "📅 <b>Today's meetings:</b>" if html else "📅 Today's meetings:"
    lines = [head]
    for m in meetings:
        time = m.get("time", "")
        title = m.get("title", "(no title)")
        who = ", ".join(m.get("with", []) or [])
        emails = ", ".join(m.get("emails", []) or [])
        line = f"• {time}  {title}".strip()
        if who:
            line += f" — {who}"
        if emails:
            line += f" ({emails})"
        lines.append(escape(line, quote=False) if html else line)
    return "\n".join(lines)


def _facts(d: dict) -> str:
    """The raw situation handed to Claude so it can narrate what's going on today."""
    base = (
        f"Date: {datetime.now().strftime('%A %d %B')}\n"
        f"Real emails received today: {len(d['received'])}"
        f" (from: {', '.join(_name(e['from']) for e in d['received'][:5]) or 'none'})\n"
        f"Emails still awaiting his reply: {len(d['outstanding'])}"
        f" (subjects: {'; '.join(e['subject'] for e in d['outstanding'][:5]) or 'none'})\n"
        f"Draft replies waiting in his Gmail Drafts: {len(d['drafts'])}\n"
        f"Sign-offs where the person just replied (handoffs received): {len(d['replied'])}"
        f" ({'; '.join(s['waiting_on'] for s in d['replied']) or 'none'})\n"
        f"Sign-offs still outstanding (waiting on others): {len(d['waiting'])}"
        f" ({'; '.join(s['waiting_on'] for s in d['waiting']) or 'none'})\n"
        f"Meetings today: {len(d['meetings'])}"
        f" ({'; '.join(m['time'] + ' ' + m['title'] + (' with ' + ', '.join(m['with']) if m['with'] else '') for m in d['meetings'][:6]) or 'none'})"
    )

    pipeline_text = d.get("pipeline_text", "")
    if pipeline_text:
        base += f"\n{pipeline_text}"
    else:
        pipeline = d.get("pipeline", {})
        clients = pipeline.get("clients", [])
        if clients:
            counts = pipeline.get("counts", {})
            count_str = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
            roster = "; ".join(
                f"{c['name']} [{c.get('pipeline_stage', 'interested')}]"
                + (f", next: {c['next_step']}" if c.get("next_step") else "")
                for c in clients[:10]
            )
            base += f"\nClient pipeline ({count_str}): {roster}"

    events = d.get("new_events", [])
    if events:
        base += "\nBusiness changes in the last day: " + "; ".join(e["summary"] for e in events[:8])

    return base


def write_focus(d: dict) -> str:
    """A short, prioritised to-do list for the day (stats + meetings are shown separately)."""
    prompt = (
        _facts(d)
        + "\n\nThe stats and the meeting list are ALREADY shown to Heinrich above, so do NOT repeat the raw "
        "counts or re-list the meeting times. Write his TO-DO for today: the 2 to 4 most important things he "
        "should actually DO, most important first, as short bullet lines each starting with '• '. Base them on "
        "what needs action — emails awaiting his reply, drafts to clear, sign-offs to chase, client next steps, "
        "and prepping for any meeting above. Each bullet is action-first and max ~12 words "
        "(e.g. '• Reply to Renier about scheduling', '• Push Osun for final sign-off', '• Prep for the 14:00 "
        "call'). No intro line, no headings, no fluff. If there's genuinely nothing to do, write a single line: "
        "'Quiet day — nothing urgent.'"
    )
    resp = client.messages.create(model=MODEL, max_tokens=200, messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def build_brief() -> str:
    """Plain-text preview of the full brief, used by GET /daily-brief.
    Structure: scoreboard → meetings → nudges → today's focus → builds & deadlines."""
    d = gather()
    parts = [_scoreboard_block(d, html=False)]
    for block in (_meetings_block(d, html=False), _nudges_block(d, html=False)):
        if block:
            parts.append(block)
    parts.append("🎯 Today's focus:\n" + write_focus(d))
    builds = _builds_block(d, html=False)
    if builds:
        parts.append(builds)
    return "\n\n".join(parts)


def send_daily_brief() -> dict:
    d = gather()
    header = "📊 <b>Daily Brief</b> · " + datetime.now(SAST).strftime("%a %d %b")
    parts = [header, _scoreboard_block(d, html=True)]
    for block in (_meetings_block(d, html=True), _nudges_block(d, html=True)):
        if block:
            parts.append(block)
    focus = write_focus(d)
    parts.append("🎯 <b>Today's focus:</b>\n" + escape(focus, quote=False))
    builds = _builds_block(d, html=True)
    if builds:
        parts.append(builds)
    send_telegram(
        "\n\n".join(parts),
        chat_id=TELEGRAM_BRIEF_CHAT_ID,
        message_thread_id=TELEGRAM_BRIEF_TOPIC_ID,
    )
    return {"sent": True, "brief": focus}
