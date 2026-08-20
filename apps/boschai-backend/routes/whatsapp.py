"""The WhatsApp quote bot.

A technician finishes a site visit, messages this number in whatever words come out,
and gets back a tidy summary. He replies SEND and the customer has a numbered PDF
quote on their phone about ten seconds later.

Two ideas hold the whole thing up:

1. Nothing sends without SEND. The parse is a draft and a human confirms it, because
   a mistyped digit posts a customer's quote to a stranger.
2. Every reply goes out through the REST API from a background task, never as TwiML.
   Twilio times a webhook out at 15 seconds and a Chromium render can outlast that.
"""
import base64
import hashlib
import hmac
import os
import re
import threading
from datetime import datetime, timezone
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import HTMLResponse

from config import (
    API_SECRET_KEY,
    QUOTE_BOT_ENABLED,
    QUOTE_TECHNICIANS,
    WHATSAPP_VALIDATE_SIGNATURE,
    public_base_url,
)
from services import quotes, whatsapp
from services.notify import send_telegram

router = APIRouter()

# Bumped by hand whenever this file changes, so /quotebot/status proves which
# build Railway is actually running. Guessing at that has cost hours.
BUILD = "quotebot-3 (2026-08-20, lock + persistence + forgiving SEND)"

EMPTY_TWIML = Response(content="<Response></Response>", media_type="application/xml")

YES = {"send", "yes", "y", "ja", "ok", "okay", "go", "send it", "stuur"}
NO = {"cancel", "no", "nee", "stop", "scrap", "delete"}
HELP = {"help", "?", "hi", "hello", "start"}

HELP_TEXT = (
    "*Quote bot*\n\n"
    "Send me the job as you would say it out loud. For example:\n\n"
    "_Sarah Adams, 082 555 1234, sarah@gmail.com - 2 sliding panels lounge "
    "1.8x2.1, 6.38 laminated, replace both tracks, R11 500 incl labour_\n\n"
    "I will write it up and show you before anything goes out. "
    "Reply *SEND* to send it, or just tell me what to change."
)


# ------------------------------------------------------------------ security

