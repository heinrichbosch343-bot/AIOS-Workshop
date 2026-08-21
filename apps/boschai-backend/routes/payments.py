"""Paystack webhooks: the moment a quote turns into money.

Three defences, because this endpoint marks a customer's money as received:

1. **Signature.** Paystack signs the raw body with the secret key. Unsigned, it is a
   button that marks any quote paid.
2. **Idempotency.** `payment_events.event_id` is UNIQUE. Payment gateways retry hard,
   and telling a customer twice that their money is in — while the office reconciles
   a double payment that never happened — is worse than being slow.
3. **Verification.** The webhook body is only a hint. Before anything is written down
   we ask Paystack directly what happened to that reference. A webhook is something
   that arrived over the internet; `verify()` is the truth.
"""
import json

from fastapi import APIRouter, BackgroundTasks, Request, Response

from config import API_SECRET_KEY
from services import payments
from services import quote_doc as doc
from services import quote_engine as engine
from services import quote_store as store

router = APIRouter()


def _settle(reference: str, event_id: str, event: str, payload: dict) -> None:
    """Confirm the payment with Paystack, then record it and tell everyone."""
    quote = store.quote_by_payment_reference(reference)
    if not quote:
        print(f"[payments] no quote for reference {reference}", flush=True)
        return

    try:
        confirmed = payments.verify(reference)
    except Exception as exc:
        print(f"[payments] could not verify {reference}: {exc}", flush=True)
        return

    if not confirmed["paid"]:
        # Paystack sends events for failed and abandoned attempts too. Recording the
        # attempt is useful; calling it paid would not be.
        store.update_quote(quote["id"], {"payment_status": "failed",
                                         "payment_error": confirmed.get("gateway_response")})
        print(f"[payments] {reference} is {confirmed['status']}, not settling", flush=True)
        return

    if quote.get("payment_status") == "paid":
        print(f"[payments] {reference} already settled, ignoring", flush=True)
        return

    store.update_quote(quote["id"], {
        "payment_status": "paid",
        "paid_at": confirmed.get("paid_at") or doc.now_iso(),
        "paid_amount": confirmed["amount_rand"],
        "paid_channel": confirmed.get("channel"),
        "payment_error": None,
    })
    engine.payment_received(quote, confirmed["amount_rand"], confirmed.get("channel") or "")
    print(f"[payments] {reference} settled: {confirmed['amount_rand']}", flush=True)


@router.post("/webhook/paystack")
async def paystack_webhook(request: Request, background: BackgroundTasks):
    """Paystack posts here on every payment event.

    Answers immediately and does the work in the background — Paystack retries a slow
    endpoint, and verification plus two WhatsApp sends is not fast.
    """
    raw = await request.body()

    if not payments.enabled():
        return Response(status_code=503)

    if not payments.valid_signature(raw, request.headers.get("x-paystack-signature", "")):
        print("[payments] rejected: bad Paystack signature", flush=True)
        return Response(status_code=403)

    try:
        body = json.loads(raw.decode("utf-8"))
    except Exception:
        return Response(status_code=400)

    data = body.get("data") or {}
    event = body.get("event", "")
    reference = data.get("reference", "")
    # Paystack does not always send an id, so fall back to something stable per event
    # and reference — the point is that a retry of the SAME thing collides.
    event_id = str(data.get("id") or f"{event}:{reference}")

    if not store.log_payment_event(event_id=event_id, event=event, reference=reference,
                                   amount=payments.to_rand(data.get("amount") or 0),
                                   currency=data.get("currency"),
                                   status=data.get("status"), payload=body):
        print(f"[payments] ignoring repeat of {event_id}", flush=True)
        # 200, not an error: a duplicate handled correctly is a success, and anything
        # else makes Paystack retry it again.
        return Response(status_code=200)

    print(f"[payments] {event} {reference} {data.get('status')}", flush=True)

    if event == "charge.success" and reference:
        background.add_task(_settle, reference, event_id, event, body)

    return Response(status_code=200)


@router.get("/quotebot/payments")
def payment_status(key: str = ""):
    """Is the payment side configured, and is it live or in test mode?

    The test/live distinction is the one worth surfacing loudly: a test key produces
    checkout pages that look completely real and move no money whatsoever.
    """
    if not API_SECRET_KEY or key != API_SECRET_KEY:
        return Response(status_code=403)

    policy = doc.payment_policy()
    configured = payments.enabled()
    return {
        "configured": configured,
        "mode": ("TEST — links look real, no money moves" if configured
                 and payments.is_test_key() else "LIVE" if configured else "not set up"),
        "enabled_in_business_json": bool(policy.get("enabled")),
        "deposit_percent": policy.get("deposit_percent"),
        "sends_link_with_quote": bool(policy.get("send_with_quote")),
        "webhook_url": "/webhook/paystack",
        "recent": store.recent_payment_events(15),
    }
