"""The WhatsApp quote bot: the HTTP edge.

Everything here is plumbing — parse the form, prove it came from Twilio, refuse a
message we have already handled, work out who is talking, hand off. The thinking lives
in services/quote_engine.py and the document in services/quote_doc.py.

Two rules hold this edge up:

1. Answer Twilio immediately. It times a webhook out at 15 seconds, and a model call
   plus a render plus two sends can outlast that. Every reply goes back out through
   the REST API from a background task, never as TwiML.
2. Never act on the same MessageSid twice. Twilio redelivers on timeout, and a
   redelivered approval is a second quote on a customer's phone.
"""
import base64
import hashlib
import hmac
import os
import threading
from urllib.parse import parse_qs

from fastapi import APIRouter, BackgroundTasks, Request, Response
from fastapi.responses import HTMLResponse

from config import (
    API_SECRET_KEY,
    clean_env,
    has_stray_quotes,
    QUOTE_BOT_ENABLED,
    QUOTE_TECHNICIANS,
    WHATSAPP_VALIDATE_SIGNATURE,
    public_base_url,
)
from services import quote_doc as doc
from services import quote_engine as engine
from services import quote_store as store

router = APIRouter()

# Bumped by hand whenever this file changes, so /quotebot/status proves which build
# Railway is actually running. Guessing at that has cost hours.
BUILD = "quotebot-7 (2026-08-20, rebuilt: postgres state, model conversation, fpdf2)"


def _ack() -> Response:
    """An empty TwiML acknowledgement — a NEW object every single time.

    This was the bug that ate three days. It used to be one module-level Response
    reused by every request, which looks harmless and is not: FastAPI attaches the
    request's background tasks to a returned Response only `if response.background
    is None`. The first request set that field, and from then on it was never None
    again — so every later message re-ran the FIRST message's background task and
    its own was silently dropped.

    On a phone that looks exactly like what Heinrich saw. The bot answers a message
    he sent ten minutes ago, ignores what he just typed, and SEND never works. It
    also explains the debug screen showing the same body three times: the body really
    was being handled three times.

    Never return a shared Response instance from a route with background work.
    """
    return Response(content="<Response></Response>", media_type="application/xml")


NOT_FOR_YOU = ("Thanks for the message. This number only handles quotes for our own "
               "team — please call the office and we'll help you straight away.")


# ────────────────────────────────────────────────────────────────────── security

def _signed_url_candidates(request: Request) -> list:
    """Every URL Twilio might plausibly have signed.

    Twilio computes its signature over the exact URL it POSTed to, so ours has to match
    that string character for character. Three things routinely make it differ:

      - Railway terminates TLS and forwards over http, so request.url says "http://"
        while Twilio signed "https://".
      - The console URL may or may not carry a trailing slash or a query string.
      - PUBLIC_BASE_URL may be set to something slightly different from the host header.

    A mismatch is indistinguishable from an attack: 403, no reply, a bot that looks
    dead. One stray quote in PUBLIC_BASE_URL already caused exactly that. So rather than
    betting on one reconstruction, we check the handful that are all legitimately OURS.
    This is not a weakening — every candidate is a URL on our own host, and the request
    still has to carry a signature validly made with our auth token for one of them.
    """
    path = request.url.path
    query = f"?{request.url.query}" if request.url.query else ""
    host = request.headers.get("host", "").strip()
    proto = request.headers.get("x-forwarded-proto", "https").split(",")[0].strip()

    bases = [
        public_base_url() + path,
        f"{proto}://{host}{path}" if host else "",
        f"https://{host}{path}" if host else "",
        str(request.url).split("?")[0],
        str(request.url).split("?")[0].replace("http://", "https://", 1),
    ]

    # Both with and without a trailing slash — the console URL may carry one, and
    # Twilio signs it exactly as configured.
    forms = []
    for base in bases:
        if not base:
            continue
        bare = base.rstrip("/")
        forms += [bare, bare + "/"]

    # The query string, when there is one, is part of what Twilio signed.
    candidates = [f + query for f in forms] if query else forms

    seen, out = set(), []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


# The last time a signature was refused, and what we compared against. No token and no
# message body — just the URLs — so /quotebot/ready can show it without leaking anything.
_LAST_REJECTION = {}


def _valid_signature(request: Request, form: dict) -> bool:
    """Twilio signs every webhook: HMAC-SHA1 over the full URL plus the sorted POST
    params, keyed on the auth token. Without this the endpoint is an open megaphone
    that sends WhatsApp messages on demand, billed to us."""
    signature = request.headers.get("X-Twilio-Signature", "")
    token = clean_env("TWILIO_AUTH_TOKEN")
    if not signature or not token:
        _LAST_REJECTION.update({"at": doc.now_iso(),
                                "why": "no signature header" if not signature
                                       else "TWILIO_AUTH_TOKEN not set", "tried": []})
        return False

    params = "".join(k + str(form[k]) for k in sorted(form))
    for url in _signed_url_candidates(request):
        digest = hmac.new(token.encode(), (url + params).encode("utf-8"),
                          hashlib.sha1).digest()
        if hmac.compare_digest(base64.b64encode(digest).decode(), signature):
            _LAST_REJECTION.clear()
            return True

    _LAST_REJECTION.update({"at": doc.now_iso(), "why": "no candidate URL matched",
                            "tried": _signed_url_candidates(request)})
    return False


