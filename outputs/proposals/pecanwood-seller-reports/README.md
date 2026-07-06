# Pecanwood Seller Reports — the leave-behind for Louise (Seeff Pecanwood)

**Date:** 2026-07-06
**Play:** Same as the XCO introduction. Built from her own public data, no access needed, shown as a working sample. Full prospect research: `outputs/research/pecanwood-seeff-2026-07-06.md`.

## What's in this folder

Three sample "Monday Seller Update" one-pagers, each for a REAL current listing of hers:

| File | Listing | The story it tells |
|---|---|---|
| `seller-update-8-forest-crescent.pdf` | R3.5M, 4-bed, 308m² | Priced 15% under estate median: "well positioned, here's proof" |
| `seller-update-202-jack-nicklaus-drive.pdf` | R3.19M, 3-bed, 212m² | Priced 13% over median: the diplomatic repricing conversation, data-first |
| `seller-update-6-mountain-view-drive.pdf` | R9.9M, 5-bed, 476m², Exclusive Sole | Premium stock: "trades on reach, not price cuts" |

Plus the dataset behind them:
- `pecanwood_listings.json` — all 49 active Seeff for-sale listings in the estate (price, size, beds, mandate type, URL), scraped 2026-07-06
- `louise_deals.json` — 16 recent concluded deals from her public sold/rented page (9 Pecanwood sales among them)

This dataset is the first layer of the **Pecanwood Property Brain**: assembling it was required to compute the market stats anyway, which is the point of the Trojan horse.

## What's real vs sample on the reports

- **Real:** prices, sizes, price/m², estate median (R13,370/m² across 46 priced listings), competing-stock counts, recent sold prices (R2.85M to R6.5M, all Pecanwood), levies (R6,960 estate levy) and rates from her own listing pages, the 139-deal office record, web refs, addresses.
- **Sample (labeled on the page):** the "This week's activity" block (portal views, enquiries, viewings, buyer matches) and the "what we're doing this week" bullets. The shaded zone carries "SAMPLE FIGURES" and "goes live once portal dashboards are connected", and the footer states the whole page is a Boschly-built sample never sent to any seller.

## How to use it

1. WhatsApp or coffee, not email. She knows Heinrich, keep it personal.
2. The line: "I pulled your listings off Seeff's site this morning and built something. This is what every one of your sellers could get every Monday, written automatically. Real numbers, look: that's your actual median, those are your actual sales."
3. Let her spot her own addresses. That's the moment.
4. The competitive hook (verified): Pecanwood is a three-way fight — Pam Golding has 44 listings there, Seeff 42, RE/MAX 35. "When a seller's mandate is up, Pam Golding and RE/MAX are one call away. The agent whose sellers feel most looked-after keeps the mandate and gets the referral. Nobody sends weekly updates because they can't. You'd be the only one who does, and it costs you no time."
5. The ask is small: "Give me two weeks and read-only access to your Property24 dashboard, and I'll run it live on five mandates."
5. Do NOT open with FICA/compliance or the full Property Brain. Both are second-conversation material (see the research doc).

## Rebuild

Generator script: session scratchpad `seller_reports.py` (fpdf2, Segoe UI, validated palette #2E6FB8/#B07C2E on #FAF8F5). Scrapers: `scrape_seeff.js` + `parse_seeff.js` (Firecrawl). Re-run the scrape first if listings have changed.