def _valid_signature(request: Request, form: dict, body_url: str) -> bool:
    """Twilio signs every webhook: HMAC-SHA1 over the full URL plus the sorted
    POST params, keyed on the auth token. Without this the endpoint is an open
    megaphone that sends WhatsApps on demand, billed to us."""
    signature = request.headers.get("X-Twilio-Signature", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not signature or not token:
        return False
    payload = body_url + "".join(k + str(form[k]) for k in sorted(form))
    digest = hmac.new(token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature)


def _authorised(number: str) -> bool:
    """Empty allowlist means demo mode: anyone who can reach the sandbox may quote.
    Set QUOTE_TECHNICIANS before this touches a real business."""
    if not QUOTE_TECHNICIANS:
        return True
    return number in QUOTE_TECHNICIANS


# ------------------------------------------------------------- message shapes

def _confirmation(draft: dict) -> str:
    lines = ["Here is the quote. Nothing has been sent yet.", ""]
    for item in draft["line_items"]:
        amount = (quotes.fmt_money(item["amount"])
                  if item.get("amount") is not None else "")
        lines.append(f"- {item['description']}" + (f"  _{amount}_" if amount else ""))
    lines += [
        "",
        f"*Total: {quotes.fmt_money(draft['total'])}*",
        "",
        f"To: {draft['customer_name']} on "
        f"{quotes.display_phone(draft['customer_phone_e164'])}",
    ]
    if draft.get("customer_email"):
        lines.append(f"Email: {draft['customer_email']}")
    lines += ["", "Reply *SEND* to send it, or tell me what to fix."]
    return "\n".join(lines)


def _why_no_whatsapp(e164: str) -> str:
    """Name the actual reason, because 'that number will not work' invites an argument
    and 'that is a share-call number' ends one."""
    national = e164[3:] if e164.startswith("+27") else ""
    if national.startswith(("86", "87")):
        return "086 and 087 are share-call numbers, not mobiles"
    if national[:1] in ("1", "2", "3", "4", "5"):
        return "that is a landline"
    return "it is not a South African mobile"


def _needs_more(draft: dict) -> str:
    missing = ", ".join(draft["missing"])
    return (f"Almost there - I still need {missing}.\n\n"
            "Just send it and I will add it to what you already gave me.")


# ---------------------------------------------------------------- the worker

_locks_guard = threading.Lock()
_locks = {}


def _lock_for(technician: str) -> threading.Lock:
    """One lock per technician, so his messages are handled in the order he sent them.

    Without this, SEND typed a second after the job races the Claude parse that is
    still writing the draft: get_draft() returns nothing and he is told there is
    nothing to send, for a quote he is looking at. Different technicians never
    block each other.
    """
    with _locks_guard:
        if technician not in _locks:
            _locks[technician] = threading.Lock()
        return _locks[technician]


def _command(text: str) -> str:
    """Normalise a one-word command. People type 'SEND', 'send.', 'Send it!'.

    Keeps ONLY a-z and spaces, so a zero-width space, a non-breaking space, an
    autocorrect full stop or a stray emoji cannot stop SEND from being SEND.
    """
    return re.sub(r"[^a-z ]", "", text.lower()).strip()


# What the bot last saw, newest first. Exposed at /quotebot/status because this
# runs on Railway where reading logs mid-conversation is not practical, and every
# bug so far has come down to "what exactly arrived in Body?".
_RECENT = []
_RECENT_MAX = 25


def _record(**row) -> None:
    _RECENT.insert(0, {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **row})
    del _RECENT[_RECENT_MAX:]


def _handle(technician: str, body: str) -> None:
    """All the slow work: Claude, Chromium, Twilio. Runs after the webhook returns."""
    with _lock_for(technician):
        _handle_locked(technician, body)


def _handle_locked(technician: str, body: str) -> None:
    text = (body or "").strip()
    lowered = _command(text)
    draft = quotes.get_draft(technician)
    # ascii(), not !r: an invisible character shows up as ​ rather than as
    # nothing at all, which is the whole reason this line exists -- and it can
    # never raise UnicodeEncodeError on a non-UTF-8 stdout. That matters because
    # this runs BEFORE the try below, so a throw here would swallow the message
    # entirely and the technician would get silence.
    safe_body = ascii(body)
    print(f"[quotebot] {technician}: raw={safe_body} command={lowered!r} "
          f"draft={'yes' if draft else 'no'}", flush=True)

    try:
        # `?` survives _command as an empty string, so check the raw text too.
        if not text or lowered in HELP or text in HELP:
            _record(number=technician, raw=safe_body, command=lowered, action="help")
            whatsapp.send_text(technician, HELP_TEXT)
            return

        if lowered in NO:
            _record(number=technician, raw=safe_body, command=lowered, action="cancel")
            quotes.clear_draft(technician)
            whatsapp.send_text(technician, "Scrapped. Nothing was sent.")
            return

        if lowered in YES:
            if not draft or draft.get("missing"):
                _record(number=technician, raw=safe_body, command=lowered,
                        action="send-but-no-draft", draft=bool(draft))
                whatsapp.send_text(
                    technician, "Nothing ready to send yet. Send me the job first.")
                return
            _record(number=technician, raw=safe_body, command=lowered, action="issue")
            _issue(technician, draft)
            return

        _record(number=technician, raw=safe_body, command=lowered,
                action="parse", had_draft=bool(draft))

        # Anything else is either a new job or a correction to the one in progress.
        parsed = quotes.parse_message(text, prior=draft if draft else None)
        parsed["customer_phone_e164"] = quotes.normalize_sa_phone(parsed.get("customer_phone"))
        quotes.save_draft(technician, parsed)

        if parsed["missing"]:
            whatsapp.send_text(technician, _needs_more(parsed))
            return

        if not quotes.is_whatsapp_capable(parsed["customer_phone_e164"]):
            whatsapp.send_text(
                technician,
                f"Heads up: {parsed['customer_phone_e164']} cannot receive WhatsApp - "
                f"{_why_no_whatsapp(parsed['customer_phone_e164'])}. It would fail "
                "silently, so nobody would know. Send me a mobile number for them "
                "(06, 07, 081-084), or reply SEND and I will give you a link to pass on.")
            return

        whatsapp.send_text(technician, _confirmation(parsed))

    except whatsapp.WhatsAppError as exc:
        print(f"[quotebot] whatsapp error for {technician}: {exc}", flush=True)
    except Exception as exc:
        print(f"[quotebot] failed for {technician}: {exc}", flush=True)
        try:
            whatsapp.send_text(
                technician, "Something went wrong on my side. Try sending that again.")
        except Exception:
            pass


def _issue(technician: str, draft: dict) -> None:
    """Number it, render it, send it to the customer, tell the office."""
    import asyncio

    biz = quotes.business()
    today = quotes.today()
    quote = dict(draft)
    quote["quote_number"] = quotes.next_quote_number(biz.get("quote_prefix", "Q"), today)
    quote["issued_date"] = today.isoformat()
    quote["quoted_by"] = quotes.technician_name(technician)
    quote["customer_phone"] = draft["customer_phone_e164"]

    html = quotes.render_html(quote)
    token = quotes.new_token()

    pdf = None
    try:
        pdf = asyncio.run(quotes.html_to_pdf(html))
    except Exception as exc:
        # Chromium missing on the host. The quote still goes out, as a link.
        print(f"[quotebot] PDF render failed, falling back to link: {exc}", flush=True)

    quotes.store_issued(token, {"html": html, "pdf": pdf,
                                "quote_number": quote["quote_number"]})

    base = public_base_url()
    link = f"{base}/q/{token}"
    number = quote["quote_number"]
    total = quotes.fmt_money(quote["total"])

    customer_msg = (
        f"Hi {quote['customer_name']}, thanks for having us out today.\n\n"
        f"Here is your quote from {biz['name']} - *{number}*, total *{total}*.\n\n"
        f"{biz.get('accept_line', '')}\n\n{link}"
    )

    to = quote["customer_phone"]
    try:
        if pdf:
            whatsapp.send_media(to, customer_msg, f"{base}/q/{token}.pdf")
        else:
            whatsapp.send_text(to, customer_msg)
    except whatsapp.WhatsAppError as exc:
        # The draft is deliberately KEPT so he can retry SEND once the cause is
        # fixed, rather than retyping the whole job.
        print(f"[quotebot] delivery to {to} failed: {exc}", flush=True)
        whatsapp.send_text(
            technician,
            f"The quote is ready ({number}, {total}) but it would not deliver to "
            f"{quotes.display_phone(to)}.\n\n{exc}\n\nHere it is either way - "
            f"you can forward this link:\n{link}\n\nFix that and reply *SEND* again.")
        return

    quotes.clear_draft(technician)
    whatsapp.send_text(
        technician,
        f"Sent. *{number}* for {total} is on {quote['customer_name']}'s phone.\n\n{link}")

    try:
        send_telegram(
            f"\U0001f4c4 Quote <b>{number}</b> issued to {quote['customer_name']} "
            f"({total}) by {technician}.\n{link}")
    except Exception:
        pass  # the office ping is nice to have, never a reason to fail a send


# -------------------------------------------------------------------- routes

def _parse_form(raw: bytes) -> dict:
    """Twilio always posts application/x-www-form-urlencoded, so parse it with the
    stdlib rather than Starlette's request.form().

    Not a style preference: request.form() asserts on python-multipart being
    installed, for urlencoded bodies too, and that package is not a FastAPI
    dependency. Relying on it would mean the webhook 500s on a host where nobody
    remembered to add it — which is exactly how this was found.

    parse_qs also URL-decodes, which is what the signature is computed over.
    """
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}


