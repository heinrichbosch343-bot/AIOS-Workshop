"""Can we actually reach the customer right now — on WhatsApp, and by email?

Configuration being *present* is not the same as it *working*. A Twilio token can be
rotated, a Google refresh token expires every seven days while the OAuth consent screen
sits in Testing mode, and both failures look identical from outside: the quote goes out,
or it doesn't, and nobody knows why.

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

    The refresh token behind this expires every seven days while the Google project is
    in Testing mode, which is why a quote that emailed fine last week silently stops.
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
            result = {**result, "fix": ("The Google refresh token has expired — this "
                                        "happens every 7 days while the OAuth consent "
                                        "screen is in Testing mode. Re-authorise at "
                                        "/auth/google, or publish the consent screen.")}
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


def all_channels() -> dict:
    return {"whatsapp": whatsapp_health(),
            "email": email_health(),
            "payments": payments_health()}
