"""
Campaign auto-responder — monitors 5-10 outreach email accounts and replies
to inbound prospect responses within minutes, in Heinrich's voice.

Provider-agnostic: uses IMAP/SMTP by default (works with virtually any email
provider). Swap the adapter when the provider is chosen.

Separate from followup.py (personal nudge drafter for Heinrich's Gmail).

Flow:
  1. Poll each campaign inbox via IMAP for new replies
  2. Classify: interested / not-interested / unsubscribe / out-of-office
  3. Interested → compose reply in Heinrich's voice → send via SMTP
  4. Not-interested / unsubscribe → flag in DB, skip
  5. Notify Heinrich on Telegram with a summary
"""
import email as email_lib
import imaplib
import json
import re
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.text import MIMEText

import anthropic

from config import ANTHROPIC_API_KEY, CALENDAR_BOOKING_LINK
from db.client import supabase
from services.notify import send_telegram

_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _cfg():
    """Late import to avoid circular imports."""
    from config import (
        CAMPAIGN_ENABLED,
        CAMPAIGN_ACCOUNTS,
        CAMPAIGN_REPLY_DELAY_MINUTES,
        CAMPAIGN_DAILY_CAP_PER_ACCOUNT,
        CAMPAIGN_KILL_SWITCH,
    )
    return {
        "enabled": CAMPAIGN_ENABLED,
        "accounts": CAMPAIGN_ACCOUNTS,
        "reply_delay_minutes": CAMPAIGN_REPLY_DELAY_MINUTES,
        "daily_cap": CAMPAIGN_DAILY_CAP_PER_ACCOUNT,
        "kill_switch": CAMPAIGN_KILL_SWITCH,
    }


# ---------------------------------------------------------------------------
# IMAP/SMTP adapter (default — works with any provider)
# ---------------------------------------------------------------------------

def _imap_connect(account: dict) -> imaplib.IMAP4_SSL:
    """Connect to an IMAP mailbox."""
    conn = imaplib.IMAP4_SSL(account["imap_host"], int(account.get("imap_port", 993)))
    conn.login(account["email"], account["password"])
    return conn


def _fetch_unseen(account: dict) -> list[dict]:
    """Fetch unseen emails from a campaign account via IMAP."""
    results = []
    try:
        conn = _imap_connect(account)
        conn.select("INBOX")
        _, msg_nums = conn.search(None, "UNSEEN")

        for num in msg_nums[0].split():
            if not num:
                continue
            _, data = conn.fetch(num, "(RFC822)")
            raw = data[0][1]
            msg = email_lib.message_from_bytes(raw)

            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode("utf-8", "ignore")
                        break
            else:
                body = msg.get_payload(decode=True).decode("utf-8", "ignore")

            from_addr = msg.get("From", "")
            # Extract email from "Name <email>" format
            match = re.search(r"<([^>]+)>", from_addr)
            from_email = match.group(1) if match else from_addr

            results.append({
                "uid": num.decode(),
                "from": from_addr,
                "from_email": from_email.lower().strip(),
                "to": msg.get("To", ""),
                "subject": msg.get("Subject", "(no subject)"),
                "date": msg.get("Date", ""),
                "message_id": msg.get("Message-ID", ""),
                "in_reply_to": msg.get("In-Reply-To", ""),
                "references": msg.get("References", ""),
                "body": body.strip(),
            })

        conn.logout()
    except Exception as e:
        print(f"[campaign] IMAP fetch failed for {account.get('email', '?')}: {e}", flush=True)

    return results


def _send_smtp(account: dict, to_addr: str, subject: str, body: str,
               in_reply_to: str = None, references: str = None) -> bool:
    """Send a reply via SMTP."""
    try:
        mime = MIMEText(body)
        mime["From"] = account["email"]
        mime["To"] = to_addr
        mime["Subject"] = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        if in_reply_to:
            mime["In-Reply-To"] = in_reply_to
            mime["References"] = (references + " " + in_reply_to).strip() if references else in_reply_to

        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(account["smtp_host"], int(account.get("smtp_port", 465)), context=ctx) as server:
            server.login(account["email"], account["password"])
            server.send_message(mime)

        return True
    except Exception as e:
        print(f"[campaign] SMTP send failed for {account.get('email', '?')}: {e}", flush=True)
        return False


# ---------------------------------------------------------------------------
# Reply classification
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = """Classify this email reply to a cold outreach campaign. The reply is from a prospect.

Categories:
- "interested" — wants to learn more, asks questions, requests a call/meeting, positive response
- "not_interested" — declines, says no thanks, not relevant, bad timing
- "unsubscribe" — asks to be removed, stop emailing, opt out
- "out_of_office" — auto-reply, vacation, OOO
- "bounce" — delivery failure, address not found

Respond with ONLY a JSON object:
{"category": "<one of the categories>", "reason": "<one short line>"}"""