@router.post("/webhook/whatsapp")
async def inbound(request: Request, background: BackgroundTasks):
    """Twilio posts here on every message to our WhatsApp number."""
    form = _parse_form(await request.body())

    if WHATSAPP_VALIDATE_SIGNATURE:
        url = public_base_url() + request.url.path
        if not _valid_signature(request, form, url):
            print("[quotebot] rejected: bad Twilio signature", flush=True)
            return Response(status_code=403)

    if not QUOTE_BOT_ENABLED:
        return EMPTY_TWIML

    sender = str(form.get("From", "")).replace("whatsapp:", "").strip()
    body = str(form.get("Body", ""))
    if not sender:
        return EMPTY_TWIML

    if not _authorised(sender):
        print(f"[quotebot] unauthorised sender {sender}", flush=True)
        background.add_task(
            whatsapp.send_text, sender,
            "This number is not set up to issue quotes.")
        return EMPTY_TWIML

    background.add_task(_handle, sender, body)
    return EMPTY_TWIML


@router.get("/quotebot/status")
def status(key: str = ""):
    """What build is live, how it is configured, and what it last received.

    Exists because every bug so far was invisible from outside: the deployed
    commit could not be confirmed, and the exact `Body` Twilio posted could not
    be seen. Guarded by API_SECRET_KEY -- it exposes phone numbers and message
    text, which is the point and also why it is not open.
    """
    if not API_SECRET_KEY or key != API_SECRET_KEY:
        return Response(status_code=403)
    return {
        "build": BUILD,
        "enabled": QUOTE_BOT_ENABLED,
        "technicians": QUOTE_TECHNICIANS or "(anyone - allowlist empty)",
        "signature_check": WHATSAPP_VALIDATE_SIGNATURE,
        "sender": os.getenv("TWILIO_WHATSAPP_FROM", "(unset)"),
        "base_url": public_base_url(),
        "yes_words": sorted(YES),
        "drafts_in_memory": sorted(quotes.DRAFTS),
        "draft_persistence": quotes._drafts_table_ok,
        "issued_this_boot": len(quotes.ISSUED),
        "recent": _RECENT,
    }


@router.get("/q/{token}.pdf")
def quote_pdf(token: str):
    """Twilio fetches this to attach the quote, so it has to be public and
    unauthenticated. The token is the secret."""
    issued = quotes.get_issued(token)
    if not issued or not issued.get("pdf"):
        return Response(status_code=404)
    return Response(
        content=issued["pdf"], media_type="application/pdf",
        headers={"Content-Disposition":
                 f'inline; filename="{issued["quote_number"]}.pdf"'},
    )


@router.get("/q/{token}")
def quote_page(token: str):
    """The same quote as a web page - the fallback when Chromium is unavailable,
    and what the customer taps on their phone either way."""
    issued = quotes.get_issued(token)
    if not issued:
        return HTMLResponse("<h1>This quote link has expired.</h1>", status_code=404)
    return HTMLResponse(issued["html"])
