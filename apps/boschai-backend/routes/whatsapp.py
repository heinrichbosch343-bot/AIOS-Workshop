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
    TELEGRAM_ENABLED,
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
from services import whatsapp

router = APIRouter()

# Bumped by hand whenever this file changes, so /quotebot/status proves which build
# Railway is actually running. Guessing at that has cost hours.
BUILD = "quotebot-17 (2026-08-23, review fixes: stored money, armed sends, loop guards, startup)"


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

# The last time handling a message blew up. Recorded rather than swallowed: a bot
# that cannot even apologise used to leave no trace at all.
_LAST_DISPATCH_FAILURE = {}


def _valid_signature(request: Request, form: dict, inbound: bool = True) -> bool:
    """Twilio signs every webhook: HMAC-SHA1 over the full URL plus the sorted POST
    params, keyed on the auth token. Without this the endpoint is an open megaphone
    that sends WhatsApp messages on demand, billed to us.

    `inbound` says whether this is a real message on /webhook/whatsapp. Only those
    clear the rejection record. Status callbacks now hit the same validator, and
    since every send we make produces one, a successful callback would otherwise
    wipe the evidence that inbound messages were being refused — turning the probe's
    "none since restart" into a lie at exactly the moment it is being trusted.
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    token = clean_env("TWILIO_AUTH_TOKEN")
    if not signature or not token:
        if inbound:
            _LAST_REJECTION.update({"at": doc.now_iso(),
                                    "why": "no signature header" if not signature
                                           else "TWILIO_AUTH_TOKEN not set", "tried": []})
        return False

    params = "".join(k + str(form[k]) for k in sorted(form))
    for url in _signed_url_candidates(request):
        digest = hmac.new(token.encode(), (url + params).encode("utf-8"),
                          hashlib.sha1).digest()
        if hmac.compare_digest(base64.b64encode(digest).decode(), signature):
            if inbound:
                _LAST_REJECTION.clear()
            return True

    if inbound:
        _LAST_REJECTION.update({"at": doc.now_iso(), "why": "no candidate URL matched",
                                "tried": _signed_url_candidates(request)})
    return False


# Twilio posts a callback per state change and retries on a non-2xx, so the same
# MessageSid arrives repeatedly. Bounded, because this is a process-local cache and
# an unbounded dict on a long-lived server is a slow leak.
_seen_status_sids = []
_seen_guard = threading.Lock()


def _seen_status(sid: str) -> bool:
    """True the FIRST time this status callback is seen, False every time after."""
    with _seen_guard:
        if sid in _seen_status_sids:
            return False
        _seen_status_sids.append(sid)
        if len(_seen_status_sids) > 500:
            del _seen_status_sids[:250]
        return True


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


def _role_of(sender: str):
    """Is this person quoting, or being quoted? Returns (role, quote).

    The allowlist decides, and nothing overrides it. A number in QUOTE_TECHNICIANS is
    always the technician. Only a number that is NOT on that list can ever be treated
    as a customer, and it takes a quote actually addressed to it to do so.

    This used to be decided by the data instead — whoever held a quote that someone
    else had sent them was read as a customer, even if they were themselves listed —
    so that both phones could play both parts while recording. It backfired exactly
    where it mattered. Once one take had quoted Heinrich's own phone, that row sat in
    the table, and every message he sent from then on was answered as a customer
    reply. There was no way back into the technician seat short of deleting the row.

    One direction, fixed by config, is also the truthful rule for the business it runs
    for: FIXITT's technicians issue quotes and customers receive them. A technician
    being quoted by a colleague is a curiosity, not a use case, and it is not worth
    the failure mode above.
    """
    if _is_technician(sender):
        return "technician", None

    quote = store.latest_quote_for_phone(sender)
    if quote:
        return "customer", quote

    if not QUOTE_TECHNICIANS:
        # Demo mode: no allowlist set, so anyone reaching the sandbox may quote.
        return "technician", None

    return "stranger", None


def _dispatch(sender: str, body: str, message_sid: str) -> None:
    """Work out who this is, and hand them to the right half of the engine."""
    with _lock_for(sender):
        try:
            role, quote = _role_of(sender)
            print(f"[quotebot] {sender} is the {role}", flush=True)

            if role == "technician":
                engine.handle_technician(sender, body, message_sid)
                return
            if role == "customer":
                engine.handle_customer(sender, body, quote, message_sid)
                return

            engine.say(sender, NOT_FOR_YOU)
        except Exception as exc:
            print(f"[quotebot] dispatch failed for {sender}: {exc}", flush=True)
            _LAST_DISPATCH_FAILURE.update({
                "at": doc.now_iso(), "who": "…" + str(sender)[-3:],
                "error": str(exc)[:300]})
            # If the failure was the SEND itself — which it usually is — apologising
            # through the same channel goes to the same place: nowhere. It used to be
            # swallowed with a bare `except: pass`, so a bot that could not talk left
            # no trace anywhere. Record it, and only try the apology when the thing
            # that broke was not the sending.
            if isinstance(exc, whatsapp.WhatsAppError):
                return
            try:
                engine.say(sender, "Something went wrong on my side. Send that again?")
            except Exception as second:
                _LAST_DISPATCH_FAILURE["apology_also_failed"] = str(second)[:200]


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


# The last delivery failure Twilio reported, for the probe. No message body; the
# number is cut to three digits so this stays safe on an unguarded endpoint.
_LAST_DELIVERY_FAILURE = {}


@router.post("/webhook/whatsapp/status")
async def delivery_status(request: Request, background: BackgroundTasks):
    """Twilio tells us what became of a message it had already accepted.

    Twilio returns 201 "queued" for sends it will never deliver. An unjoined sandbox
    number (63015) and a closed 24-hour window (63016) both fail minutes later, out
    of band, raising nothing — so the technician is told "Sent ✓" while the customer
    receives silence. That is the precise failure this whole system exists to remove,
    reproduced by the system itself, and it has now cost two sessions.

    So: when a delivery fails, say so on the technician's phone.
    """
    form = _parse_form(await request.body())
    status = str(form.get("MessageStatus") or "").lower()
    to = str(form.get("To", "")).replace("whatsapp:", "").strip()
    code = str(form.get("ErrorCode") or "").strip()
    sid = str(form.get("MessageSid") or "").strip()

    if WHATSAPP_VALIDATE_SIGNATURE and not _valid_signature(request, form, inbound=False):
        return Response(status_code=403)

    # Twilio posts a callback per state change and retries on a non-2xx, so the same
    # failure arrives more than once. Without this the technician gets the same
    # warning three times; worse, each warning is itself a send that can fail and
    # produce another callback.
    if sid and not _seen_status(sid):
        return _ack()

    if status in ("failed", "undelivered"):
        from services.whatsapp import FRIENDLY, SANDBOX_HINT
        reason = (SANDBOX_HINT if code == "63015"
                  else FRIENDLY.get(int(code)) if code.isdigit() else "")
        _LAST_DELIVERY_FAILURE.update({
            "at": doc.now_iso(), "to": "…" + to[-3:], "status": status,
            "error_code": code, "reason": reason or "(no Twilio reason given)"})
        print(f"[quotebot] DELIVERY FAILED to ...{to[-3:]} — {status} {code}", flush=True)
        # Was the undelivered message itself one of our warnings? If so, stop here.
        was_warning = str(form.get("Body") or "").startswith(WARNING_MARK)
        background.add_task(_warn_delivery_failed, to, code, reason, was_warning)

    return _ack()


# A warning about an undelivered message is itself a message that can fail to be
# delivered. With one technician the "don't warn the number that just failed" rule
# ends it; with two it ping-pongs — A fails, warn B, B fails, warn A — forever, on a
# billed API. So warnings are marked, and a warning that fails never spawns another.
WARNING_MARK = "⚠️"          # the sign the note itself opens with
_warned_recently = {}
_warn_guard = threading.Lock()


def _warn_delivery_failed(to: str, code: str, reason: str, was_warning: bool) -> None:
    """Tell a technician a message did not arrive.

    Never tells the person it failed to reach — by definition we cannot reach them —
    and never warns about a warning, which is what makes this terminate.
    """
    if not QUOTE_TECHNICIANS or was_warning:
        return

    # One warning per number per five minutes. A phone that has dropped out of the
    # sandbox fails every single send, and without this the technician's own phone
    # becomes the outage.
    with _warn_guard:
        import time
        now = time.time()
        if now - _warned_recently.get(to, 0) < 300:
            return
        _warned_recently[to] = now

    note = [f"{WARNING_MARK} A message to {doc.display_phone(to)} did not arrive.", ""]
    if reason:
        note.append(reason)
    if code:
        note.append(f"(Twilio code {code})")
    for technician in QUOTE_TECHNICIANS:
        if technician == to:
            continue          # they cannot receive it either; that is the whole problem
        try:
            engine.say(technician, "\n".join(note))
        except Exception as exc:
            print(f"[quotebot] could not warn {technician}: {exc}", flush=True)


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

    # A number on the allowlist is ALWAYS the technician, so a quote sent to it can
    # never be replied to — the reply is read as the start of a new job instead.
    # Worth knowing, but NOT a blocker: after the demo roles are swapped round, the
    # new technician number is legitimately holding quotes from when it played the
    # customer, and nothing is wrong. Putting that in `blockers` would be telling
    # him to fix something that is fine, and a blocker list is only worth reading
    # if everything in it needs acting on. No phone number is returned either way.
    quoted_technicians = 0
    for number in QUOTE_TECHNICIANS:
        try:
            if store.latest_quote_for_phone(number):
                quoted_technicians += 1
        except Exception:
            break

    warnings = []
    if quoted_technicians:
        warnings.append(
            f"{quoted_technicians} of the {len(QUOTE_TECHNICIANS)} allowlisted "
            "technician number(s) is holding a quote of its own. It stays the "
            "technician, so it cannot reply to that quote — a reply from it starts a "
            "new job. Expected right after swapping the demo roles round; a problem "
            "only if that number was meant to be the customer.")

    # Does Railway agree with the repo about who the technicians are? quote_business.json
    # names them for the 'Quoted by' line; QUOTE_TECHNICIANS decides who may quote. They
    # are meant to be the same set, and when they drift the symptom is baffling: the
    # right phone is treated as a customer and answers its own job. Comparing them names
    # that in one line — and comparing SETS rather than printing them keeps this endpoint
    # free of phone numbers.
    named = set(doc.business().get("technicians", {}))
    listed = set(QUOTE_TECHNICIANS)
    config_agrees = (not listed and not named) or listed == named
    if listed and named and not config_agrees:
        blockers.append(
            f"QUOTE_TECHNICIANS on Railway ({len(listed)} number(s)) does not match the "
            f"technicians named in quote_business.json ({len(named)}). The allowlist is "
            "what decides who may quote, so if the wrong number is on it the right phone "
            "gets treated as a customer. Make them the same set.")

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
        "warnings": warnings or "none",
        "checks": checks,
        "roles": {
            "technicians_listed": len(QUOTE_TECHNICIANS),
            "allowlist_matches_quote_business_json": config_agrees,
            "allowlisted_numbers_already_quoted": quoted_technicians,
            "rule": ("A listed number is ALWAYS the technician. Anyone else holding a "
                     "quote from the last 60 days is the customer. Everyone else is "
                     "told to call the office."
                     if QUOTE_TECHNICIANS else
                     "No allowlist set — ANY number that reaches this bot may issue "
                     "quotes. Fine for a sandbox, wrong for a real business."),
        },
        "tables": tables,
        # "It doesn't reply" has two causes with one symptom: nothing is reaching us,
        # or replies are not leaving. This says which, without a key and without
        # exposing a phone number or a word of anyone's message.
        "traffic": store.activity_summary(24),
        "model": engine.MODEL,
        "env_with_stray_quotes": dirty,
        "last_signature_rejection": _LAST_REJECTION or "none since restart",
        "last_delivery_failure": _LAST_DELIVERY_FAILURE or "none since restart",
        "last_dispatch_failure": _LAST_DISPATCH_FAILURE or "none since restart",
        "telegram_notifications": "on" if TELEGRAM_ENABLED else "OFF (set TELEGRAM_ENABLED=1 to restore)",
        "payment_policy": {k: doc.payment_policy().get(k) for k in
                           ("enabled", "deposit_percent", "send_with_quote")},
        "last_payment_attempt": engine.LAST_PAYMENT_ATTEMPT or "none since restart",
        "twilio_sender": clean_env("TWILIO_WHATSAPP_FROM") or "(unset)",
        "paystack_mode": ("test" if paystack_key.startswith("sk_test_")
                          else "live" if paystack_key else "unset"),
        "base_url": public_base_url(),
    }


@router.get("/quotebot/channels")
def channels():
    """Can we actually reach a customer right now — WhatsApp, email, and payments?

    Separate from /quotebot/ready because this one makes real (read-only) calls to
    Twilio, Google and Paystack. Results are cached for 60s so an open endpoint can
    never be used to hammer someone else's API, and nothing here sends a message,
    an email or a payment.

    Config being PRESENT is not the same as it WORKING: a Twilio token can be rotated
    and a Google refresh token expires every seven days while the consent screen is in
    Testing mode. Both look identical from outside until you ask.
    """
    from services import delivery_health
    result = delivery_health.all_channels()
    broken = [name for name, r in result.items() if not r.get("ok")]
    # Credentials being accepted is not the same as messages arriving. This asks
    # Twilio what actually happened to the last ones we sent.
    deliveries = delivery_health.recent_deliveries(15)
    return {
        "build": BUILD,
        "all_working": not broken and deliveries.get("ok", True),
        "not_working": broken or "none",
        "delivery": deliveries,
        "channels": result,
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
