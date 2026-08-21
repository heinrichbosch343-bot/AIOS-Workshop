# The WhatsApp quote bot

A technician finishes a job, WhatsApps it to a bot number in whatever words come out,
and the customer has a numbered, branded PDF quote on their phone about ten seconds
later.

Built for **FIXITT Glass & Aluminium** off the review-mining diagnosis: 13 of 20 of
their negative reviews are *inspection done, quote never arrived*. Their phones are
fine — Zaheer said so and the reviews agree. What fails is the handoff after the
phone. So the thesis is **quote at the kerb, not at the office**.

---

## What it looks like

```
HIM   Sarah Adams 082 555 1234 sarah@gmail.com - 2 sliding panels lounge,
      6.38 laminated, replace both tracks, R11 500

BOT   Got it.

      *Sarah Adams*
      082 555 1234 · sarah@gmail.com

      • 2 x sliding panels, lounge — 6.38 laminated safety glass
      • Replace both bottom tracks and rollers
      *Total: R 11 500.00*

      Send it?

HIM   ja stuur dit

BOT   Sent ✓

      *FQ-2026-001* · R 11 500.00
      → WhatsApp to 082 555 1234 ✓
      → Email to sarah@gmail.com ✓
```

If something is missing it asks in its own words. It can be corrected ("make it
12500"), asked questions ("what's the total again?"), told to scrap it, or handed a
completely different job mid-conversation.

The customer gets a branded message with the PDF attached, and when they reply the
technician and Telegram both hear about it — `accepted_at` gets stamped on a yes.
**A quote nobody chased is the failure this exists to remove, so the loop closes.**

### Who is the technician, and who is the customer

`QUOTE_TECHNICIANS` decides, and nothing overrides it:

- a number **on the list** is always the technician;
- a number **not on the list** holding a quote from the last 60 days is that
  quote's customer;
- anyone else is told to call the office.

It ran the other way round briefly — the role was inferred from the data, so that
one phone could play both parts while recording a demo. It backfired: once a take
had quoted the technician's own number, that row sat in the table and every message
he sent afterwards was answered as a customer reply, with no way back short of
deleting the row. One direction, fixed by config, is also the truthful rule for the
business — technicians issue quotes, customers receive them.

The consequence worth knowing: **a listed number can never receive a quote it can
reply to.** Put the demo's customer phone on the list and its "yes" is read as the
start of a new job. `/quotebot/ready` checks for exactly that and says so, and it
also compares the list against the `technicians` map in `quote_business.json`, since
the two drifting apart produces the same baffling symptom.

---

## The one rule that matters

**The model understands and speaks. The code decides and sends.**

The model reads the thread, works out what he meant, merges the facts, and writes the
sentence he gets back. It is never asked to type a price, a total or a quote number —
code renders those underneath its words, from the stored job, so the figures on his
phone are the figures on the PDF by construction.

It also cannot cause a send. It returns `action: "send"`; `quote_engine` then checks
the job is complete, that the number can actually receive WhatsApp, and that he has
**seen the card**. A first message ending in "…and send it now" still gets shown to
him first. That step is what stops a mistyped digit putting one person's quote on a
stranger's phone.

---

## Files

| File | |
|---|---|
| `routes/whatsapp.py` | HTTP edge: webhook, signature, idempotency, routing, public quote URLs |
| `services/quote_engine.py` | The conversation: the model call, the state machine, issuing |
| `services/quote_doc.py` | The PDF (fpdf2), the web page, and every word the customer reads |
| `services/quote_store.py` | All Supabase access — sessions, messages, quotes, payment events |
| `services/payments.py` | Paystack: the link, the verification, the signature |
| `routes/payments.py` | The Paystack webhook and the payment status endpoint |
| `services/quote_selftest.py` | 13 real technician messages, run against the real model |
| `services/whatsapp.py` | Twilio send, with the error codes worth naming |
| `quote_business.json` | **All copy and business detail. Edit here, never in code.** |
| `db/migrations/014_quote_bot.sql` | The schema. Not optional. |
| `db/migrations/015_quote_payments.sql` | Payment columns + the webhook log. |

---

## Why it is built this way

**State is in Postgres, not in memory.** The first build kept the in-progress quote in
a module-level dict. Railway restarts the web process on every deploy, so a quote he
was looking at had already stopped existing when he replied SEND.

**Every message is logged with Twilio's `MessageSid`, which is UNIQUE.** A redelivery
inserts zero rows and the turn stops. That removes double-sends and reply loops as a
category rather than as a series of bugs.

**The PDF is fpdf2, not headless Chromium.** Pure Python, installs from
requirements.txt, renders in ~30ms, no system packages, no `nixpacks.toml`, nothing to
prove on a deploy. It is regenerated on demand from the stored row, so there are no
blobs to keep and the document can never drift from the record.

**Never return a shared `Response` object from a route that uses background tasks.**
This one cost days. FastAPI attaches background tasks to a returned Response only
`if response.background is None`. A module-level `EMPTY_TWIML = Response(...)` was
claimed by the first request and never released, so **every subsequent message re-ran
the first message's handler and dropped its own.** On a phone that looks like a bot
answering something you sent ten minutes ago and ignoring what you just typed. See
`_ack()` in `routes/whatsapp.py`.

---

## The payment link

The quote arrives with a deposit link already in it. She taps, pays, and the technician
and the office both know within seconds.

```
To get started, the deposit is *R 5 750.00* — you can pay it securely here:
https://checkout.paystack.com/wizamgma8xdz9h4
```

**Paystack**, chosen for one reason: it is the only South African gateway with a clean
API for *creating a link per quote from a server*. Yoco is cheaper on card (2.55% flat
vs 2.9% + R1) and PayFast has more local payment methods including Instant EFT, but
neither generates links programmatically as cleanly, and that is the whole job here.

**The deposit policy lives in `quote_business.json`, not in code.** `deposit_percent`
50 asks for half; 100 asks for the whole amount and the wording changes from "deposit"
to "payment" on its own; 0 or `enabled: false` turns links off entirely without a
deploy. **This is Zaheer's decision, not ours** — emergency callouts are usually
settled on completion, while fabricated work needs materials paid for up front.

### Money is Decimal, never float

`to_cents` and `deposit_for` both use `Decimal(str(x))` with `ROUND_HALF_UP`. This is
not fastidiousness. In plain floats, half of R2 499.99 comes out as R1 249.99 rather
than R1 250.00, because 1249.995 is really 1249.99499… once stored — and then the
deposit plus the balance no longer add up to the quote. A test asserts that invariant
across seven awkward totals.

### The webhook has three defences

It marks a customer's money as received, so:

1. **Signature** — Paystack signs the raw body with the secret key, HMAC-SHA512.
   Computed over the exact bytes received; re-serialising the JSON first changes key
   order and it will never match. Unsigned, this endpoint is a button that marks any
   quote paid.
2. **Idempotency** — `payment_events.event_id` is UNIQUE. Gateways retry hard, and
   thanking a customer twice while the office reconciles a payment that never happened
   is worse than being slow.
3. **Verification** — the webhook body is only a hint. Before anything is written down
   we ask Paystack directly what happened to that reference. A webhook is something
   that arrived over the internet; `verify()` is the truth. A body claiming success for
   a card that actually failed is recorded as failed.

### Two deliberate choices

**The PDF never carries the payment link.** A PDF gets forwarded, printed and filed,
and a live payment URL sitting in a filing cabinet is a way to be paid twice for one
job. The document names the deposit; the link lives on WhatsApp and on the quote page.

**A gateway outage never withholds the quote.** If Paystack is down the quote still
goes out, the technician is told there is no link, and the office chases that one
payment the old way. The quote is what the customer has been waiting days for.

### Checking it

`GET /quotebot/payments?key=…` — whether it is configured, **whether the key is TEST or
LIVE**, the deposit policy, and the last 15 events. The test/live line matters: a test
key produces checkout pages indistinguishable from the real thing that move no money at
all, which is the thing to find out before a demo rather than during one.


---

## Setting it up

1. **Run `db/migrations/014_quote_bot.sql`** in the Supabase SQL editor. The bot's
   memory *is* that schema — this is not optional.
2. **Railway env:** `QUOTE_BOT_ENABLED=1`, `QUOTE_TECHNICIANS=+27712824797`,
   plus the three `TWILIO_*` values. See `.env.example`.
3. **Twilio:** point the sandbox's "When a message comes in" at
   `https://<host>/webhook/whatsapp`, method POST.
4. **Paystack:** set `PAYSTACK_SECRET_KEY` on Railway, and in the Paystack dashboard
   point the webhook at `https://<host>/webhook/paystack`. Run
   `db/migrations/015_quote_payments.sql` too.
5. **Every phone in the demo must join the sandbox** — send the join code from it
   once. The sandbox silently refuses numbers that have not. No code can work around
   this.

### Checking it works, without messaging anybody

| | |
|---|---|
| `GET /quotebot/ready` | **Start here when it's broken.** Whether it can quote right now and, if not, a `blockers` list saying what to go and do. Unguarded on purpose — the moment something is wrong is the moment a key-protected endpoint is hardest to reach. Reports only whether things exist: no numbers, no message text, booleans for secrets. |
| `GET /quotebot/channels` | Asks Twilio, Google and Paystack directly whether they still accept our credentials. Read-only, cached 60s, sends nothing. Config being *present* is not the same as it *working* — a Google refresh token expires every 7 days while the consent screen is in Testing mode. |
| `GET /quotebot/status?key=…` | The live build string, the config, whether each table exists, and the last 25 messages |
| `GET /quotebot/selftest?key=…` | Puts 13 real technician messages through the real model and reports what it made of each. Costs a few cents. Sends nothing. |

The last two are guarded by `API_SECRET_KEY` because they expose phone numbers and
message text.

---

## Standing constraints

- **Never register FIXITT's published number to the API.** It is a one-way door: the
  number leaves the WhatsApp Business app permanently. Use a fresh line.
- **Only 06x, 07x and 081–084 receive WhatsApp.** 086 and 087 look like mobiles and
  fail silently. The bot refuses them by name before sending, rather than reporting it
  afterwards.
- **Nothing sends without a human approving it.** Not a setting — a state machine.
- **Never invent a VAT number.** `vat_registered` is false until Zaheer confirms, and
  the document then says nothing about VAT at all rather than implying either way.
- The demo runs on the **Twilio sandbox**: no Meta verification, both phones must
  join, and membership lapses after 72h idle. Production needs business verification,
  a dedicated number, and an approved utility template for anything sent outside the
  24-hour window.
- Email currently sends from the connected Boschly mailbox, not FIXITT's. A real
  install points it at theirs.
