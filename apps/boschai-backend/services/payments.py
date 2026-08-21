"""Paystack: turning a quote into a link the customer can tap.

One rule runs through this file: **money is in cents when it touches Paystack, and in
rand everywhere else.** Paystack's API takes the smallest currency unit, so R11 500.00
goes over the wire as 1150000. Converting in two places is how somebody gets charged
a hundred times the quote, so the conversion happens here and nowhere else.

The other rule: nothing in this file decides whether to charge, or how much. It is
handed an amount and it makes a link. `quote_business.json` owns the deposit policy.
"""
import hashlib
import hmac
import json
import os
import secrets
from decimal import ROUND_HALF_UP, Decimal

import httpx

API = "https://api.paystack.co"
TIMEOUT = 30


class PaymentError(RuntimeError):
    """Something Paystack refused, phrased for a human."""


def enabled() -> bool:
    return bool(os.getenv("PAYSTACK_SECRET_KEY", "").strip())


def _secret() -> str:
    key = os.getenv("PAYSTACK_SECRET_KEY", "").strip()
    if not key:
        raise PaymentError("PAYSTACK_SECRET_KEY is not set.")
    return key


def is_test_key() -> bool:
    """Worth surfacing loudly. A test key produces links that look completely real and
    move no money at all — exactly the thing to discover before a demo, not during."""
    return _secret().startswith("sk_test_")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_secret()}", "Content-Type": "application/json"}


def to_cents(rand) -> int:
    """R11 500.00 -> 1150000.

    Decimal, not float, and `Decimal(str(x))` rather than `Decimal(x)` — converting the
    float's *string* form is what leaves the binary noise behind. Done in plain floats,
    round(1234.565 * 100) gives 123456 rather than 123457, because 1234.565 is really
    1234.56499… once stored. That is a cent, and a cent between the quote and the
    payment link is a reconciliation nobody can close.

    ROUND_HALF_UP because it is the rounding a person would do by hand and can be
    explained to a customer. Python's default rounds half to even, which is correct for
    statistics and surprising on an invoice.
    """
    return int((Decimal(str(rand)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def to_rand(cents) -> float:
    return float((Decimal(int(cents)) / 100).quantize(Decimal("0.01"),
                                                      rounding=ROUND_HALF_UP))


def new_reference(quote_number: str) -> str:
    """Readable enough to reconcile by eye, unique enough that a retry cannot collide
    with the first attempt — Paystack rejects a reference it has already seen."""
    return f"{quote_number}-{secrets.token_hex(3)}"


def create_link(*, amount_rand, email: str, reference: str, quote: dict,
                callback_url: str = "") -> dict:
    """Create a hosted checkout link. Returns {'url', 'reference', 'access_code'}.

    `email` is required by Paystack and is where it sends the receipt. Plenty of jobs
    are quoted with only a phone number, so the caller passes a synthetic address in
    that case rather than failing — the customer still gets the link on WhatsApp,
    which is the channel that matters here.
    """
    payload = {
        "email": email,
        "amount": to_cents(amount_rand),
        "currency": quote.get("currency", "ZAR"),
        "reference": reference,
        "metadata": {
            "quote_number": quote.get("quote_number"),
            "customer_name": quote.get("customer_name"),
            "customer_phone": quote.get("customer_phone"),
            "quote_total": str(quote.get("total")),
            # Shown on Paystack's own dashboard, so the office sees what a payment was
            # for without opening anything else.
            "custom_fields": [
                {"display_name": "Quote", "variable_name": "quote",
                 "value": str(quote.get("quote_number"))},
                {"display_name": "Customer", "variable_name": "customer",
                 "value": str(quote.get("customer_name"))},
            ],
        },
    }
    if callback_url:
        payload["callback_url"] = callback_url

    try:
        resp = httpx.post(f"{API}/transaction/initialize", headers=_headers(),
                          json=payload, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise PaymentError(f"Could not reach Paystack: {exc}") from exc

    body = _json(resp)
    if resp.status_code >= 400 or not body.get("status"):
        raise PaymentError(body.get("message") or f"Paystack returned {resp.status_code}")

    data = body.get("data") or {}
    if not data.get("authorization_url"):
        raise PaymentError("Paystack returned no checkout URL.")
    return {"url": data["authorization_url"], "reference": data.get("reference", reference),
            "access_code": data.get("access_code")}


def verify(reference: str) -> dict:
    """Ask Paystack directly what happened to a reference.

    The webhook is the fast path; this is the truth. Anything that changes money is
    confirmed here before it is written down, because a webhook body is just something
    that arrived over the internet.
    """
    try:
        resp = httpx.get(f"{API}/transaction/verify/{reference}",
                         headers=_headers(), timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise PaymentError(f"Could not reach Paystack: {exc}") from exc

    body = _json(resp)
    if resp.status_code >= 400 or not body.get("status"):
        raise PaymentError(body.get("message") or f"Paystack returned {resp.status_code}")

    data = body.get("data") or {}
    return {
        "paid": data.get("status") == "success",
        "status": data.get("status"),
        "reference": data.get("reference"),
        "amount_rand": to_rand(data.get("amount") or 0),
        "currency": data.get("currency"),
        "channel": data.get("channel"),
        "paid_at": data.get("paid_at"),
        "gateway_response": data.get("gateway_response"),
    }


def valid_signature(raw_body: bytes, signature: str) -> bool:
    """Paystack signs every webhook: HMAC-SHA512 of the raw body, keyed on the SECRET
    key. Computed over the exact bytes received — re-serialising the JSON first changes
    whitespace and key order and the signature will never match.

    Without this the endpoint is a button that marks any quote paid."""
    if not signature:
        return False
    digest = hmac.new(_secret().encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(digest, signature)


def _json(resp) -> dict:
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        return {"status": False, "message": resp.text[:300]}
