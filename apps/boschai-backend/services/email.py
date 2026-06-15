"""
Gmail service — list the inbox, read a message, and send a reply.

Reuses the same Google OAuth token as Drive (services.drive.get_credentials),
so no separate sign-in is needed. Requires the gmail.modify + gmail.send scopes,
which are granted during the /auth/google flow.
"""
import base64
import re
from datetime import datetime
from email.mime.text import MIMEText
from html import unescape

from googleapiclient.discovery import build

from services.drive import get_credentials


def _html_to_text(html: str) -> str:
    """Rough HTML -> readable text: drop script/style, tags, collapse whitespace."""
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", html)
    html = re.sub(r"(?i)<br\s*/?>", "\n", html)
    html = re.sub(r"(?i)</p\s*>", "\n\n", html)
    text = re.sub(r"(?s)<[^>]+>", "", html)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _gmail():
    return build("gmail", "v1", credentials=get_credentials())


def _header(headers: list[dict], name: str) -> str:
    """Pull a single header value (case-insensitive) from a Gmail headers list."""
    name = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def _extract_body(payload: dict) -> str:
    """Walk the MIME tree and return the best plain-text body we can find."""
    mime = payload.get("mimeType", "")
    body = payload.get("body", {})

    if mime == "text/plain" and body.get("data"):
        return base64.urlsafe_b64decode(body["data"]).decode("utf-8", "ignore")

    # Recurse into multipart messages, preferring text/plain.
    parts = payload.get("parts", []) or []
    for part in parts:
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "ignore")
    for part in parts:
        found = _extract_body(part)
        if found:
            return found

    # Last resort: decode any html part and convert to readable text.
    for part in parts:
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "ignore")
            return _html_to_text(html)
    if mime == "text/html" and body.get("data"):
        html = base64.urlsafe_b64decode(body["data"]).decode("utf-8", "ignore")
        return _html_to_text(html)
    return ""


# Address patterns that signal an automated / no-reply / bounce sender. Checked
# against From, Return-Path and Sender (a real reply goes back to a person, not these).
_AUTOMATED_FROM = re.compile(
    r"(no[-_. ]?reply|do[-_. ]?not[-_. ]?reply|donotreply|mailer[-_.]?daemon|postmaster|"
    r"notif(y|ication)|@notify\.|alerts?@|auto[-_.]?(mated|reply|responder)|bounce|"
    r"updates?@|mailer@|noreply)",
    re.I,
)

# Header NAMES that only bulk / ESP / marketing infrastructure attaches. Genuine
# person-to-person mail from Gmail / Outlook / Apple Mail / Exchange never carries
# these — so their mere PRESENCE is a reliable "this was machine-sent" signal.
# Matched case-insensitively against the start of each header name.
_BULK_HEADER_PREFIXES = (
    "list-unsubscribe", "list-id",                       # mailing lists / bulk senders
    "feedback-id", "x-feedback-id", "x-msfbl",           # ESP bounce/complaint tracking (SES, Customer.io)
    "x-mailgun", "x-ses", "x-sg-eid", "x-sg-id", "x-sgg",  # Mailgun / Amazon SES / SendGrid
    "x-cio", "x-customerio", "x-mc-", "x-mandrill",      # Customer.io / Mailchimp / Mandrill
    "x-mj-", "x-pm-", "x-sparkpost", "x-klaviyo",        # Mailjet / Postmark / SparkPost / Klaviyo
    "x-mailchimp", "x-campaign", "x-marketing", "x-report-abuse",
)

# X-Mailer values naming a bulk-email provider. (Real clients set "Microsoft
# Outlook" / "Apple Mail" here, so we match the provider name, not mere presence.)
_ESP_MAILER = re.compile(
    r"(customer\.io|customeriomail|sendgrid|mailgun|mailchimp|mandrill|amazonses|"
    r"sendinblue|brevo|mailjet|postmark|sparkpost|constantcontact|hubspot|klaviyo|"
    r"intercom|braze|iterable|\bses\b|\bloops\b|\bresend\b)",
    re.I,
)

# Google Calendar stamps every invite / update / RSVP with this Sender address.
_CALENDAR_SENDER = "calendar-notification@google.com"

