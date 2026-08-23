# Going live on WhatsApp — the template, and everything it depends on

The sandbox is fine for filming and for showing Zaheer. This is what has to happen
before a real customer of his receives a quote.

**The thing to understand first:** the technician's side never changes. He messages the
bot, so everything he does is inside WhatsApp's 24-hour window and stays free-form
exactly as it works today. **Only the first message to the customer is templated** —
because she never messaged us first. The moment she replies, the window opens and the
acknowledgement, the payment link and the confirmations are all free-form again.

So this is one message, once.

---

## The order it has to happen in

Steps 1–3 are Zaheer's business, not ours, and 2 is the slow one.

| # | What | Where | Roughly |
|---|---|---|---|
| 1 | Pick a **new** number for the bot | see the warning below | — |
| 2 | Verify FIXITT as a business with Meta | Meta Business Manager | 1–5 days |
| 3 | Register the number as a WhatsApp sender | Twilio Console | ~1 hour |
| 4 | Submit the template | Twilio Content Template Builder | minutes to a few hours |
| 5 | Point the code at it | `services/whatsapp.py` | under a day |

### The links

- **Meta Business Manager** — https://business.facebook.com/
- **Business verification** — https://business.facebook.com/settings/security
- **Twilio WhatsApp senders** — https://console.twilio.com/us1/develop/sms/senders/whatsapp-senders
- **Twilio Content Template Builder** — https://console.twilio.com/us1/develop/content-template-builder
- **WhatsApp Manager** (Meta's own view of template status) — https://business.facebook.com/wa/manage/message-templates/
- **Meta's template rules** — https://developers.facebook.com/docs/whatsapp/message-templates/guidelines
- **Business Messaging Policy** — https://www.whatsapp.com/legal/business-policy/
- **Twilio Content API docs** — https://www.twilio.com/docs/content

Twilio moves its console around. If a link 404s, it is under **Messaging** in the left nav.

---

## ⚠️ The number: a one-way door

Whatever number becomes the API sender **leaves the WhatsApp Business app permanently**.
Zaheer will not be able to answer it from his phone again. It cannot be undone by
unregistering.

**FIXITT's published number is 087 153 6444, and it is an 087** — which cannot receive
WhatsApp at all, so it was never a candidate. Get a **new dedicated mobile number** for
the bot (06x, 07x or 081–084). Cheap, clean, and nothing of his is at risk.

Do not skip this decision. It is the only irreversible step in the whole build.

---

## The template

Submit as **Utility**. It is a document for work already carried out, which is exactly
what Utility is for — it costs less per message than Marketing and approves faster.

**Name:** `fixitt_quote_ready`
**Category:** Utility
**Language:** English (`en`)

### Header — Document

The quote PDF. Twilio takes the media URL at send time, so this is
`{base}/q/{token}.pdf` — the same URL the sandbox build already sends.

### Body

```
Hi {{1}}, thank you for choosing FIXITT Glass & Aluminium.

Your quote {{2}} for the work we looked at today is attached. The total is {{3}} and it is valid for {{4}} days.

Reply YES and we will book the installation.
```

Sample values to give Meta at submission:

| Variable | Sample | Filled from |
|---|---|---|
| `{{1}}` | `Sarah` | `doc.first_name(quote["customer_name"])` |
| `{{2}}` | `FQ-2026-014` | `quote["quote_number"]` |
| `{{3}}` | `R 11 500.00` | `doc.fmt_money(quote["total"], …)` |
| `{{4}}` | `30` | `business()["validity_days"]` |

### Button — Visit website (dynamic URL)

| | |
|---|---|
| Label | `View & pay` |
| URL | `https://aios-workshop-production.up.railway.app/q/{{1}}` |
| Sample | the quote's `token` |

**Why the button points at our own page and not at Paystack.** A dynamic URL button
only lets the *suffix* vary — the domain is fixed at approval. Our quote page already
renders the deposit button, so the chain is template → quote page → pay. Two things
fall out of that, both good: the payment URL never has to survive Meta's review, and
changing the deposit from 50% to 100% stays a `quote_business.json` edit instead of a
resubmission.

---

## What gets rejected, and why

Nearly every rejection is one of these:

- **Promotional language in a Utility template.** No "best prices", no "5% off", no
  "beat any written quote". FIXITT's promises belong in the PDF, and they are already
  there — keep them out of the template body.
- **A variable at the very start or very end of the body.** Meta reads it as spam
  scaffolding. The body above deliberately opens with `Hi` and closes on a sentence.
- **Variables that could be anything.** The samples must look like the real thing.
- **A URL whose domain is not yours.** Another reason the button points at our page.

If it is rejected, the reason appears in WhatsApp Manager and you can edit and
resubmit. It is not a one-shot.

---

## The code change, when the template is approved

Contained, and only on the customer side.

- **`services/whatsapp.py`** — the customer send switches from a free-form body to a
  Twilio Content Template: `ContentSid` plus `ContentVariables` (a JSON map of
  `{"1": "Sarah", "2": "FQ-2026-014", …}`). The technician sends stay free-form.
- **`quote_business.json`** — `customer_message` stops being the whole sentence and
  becomes the variable values. Add the `ContentSid` here too, so swapping the template
  never means touching code.
- **Everything else is untouched** — the engine, the PDF, the quote page, Paystack,
  the customer reply handling, the payment webhook.

`handle_customer()` already works on whatever comes back, and `_sounds_like_yes()`
already accepts "yes" in the words people actually use, so her reply needs nothing new.

---

## Two things that are Zaheer's, not ours

Worth raising with him before go-live rather than after:

1. **The Paystack account must be his.** It is currently Boschly's, on a test key, and
   `receipt_fallback_email` deliberately points at Heinrich so a test receipt can never
   land in a customer's inbox. Real money must not move through our account.
2. **Outbound email currently sends from the Boschly mailbox.** For his install it
   should be FIXITT's own address, or the emailed copy of a quote arrives from a
   company his customer has never heard of.

---

## And the rule that does not change

The opt-in is real in this business: a technician stood at her house, took her number
and said he would WhatsApp the quote. POPIA does not treat a requested quote as direct
marketing, and Meta's policy is satisfied.

That holds only while it stays tied to a real site visit. Point this at a list and the
block rate takes the number's quality rating down, sending limits get cut, and **the
real quotes stop arriving too** — which would break the exact thing the system was
built to fix.

Automatic yes, unsolicited no.
