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
        pipeline = cs.pipeline_summary()
    except Exception:
        pipeline = {"counts": {}, "anchor": 0, "clients": []}
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
        "new_events": new_events,
    }


def _stats_block(d: dict, html: bool = True) -> str:
    """The five at-a-glance numbers, one per line. `html` bolds the counts for Telegram."""
    def n(x) -> str:
        return f"<b>{x}</b>" if html else str(x)
    rows = [
        f"📥 Emails received: {n(len(d['received']))}",
        f"✉️ Awaiting reply: {n(len(d['outstanding']))}",
        f"📝 Drafts ready: {n(len(d['drafts']))}",
        f"📅 Meetings today: {n(len(d['meetings']))}",
        f"⏳ Sign-offs pending: {n(len(d['waiting']))}",
    ]
    counts = d.get("pipeline", {}).get("counts", {})
    if counts:
        rows.append(f"🏢 Clients: {n(counts.get('anchor', 0))} anchor · {n(counts.get('pipeline', 0))} pipeline")
    return "\n".join(rows)


def _facts(d: dict) -> str:
    """The raw situation handed to Claude so it can narrate what's going on today."""
    base = (
        f"Date: {datetime.now().strftime('%A %d %B')}\n"
        f"Real emails received today: {len(d['received'])}"
        f" (from: {', '.join(_name(e['from']) for e in d['received'][:5]) or 'none'})\n"
        f"Emails still awaiting her reply: {len(d['outstanding'])}"
        f" (subjects: {'; '.join(e['subject'] for e in d['outstanding'][:5]) or 'none'})\n"
        f"Draft replies waiting in her Gmail Drafts: {len(d['drafts'])}\n"
        f"Sign-offs where the person just replied (handoffs received): {len(d['replied'])}"
        f" ({'; '.join(s['waiting_on'] for s in d['replied']) or 'none'})\n"
        f"Sign-offs still outstanding (waiting on others): {len(d['waiting'])}"
        f" ({'; '.join(s['waiting_on'] for s in d['waiting']) or 'none'})\n"
        f"Meetings today: {len(d['meetings'])}"
        f" ({'; '.join(m['time'] + ' ' + m['title'] + (' with ' + ', '.join(m['with']) if m['with'] else '') for m in d['meetings'][:6]) or 'none'})"
    )

    pipeline = d.get("pipeline", {})
    clients = pipeline.get("clients", [])
    if clients:
        counts = pipeline.get("counts", {})
        count_str = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
        roster = "; ".join(
            f"{c['name']} [{c.get('pipeline_stage', 'pipeline')}]"
            + (f", next: {c['next_step']}" if c.get("next_step") else "")
            for c in clients[:10]
        )
        base += f"\nClient pipeline ({count_str}): {roster}"

    events = d.get("new_events", [])
    if events:
        base += "\nBusiness changes in the last day: " + "; ".join(e["summary"] for e in events[:8])

    return base


def write_paragraph(d: dict) -> str:
    """One short paragraph on what's actually going on today (the counts are shown separately)."""
    prompt = (
        _facts(d)
        + "\n\nThe numbers above are ALREADY shown to Heinrich as a stats list, so do NOT repeat the counts. "
        "Write a SHORT paragraph (max ~70 words) telling him what's actually going on today: who emailed and "
        "what they want, what needs his attention first, any sign-off that just came back, any new client or "
        "pipeline change worth noting, and meetings to prep for. Direct and second person ('You have…', "
        "'Thabo is waiting on…'). No headings, no bullet points, no "
        "greeting. Mention only what matters today — skip anything quiet or zero. If it's genuinely a quiet day, "
        "say so in one line."
    )
    resp = client.messages.create(model=MODEL, max_tokens=300, messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def build_brief() -> str:
    """Plain-text preview of the full brief (stats + paragraph), used by GET /daily-brief."""
    d = gather()
    return _stats_block(d, html=False) + "\n\n" + write_paragraph(d)


def send_daily_brief() -> dict:
    d = gather()
    header = "📊 <b>Daily Brief</b> · " + datetime.now().strftime("%a %d %b")
    stats = _stats_block(d, html=True)
    paragraph = write_paragraph(d)
    send_telegram(f"{header}\n\n{stats}\n\n{escape(paragraph)}")
    return {"sent": True, "brief": paragraph, "stats": _stats_block(d, html=False)}