def _classify_reply(subject: str, body: str) -> dict:
    """Classify a prospect's reply into a category."""
    try:
        resp = _ai.messages.create(
            model=_MODEL,
            max_tokens=256,
            system=_CLASSIFY_PROMPT,
            messages=[{"role": "user", "content": f"Subject: {subject}\n\nBody:\n{body[:2000]}"}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
    except Exception as e:
        print(f"[campaign] classify failed: {e}", flush=True)
    return {"category": "interested", "reason": "classification failed, defaulting to interested"}


# ---------------------------------------------------------------------------
# Reply composition
# ---------------------------------------------------------------------------

_COMPOSE_PROMPT = f"""You are replying to a prospect who responded to a cold outreach email from Heinrich Bosch (BoschAI — builds custom AI Operating Systems for businesses).

Write a SHORT, natural reply that:
- Acknowledges what they said
- Is warm and professional, not salesy or desperate
- Moves toward a quick call/meeting if they seem interested
- When you invite them to a call, include Heinrich's booking link on its OWN line so they can pick a time directly: {CALENDAR_BOOKING_LINK}
- Keeps Heinrich's voice: sharp, direct, concise, no fluff
- 2-5 sentences max
- Signed "Heinrich"

Do NOT invent specifics about their business. Keep it general until the call.

Respond with ONLY a JSON object:
{{"reply_body": "<the reply text>"}}"""


def _compose_reply(subject: str, prospect_body: str, prospect_name: str) -> str | None:
    """Compose a reply to an interested prospect."""
    try:
        resp = _ai.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=_COMPOSE_PROMPT,
            messages=[{"role": "user", "content": (
                f"Prospect name: {prospect_name}\n"
                f"Subject: {subject}\n\n"
                f"Their reply:\n{prospect_body[:2000]}"
            )}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(text[start:end + 1])
            return data.get("reply_body", "").strip() or None
    except Exception as e:
        print(f"[campaign] compose failed: {e}", flush=True)
    return None


# ---------------------------------------------------------------------------
# DB tracking
# ---------------------------------------------------------------------------

def _get_today_count(account_email: str) -> int:
    """How many auto-replies this account has sent today."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    resp = supabase.table("campaign_replies").select("id", count="exact").eq(
        "account_email", account_email
    ).gte("replied_at", today_start).execute()
    return resp.count or 0


def _log_reply(account_email: str, prospect_email: str, subject: str,
               category: str, action: str, prospect_body: str = None) -> dict:
    """Log a campaign reply action to the DB."""
    row = {
        "account_email": account_email,
        "prospect_email": prospect_email,
        "subject": subject,
        "category": category,
        "action": action,
        "prospect_body_preview": (prospect_body or "")[:500],
        "replied_at": datetime.now(timezone.utc).isoformat(),
    }
    resp = supabase.table("campaign_replies").insert(row).execute()
    return (resp.data or [{}])[0]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_status() -> dict:
    """Status summary for Telegram command."""
    cfg = _cfg()
    accounts = cfg["accounts"]
    counts = {}
    for acc in accounts:
        counts[acc["email"]] = _get_today_count(acc["email"])
    return {
        "enabled": cfg["enabled"],
        "kill_switch": cfg["kill_switch"],
        "account_count": len(accounts),
        "today_replies": counts,
        "daily_cap": cfg["daily_cap"],
    }


def set_kill_switch(on: bool) -> bool:
    """Toggle campaign kill switch. Runtime only — set env var for persistence."""
    import config
    config.CAMPAIGN_KILL_SWITCH = on
    return on


def run() -> dict:
    """Main entry point — called by the scheduler every few minutes.

    Polls all campaign inboxes, classifies replies, auto-responds to
    interested prospects, flags the rest.
    """
    cfg = _cfg()

    if not cfg["enabled"]:
        return {"skipped": True, "reason": "campaign responder disabled"}
    if cfg["kill_switch"]:
        return {"skipped": True, "reason": "kill switch engaged"}
    if not cfg["accounts"]:
        return {"skipped": True, "reason": "no campaign accounts configured"}

    daily_cap = cfg["daily_cap"]
    actions = []
    skipped = []

    for account in cfg["accounts"]:
        account_email = account["email"]
        today_count = _get_today_count(account_email)

        if today_count >= daily_cap:
            skipped.append({"account": account_email, "reason": "daily cap reached"})
            continue

        remaining = daily_cap - today_count
        replies = _fetch_unseen(account)

        for reply in replies:
            if remaining <= 0:
                break

            # Classify the reply
            classification = _classify_reply(reply["subject"], reply["body"])
            category = classification.get("category", "interested")

            if category in ("not_interested", "unsubscribe", "bounce", "out_of_office"):
                _log_reply(
                    account_email=account_email,
                    prospect_email=reply["from_email"],
                    subject=reply["subject"],
                    category=category,
                    action="flagged",
                    prospect_body=reply["body"],
                )
                skipped.append({
                    "account": account_email,
                    "prospect": reply["from_email"],
                    "category": category,
                    "reason": classification.get("reason", ""),
                })
                continue

            # Interested — compose and send
            prospect_name = reply["from"].split("<")[0].strip().strip('"') or reply["from_email"]
            body = _compose_reply(reply["subject"], reply["body"], prospect_name)

            if not body:
                skipped.append({
                    "account": account_email,
                    "prospect": reply["from_email"],
                    "reason": "could not compose reply",
                })
                continue

            sent = _send_smtp(
                account=account,
                to_addr=reply["from_email"],
                subject=reply["subject"],
                body=body,
                in_reply_to=reply["message_id"],
                references=reply["references"],
            )

            if sent:
                _log_reply(
                    account_email=account_email,
                    prospect_email=reply["from_email"],
                    subject=reply["subject"],
                    category=category,
                    action="replied",
                    prospect_body=reply["body"],
                )
                actions.append({
                    "account": account_email,
                    "prospect": reply["from_email"],
                    "subject": reply["subject"],
                })
                remaining -= 1
            else:
                skipped.append({
                    "account": account_email,
                    "prospect": reply["from_email"],
                    "reason": "SMTP send failed",
                })

    # Notify Heinrich
    if actions:
        lines = [f"Campaign responder — {len(actions)} auto-reply(s) sent:"]
        for a in actions:
            lines.append(f"  {a['account']} -> {a['prospect']}: {a['subject']}")
        try:
            send_telegram("\n".join(lines))
        except Exception:
            pass

    return {
        "actions": len(actions),
        "details": actions,
        "skipped": skipped,
    }
