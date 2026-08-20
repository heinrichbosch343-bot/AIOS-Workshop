# Quote bot, rebuilt

**Date:** 2026-08-20
**Client:** FIXITT Glass & Aluminium (Zaheer)
**Status:** plan → build

---

## 1. Why the first build failed

Three separate faults, only one of which I diagnosed correctly.

**a) The draft lived in the web process's memory.** Railway restarts on deploy and
cycles containers. A draft written at 21:04 was gone at 21:06, so `SEND` answered
"nothing to send" for a quote he was looking at. Every fix I layered on top of this
was a fix to the wrong thing.

**b) The bot had no memory of the conversation.** Each message was parsed alone
against a draft blob. So a reply could not be understood *in context* — which is
exactly what a reply is.

**c) The diagnostic lied to me, and I believed it.** `_debug_text` showed the last
6 *records*, and every message wrote 2 records (one at the webhook, one at the
decision). Six records is three messages. Heinrich sent `debug` three times because
it was slow; the view filled with those three and pushed the earlier `hello` and the
R9000 job off the end. I read that as "three different messages all arrived as
`debug`" and spent the next hour hunting a body-mismatch bug that never existed.

The lesson is in the rebuild: **state goes in the database, the conversation has
history, and the audit log is a table, not a list in RAM.**

---

## 2. What the system does

### The technician's side

He finishes a job and messages the bot however the words come out. The bot holds a
conversation until it has what a quote needs, shows him the numbers, and waits.

```
HIM   Sarah Adams 082 555 1234 sarah@gmail.com - 2 sliding panels lounge,
      6.38 laminated, replace both tracks, R11 500

BOT   Got it.

      *Sarah Adams*
      082 555 1234 · sarah@gmail.com

      • 2 sliding panels, lounge - 6.38 laminated glass
      • Replace both tracks
      *Total: R 11 500.00*

      Send it to her?

HIM   ja stuur

BOT   Sent ✓
      *FQ-2026-001* · R 11 500.00
      → WhatsApp to 082 555 1234 ✓
      → Email to sarah@gmail.com ✓
```

If something is missing it just asks, in its own words:

```
HIM   Fixed a window for Johan, R2500
BOT   Nice one. What's Johan's number so I can get it to him?
HIM   076 389 7179
BOT   [the card above]
```

It can also be asked things — "what's the total again?", "make it 1200",
"no wait, different job" — and it answers or adjusts, because it has the
conversation in front of it.

### The customer's side

The moment he approves, the customer's phone gets:

```
Hi Sarah 👋

Thank you for choosing FIXITT Glass & Aluminium.

Here's the quote for the work we looked at today — *FQ-2026-001*.

• 2 sliding panels, lounge - 6.38 laminated glass
• Replace both tracks
*Total: R 11 500.00*

The full quote is attached. It's valid for 30 days.

✓ Two-year guarantee on spares and workmanship
✓ We'll beat any written quote by 5%
✓ Emergency callouts, 24 hours a day, 365 days a year

Reply YES and we'll book the installation.

FIXITT Glass & Aluminium · 087 153 6444
```

…with the branded PDF attached, and the same PDF emailed if an address was given.

**The loop closes.** When she replies, that reply lands on the same webhook. The bot
recognises her as the customer on an open quote, marks it accepted if she said yes,
and tells the technician on WhatsApp plus the office on Telegram. A quote sent and
never chased is the exact failure the reviews describe, so the system tracks it.

---

## 3. Architecture

### Data (Supabase — migration `014_quote_bot.sql`)

| Table | Holds | Why it exists |
|---|---|---|
| `quote_sessions` | one row per technician: state, the job so far, the last 20 turns | survives redeploys; gives the model memory |
| `quote_messages` | every message in and out, keyed on Twilio's `message_sid` (unique) | idempotency + a real audit trail |
| `quotes` | issued quotes: number, customer, line items, delivery status, `accepted_at` | the record, and the follow-up clock |

`message_sid` unique + `on conflict do nothing` is the single most valuable line in
the rebuild: a Twilio redelivery inserts 0 rows, and we return without acting. That
kills double-sends and reply loops as a class.

### The AI turn

One Claude call per inbound technician message. It receives the business context,
the job assembled so far, the recent conversation, and the new message. It returns:

```json
{
  "job":     { "customer_name": …, "customer_phone": …, "customer_email": …,
               "line_items": [{ "description": …, "amount": … }], "total": … },
  "missing": ["customer phone"],
  "action":  "ask" | "confirm" | "send" | "cancel" | "chat",
  "reply":   "what to say back to him"
}
```

**The model writes the prose. Code writes the numbers.** It never composes a price,
a total or a quote number — code renders those from the stored job and appends them.
A model that paraphrases R11 500 as R11 000 cannot cost anyone money here.

**The model never sends anything.** It returns `action: "send"`; code decides whether
to honour it:

- the job must be complete (name, WhatsApp-capable phone, ≥1 line item, total > 0)
- the session must already be in `ready` — meaning he has *seen* the card
- a first message that says "…and send it now" still gets the card first

That last rule is deliberate. Confirmation is the one step protecting a stranger from
receiving someone else's quote because a digit was mistyped.

### Rendering

**fpdf2**, not headless Chromium. Pure Python, no system packages, ~30 ms, nothing to
install on Railway beyond a pip line. The current invoicing PDF path needs Chromium
via `nixpacks.toml` and has never once been proven on a real deploy — this build does
not inherit that risk. The PDF is regenerated on demand from the `quotes` row, so
there are no blobs to store and the document always matches the record.

`/q/{token}` serves the same quote as a mobile web page; `/q/{token}.pdf` is what
Twilio fetches to attach.

### Routing an inbound message

1. sender in `QUOTE_TECHNICIANS` → technician
2. else sender has an open quote → customer
3. else allowlist is empty (demo mode) → technician
4. else → polite decline

---

## 4. Files

| File | |
|---|---|
| `db/migrations/014_quote_bot.sql` | new — supersedes 013, which was never run |
| `services/quote_store.py` | new — all Supabase reads/writes, one place |
| `services/quote_doc.py` | new — fpdf2 PDF, HTML page, money/date, numbering |
| `services/quote_engine.py` | new — the conversation: state machine + the Claude turn |
| `routes/whatsapp.py` | rewritten — webhook, idempotency, routing, public routes |
| `services/whatsapp.py` | kept as is |
| `quote_business.json` | extended — customer message copy lives here, not in code |
| `services/quotes.py` | **deleted** |
| `requirements.txt` | `+ fpdf2` |

---

## 5. Outside the code

1. **Run `014_quote_bot.sql`** in the Supabase SQL editor. Not optional this time —
   the bot's memory is that schema.
2. **+27 76 389 7179 must join the Twilio sandbox** (send the join code once). No code
   can work around this; the sandbox refuses numbers that have not joined.
3. **Railway env:** `QUOTE_BOT_ENABLED=1`, `QUOTE_TECHNICIANS=+27712824797`.
   Setting the allowlist explicitly is what makes technician-vs-customer routing exact.
