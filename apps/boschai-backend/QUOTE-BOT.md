# The WhatsApp quote bot

A technician finishes a site visit and messages a WhatsApp number in whatever words
come out. It writes the quote up, shows him, and on **SEND** the customer has a
numbered PDF on their phone about ten seconds later.

Built for **FIXITT Glass & Aluminium** (Zaheer Omarjee, Cape Town). Their own reviews
say the diagnosis out loud: 13 of 20 negative reviews are *inspection done, quote never
arrived* — eight days, two weeks, four weeks of chasing. The phones are fine; Zaheer
told us so and the reviews agree. What fails is the handoff after the phone. The person
who knows the price drives away and the number has to survive a queue and a department
before it reaches the customer who was standing right there.

So: **quote at the kerb, not at the office.**

---

## The flow

```
technician  ──►  bot number  ──►  Claude parses  ──►  confirmation back to him
                                                              │
                                                      he replies SEND
                                                              │
                                     PDF rendered  ──►  customer's WhatsApp
                                                              │
                                                      Telegram ping to the office
```

Two rules hold it up:

1. **Nothing sends without SEND.** The parse is always a draft. A mistyped digit
   posts a customer's quote to a stranger, so a human confirms every time.
2. **Every reply goes out through the REST API from a background task**, never as
   TwiML. Twilio times a webhook out at 15 seconds and a Chromium render can outlast
   that.

## What he can send

Anything. Wrong order, abbreviations, mixed English and Afrikaans, no punctuation:

> Sarah Adams, 082 555 1234, sarah@gmail.com - 2 slidin panels lounge 1.8x2.1 6.38 lam,
> replace both tracks, 11.5k incl labour

Trade shorthand gets expanded into something a customer can read, and every measurement
and spec is kept exactly as given. Specs are never invented.

**Corrections are just messages.** "make it 12500" or "her number is 083 not 082" —
the draft updates and he gets a fresh confirmation. **CANCEL** scraps it.

## Guard rails

| Guard | Why |
|---|---|
| Twilio signature checked on every webhook | Without it the endpoint is an open megaphone that sends WhatsApps on our bill |
| `QUOTE_TECHNICIANS` allowlist | Only approved numbers may issue quotes on the company's letterhead |
| Non-mobile numbers refused | Only 06x, 07x, 081–084 reach WhatsApp. 086/087 are share-call numbers that look mobile and **fail silently** — FIXITT's own glass line is an 087 |
| Never invents a price or a spec | Missing means missing; he gets asked |
| PDF failure degrades to a link | The quote still goes out if Chromium is unavailable |

## Files

| File | What it does |
|---|---|
| `routes/whatsapp.py` | Webhook, the SEND/CANCEL state machine, serves `/q/{token}` and `/q/{token}.pdf` |
| `services/quotes.py` | Claude parse, phone rules, numbering, HTML and PDF render, in-memory store |
| `services/whatsapp.py` | Twilio send, with the errors that actually happen named |
| `templates/quote.html` | The document |
| `quote_business.json` | **All the copy and business details.** Edit here, never in code |
| `db/migrations/013_quotes.sql` | The quote log. Not needed for the demo, required before go-live |

## Environment

```
TWILIO_ACCOUNT_SID=…
TWILIO_AUTH_TOKEN=…
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886   # the sandbox number
QUOTE_BOT_ENABLED=1                          # off by default, like every sender here
QUOTE_TECHNICIANS=+27712824797               # empty = anyone who can reach it
PUBLIC_BASE_URL=                             # optional; Railway's domain is used otherwise
WHATSAPP_VALIDATE_SIGNATURE=1                # only ever 0 against a local tunnel
QUOTE_PARSING_MODEL=                         # optional; defaults to claude-sonnet-4-6
```

## Setting up the demo

1. Twilio Console → **Messaging → Try it out → Send a WhatsApp message**
2. Send the `join <code>` message from **both** phones — the technician and the customer
3. Set the env vars above on Railway and deploy
4. Same Twilio page → **Sandbox settings** → *When a message comes in*:
   `https://<railway-url>/webhook/whatsapp`, method **POST**
5. Message the bot from the technician phone

**Sandbox membership lapses after 72 hours idle.** Re-send the join code before filming.

The sandbox has no templates, so everything is free-form, which means the customer's
24-hour window must be open — joining opens one. If a send fails with code 63016, have
that phone message the sandbox again.

## Going to production

The sandbox cannot touch a real customer. Production needs a Meta Business account,
business verification against FIXITT's CIPC documents, an approved display name, a
dedicated number **that is not on WhatsApp**, and one approved utility template. That
queue can run from a day to several weeks, so it starts on day one of the project.

Full walkthrough: `claude-vault/modules/review-booster/reference/whatsapp-setup.md`.

**The number is a one-way door.** Whatever number becomes the API sender is removed
from the WhatsApp Business app and its chat history is lost. Never use FIXITT's
published line. A fresh number is also the free gift we already owe them, since their
087 cannot receive WhatsApp at all.

## Known limits

- **Issued quotes live in memory** and die on redeploy, so an old quote link can
  404. Drafts are persisted to `quote_drafts` (migration 013) and fall back to
  memory if that table is absent -- run the migration and an in-progress quote
  survives a Railway restart.
- **Messages from one technician are serialised** by a per-number lock. Without it,
  SEND typed a second after the job races the Claude parse still writing the draft,
  and he gets "nothing to send" for a quote he is looking at. This actually happened
  on the first live test (20 Aug). Different technicians never block each other.
- **VAT is off** until Zaheer confirms whether they are registered. Never invent a
  VAT number — set `vat_registered` and `vat_number` in `quote_business.json`.
- **No email copy yet.** Deliberate: the only mail sender wired up is Heinrich's own
  Gmail, and a FIXITT quote should not arrive from it. Insurance and landlord
  forwarding both want email, so this is the first thing to add for production.
- **Voice notes are not handled.** Typed only. Voice is the better product — a
  technician in the sun with dirty hands will not type — but it is three moving parts
  instead of one, so it comes after the loop is proven.
- **Only covers jobs priced on site.** Fabricated shopfronts that need supplier
  pricing still go back to the office. Say that limit to Zaheer before he says it
  to you; the win is still real, because silence is what his reviewers are angry about.