def _is_technician(number: str) -> bool:
    return number in QUOTE_TECHNICIANS


# ──────────────────────────────────────────────────────────────────── the worker

_locks_guard = threading.Lock()
_locks = {}


def _lock_for(number: str) -> threading.Lock:
    """One lock per phone, so a person's messages are handled in the order they were
    sent. Two messages a second apart otherwise race each other through the session
    read-modify-write, and the later one wins carrying stale facts."""
    with _locks_guard:
        if number not in _locks:
            _locks[number] = threading.Lock()
        return _locks[number]


def _dispatch(sender: str, body: str, message_sid: str) -> None:
    """Work out who this is, and hand them to the right half of the engine.

    Routing is by DATA first, not by config: anyone holding a recent quote from us is
    a customer replying, whatever the allowlist says. That is what closes the loop even
    in demo mode, where the allowlist is empty.
    """
    with _lock_for(sender):
        try:
            if _is_technician(sender):
                engine.handle_technician(sender, body, message_sid)
                return

            quote = store.latest_quote_for_phone(sender)
            if quote:
                engine.handle_customer(sender, body, quote, message_sid)
                return

            if not QUOTE_TECHNICIANS:
                # Demo mode: no allowlist set, so anyone reaching the sandbox may quote.
                engine.handle_technician(sender, body, message_sid)
                return

            engine.say(sender, NOT_FOR_YOU)
        except Exception as exc:
            print(f"[quotebot] dispatch failed for {sender}: {exc}", flush=True)
            try:
                engine.say(sender, "Something went wrong on my side. Send that again?")
            except Exception:
                pass


# ───────────────────────────────────────────────────────────────────── the routes

def _parse_form(raw: bytes) -> dict:
    """Twilio always posts application/x-www-form-urlencoded, so parse it with the
    stdlib rather than Starlette's request.form().

    Not a style preference: request.form() asserts on python-multipart being installed,
    for urlencoded bodies too, and that package is not a FastAPI dependency. Relying on
    it means the webhook 500s on a host where nobody remembered to add it — which is
    exactly how this was found the first time.
    """
    parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {k: v[0] for k, v in parsed.items()}


@router.post("/webhook/whatsapp")
async def inbound(request: Request, background: BackgroundTasks):
    """Twilio posts here on every message to our WhatsApp number."""
    form = _parse_form(await request.body())
    sender = str(form.get("From", "")).replace("whatsapp:", "").strip()
    body = str(form.get("Body", ""))
    sid = str(form.get("MessageSid", "")).strip()

    if WHATSAPP_VALIDATE_SIGNATURE:
        if not _valid_signature(request, form):
            print(f"[quotebot] rejected: bad Twilio signature (sid {sid[-8:]})", flush=True)
            return Response(status_code=403)

    if not QUOTE_BOT_ENABLED or not sender:
        return _ack()

    # The idempotency gate, deliberately synchronous. Done inside the background task
    # instead, two concurrent deliveries of one message would both pass it.
    if not store.log_inbound(message_sid=sid, from_number=sender,
                             to_number=str(form.get("To", "")), body=body, role=None):
        print(f"[quotebot] ignoring redelivery of {sid[-8:]}", flush=True)
        return _ack()

    # ascii(), never the raw body: this stdout is not always UTF-8, and a print that
    # raises here would swallow the message and leave the technician with silence.
    print(f"[quotebot] {sender} #{sid[-8:]}: {ascii(body)[:200]}", flush=True)

    background.add_task(_dispatch, sender, body, sid)
    return _ack()


