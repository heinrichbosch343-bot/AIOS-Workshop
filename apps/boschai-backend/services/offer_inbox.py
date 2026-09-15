"""Replies to offers, read straight out of the mailbox.

The offer desk saves a merchant a draft; a person sends it; the merchant writes
back into the same Gmail account. For each send the desk is tracking this finds
both halves: whether the draft actually went out (in:sent, to them, after the
offer date) and what has come back since (from them, after the offer date), and
asks the model what the newest reply means.

The model understands; the desk decides. What comes back is a label and one
sentence of reason and nothing else. Which stage a buyer lands on, and whether a
stage may ever move down, is settled in the desk's own code, where it is tested.
A classification that fails still returns the replies, so a model outage never
hides a buyer who wrote back.
"""
import json
import re
from datetime import datetime, timezone

from anthropic import Anthropic

from config import clean_env
from services import email as mail

MODEL = clean_env("OFFER_MODEL") or clean_env("QUOTE_MODEL") or "claude-sonnet-4-6"
LABELS = ("committed", "interested", "question", "declined", "other")
MAX_REPLIES = 10
MAX_TEXT = 4000

_client = None


def _ai() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=clean_env("ANTHROPIC_API_KEY"))
    return _client


SYSTEM = """You read replies from wholesale buyers to a closeout offer email sent by a liquidation distributor. The offer listed products, quantities and a cost per unit, and asked the buyer which lines they want.

You are given the buyer's replies to one offer, oldest first. Say what the NEWEST one means. Reply with JSON only, no prose, no code fences:

{"label": "committed" | "interested" | "question" | "declined" | "other", "reason": "one short sentence, under 20 words"}

committed: they are taking it. Confirming quantities, sending a PO, agreeing the price.
interested: they want some or all of it but have not confirmed. Asking to hold stock, asking for a best price on lines they name, saying they will confirm.
question: they need something before deciding. Photos, dates, a breakdown, a split.
declined: they are passing on this offer.
other: anything else. Out of office, unrelated, a forward, thanks with no decision.

Never put words in their mouth. A question about price is "question", not "interested", unless they also say they want it."""


# ───────────────────────────────────────────────────────────────── time helpers

def _epoch_seconds(iso: str) -> int:
    value = (iso or "").strip()
    if not value:
        return 0
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


# ───────────────────────────────────────────────────────────── the buyer's words

# Where the quoted history starts. Everything below one of these is our own
# email coming back, and feeding it to the model is how a reply that says
# "no thanks" under a quoted offer gets read as an offer.
_QUOTED = re.compile(
    r"(?m)^(On .{0,300}?wrote:\s*$"
    r"|-{2,}\s*Original Message\s*-{2,}"
    r"|From:\s.+\n(Sent|Date):\s)",
    re.I | re.S,
)


def own_words(text: str) -> str:
    """The part of a reply the buyer typed, without the thread underneath it."""
    text = text or ""
    match = _QUOTED.search(text)
    if match:
        text = text[:match.start()]
    lines = [line for line in text.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()[:MAX_TEXT]


# ──────────────────────────────────────────────────────────────── gmail lookups

def _refs(gmail, q: str, n: int) -> list[dict]:
    listing = gmail.users().messages().list(userId="me", q=q, maxResults=n).execute()
    return listing.get("messages", []) or []


def find_sent(gmail, email: str, since_s: int) -> dict | None:
    """The first email to this address after the offer date, if one went out."""
    earliest = None
    for ref in _refs(gmail, f"in:sent to:{email} after:{since_s}", 5):
        msg = gmail.users().messages().get(userId="me", id=ref["id"], format="metadata").execute()
        ms = int(msg.get("internalDate", "0") or "0")
        if ms and (earliest is None or ms < earliest["ms"]):
            earliest = {"message_id": msg["id"], "ms": ms}
    if earliest is None:
        return None
    return {"message_id": earliest["message_id"], "at": _iso(earliest["ms"])}


def find_replies(gmail, email: str, since_s: int, after_ms: int) -> list[dict]:
    """Every email from this address since the offer went out, newer than after_ms."""
    out = []
    for ref in _refs(gmail, f"from:{email} after:{since_s} -in:sent -in:draft", MAX_REPLIES):
        msg = gmail.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        ms = int(msg.get("internalDate", "0") or "0")
        if ms <= after_ms:
            continue
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        from_value = mail._header(headers, "From")
        # A bounce or an auto-responder is not the buyer speaking.
        if mail._is_automated(headers, from_value):
            continue
        out.append({
            "message_id": msg["id"],
            "at": _iso(ms),
            "subject": mail._header(headers, "Subject") or "",
            "text": own_words(mail._extract_body(payload)) or msg.get("snippet", ""),
            "_ms": ms,
        })
    out.sort(key=lambda r: r["_ms"])
    for r in out:
        r.pop("_ms", None)
    return out


# ────────────────────────────────────────────────────────────────── the reading

def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON in model reply: {cleaned[:200]}")
    return json.loads(cleaned[start:end + 1])


def classify(offer_name: str, replies: list[dict]) -> dict:
    """What the newest reply means. Never raises: a failure is reported, not thrown."""
    payload = {
        "offer": offer_name or "a closeout offer",
        "replies": [{"at": r["at"], "text": r["text"]} for r in replies[-5:]],
    }
    try:
        resp = _ai().messages.create(
            model=MODEL, max_tokens=200, system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        data = _extract_json(resp.content[0].text)
    except Exception as exc:  # noqa: BLE001 - the replies must still go back
        return {"label": None, "reason": None, "error": str(exc)[:200]}

    label = str(data.get("label") or "").strip().lower()
    reason = str(data.get("reason") or "").strip()[:200]
    return {"label": label if label in LABELS else "other", "reason": reason}


def check(sends: list[dict]) -> dict:
    """One pass over the mailbox for every send the desk asked about."""
    gmail = mail._gmail()
    results = []
    for send in sends:
        since_s = _epoch_seconds(send.get("since", ""))
        after_ms = int(send.get("after_ms") or 0)
        email = send["email"].strip().lower()

        replies = find_replies(gmail, email, since_s, after_ms)
        reading = classify(send.get("offer_name", ""), replies) if replies else {"label": None, "reason": None}
        results.append({
            "id": send["id"],
            "sent": find_sent(gmail, email, since_s),
            "replies": replies,
            "label": reading.get("label"),
            "reason": reading.get("reason"),
            "error": reading.get("error"),
        })

    return {"mailbox": mail.own_address(), "sends": results}