# Calendar event subject prefixes (Google Calendar invites, updates, RSVPs).
_CALENDAR_SUBJECT = re.compile(
    r"^\s*(re:\s*)?(invitation( from an unknown sender)?|updated invitation|"
    r"accepted|declined|tentative|cancell?ed)\s*:",
    re.I,
)


def _is_calendar(headers_map: dict, subject: str) -> bool:
    """True if the message is a calendar invite / update / RSVP (not a typed email)."""
    if _CALENDAR_SENDER in headers_map.get("sender", "").lower():
        return True
    if subject and _CALENDAR_SUBJECT.search(subject):
        return True
    return False


def _is_automated(headers: list[dict], from_value: str) -> bool:
    """
    True if the email is almost certainly machine-sent (not typed by a real person).

    The decisive test is infrastructure headers that only bulk/ESP/marketing systems
    attach (List-Unsubscribe, Feedback-ID, X-Mailgun-*, X-Mailer: Customer.io, ...) —
    personal mail never carries them. Calendar invites, no-reply/bounce addresses on
    From/Return-Path/Sender, Precedence: bulk and Auto-Submitted are also caught.
    """
    h = {x.get("name", "").lower(): x.get("value", "") for x in headers}

    # Calendar invites / RSVPs (often sent FROM a real person via Google Calendar).
    if _is_calendar(h, h.get("subject", "")):
        return True

    # no-reply / bounce / mailer-daemon on any of the addressing headers.
    for field in ("from", "return-path", "sender"):
        val = from_value if field == "from" else h.get(field, "")
        if val and _AUTOMATED_FROM.search(val):
            return True

    # Any bulk/ESP infrastructure header → machine-sent.
    for name in h:
        if name.startswith(_BULK_HEADER_PREFIXES):
            return True

    # Bulk-email provider named in X-Mailer (real clients name Outlook/Apple Mail).
    if _ESP_MAILER.search(h.get("x-mailer", "")):
        return True

    # Classic bulk markers.
    if h.get("precedence", "").strip().lower() in ("bulk", "list", "junk", "auto_reply"):
        return True
    if "auto" in h.get("auto-submitted", "").lower():
        return True
    return False


def _has_been_replied_to(gmail, thread_id: str, received_ms: int) -> bool:
    """
    True if Heinrich has already replied to this email — i.e. the thread contains a
    SENT message dated after the received message. Used to drop handled emails
    from the dashboard feed.
    """
    if not thread_id:
        return False
    try:
        thread = gmail.users().threads().get(
            userId="me", id=thread_id, format="minimal",
        ).execute()
    except Exception:
        return False
    for m in thread.get("messages", []):
        if "SENT" in m.get("labelIds", []) and int(m.get("internalDate", "0") or "0") > received_ms:
            return True
    return False


def list_inbox(max_results: int = 15, q: str = "in:inbox category:primary",
               people_only: bool = False, today_only: bool = False,
               exclude_replied: bool = False) -> list[dict]:
    """
    Return recent inbox messages as a list of summary dicts.

    `q` is a Gmail search query. Default = the Primary tab (real people/companies),
    which excludes Promotions/Social/spam. Pass 'in:inbox category:primary is:unread'
    for only new mail, or 'in:inbox' for everything.

    `people_only`: when True, drop automated/bulk mail (GitHub, Railway, newsletters,
    no-reply notifications) so only real-person emails remain. Each returned item also
    carries an `automated` boolean for transparency.

    `today_only`: when True, keep only messages actually received TODAY (server-local
    calendar date), using each message's internalDate — strict, not a rolling 24h window.
    """
    gmail = _gmail()
    # "People only" means typed-by-a-human mail, so drop calendar invites at the
    # source — every Google/Outlook invite attaches an invite.ics file.
    if people_only and "filename:" not in q:
        q = f"{q} -filename:ics"
    # Over-fetch when filtering, so we still return a useful count after dropping bots/old mail.
    fetch_n = max_results * 4 if (people_only or today_only) else max_results
    listing = gmail.users().messages().list(
        userId="me", q=q, maxResults=fetch_n,
    ).execute()

    today = datetime.now().date() if today_only else None
    summaries = []
    for ref in listing.get("messages", []):
        # format="metadata" with no header filter returns ALL headers but not the
        # body — cheap, and lets _is_automated see ESP/bulk infrastructure headers.
        msg = gmail.users().messages().get(
            userId="me", id=ref["id"], format="metadata",
        ).execute()

        ms = int(msg.get("internalDate", "0") or "0")
        if today_only:
            if not ms or datetime.fromtimestamp(ms / 1000).date() != today:
                continue

        headers = msg.get("payload", {}).get("headers", [])
        from_value = _header(headers, "From")
        automated = _is_automated(headers, from_value)
        if people_only and automated:
            continue

        if exclude_replied and _has_been_replied_to(gmail, msg.get("threadId"), ms):
            continue

        summaries.append({
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "from": from_value,
            "subject": _header(headers, "Subject") or "(no subject)",
            "date": _header(headers, "Date"),
            "snippet": msg.get("snippet", ""),
            "unread": "UNREAD" in msg.get("labelIds", []),
            "automated": automated,
        })
        if len(summaries) >= max_results:
            break
    return summaries


