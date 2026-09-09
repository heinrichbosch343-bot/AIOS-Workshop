"""Can we actually reach the customer right now — on WhatsApp, and by email?

Configuration being *present* is not the same as it *working*. A Twilio token can be
rotated, a Google refresh token dies the moment the account password changes (Gmail
scopes are invalidated on a password change), and both failures look identical from
outside: the quote goes out, or it doesn't, and nobody knows why.

So this asks each provider directly, with a read-only call that sends nothing to anyone.

Cached for 60 seconds, because it hangs off an unguarded probe and nothing here should
be a way to make our backend hammer someone else's API.
"""
import time

import httpx

from config import clean_env

_CACHE = {}
_TTL = 60


def _cached(key: str, fn):
    now = time.time()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        value = fn()
    except Exception as exc:                      # never let a probe raise
        value = {"ok": False, "detail": str(exc)[:200]}
    _CACHE[key] = (now, value)
    return value


def whatsapp_health() -> dict:
    """Ask Twilio whether our credentials are still good, and what the sender is.

    Fetching the account is the cheapest authenticated call there is: it proves the SID
    and token together, without touching a message.
    """
    def check():
        sid = clean_env("TWILIO_ACCOUNT_SID")
        token = clean_env("TWILIO_AUTH_TOKEN")
        sender = clean_env("TWILIO_WHATSAPP_FROM")
        if not sid or not token:
            return {"ok": False, "detail": "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN not set"}
        if not sender:
            return {"ok": False, "detail": "TWILIO_WHATSAPP_FROM not set — nothing to send from"}

        resp = httpx.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}.json",
                         auth=(sid, token), timeout=15)
        if resp.status_code == 401:
            return {"ok": False, "detail": "Twilio rejected the credentials (401)"}
        if resp.status_code >= 400:
            return {"ok": False, "detail": f"Twilio returned {resp.status_code}"}

        body = resp.json()
        sandbox = "14155238886" in sender
        return {
            "ok": body.get("status") == "active",
            "sender": sender,
            "account_status": body.get("status"),
            "mode": "sandbox" if sandbox else "production number",
            "detail": ("Sandbox: every recipient must have sent the join code, and "
                       "membership lapses after 72h idle." if sandbox else
                       "Production number — recipients outside the 24h window need an "
                       "approved template."),
        }
    return _cached("whatsapp", check)


def email_health() -> dict:
    """Whether the Gmail connector can still authenticate, and as whom.

    The consent screen is published, so the refresh token has no expiry clock. It dies
    on a Google password change, on revocation, or after six months unused - which is
    why a quote that emailed fine last week can silently stop.
    getProfile is read-only and sends nothing.
    """
    def check():
        from googleapiclient.discovery import build
        from services.drive import get_credentials

        creds = get_credentials()
        profile = build("gmail", "v1", credentials=creds).users().getProfile(
            userId="me").execute()
        return {
            "ok": True,
            "sending_as": profile.get("emailAddress"),
            "detail": ("Quotes are emailed from this mailbox. For a real client install "
                       "this should be THEIR address, not Boschly's."),
        }

    result = _cached("email", check)
    if not result.get("ok"):
        detail = str(result.get("detail", ""))
        if "No Google token" in detail:
            result = {**result, "fix": "Visit /auth/google once to connect the mailbox."}
        elif "invalid_grant" in detail or "expired" in detail.lower():
            result = {**result, "fix": ("The Google refresh token is no longer valid. The "
                                        "consent screen is published, so the usual cause is "
                                        "a Google account password change, which invalidates "
                                        "tokens carrying Gmail scopes. Re-authorise at "
                                        "/auth/google.")}
    return result


def payments_health() -> dict:
    """Whether Paystack accepts our key, and whether it can actually move money."""
    def check():
        key = clean_env("PAYSTACK_SECRET_KEY")
        if not key:
            return {"ok": False, "detail": "PAYSTACK_SECRET_KEY not set"}
        resp = httpx.get("https://api.paystack.co/transaction/totals",
                         headers={"Authorization": f"Bearer {key}"}, timeout=15)
        if resp.status_code == 401:
            return {"ok": False, "detail": "Paystack rejected the key (401)"}
        if resp.status_code >= 400:
            return {"ok": False, "detail": f"Paystack returned {resp.status_code}"}
        test = key.startswith("sk_test_")
        return {
            "ok": True,
            "mode": "TEST" if test else "LIVE",
            "detail": ("Test mode: checkout pages look completely real and no money "
                       "moves." if test else "LIVE — real cards will be charged."),
        }
    return _cached("payments", check)


def recent_deliveries(limit: int = 15) -> dict:
    """What Twilio says actually HAPPENED to the last messages we sent.

    Our own log records what we handed to Twilio, which is not the same thing at all.
    Twilio accepts a send, returns 201, and then fails to deliver it asynchronously —
    so a bot that looks like it is replying can be reaching nobody. That gap is
    exactly where every "it doesn't work" afternoon has been spent.

    Twilio knows the answer: each message carries a status (delivered / sent / failed /
    undelivered) and an error code. 63015 and 63016 both mean the sandbox — the
    recipient never joined, or their 24-hour window has closed.

    Phone numbers are reduced to their last three digits. Enough to tell two demo
    phones apart, not enough to be anyone's contact details on an open endpoint.
    """
    def check():
        sid = clean_env("TWILIO_ACCOUNT_SID")
        token = clean_env("TWILIO_AUTH_TOKEN")
        if not sid or not token:
            return {"ok": False, "detail": "Twilio credentials not set"}

        resp = httpx.get(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                         params={"PageSize": limit}, auth=(sid, token), timeout=20)
        if resp.status_code >= 400:
            return {"ok": False, "detail": f"Twilio returned {resp.status_code}"}

        from services.whatsapp import FRIENDLY, SANDBOX_HINT

        messages, failures = [], 0
        for m in (resp.json().get("messages") or [])[:limit]:
            code = m.get("error_code")
            status = m.get("status")
            if status in ("failed", "undelivered"):
                failures += 1
            row = {
                "at": m.get("date_sent") or m.get("date_created"),
                "direction": "out" if str(m.get("direction", "")).startswith("outbound")
                             else "in",
                "to": "…" + str(m.get("to") or "")[-3:],
                "status": status,
            }
            if code:
                row["error_code"] = code
                row["error"] = (FRIENDLY.get(int(code)) if str(code).isdigit()
                                else None) or m.get("error_message") or ""
                if str(code) in ("63015", "63016"):
                    row["error"] = SANDBOX_HINT if str(code) == "63015" else row["error"]
            messages.append(row)

        undelivered = [m for m in messages
                       if m["direction"] == "out"
                       and m["status"] in ("failed", "undelivered")]
        if undelivered:
            codes = sorted({str(m.get("error_code")) for m in undelivered})
            reading = (f"{len(undelivered)} of the last outbound messages did NOT reach "
                       f"the phone (Twilio codes {', '.join(codes)}). The bot is "
                       "replying; the replies are not arriving.")
        elif any(m["direction"] == "out" for m in messages):
            reading = ("Every recent outbound message was accepted and delivered by "
                       "Twilio. If a phone still shows nothing, it is looking at a "
                       "different chat or a different number.")
        else:
            reading = "Twilio has no recent outbound messages on this account."

        return {"ok": failures == 0, "reading": reading, "messages": messages}

    return _cached(f"deliveries-{limit}", check)


def all_channels() -> dict:
    return {"whatsapp": whatsapp_health(),
            "email": email_health(),
            "payments": payments_health()}
