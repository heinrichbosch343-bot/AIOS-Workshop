"""
Email auto-follow-up engine — scans Heinrich's sent threads for no-reply
conversations past a configurable delay, drafts (or sends) a follow-up with
hard guardrails: recipient allowlist, daily cap, kill switch, and warmup
(draft-only) mode.

All follow-up state lives in the Supabase `followups` table (003_followups.sql).
Called by the scheduler on a recurring basis and surfaced via Telegram commands.
"""
import base64
import json
import re
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

import anthropic

from config import ANTHROPIC_API_KEY
from core.prime import build_system_prompt
from core.writing_style import writing_style_block
from db.client import supabase
from services import email as email_service
from services.notify import send_telegram

# ---------------------------------------------------------------------------
# Configuration — all values read from config.py (populated from .env)
# ---------------------------------------------------------------------------

def _cfg():
    """Late import to avoid circular import at module level."""
    from config import (
        FOLLOWUP_ENABLED,
        FOLLOWUP_ALLOWLIST,
        FOLLOWUP_DELAY_DAYS,
        FOLLOWUP_DAILY_CAP,
        FOLLOWUP_KILL_SWITCH,
        FOLLOWUP_WARMUP,
        FOLLOWUP_MAX_ATTEMPTS,
    )
    return {
        "enabled": FOLLOWUP_ENABLED,
        "allowlist": FOLLOWUP_ALLOWLIST,
        "delay_days": FOLLOWUP_DELAY_DAYS,
        "daily_cap": FOLLOWUP_DAILY_CAP,
        "kill_switch": FOLLOWUP_KILL_SWITCH,
        "warmup": FOLLOWUP_WARMUP,
        "max_attempts": FOLLOWUP_MAX_ATTEMPTS,
    }


# ---------------------------------------------------------------------------
# AI drafting
# ---------------------------------------------------------------------------

_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_MODEL = "claude-sonnet-4-6"

_FOLLOWUP_INSTRUCTIONS = """You are writing a follow-up email for Heinrich Bosch (BoschAI).

The original email was sent by Heinrich and the recipient has not replied after several days.
Write a SHORT, warm, professional follow-up that:
- References the original subject/context naturally
- Is NOT pushy or desperate — just a gentle nudge
- Asks if they had a chance to look at it, or if there's anything they need
- Keeps Heinrich's voice: sharp, direct, concise
- Signed "Heinrich Bosch"
- 2-4 sentences max

Do NOT invent facts, dates, figures, or commitments. If a detail is needed,
leave a [bracketed placeholder].

Respond with ONLY a JSON object:
{"followup_body": "<the follow-up email text>"}"""


def _compose_followup(original_subject: str, original_body: str,
                      contact_name: str, attempt: int) -> str | None:
    """Use Claude to draft a follow-up email. Returns the body text or None."""
    attempt_label = "first" if attempt <= 1 else f"follow-up #{attempt}"
    user_block = (
        f"Original subject: {original_subject}\n"
        f"Recipient: {contact_name}\n"
        f"This is the {attempt_label} follow-up.\n\n"
        f"Original email body (truncated):\n{(original_body or '')[:3000]}"
    )
    try:
        resp = _ai.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=_FOLLOWUP_INSTRUCTIONS,
            messages=[{"role": "user", "content": user_block}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        data = json.loads(text)
        return data.get("followup_body", "").strip() or None
    except Exception as e:
        print(f"[followup] compose failed: {e}", flush=True)
        return None


# ---------------------------------------------------------------------------
# Allowlist matching
# ---------------------------------------------------------------------------

def _matches_allowlist(email_addr: str, allowlist: list[str]) -> bool:
    """Check if an email address matches any entry in the allowlist.
    Entries can be full addresses (user@example.com) or domains (@example.com).
    """
    if not allowlist:
        return False
    addr = _extract_email(email_addr)
    for entry in allowlist:
        entry = entry.lower().strip()
        if not entry:
            continue
        if entry.startswith("@"):
            # Domain match
            if addr.endswith(entry):
                return True
        else:
            # Exact address match
            if addr == entry:
                return True
    return False


def _extract_email(from_value: str) -> str:
    """Extract bare email address from 'Name <addr>' or plain 'addr'."""
    match = re.search(r"<([^>]+)>", from_value)
    return match.group(1).lower().strip() if match else from_value.lower().strip()


def _extract_name(from_value: str) -> str:
    """Extract display name from 'Name <addr>', or return the address."""
    match = re.match(r'^"?([^"<]+)"?\s*<', from_value)
    return match.group(1).strip() if match else from_value.strip()


# ---------------------------------------------------------------------------
# Gmail helpers
# ---------------------------------------------------------------------------

def _get_sent_threads(max_results: int = 30, since_days: int = 14) -> list[dict]:
    """Fetch recent sent messages to scan for threads needing follow-up.
    Returns messages Heinrich sent that are to real people (not automated).
    """
    from services.email import _gmail, _header, _extract_body

    gmail = _gmail()
    # Only look at sent mail from the last N days
    after_date = (datetime.now() - timedelta(days=since_days)).strftime("%Y/%m/%d")
    q = f"in:sent after:{after_date}"

    listing = gmail.users().messages().list(
        userId="me", q=q, maxResults=max_results * 2,
    ).execute()

    results = []
    seen_threads = set()

    for ref in listing.get("messages", []):
        msg = gmail.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
        ).execute()

        thread_id = msg.get("threadId")
        if thread_id in seen_threads:
            continue
        seen_threads.add(thread_id)

        headers = msg.get("payload", {}).get("headers", [])
        to_value = _header(headers, "To")
        subject = _header(headers, "Subject") or "(no subject)"
        sent_ms = int(msg.get("internalDate", "0") or "0")

        results.append({
            "id": msg["id"],
            "thread_id": thread_id,
            "to": to_value,
            "subject": subject,
            "sent_at": datetime.fromtimestamp(sent_ms / 1000, tz=timezone.utc),
        })

        if len(results) >= max_results:
            break

    return results


