"""The conversation: what the technician meant, and what happens next.

The division of labour here is the whole design.

  The model understands and speaks.  It reads the thread, works out what he meant,
  merges the new facts into the job, and writes the sentence he gets back.

  The code decides and sends.  It works out what is still missing, whether a quote
  may go out, what it is numbered, what the figures are, and who receives it.

The model is never asked to type a price and can never cause a send on its own. It
returns `action: "send"`; this file then checks the job is complete and that he has
actually SEEN the card before anything reaches a customer. That is the step which
stops a mistyped digit putting one person's quote on a stranger's phone.
"""
import json
import os
import re
from datetime import datetime, timedelta

from anthropic import Anthropic

from config import clean_env, public_base_url
from services import quote_doc as doc
from services import payments
from services import quote_store as store
from services import whatsapp

MODEL = clean_env("QUOTE_MODEL") or "claude-sonnet-4-6"

_client = None


def _ai() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=clean_env("ANTHROPIC_API_KEY"))
    return _client


# ─────────────────────────────────────────────────────────────────── the prompt

SYSTEM = """You are the quote assistant for {business}, a South African {trade} company.

A technician messages you from site, in whatever words come out — often one-handed,
often in a mix of English and Afrikaans, often with typos. Your job is to understand
him well enough that a quote can go to the customer within a minute of him finishing
the job.

You will be given the job assembled so far, the recent conversation, and his newest
message. Reply with JSON only — no prose, no code fences:

{{
  "action": "ask" | "confirm" | "send" | "cancel" | "chat",
  "replace_job": false,
  "job": {{
    "customer_name": string or null,
    "customer_phone": string or null,
    "customer_email": string or null,
    "site_address": string or null,
    "line_items": [{{"description": string, "amount": number or null}}],
    "total": number or null,
    "notes": string or null
  }},
  "reply": string
}}

CHOOSING THE ACTION
- "send"    — he is approving the quote he was just shown. Anything that means yes:
              "send", "SEND", "stuur dit", "ja", "yes send it to her", "ok go", a
              thumbs up. Also when he swipe-replies to the card and adds a yes.
- "cancel"  — scrap it, start over, wrong customer, "no forget it".
- "chat"    — he asked you something ("what's the total?", "did that go through?")
              or said something that changes nothing. Answer him in `reply`.
- "confirm" — you now have everything a quote needs: a customer name, a contact
              number, what the work was, and a price.
- "ask"     — something is still missing. Ask for the missing thing, nothing else.

READING THE JOB
- Always return the job COMPLETE — carry forward every fact that is still true, not
  only what changed. A field you leave null that you were given earlier is a fact the
  business loses.
- Set "replace_job": true ONLY when this is plainly a different customer or a
  different job, not a correction to the current one. Then return only the new facts.
- Money: "R11 500", "11500", "11.5k", "eleven five" all mean 11500. Never invent a
  price and never round one.
- Break the work into line items when he describes separate pieces of work with
  separate prices. One lump price is one line item. If the amounts add up to his
  stated total, keep them; if they conflict, trust the total he stated and say so in
  `reply`.
- Write line item descriptions in clean, professional English — this text is printed
  on a document the customer keeps. Fix his typos and shorthand, but never add work
  he did not mention. "2 slidin panels lounge 6.38 lam" becomes "2 x sliding panels,
  lounge — 6.38 laminated safety glass".
- A phone number belongs in customer_phone, never in a description.

WRITING THE REPLY
- One or two short lines. He is standing next to his bakkie.
- Plain South African register. "Got it." "Nice one." "What's her number?"
- NEVER write a price, a total or a quote number in `reply`. The system prints those
  itself, underneath your words, so they always match the document. If you write a
  number too it will appear twice and one of them may be wrong.
- For "ask": ask only for what is missing, in one sentence.
- For "confirm": a short lead-in only — "Here it is." The figures follow automatically.
- For "chat": answer him properly, using the job in front of you.
"""


def _system_prompt() -> str:
    biz = doc.business()
    return SYSTEM.format(business=biz["name"], trade="glass and aluminium")


