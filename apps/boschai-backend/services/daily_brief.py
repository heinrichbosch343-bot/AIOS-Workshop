"""
Daily Brief — a short, one-paragraph morning summary for Heinrich, sent to Telegram.

Pulls live data from what's connected: today's real emails, the ones still awaiting
his reply, drafts waiting in Gmail, and sign-offs (waiting on + replies just received).
Synthesises ONE tight paragraph with Claude Haiku and pushes it to Telegram.

Run on a morning schedule (Railway) or on-demand via POST /daily-brief.
"""
from datetime import datetime, timedelta, timezone
from html import escape

import anthropic
from googleapiclient.discovery import build as gbuild

from config import ANTHROPIC_API_KEY
from db.client import supabase
from services import context_store as cs
from services import email as email_service
from services.drive import get_credentials
from services.notify import send_telegram

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-haiku-4-5-20251001"

_TODAY_Q = "in:inbox category:primary newer_than:2d"


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
    }


def _stats_block(d: dict, html: bool = True) -> str:
    """At-a-glance numbers, one per line — but only the lines that matter today.
    Any stat that's zero/quiet is skipped, so a slow day stays short and a busy day
    shows up to six lines. `html` bolds the counts for Telegram."""
    def n(x) -> str:
        return f"<b>{x}</b>" if html else str(x)

    rows = []
    if len(d["received"]):
        rows.append(f"📥 Emails received: {n(len(d['received']))}")
    if len(d["outstanding"]):
        rows.append(f"✉️ Awaiting reply: {n(len(d['outstanding']))}")
    if len(d["drafts"]):
        rows.append(f"📝 Drafts ready: {n(len(d['drafts']))}")
    if len(d["waiting"]):
        rows.append(f"⏳ Sign-offs pending: {n(len(d['waiting']))}")
    counts = d.get("pipeline", {}).get("counts", {})
    active_count = sum(v for k, v in counts.items() if k not in ("won", "lost"))
    won_count = counts.get("won", 0)
    if active_count or won_count:
        rows.append(f"📊 Pipeline: {n(active_count)} active · {n(won_count)} won")
    nudges = d.get("pipeline_nudges", [])
    if nudges:
        rows.append(f"🔔 Nudges: {n(len(nudges))} leads need attention")

    # Fallback so the block is never empty on a genuinely quiet morning.
    if not rows:
        rows.append("📥 Nothing new — quiet morning.")
    return "\n".join(rows)


def _meetings_block(d: dict, html: bool = True) -> str:
    """Today's meetings, listed out (time, title, who). Empty string if none."""
    meetings = d.get("meetings", [])
    if not meetings:
        return ""
    head = "📅 <b>Today's meetings:</b>" if html else "📅 Today's meetings:"
    lines = [head]
    for m in meetings:
        time = m.get("time", "")
        title = m.get("title", "(no title)")
        who = ", ".join(m.get("with", []) or [])
        line = f"• {time} {title}".strip()
        if who:
            line += f" — with {who}"
        lines.append(escape(line) if html else line)
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
    """Plain-text preview of the full brief (stats + meetings + to-do), used by GET /daily-brief."""
    d = gather()
    parts = [_stats_block(d, html=False)]
    meetings = _meetings_block(d, html=False)
    if meetings:
        parts.append(meetings)
    parts.append("🎯 Today's focus:\n" + write_focus(d))
    return "\n\n".join(parts)


def send_daily_brief() -> dict:
    d = gather()
    header = "📊 <b>Daily Brief</b> · " + datetime.now().strftime("%a %d %b")
    parts = [header, _stats_block(d, html=True)]
    meetings = _meetings_block(d, html=True)
    if meetings:
        parts.append(meetings)
    focus = write_focus(d)
    parts.append("🎯 <b>Today's focus:</b>\n" + escape(focus))
    send_telegram("\n\n".join(parts))
    return {"sent": True, "brief": focus, "stats": _stats_block(d, html=False)}