def _build_followup_mime(to_addr: str, subject: str, body: str,
                        message_id: str | None, references: str | None) -> str:
    """Build raw MIME for a follow-up, correctly addressed to the contact (not self).

    Unlike email.py's _build_reply (which replies to original["from"]), this targets
    `to_addr` explicitly so follow-ups to SENT messages go to the recipient, not back
    to Heinrich.
    """
    body = email_service._sanitize_outgoing(body)
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    mime = MIMEText(body)
    mime["To"] = to_addr
    mime["Subject"] = subject
    if message_id:
        mime["In-Reply-To"] = message_id
        mime["References"] = (references + " " + message_id).strip() if references else message_id

    return base64.urlsafe_b64encode(mime.as_bytes()).decode()


def _send_followup_reply(to_addr: str, subject: str, body: str,
                         thread_id: str, message_id: str | None,
                         references: str | None) -> dict:
    """Send a follow-up reply to the contact, threaded in the original conversation."""
    raw = _build_followup_mime(to_addr, subject, body, message_id, references)
    sent = email_service._gmail().users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id},
    ).execute()
    return {"sent_id": sent.get("id"), "thread_id": sent.get("threadId"), "to": to_addr}


def _draft_followup_reply(to_addr: str, subject: str, body: str,
                          thread_id: str, message_id: str | None,
                          references: str | None) -> dict:
    """Save a follow-up as a Gmail draft, threaded in the original conversation."""
    raw = _build_followup_mime(to_addr, subject, body, message_id, references)
    draft = email_service._gmail().users().drafts().create(
        userId="me",
        body={"message": {"raw": raw, "threadId": thread_id}},
    ).execute()
    return {"draft_id": draft.get("id"), "thread_id": thread_id, "to": to_addr}


def _thread_has_reply(thread_id: str, after_ms: int) -> bool:
    """Check if someone (not Heinrich) replied in this thread after the given timestamp."""
    from services.email import _gmail

    gmail = _gmail()
    try:
        thread = gmail.users().threads().get(
            userId="me", id=thread_id, format="minimal",
        ).execute()
    except Exception:
        return True  # If we can't check, assume replied (safe default)

    for m in thread.get("messages", []):
        msg_ms = int(m.get("internalDate", "0") or "0")
        labels = m.get("labelIds", [])
        # A message in INBOX (not SENT) after our send = someone replied
        if msg_ms > after_ms and "SENT" not in labels and "INBOX" in labels:
            return True
    return False


# ---------------------------------------------------------------------------
# Supabase operations
# ---------------------------------------------------------------------------

def _get_tracked(thread_id: str) -> dict | None:
    """Get existing followup record for a thread."""
    resp = supabase.table("followups").select("*").eq(
        "thread_id", thread_id
    ).execute()
    rows = resp.data or []
    return rows[0] if rows else None