@router.get("/quotebot/ready")
def ready():
    """Is this thing actually able to work right now, and if not, what is missing?

    Deliberately UNGUARDED, because the moment something is broken is the moment the
    key-protected endpoint is hardest to get at — and being blind is what turned a
    one-line bug into a three-day hunt. It is safe to leave open because it reports
    only whether things EXIST: no phone numbers, no message text, no customer data,
    and booleans for secrets rather than the secrets themselves.

    `blockers` is the whole point: it says what to go and do, in order.
    """
    from services import payments

    tables = store.health()
    missing = [name for name, state in tables.items() if state != "ok"]

    paystack_key = clean_env("PAYSTACK_SECRET_KEY")
    checks = {
        "quote_bot_enabled": QUOTE_BOT_ENABLED,
        "technicians_allowlisted": bool(QUOTE_TECHNICIANS),
        "twilio_sender_set": bool(clean_env("TWILIO_WHATSAPP_FROM")),
        "twilio_auth_set": bool(clean_env("TWILIO_AUTH_TOKEN")),
        "anthropic_key_set": bool(clean_env("ANTHROPIC_API_KEY")),
        "paystack_key_set": bool(paystack_key),
    }

    # A pasted quote character is invisible and catastrophic: it broke every Twilio
    # signature check for a day, because the signature is computed over the URL. The
    # values are cleaned before use now, but the paste error is still worth naming.
    dirty = [name for name in
             ("PUBLIC_BASE_URL", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
              "TWILIO_WHATSAPP_FROM", "ANTHROPIC_API_KEY", "PAYSTACK_SECRET_KEY",
              "API_SECRET_KEY", "QUOTE_TECHNICIANS")
             if has_stray_quotes(name)]

    blockers = []
    if dirty:
        blockers.append("These Railway variables have stray quote characters around "
                        f"their values: {', '.join(dirty)}. They are stripped "
                        "automatically now, but tidy them so nothing else trips on it.")
    if not checks["quote_bot_enabled"]:
        blockers.append("Set QUOTE_BOT_ENABLED=1 on Railway — the bot ignores every "
                        "message until you do.")
    if not checks["anthropic_key_set"]:
        blockers.append("ANTHROPIC_API_KEY is not set — the bot cannot understand "
                        "anything without it.")
    if not checks["twilio_auth_set"] or not checks["twilio_sender_set"]:
        blockers.append("TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM missing — it can "
                        "receive messages but cannot reply.")
    for name in missing:
        sql = ("015_quote_payments.sql" if name == "payment_events"
               else "014_quote_bot.sql")
        blockers.append(f"Table '{name}' is missing — run {sql} in the Supabase SQL "
                        f"editor.")
    if not checks["paystack_key_set"]:
        blockers.append("PAYSTACK_SECRET_KEY is not set — quotes still go out, just "
                        "with no payment link.")

    # Quotes still work without the payment side, so 'ready' does not depend on it.
    core_ok = (checks["quote_bot_enabled"] and checks["anthropic_key_set"]
               and checks["twilio_auth_set"] and checks["twilio_sender_set"]
               and "quotes" not in missing and "quote_sessions" not in missing
               and "quote_messages" not in missing)

    return {
        "build": BUILD,
        "ready_to_quote": core_ok,
        "ready_to_take_payment": core_ok and checks["paystack_key_set"]
                                 and "payment_events" not in missing,
        "blockers": blockers or ["none — everything needed is in place"],
        "checks": checks,
        "tables": tables,
        "model": engine.MODEL,
        "env_with_stray_quotes": dirty,
        "last_signature_rejection": _LAST_REJECTION or "none since restart",
        "twilio_sender": clean_env("TWILIO_WHATSAPP_FROM") or "(unset)",
        "paystack_mode": ("test" if paystack_key.startswith("sk_test_")
                          else "live" if paystack_key else "unset"),
        "base_url": public_base_url(),
    }


@router.get("/quotebot/status")
def status(key: str = ""):
    """What build is live, how it is configured, whether the migration was run, and
    what came in last.

    Guarded by API_SECRET_KEY: it exposes phone numbers and message text, which is the
    point of it and also why it is not open.
    """
    if not API_SECRET_KEY or key != API_SECRET_KEY:
        return Response(status_code=403)
    return {
        "build": BUILD,
        "enabled": QUOTE_BOT_ENABLED,
        "model": engine.MODEL,
        "technicians": QUOTE_TECHNICIANS or "(anyone — allowlist empty, demo mode)",
        "signature_check": WHATSAPP_VALIDATE_SIGNATURE,
        "sender": os.getenv("TWILIO_WHATSAPP_FROM", "(unset)"),
        "base_url": public_base_url(),
        "database": store.health(),
        "recent": store.recent_messages(25),
    }


@router.get("/quotebot/selftest")
def selftest(key: str = ""):
    """Put thirteen real technician messages through the real model and report what it
    made of each one — approvals in two languages, a swipe-to-reply, a correction, a
    question, and one sentence that must NOT be read as an approval.

    It lives here because the working Anthropic key is on this host. Nothing is sent to
    anybody: no Twilio, no database writes, no customer. Costs a few cents per run.
    """
    if not API_SECRET_KEY or key != API_SECRET_KEY:
        return Response(status_code=403)
    from services import quote_selftest
    return quote_selftest.run()


@router.get("/q/{token}.pdf")
def quote_pdf(token: str):
    """Twilio fetches this in order to attach the quote, so it has to be public and
    unauthenticated. The token is the secret.

    Rendered on demand from the stored row rather than kept as a blob: nothing to
    store, nothing to lose on a restart, and the document can never drift from the
    record it was made from.
    """
    quote = store.get_quote_by_token(token)
    if not quote:
        return Response(status_code=404)
    return Response(
        content=doc.render_pdf(quote), media_type="application/pdf",
        headers={"Content-Disposition":
                 f'inline; filename="{quote["quote_number"]}.pdf"',
                 "Cache-Control": "public, max-age=3600"},
    )


@router.get("/q/{token}")
def quote_page(token: str):
    """The same quote as a phone-friendly page — what the customer taps."""
    quote = store.get_quote_by_token(token)
    if not quote:
        return HTMLResponse(
            "<body style='font:16px system-ui;padding:40px;text-align:center'>"
            "<h1>This quote link has expired.</h1>"
            "<p>Please contact us and we'll send it again.</p></body>",
            status_code=404)
    return HTMLResponse(doc.render_html(quote, f"/q/{token}.pdf"))
