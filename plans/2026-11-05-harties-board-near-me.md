# Harties Board: "Near me" distance filter

**Status:** Implemented 5 Nov 2026 on branch `nearby` (worktree `C:/Users/gamin/BoschAI/harties-board-owners`). Not shipped: needs Heinrich's go, then merge `origin/live`, rerun `harties_geo.py` on the shipped seed, `npm run ship -- --branch=nearby`.

## Why
Heinrich looked at Pecanwood and missed an event at Aviators, because the app files Aviators under "Mountain Lake & R512". Area names have hard edges. A distance filter does not.

## What people get
- The area pill opens a sheet. Top: **Near me** (phone location, asked once) or **Near a place** (Pecanwood, Schoemansville, Kosmos...). Then a distance: 2, 5, 10 or 20 km. Below: the old area list still works.
- Every list (Today, This weekend, This week, Coming up, Browse, categories, Search, Sponsored) filters to that circle.
- Cards say "1.2 km away". Places in a category sort nearest first.
- Pill says "Within 5 km of Pecanwood" and stays green like the area filter.
- Homes use the middle of their area, with no distance on the card (we never show a home's exact position).

## How (small steps)
1. `lib/geo.ts`: distance maths, area centres, the scope string `near:<km>:<lat>:<lng>:<spot>` (kept in the existing `hb_area` cookie, so every page already reads it).
2. `lib/areas.ts`: `inArea` understands the near scope; `areaName` words it.
3. Business and promo get optional `lat`/`lng`, checked in `parse-board.ts` (inside the Harties box, else dropped). A promo falls back to its business, then to its area centre.
4. `lib/board.ts`: cards get `away`, places sort nearest first in a near scope.
5. `components/AreaSwitch.tsx` becomes a sheet. Location is read once in the browser, rounded to about 100 m, kept only in the cookie. Privacy page gets one line.
6. `scripts/harties_geo.py` (workspace): fills `lat`/`lng` in a seed from the Google Maps scrape by phone, website and name, and gives events their venue's point. Re-runnable, prints what it could not place. Run it after any seed refresh.
7. Tests, browser checks, ship only on Heinrich's go.

## Coordinates we have
- 2,939 Google Maps places, all with a point (2,050 inside Harties).
- Businesses: about 70% match by name already; phone and website matching add more. The rest use their area centre.
- Events: 97 of 173 name a venue.
- Homes: area centre only.

## Open
- A listing added through the website has no point yet (area centre until we add address lookup).
- The `directory` branch session has a bigger seed; whoever ships second must rerun `harties_geo.py`.

## Implementation notes (5 Nov 2026)
- Done as planned. Changes from the plan: the default distance is 10 km (Aviators is about 7 km from Pecanwood, so 5 km would have hidden the event that started this); the privacy wording says the cookie is read by the board and not saved (a cookie is sent with each request, so "never leaves the phone" would have been untrue); the sheet draws only while open; a place with no point of its own sorts a kilometre behind real ones; area centres come from landmarks, not the average of the businesses filed under an area (an early guess was several km out).
- `Permissions-Policy` had `geolocation=()`, which would have blocked Near me silently. Now `geolocation=(self)`.
- Checks: 434 unit tests pass (14 new), `check-screens.mjs` all checks pass, `check-near.mjs` all pass, lint and types clean.
- Not built: address lookup for businesses listed through the website; a map view; distance on homes.
