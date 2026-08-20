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
| `services/quote_store.py` | All Supabase access — sessions, messages, quotes |
| `services/quote_selftest.py` | 13 real technician messages, run against the real model |
| `services/whatsapp.py` | Twilio send, with the error codes worth naming |
| `quote_business.json` | **All copy and business detail. Edit here, never in code.** |
| `db/migrations/014_quote_bot.sql` | The schema. Not optional. |

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

## Setting it up

1. **Run `db/migrations/014_quote_bot.sql`** in the Supabase SQL editor. The bot's
   memory *is* that schema — this is not optional.
2. **Railway env:** `QUOTE_BOT_ENABLED=1`, `QUOTE_TECHNICIANS=+27712824797`,
   plus the three `TWILIO_*` values. See `.env.example`.
3. **Twilio:** point the sandbox's "When a message comes in" at
   `https://<host>/webhook/whatsapp`, method POST.
4. **Every phone in the demo must join the sandbox** — send the join code from it
   once. The sandbox silently refuses numbers that have not. No code can work around
   this.

### Checking it works, without messaging anybody

| | |
|---|---|
| `GET /quotebot/status?key=…` | The live build string, the config, whether each table exists, and the last 25 messages |
| `GET /quotebot/selftest?key=…` | Puts 13 real technician messages through the real model and reports what it made of each. Costs a few cents. Sends nothing. |

Both are guarded by `API_SECRET_KEY` because they expose phone numbers and message
text.

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
