# Pecanwood Portfolio — dashboard demo for Louise Cawood (Seeff Pecanwood)

The show-piece for the first conversation. One screen with her whole book, styled to
match the three printed Monday seller updates (`outputs/proposals/pecanwood-seller-reports/`).

**Run:** `run.bat` → http://localhost:8509 (uses the repo `venv`)

## What's on it

| Panel | Data |
|---|---|
| KPI strip (49 listings, R241M book, R13 370/m² median, 27 sole mandates, 139 deals) | REAL — scraped seeff.com + property24.com, 2026-07-06 |
| Scatter: every listing, size vs price, against the estate median line | REAL |
| "The fight for Pecanwood" agency bars (Pam Golding 44 / Seeff 42 / RE/MAX 35) | REAL — Property24 |
| Recently concluded sales | REAL — her public deals page |
| Listings table (sortable, searchable, click → drawer with positioning bars) | REAL, except Views/wk column |
| Monday seller updates rail (3 PDFs open in-page) | REAL PDFs, sample activity inside them labeled |
| Buyer-enquiry instant-responder feed | SAMPLE — scripted simulation, labeled |

Per-listing "activity" numbers are deterministic sample data (seeded from the web ref)
and carry SAMPLE chips. Everything else is real. The REAL/SAMPLE chip legend is part of
the pitch: "blue chips are your actual data, today."

## Rebuild data after a fresh scrape

1. Re-run the scrape (session scratchpad `scrape_seeff.js` + `parse_seeff.js`, needs FIRECRAWL_API_KEY)
2. Copy the new `pecanwood_listings.json` / `louise_deals.json` into `data/`
3. `python build_data.py` → regenerates `data/portfolio.json`

Fonts load from Google Fonts (Fraunces + Public Sans), so the demo wants internet.
Chart.js is vendored (`static/vendor/chart.umd.js`, copied from the jarvis demo).