def get_message(msg_id: str) -> dict:
    """Return one message with its full plain-text body and key headers."""
    gmail = _gmail()
    msg = gmail.users().messages().get(userId="me", id=msg_id, format="full").execute()
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    return {
        "id": msg["id"],
        "thread_id": msg.get("threadId"),
        "from": _header(headers, "From"),
        "to": _header(headers, "To"),
        "subject": _header(headers, "Subject") or "(no subject)",
        "date": _header(headers, "Date"),
        "message_id": _header(headers, "Message-ID"),
        "references": _header(headers, "References"),
        "body": _extract_body(payload),
    }


def _sanitize_outgoing(body: str) -> str:
    """Backstop for the no-em-dash writing rule on outgoing mail.

    The model is told to use zero em-dashes, but it slips, so strip them here:
    em-dashes (always) and spaced en-dashes (used as em-dashes) become commas.
    Unspaced en-dashes like '2-3' ranges are left alone.
    """
    if not body:
        return body
    body = re.sub(r"\s*—\s*", ", ", body)      # em-dash -> comma
    body = re.sub(r"\s+–\s+", ", ", body)       # spaced en-dash -> comma (keep numeric ranges)
    body = re.sub(r",\s*,", ",", body)           # tidy any doubled commas
    return body


def _build_reply(msg_id: str, body: str):
    """Build the raw MIME for a threaded reply. Returns (raw, thread_id, to, subject)."""
    body = _sanitize_outgoing(body)
    original = get_message(msg_id)

    to_addr = original["from"]
    subject = original["subject"]
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    mime = MIMEText(body)
    mime["To"] = to_addr
    mime["Subject"] = subject
    if original["message_id"]:
        mime["In-Reply-To"] = original["message_id"]
        refs = original["references"]
        mime["References"] = (refs + " " + original["message_id"]).strip() if refs else original["message_id"]

    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    return raw, original["thread_id"], to_addr, subject


def send_reply(msg_id: str, body: str) -> dict:
    """Send a reply to the given message, keeping it in the same thread."""
    raw, thread_id, to_addr, subject = _build_reply(msg_id, body)
    sent = _gmail().users().messages().send(
        userId="me",
        body={"raw": raw, "threadId": thread_id},
    ).execute()
    return {"sent_id": sent.get("id"), "thread_id": sent.get("threadId"), "to": to_addr, "subject": subject}


def create_draft_reply(msg_id: str, body: str) -> dict:
    """Save a reply as a Gmail draft (in the same thread) WITHOUT sending it."""
    raw, thread_id, to_addr, subject = _build_reply(msg_id, body)
    draft = _gmail().users().drafts().create(
        userId="me",
        body={"message": {"raw": raw, "threadId": thread_id}},
    ).execute()
    return {"draft_id": draft.get("id"), "thread_id": thread_id, "to": to_addr, "subject": subject}


def create_draft(to: str, subject: str, body: str) -> dict:
    """Save a brand-new email as a Gmail draft (not a reply) WITHOUT sending it."""
    body = _sanitize_outgoing(body)
    mime = MIMEText(body)
    mime["To"] = to
    mime["Subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
    draft = _gmail().users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()
    return {"draft_id": draft.get("id"), "to": to, "subject": subject}