def _extract_json(text: str) -> dict:
    """Models occasionally wrap JSON in fences or add a sentence. Take the outermost
    object and parse that."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON in model reply: {cleaned[:200]}")
    return json.loads(cleaned[start:end + 1])


def understand(session: dict, message: str) -> dict:
    """One model call. Returns the raw decision; the caller validates it."""
    payload = {
        "job_so_far": session.get("job") or {},
        "conversation": (session.get("history") or [])[-10:],
        "state": session.get("state"),
        "new_message": message,
    }
    resp = _ai().messages.create(
        model=MODEL, max_tokens=1600, system=_system_prompt(),
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
    )
    return _extract_json(resp.content[0].text)


# ───────────────────────────────────────────────────── merging and validating a job

_SCALARS = ("customer_name", "customer_phone", "customer_email", "site_address",
            "notes")


def merge_job(old: dict, new: dict, replace: bool = False) -> dict:
    """Facts can be added or changed, never silently dropped.

    The model is told to return the job complete, but "told to" is not a guarantee,
    and a quote that quietly loses the customer's phone number is worse than almost
    any other failure here. So a null from the model leaves the existing value alone;
    only `replace_job` (a genuinely different customer) starts from nothing.
    """
    merged = {} if replace else dict(old or {})
    new = new or {}

    for key in _SCALARS:
        value = new.get(key)
        if value not in (None, "", []):
            merged[key] = value

    items = new.get("line_items")
    if items:
        merged["line_items"] = [
            {"description": str(i.get("description") or "").strip(),
             "amount": _number(i.get("amount"))}
            for i in items if str(i.get("description") or "").strip()
        ]

    total = _number(new.get("total"))
    if total is not None:
        merged["total"] = total

    # A single priced line and no stated total means the line IS the total.
    if merged.get("total") is None:
        amounts = [i["amount"] for i in merged.get("line_items", [])
                   if i.get("amount") is not None]
        if amounts and len(amounts) == len(merged.get("line_items", [])):
            merged["total"] = sum(amounts)

    phone = doc.normalize_sa_phone(merged.get("customer_phone"))
    if phone:
        merged["customer_phone"] = phone
    merged.setdefault("currency", "ZAR")
    return merged


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def missing_from(job: dict) -> list:
    """What a quote cannot go out without. A rule, not a judgement, so code owns it."""
    gaps = []
    if not (job.get("customer_name") or "").strip():
        gaps.append("the customer's name")
    if not doc.normalize_sa_phone(job.get("customer_phone")):
        gaps.append("a contact number for them")
    if not [i for i in job.get("line_items") or [] if i.get("description")]:
        gaps.append("what the work was")
    if not job.get("total") or float(job["total"]) <= 0:
        gaps.append("the price")
    return gaps


# ─────────────────────────────────────────────────────────────── talking back

def say(to: str, body: str, role: str = "bot", decision: dict = None) -> None:
    whatsapp.send_text(to, body)
    store.log_outbound(to_number=to, body=body, role=role, decision=decision)


def _remember(session: dict, who: str, said: str) -> None:
    session.setdefault("history", []).append({"who": who, "said": said})


HELP = ("*Quote bot*\n\n"
        "Tell me the job the way you'd say it out loud — who it's for, their number, "
        "what you did and what it costs.\n\n"
        "_Sarah Adams, 082 555 1234, sarah@gmail.com — 2 sliding panels in the lounge, "
        "6.38 laminated, replaced both tracks, R11 500_\n\n"
        "I'll write it up and show you first. Nothing goes to the customer until you "
        "say so.")


def _card(job: dict, lead_in: str) -> str:
    """His words from the model on top, the figures from code underneath."""
    lead = (lead_in or "Here it is.").strip()
    return f"{lead}\n\n{doc.summary_card(job)}\n\nSend it?"


# ───────────────────────────────────────────────────────────────── the main turn

def handle_technician(technician: str, body: str, message_sid: str = "") -> None:
    """One inbound message from a technician, start to finish."""
    text = (body or "").strip()
    session = store.get_session(technician)

    if not text:
        say(technician, HELP)
        return

    try:
        decision = understand(session, text)
    except Exception as exc:
        print(f"[quotebot] model failed for {technician}: {exc}", flush=True)
        say(technician, "Sorry — my side glitched reading that. Send it again?")
        store.record_decision(message_sid, {"error": str(exc)[:400]})
        return

    action = str(decision.get("action") or "ask").lower()
    reply = str(decision.get("reply") or "").strip()

    _remember(session, "technician", text)

    # ── scrap it
    if action == "cancel":
        store.clear_session(technician)
        store.record_decision(message_sid, {"action": "cancel"})
        say(technician, reply or "Cleared. Send me the next job when you're ready.")
        return

    # ── merge whatever facts came with the message, WHATEVER the action was.
    # A single message can approve and correct in the same breath ("ja but make it
    # 1200"), and "…and send it now" on a first message carries the entire job. Taking
    # the facts only on an "ask" or "confirm" meant a complete job arriving with an
    # approval was answered with "I still need the customer's name".
    if decision.get("job"):
        session["job"] = merge_job(session.get("job") or {}, decision["job"],
                                   replace=bool(decision.get("replace_job")))
    job = session.get("job") or {}
    gaps = missing_from(job)

    # ── a question, or something that changes nothing
    if action == "chat":
        _remember(session, "bot", reply)
        store.save_session(session)
        store.record_decision(message_sid, {"action": "chat"})
        say(technician, reply or "Not sure I follow — say that again?")
        return

    # ── he is approving what he was shown
    if action == "send":
        if not job:
            number = session.get("last_quote_number")
            store.record_decision(message_sid, {"action": "send", "result": "nothing-open"})
            say(technician,
                f"That one's already gone — *{number}*. Send me the next job."
                if number else "Nothing waiting to send. Give me the job first.")
            return

        if gaps:
            store.record_decision(message_sid, {"action": "send", "result": "incomplete",
                                                "missing": gaps})
            store.save_session(session)
            say(technician, f"Not yet — I still need {_and_list(gaps)}.")
            return

        if _warn_unreachable(technician, session, message_sid):
            return

        # He approved something he has not actually seen — either a first message that
        # ended in "send it", or an approval of a quote that has changed since. Show it
        # and ask again. Approving from memory is how the wrong price goes out.
        if session.get("state") != "ready":
            session["state"] = "ready"
            _remember(session, "bot", "showed the card")
            store.save_session(session)
            store.record_decision(message_sid, {"action": "send", "result": "shown-first"})
            say(technician, _card(job, "Before I send — check this:"))
            return

        store.record_decision(message_sid, {"action": "send", "result": "issuing"})
        issue(technician, session)
        return

    # ── still collecting, or ready to show
    store.record_decision(message_sid, {"action": action, "missing": gaps,
                                        "replace_job": bool(decision.get("replace_job"))})

    if gaps:
        session["state"] = "collecting"
        message = reply or f"Got it. I still need {_and_list(gaps)}."
        _remember(session, "bot", message)
        store.save_session(session)
        say(technician, message)
        return

    if _warn_unreachable(technician, session, message_sid):
        return

    session["state"] = "ready"
    _remember(session, "bot", "showed the card")
    store.save_session(session)
    say(technician, _card(job, reply))


def _warn_unreachable(technician: str, session: dict, message_sid: str) -> bool:
    """Stop on a number that cannot receive WhatsApp, and say why by name.

    An 086 or 087 looks like a mobile and is quoted like one, and a WhatsApp to it
    fails silently — so the quote never arrives and nobody finds out. That is the
    precise failure this system exists to remove, so it is caught before the send
    rather than reported after it.
    """
    phone = (session.get("job") or {}).get("customer_phone")
    if doc.is_whatsapp_capable(phone):
        return False
    session["state"] = "collecting"
    warning = (
        f"Heads up — {doc.display_phone(phone)} can't receive WhatsApp; "
        f"{doc.why_no_whatsapp(phone)}. It would fail without anyone noticing.\n\n"
        "Give me a mobile for them (06, 07, 081–084) and I'll send it there.")
    _remember(session, "bot", warning)
    store.save_session(session)
    store.record_decision(message_sid, {"result": "unreachable-number", "phone": phone})
    say(technician, warning)
    return True


def _and_list(items: list) -> str:
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f" and {items[-1]}"


# ──────────────────────────────────────────────────────────────────── issuing

# The last payment link attempt: when, for which quote, and exactly why it did or did
# not work. Surfaced on /quotebot/ready because "the quote arrived but the link didn't"
# is otherwise invisible from outside, and guessing at it has already cost days. Holds
# no checkout URL, no customer name, no phone number -- just the outcome and the reason.
LAST_PAYMENT_ATTEMPT = {}


def _record_payment(**row) -> None:
    LAST_PAYMENT_ATTEMPT.clear()
    LAST_PAYMENT_ATTEMPT.update({"at": doc.now_iso(), **row})


def _attach_payment(quote_id, quote: dict) -> dict:
    """Create the deposit link for a freshly issued quote and write it to its row.

    Returns the fields to merge back into the in-memory quote. Deliberately swallows
    every failure into `payment_error`: the quote is what the customer has been waiting
    days for, and a Paystack outage is not a reason to withhold it. They get the quote,
    the technician is told there is no link, and the office can chase payment the old
    way for that one job.

    `wa_payment_url` is set only when the link should ride along with the quote itself.
    `send_with_quote: false` still creates the link — it just holds it back until they
    say yes, which suits a considered purchase where "pay now" alongside the price
    reads as pushy.
    """
    deposit = doc.deposit_for(quote)
    if deposit is None or not payments.enabled():
        reason = ("payments are switched off in quote_business.json"
                  if deposit is None else "PAYSTACK_SECRET_KEY is not set")
        store.update_quote(quote_id, {"payment_status": "skipped",
                                      "payment_error": reason})
        _record_payment(quote=quote.get("quote_number"), outcome="skipped",
                        reason=reason, deposit=deposit,
                        policy=doc.payment_policy().get("deposit_percent"),
                        total_seen=quote.get("total"))
        return {"payment_status": "skipped", "payment_error": reason}

    reference = payments.new_reference(quote["quote_number"])
    # Paystack requires an email and sends the receipt there. Most jobs are quoted with
    # a phone number only, so this falls back to the business's own address rather than
    # inventing one — an invented address on a reserved TLD is refused outright, and
    # that is precisely why quotes were arriving with no payment link.
    email = doc.receipt_email(quote)
    if not email:
        reason = ("No usable email for the Paystack receipt. Set "
                  "payment.receipt_fallback_email (or a valid business email) in "
                  "quote_business.json.")
        store.update_quote(quote_id, {"payment_status": "failed",
                                      "deposit_amount": deposit,
                                      "payment_error": reason})
        _record_payment(quote=quote.get("quote_number"), outcome="failed",
                        reason=reason, deposit=deposit)
        return {"payment_status": "failed", "payment_error": reason,
                "deposit_amount": deposit}

    try:
        created = payments.create_link(
            amount_rand=deposit, email=email, reference=reference, quote=quote,
            callback_url=f"{public_base_url()}/q/{quote['token']}")
    except Exception as exc:
        error = str(exc)[:300]
        print(f"[quotebot] payment link failed for {quote['quote_number']}: {error}",
              flush=True)
        store.update_quote(quote_id, {"payment_status": "failed",
                                      "deposit_amount": deposit,
                                      "payment_error": error})
        _record_payment(quote=quote.get("quote_number"), outcome="failed",
                        reason=error, deposit=deposit, reference=reference)
        return {"payment_status": "failed", "payment_error": error,
                "deposit_amount": deposit}

    fields = {"deposit_amount": deposit, "payment_reference": created["reference"],
              "payment_url": created["url"], "payment_status": "unpaid",
              "payment_error": None}
    store.update_quote(quote_id, fields)

    if payments.is_test_key():
        # Impossible to tell apart from the real thing by looking at it, and the whole
        # point of a demo is that everything else looks real.
        print(f"[quotebot] TEST-MODE payment link for {quote['quote_number']} "
              f"— no money will move", flush=True)

    policy = doc.payment_policy()
    rides_along = bool(policy.get("send_with_quote"))
    _record_payment(quote=quote.get("quote_number"), outcome="created",
                    deposit=deposit, reference=created["reference"],
                    sent_with_quote=rides_along, link_produced=bool(created.get("url")))
    return {**fields,
            "wa_payment_url": created["url"] if rides_along else ""}


def payment_received(quote: dict, amount_rand: float, channel: str = "") -> None:
    """A confirmed payment: thank the customer, tell the technician, ping the office.

    Only ever called after services/payments.verify() has asked Paystack directly. A
    webhook body is just something that arrived over the internet, and this function
    tells a customer their money is in.
    """
    from services.notify import send_telegram

    paid = doc.fmt_money(amount_rand, quote.get("currency", "ZAR"))
    number = quote.get("quote_number")
    name = quote.get("customer_name") or "the customer"

    if quote.get("customer_phone"):
        try:
            say(quote["customer_phone"], doc.payment_received_ack(quote))
        except Exception as exc:
            print(f"[quotebot] could not thank {quote['customer_phone']}: {exc}", flush=True)

    technician = quote.get("quoted_by_number")
    if technician:
        try:
            outstanding = float(quote.get("total") or 0) - float(amount_rand)
            note = [f"💰 *PAID* — {paid} received", "",
                    f"*{number}* · {name}"]
            if outstanding > 0.005:
                note.append("Balance still due: "
                            f"{doc.fmt_money(outstanding, quote.get('currency', 'ZAR'))}")
            if channel:
                note.append(f"Paid by {channel}")
            say(technician, "\n".join(note))
        except Exception as exc:
            print(f"[quotebot] could not notify {technician}: {exc}", flush=True)

    try:
        send_telegram(f"💰 <b>Payment received</b> — {paid} on {number} "
                      f"({name})")
    except Exception:
        pass


def issue(technician: str, session: dict) -> None:
    """Number it, render it, send it to the customer, tell the technician and the office.

    Every step that can fail is reported by name. A quote the customer never received
    is the exact failure this system was built to remove, so it is never allowed to
    look like a success.
    """
    from services.notify import send_telegram

    biz = doc.business()
    job = session["job"]
    today = doc.today()

    quote = {
        "quote_number": store.next_quote_number(biz.get("quote_prefix", "Q"), today.year),
        "token": store.new_token(),
        "customer_name": job["customer_name"],
        "customer_phone": job["customer_phone"],
        "customer_email": job.get("customer_email"),
        "site_address": job.get("site_address"),
        "line_items": job.get("line_items") or [],
        "total": job["total"],
        "currency": job.get("currency", "ZAR"),
        "notes": job.get("notes"),
        "quoted_by_number": technician,
        "quoted_by_name": doc.technician_name(technician),
        "issued_date": today.isoformat(),
        "valid_until": (today + timedelta(days=biz.get("validity_days", 30))).isoformat(),
    }

    base = public_base_url()
    link = f"{base}/q/{quote['token']}"
    pdf_url = f"{base}/q/{quote['token']}.pdf"

    # Stored BEFORE any send. If a delivery fails there is still a record of a quote
    # that was issued and did not arrive — which is the row worth having.
    saved = store.insert_quote({**quote, "whatsapp_status": "pending"})
    quote_id = saved.get("id")

    # The payment link, created before anything goes out so it can travel with the
    # quote. Best effort by design: a gateway outage must not stop the quote itself
    # from reaching the customer, because the quote is the thing they are waiting for.
    quote.update(_attach_payment(quote_id, quote))

    # WhatsApp — the one that matters.
    wa_status, wa_error = "sent", None
    try:
        whatsapp.send_media(quote["customer_phone"],
                            doc.customer_message(quote, link, with_attachment=True,
                                                 payment_url=quote.get("wa_payment_url", "")),
                            pdf_url)
    except Exception as exc:
        wa_status, wa_error = "failed", str(exc)[:400]
        print(f"[quotebot] delivery to {quote['customer_phone']} failed: {exc}", flush=True)

    # Email — best effort. Note this sends from the connected Boschly mailbox, not
    # from the client's own; a production install points it at theirs.
    email_status, email_error = "skipped", None
    if quote.get("customer_email"):
        try:
            from services import email as email_service
            subject, body = doc.customer_email(quote, link)
            email_service.send_new_with_attachment(
                quote["customer_email"], subject, body,
                doc.render_pdf(quote), f"{quote['quote_number']}.pdf")
            email_status = "sent"
        except Exception as exc:
            email_status, email_error = "failed", str(exc)[:400]
            print(f"[quotebot] email to {quote['customer_email']} failed: {exc}", flush=True)

    store.update_quote(quote_id, {
        "whatsapp_status": wa_status, "whatsapp_error": wa_error,
        "email_status": email_status, "email_error": email_error,
        "sent_at": doc.now_iso() if wa_status == "sent" or email_status == "sent" else None,
    })

    total = doc.fmt_money(quote["total"], quote["currency"])
    name = doc.first_name(quote["customer_name"])

    if wa_status == "sent":
        # Only cleared on a real delivery. If it failed, the job stays on the table so
        # he can fix the number and say send again rather than retyping everything.
        store.clear_session(technician, last_quote_number=quote["quote_number"])
        lines = [f"Sent ✓", "",
                 f"*{quote['quote_number']}* · {total}",
                 f"→ WhatsApp to {doc.display_phone(quote['customer_phone'])} ✓"]
        if email_status == "sent":
            lines.append(f"→ Email to {quote['customer_email']} ✓")
        elif email_status == "failed":
            lines.append(f"→ Email to {quote['customer_email']} didn't go — "
                         f"{email_error}")
        if quote.get("wa_payment_url"):
            deposit = doc.fmt_money(quote.get("deposit_amount"), quote["currency"])
            noun = "payment" if doc.deposit_is_full() else "deposit"
            lines.append(f"→ {deposit} {noun} link included ✓")
        elif quote.get("payment_error"):
            lines.append(f"→ No payment link — {quote['payment_error']}")
        lines += ["", link]
        say(technician, "\n".join(lines))
    else:
        session["state"] = "ready"
        store.save_session(session)
        say(technician,
             f"*{quote['quote_number']}* is written up ({total}) but it wouldn't "
             f"deliver to {doc.display_phone(quote['customer_phone'])}.\n\n{wa_error}\n\n"
             f"Here it is either way — you can forward this:\n{link}\n\n"
             "Fix that and say send again.")

    try:
        send_telegram(
            f"\U0001f9fe Quote <b>{quote['quote_number']}</b> — {name}, {total}"
            f"\nWhatsApp: {wa_status} · Email: {email_status}\n{link}")
    except Exception:
        pass          # the office ping is nice to have, never a reason to fail a send


# ───────────────────────────────────────────────────── the customer's side

# Deterministic on purpose. Both branches do the same thing — tell the technician —
# so the only thing riding on this is whether accepted_at gets stamped. A word list
# is easier to reason about than a model call for a decision that cheap.
_YES = {"yes", "yes please", "ja", "ja asseblief", "yebo", "ok", "okay", "sure",
        "go ahead", "please go ahead", "accept", "accepted", "approved", "deal",
        "yes go ahead", "book it", "lets do it", "let's do it", "y", "\U0001f44d"}


def _sounds_like_yes(text: str) -> bool:
    cleaned = re.sub(r"[^a-z' ]", "", text.lower()).strip()
    if cleaned in _YES or text.strip() in _YES:
        return True
    return bool(re.match(r"^(yes|ja|yebo|sure|ok|okay)\b", cleaned))


def handle_customer(customer: str, body: str, quote: dict, message_sid: str = "") -> None:
    """A reply to a quote we sent. Closes the loop the bad reviews are about."""
    from services.notify import send_telegram

    text = (body or "").strip()
    accepted = _sounds_like_yes(text)

    store.update_quote(quote["id"], {
        "customer_reply": text[:1000],
        **({"accepted_at": doc.now_iso()} if accepted and not quote.get("accepted_at")
           else {}),
    })
    store.record_decision(message_sid, {"role": "customer", "accepted": accepted,
                                        "quote": quote["quote_number"]})

    # A yes on an unpaid quote gets the payment link back immediately. Saying yes and
    # then waiting for someone to send banking details is the same failure as a quote
    # that never arrives, one step further along.
    pay_url = ""
    if accepted and quote.get("payment_status") == "unpaid":
        pay_url = quote.get("payment_url") or ""

    try:
        say(customer, doc.customer_ack(quote, accepted, pay_url), role="bot")
    except Exception as exc:
        print(f"[quotebot] could not acknowledge {customer}: {exc}", flush=True)

    headline = "✅ ACCEPTED" if accepted else "\U0001f4ac Replied"
    note = (f"{headline} — *{quote['quote_number']}*\n"
            f"{quote['customer_name']} ({doc.display_phone(customer)})\n\n"
            f"“{text[:600]}”")

    technician = quote.get("quoted_by_number")
    if technician:
        try:
            say(technician, note)
        except Exception as exc:
            print(f"[quotebot] could not notify {technician}: {exc}", flush=True)

    try:
        send_telegram(
            f"{'✅ <b>Quote accepted</b>' if accepted else '💬 Quote reply'} "
            f"— {quote['quote_number']}, {quote['customer_name']}"
            f"\n“{text[:400]}”")
    except Exception:
        pass
