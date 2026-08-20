"""Twilio WhatsApp: sending text and media, and the errors worth naming.

WhatsApp has a 24-hour customer service window. If the person messaged us in the
last 24 hours we may send ordinary text and media freely. Outside it, every send
must be a pre-approved template.

The Twilio SANDBOX has no templates at all, so everything here is free-form and
the window is what matters: joining the sandbox opens one. That is fine for a
demo where both phones are ours. Production swaps `send_text` for a template
send — see claude-vault/modules/review-booster/reference/whatsapp-setup.md.
"""
import os

import httpx

API_ROOT = "https://api.twilio.com/2010-04-01"
TIMEOUT = 30


class WhatsAppError(RuntimeError):
    """Something Twilio or Meta refused, phrased for a human."""


# Twilio codes that mean something specific and fixable. Anything else is
# reported raw, because a vague guess is worse than Twilio's own words.
FRIENDLY = {
    63016: ("Outside the 24-hour window, so free-form text was refused. In the sandbox: "
            "have that phone send any message to the sandbox number to reopen it. "
            "In production this has to be an approved template."),
    63018: "Rate limited by WhatsApp — sending too much, too fast.",
    63003: ("Twilio could not find that WhatsApp sender. Check TWILIO_WHATSAPP_FROM is "
            "the sandbox number in the form whatsapp:+14155238886."),
    63007: "That number is not a WhatsApp sender on this Twilio account.",
    63005: "That number has no WhatsApp, or has blocked this sender.",
    21211: "That is not a valid phone number.",
    20003: "Twilio rejected the credentials. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN.",
    21610: "That number opted out of this sender (replied STOP).",
}

# The sandbox refuses anyone who has not sent the join code. Worth its own message
# because it is by far the most common demo-day failure.
SANDBOX_HINT = ("That number has not joined the Twilio sandbox. Send the join code "
                "from it once (Messaging -> Try it out -> Send a WhatsApp message).")


def _auth() -> tuple[str, str]:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not sid or not token:
        raise WhatsAppError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are not set.")
    return sid, token


def sender() -> str:
    """Our WhatsApp number, always in Twilio's `whatsapp:+…` form."""
    raw = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
    if not raw:
        raise WhatsAppError(
            "TWILIO_WHATSAPP_FROM is not set. For the sandbox this is the number Twilio "
            "shows on the 'Send a WhatsApp message' page, e.g. whatsapp:+14155238886."
        )
    return raw if raw.startswith("whatsapp:") else f"whatsapp:{raw}"


def _to(number: str) -> str:
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


def _post(payload: dict) -> dict:
    sid, token = _auth()
    resp = httpx.post(
        f"{API_ROOT}/Accounts/{sid}/Messages.json",
        data=payload, auth=(sid, token), timeout=TIMEOUT,
    )
    if resp.status_code >= 400:
        try:
            body = resp.json()
            code, message = body.get("code"), body.get("message", resp.text)
        except Exception:
            code, message = None, resp.text[:400]
        hint = FRIENDLY.get(code)
        if code == 63016 and "sandbox" in str(message).lower():
            hint = SANDBOX_HINT
        raise WhatsAppError(f"{hint or message} (Twilio code {code})")
    return resp.json()


def send_text(to: str, body: str) -> dict:
    """Free-form message. Only legal inside the recipient's 24-hour window."""
    return _post({"From": sender(), "To": _to(to), "Body": body})


def send_media(to: str, body: str, media_url: str) -> dict:
    """Free-form message with one attachment. `media_url` must be publicly reachable —
    Twilio fetches it from its own servers, so localhost will not do."""
    return _post({"From": sender(), "To": _to(to), "Body": body, "MediaUrl": media_url})