def _upsert_followup(thread_id: str, message_id: str, contact_email: str,
                     contact_name: str, subject: str, sent_at: datetime,
                     status: str = "pending", attempt_count: int = 0,
                     last_followup_at: datetime | None = None) -> dict:
    """Insert or update a followup record."""
    row = {
        "thread_id": thread_id,
        "message_id": message_id,
        "contact_email": contact_email,
        "contact_name": contact_name,
        "subject": subject,
        "original_sent_at": sent_at.isoformat(),
        "status": status,
        "attempt_count": attempt_count,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if last_followup_at:
        row["last_followup_at"] = last_followup_at.isoformat()

    existing = _get_tracked(thread_id)
    if existing:
        resp = supabase.table("followups").update(row).eq(
            "id", existing["id"]
        ).execute()
    else:
        row["created_at"] = datetime.now(timezone.utc).isoformat()
        resp = supabase.table("followups").insert(row).execute()

    return (resp.data or [{}])[0]


def _today_send_count() -> int:
    """Count how many follow-ups were sent/drafted today."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    resp = supabase.table("followups").select("id", count="exact").gte(
        "last_followup_at", today_start
    ).in_("status", ["sent", "drafted"]).execute()
    return resp.count or 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pending() -> list[dict]:
    """List all pending follow-ups (for the /followups command)."""
    resp = supabase.table("followups").select("*").eq(
        "status", "pending"
    ).order("original_sent_at", desc=True).execute()
    return resp.data or []


def get_status_summary() -> dict:
    """Summary for the /followups Telegram command."""
    pending = get_pending()
    today_count = _today_send_count()
    cfg = _cfg()
    return {
        "pending_count": len(pending),
        "pending": pending,
        "today_sent": today_count,
        "daily_cap": cfg["daily_cap"],
        "warmup": cfg["warmup"],
        "kill_switch": cfg["kill_switch"],
        "enabled": cfg["enabled"],
    }


def set_kill_switch(on: bool) -> bool:
    """Toggle the kill switch. Returns the new state.
    Note: This sets the runtime state. For persistence across restarts,
    the env var FOLLOWUP_KILL_SWITCH should be updated.
    """
    import config
    config.FOLLOWUP_KILL_SWITCH = on
    return on


def stop_thread(thread_id: str) -> dict | None:
    """Manually stop following up on a thread."""
    existing = _get_tracked(thread_id)
    if not existing:
        return None
    resp = supabase.table("followups").update({
        "status": "stopped",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", existing["id"]).execute()
    return (resp.data or [{}])[0]


def run() -> dict:
    """Main entry point — called by the scheduler.

    1. Check guards (enabled, kill switch)
    2. Scan sent threads for no-reply past the delay
    3. For each eligible thread: draft or send a follow-up
    4. Return a summary of actions taken
    """
    cfg = _cfg()

    # Guard: master switch
    if not cfg["enabled"]:
        return {"skipped": True, "reason": "followup disabled"}

    # Guard: kill switch
    if cfg["kill_switch"]:
        return {"skipped": True, "reason": "kill switch engaged"}

    delay_days = cfg["delay_days"]
    daily_cap = cfg["daily_cap"]
    allowlist = cfg["allowlist"]
    warmup = cfg["warmup"]
    max_attempts = cfg["max_attempts"]

    # How many have we already sent/drafted today?
    today_count = _today_send_count()
    remaining_budget = max(0, daily_cap - today_count)

    if remaining_budget <= 0:
        return {"skipped": True, "reason": f"daily cap reached ({daily_cap})"}

    # Scan sent threads
    cutoff = datetime.now(timezone.utc) - timedelta(days=delay_days)
    sent_threads = _get_sent_threads(max_results=40, since_days=delay_days + 7)

    actions = []
    skipped = []

    for thread in sent_threads:
        if remaining_budget <= 0:
            break

        contact_email = _extract_email(thread["to"])
        contact_name = _extract_name(thread["to"])
        thread_id = thread["thread_id"]
        sent_at = thread["sent_at"]

        # Only consider threads old enough
        if sent_at > cutoff:
            continue

        # Check allowlist
        if not _matches_allowlist(contact_email, allowlist):
            skipped.append({
                "thread_id": thread_id,
                "contact": contact_email,
                "reason": "not on allowlist",
            })
            continue

        # Check if already replied
        sent_ms = int(sent_at.timestamp() * 1000)
        if _thread_has_reply(thread_id, sent_ms):
            # Mark as replied if we were tracking it
            existing = _get_tracked(thread_id)
            if existing and existing["status"] == "pending":
                _upsert_followup(
                    thread_id=thread_id,
                    message_id=existing["message_id"],
                    contact_email=contact_email,
                    contact_name=contact_name,
                    subject=thread["subject"],
                    sent_at=sent_at,
                    status="replied",
                    attempt_count=existing.get("attempt_count", 0),
                )
            continue

        # Check existing tracking record
        existing = _get_tracked(thread_id)
        current_attempts = existing["attempt_count"] if existing else 0

        if current_attempts >= max_attempts:
            if existing and existing["status"] != "stopped":
                _upsert_followup(
                    thread_id=thread_id,
                    message_id=existing["message_id"],
                    contact_email=contact_email,
                    contact_name=contact_name,
                    subject=thread["subject"],
                    sent_at=sent_at,
                    status="stopped",
                    attempt_count=current_attempts,
                )
            skipped.append({
                "thread_id": thread_id,
                "contact": contact_email,
                "reason": f"max attempts ({max_attempts}) reached",
            })
            continue

        if existing and existing["status"] in ("stopped", "replied", "drafted", "sent"):
            # "drafted"/"sent" with last_followup_at today = already acted on this run cycle
            # "stopped"/"replied" = terminal states, skip always
            if existing["status"] in ("stopped", "replied"):
                continue
            # For "drafted"/"sent", only skip if already acted on today
            if existing.get("last_followup_at"):
                last_fu = datetime.fromisoformat(existing["last_followup_at"])
                if last_fu.tzinfo is None:
                    last_fu = last_fu.replace(tzinfo=timezone.utc)
                if last_fu.date() >= datetime.now(timezone.utc).date():
                    continue

        # If there was a previous follow-up, check delay from THAT one too
        if existing and existing.get("last_followup_at"):
            last_fu = datetime.fromisoformat(existing["last_followup_at"])
            if last_fu.tzinfo is None:
                last_fu = last_fu.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - last_fu < timedelta(days=delay_days):
                continue

        # Read the original email to get body + threading headers
        try:
            original = email_service.get_message(thread["id"])
        except Exception as e:
            skipped.append({
                "thread_id": thread_id,
                "contact": contact_email,
                "reason": f"could not read original: {e}",
            })
            continue

        # Compose the follow-up
        body = _compose_followup(
            original_subject=thread["subject"],
            original_body=original.get("body", ""),
            contact_name=contact_name,
            attempt=current_attempts + 1,
        )

        if not body:
            skipped.append({
                "thread_id": thread_id,
                "contact": contact_email,
                "reason": "AI could not compose follow-up",
            })
            continue

        # Gate: warmup = draft only, live = actually send
        # Use our own MIME builder that addresses the CONTACT, not Heinrich.
        now = datetime.now(timezone.utc)
        new_attempt = current_attempts + 1
        orig_message_id = original.get("message_id")
        orig_references = original.get("references")

        if warmup:
            try:
                result = _draft_followup_reply(
                    to_addr=contact_email,
                    subject=thread["subject"],
                    body=body,
                    thread_id=thread_id,
                    message_id=orig_message_id,
                    references=orig_references,
                )
                status = "drafted"
                actions.append({
                    "thread_id": thread_id,
                    "contact": contact_email,
                    "subject": thread["subject"],
                    "action": "drafted",
                    "draft_id": result.get("draft_id"),
                    "attempt": new_attempt,
                })
            except Exception as e:
                skipped.append({
                    "thread_id": thread_id,
                    "contact": contact_email,
                    "reason": f"draft failed: {e}",
                })
                continue
        else:
            try:
                result = _send_followup_reply(
                    to_addr=contact_email,
                    subject=thread["subject"],
                    body=body,
                    thread_id=thread_id,
                    message_id=orig_message_id,
                    references=orig_references,
                )
                status = "sent"
                actions.append({
                    "thread_id": thread_id,
                    "contact": contact_email,
                    "subject": thread["subject"],
                    "action": "sent",
                    "sent_id": result.get("sent_id"),
                    "attempt": new_attempt,
                })
            except Exception as e:
                skipped.append({
                    "thread_id": thread_id,
                    "contact": contact_email,
                    "reason": f"send failed: {e}",
                })
                continue

        # Record in DB
        _upsert_followup(
            thread_id=thread_id,
            message_id=thread["id"],
            contact_email=contact_email,
            contact_name=contact_name,
            subject=thread["subject"],
            sent_at=sent_at,
            status=status,
            attempt_count=new_attempt,
            last_followup_at=now,
        )

        remaining_budget -= 1

    # Notify Heinrich if any actions were taken
    if actions:
        mode = "WARMUP (drafts only)" if warmup else "LIVE"
        lines = [f"Follow-up engine [{mode}] — {len(actions)} action(s):"]
        for a in actions:
            lines.append(f"  {a['action'].upper()}: {a['contact']} — {a['subject']}")
        try:
            send_telegram("\n".join(lines))
        except Exception:
            pass  # Don't let notification failure break the engine

    return {
        "scanned": len(sent_threads),
        "actions": len(actions),
        "details": actions,
        "skipped": skipped,
        "today_total": today_count + len(actions),
        "daily_cap": daily_cap,
        "warmup": warmup,
    }
