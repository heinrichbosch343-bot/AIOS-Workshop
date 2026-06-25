# API Primitives to Build Systems On

> **The pattern (the "Voyage move"):** find a single API that does one hard thing well,
> wrap a system and a plain-English story around it, and sell the story — not the API.
> The customer never hears "Voyage." They hear "ask your whole Drive in plain English."
> These five are the next primitives to experiment with, same playbook as the
> data-pooling Drive demo.

_Captured 2026-06-23. Free-tier details change — re-check before committing._

---

## 1. Document parsing → structured data — "kill data entry"

- **Experiment with:** LlamaParse, Reducto, or Mistral OCR (cheapest, ~$0.001/page)
- **Pain:** Companies drown in PDFs — invoices, contracts, delivery notes, forms. Someone is paid to retype them. Slow, costly, error-prone.
- **Solution:** Send a messy PDF, get back clean structured data (JSON, tables). Vision-model based, so it handles scans and broken layouts.
- **Dream outcome:** "Your paperwork files itself." A box of invoices becomes a finished spreadsheet before coffee.
- **Why it fits us:** Bolts straight onto the Drive system already on camera — turns documents into data you can total, chart, and act on.
- **Free tier:** 🟢 **LlamaParse — 10,000 credits/month, refreshes, no card** (~3,000 pages/mo). Mistral OCR has a free Experiment tier.

## 2. Speech-to-text + intelligence — "capture every conversation"

- **Experiment with:** Deepgram (fastest/cheapest) or AssemblyAI (best at names/emails/amounts + auto-summaries)
- **Pain:** The most valuable info in a business is spoken then lost — sales calls, meetings, site visits, support calls.
- **Solution:** Feed audio, get transcript + who-said-what + summary + action items + sentiment. One API call.
- **Dream outcome:** "Every conversation works for you after it ends." Calls auto-log to the CRM with next steps; meetings produce their own minutes.
- **Free tier:** 🟢 **Deepgram — $200 credits, no expiry** (~700 hours / 46k min — most generous of all five). AssemblyAI = $50 one-time (~185 hrs).

## 3. Voice phone agents — "never miss a call"

- **Experiment with:** Vapi (developer-first) or Retell (production-ready), ~$0.07–0.09/min all-in
- **Pain:** Missed calls = missed money. Reception is expensive, business-hours only, one call at a time.
- **Solution:** AI answers the phone, sounds human, books appointments, captures leads, hands off to a person — 24/7, infinite lines.
- **Dream outcome:** "Your phone is answered on the first ring, forever." Sells itself to dentists, clinics, law firms, trades, property.
- **Free tier:** 🔴 **Only ~$10 each** (60–90 min of calls), then pay-as-you-go. Thin because every voice minute has a real carrier cost. Enough for one demo call, not to run free.

## 4. Web data extraction — "always-on market radar"

- **Experiment with:** Firecrawl (extraction-first — describe what you want in plain English, get structured data)
- **Pain:** Competitor pricing, market intel, lead lists, catalogues sit on websites; someone copies them by hand, if ever.
- **Solution:** Point the API at any site (or a search), get clean structured data. Handles JS-heavy sites that break normal scrapers.
- **Dream outcome:** "You always know what the market is doing." Live competitor-price tracker; self-refreshing lead list; weekly "what changed" brief (feeds the daily-brief system).
- **Free tier:** 🟢 **1,000 credits/month, refreshes, no card.** Catch: 2-requests-at-a-time on free plan (only matters at scale).

## 5. Time-series forecasting — "see your numbers' future"

- **Experiment with:** Nixtla / TimeGPT — a pre-trained forecasting foundation model, one API call
- **Pain:** Companies guess at demand, over/under-order, bleed money. Can't forecast without a data scientist. **This is literally Connie's farming problem** (R10–20k/month leak).
- **Solution:** Send history (sales, stock, bookings, revenue), get back a forecast + anomaly flags. No model-building.
- **Dream outcome:** "You can see next month before it arrives." Stock the right amount; spot a dip before it happens.
- **Why it fits us:** Build once for the farming client, resell to retail, logistics, and the Cape Agri co-op in the pipeline.
- **Free tier:** 🟡 **Free trial, no credit card to activate** (sign in with Google/GitHub). Exact limits unstated — enough to prove the concept on farming data.

---

## Where to start (given the actual pipeline)

1. **LlamaParse (#1)** — free monthly, bolts onto the Drive demo already built. Strongest first move for a second LinkedIn video.
2. **Nixtla/TimeGPT (#5)** — a paying problem to point it at *now* (Connie farming). Build once, sell five times.
3. **Deepgram (#2) / Firecrawl (#4)** — both free enough to build and keep a working demo with zero spend, no card.

Voice agents (#3) are the only ones that cost real money the moment you go past a test call.

## Sources (free-tier checks, 2026-06-23)

- [LlamaParse pricing](https://www.llamaindex.ai/pricing) · [Mistral pricing](https://mistral.ai/pricing/)
- [Deepgram free credits](https://www.buildmvpfast.com/api-costs/transcription) · [AssemblyAI pricing](https://costbench.com/software/ai-transcription-apis/assemblyai/)
- [Vapi pricing](https://vapi.ai/pricing) · [Retell pricing](https://www.retellai.com/pricing)
- [Firecrawl free plan](https://costbench.com/software/web-scraping/firecrawl/free-plan/)
- [Nixtla TimeGPT quickstart](https://nixtlaverse.nixtla.io/nixtla/docs/getting-started/quickstart.html)
