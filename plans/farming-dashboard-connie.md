# Farming Dashboard — Connie's Vegetable Subscription Business

**Client:** Connie (same contact as Osun Consulting Group — separate company)
**Project name:** Farming
**Status:** Planning
**Last updated:** 2026-06-19

---

## The Problem

They grow vegetables and sell weekly/monthly subscription packages to 30–50 clients. The problem: they constantly grow too little and have to buy from a store to fulfill orders. Each store run costs ~R300. They estimate R10,000–R20,000/month in lost profit from not knowing what to grow.

**Root cause:** No system connecting active orders → vegetable requirements → growing plan.

---

## The Solution

A backend + dashboard that:
1. Knows what orders are active and what vegetables each package contains
2. Calculates total vegetable demand across the next 4–8 weeks
3. Compares demand against what's growing and when it'll be ready
4. Surfaces gaps early enough to act (plant more, or plan a store run as a last resort)

---

## Core Modules

### 1. Client & Order Management
- Client list (name, contact, subscription type, delivery frequency)
- Subscription types: weekly / monthly
- Delivery schedule (when is their next delivery due?)

### 2. Package Contents Config
- Define what each package type contains (e.g. "Standard Box = 1kg tomatoes, 500g spinach, 2 heads lettuce")
- This is the key translation layer: orders → vegetable quantities needed

### 3. Inventory & Stock Tracker
- Current stock on hand (harvested, ready to use)
- Wastage / spoilage tracking (optional, phase 2)

### 4. Growing Tracker
- What's planted right now
- Date planted, expected harvest date, expected yield (kg)
- Status: Planted / Growing / Ready to harvest / Harvested

### 5. Demand Calculator (auto)
- Reads active orders + package contents
- Outputs: total kg of each vegetable needed, grouped by delivery date
- Projects 4–8 weeks forward

### 6. Gap Dashboard (main view)
- Per vegetable, per week: Needed vs. Available
- Color coding: green (covered), yellow (tight), red (shortfall)
- Shows how far ahead they need to plant to avoid gaps (based on each vegetable's grow time)

### 7. Alerts / Recommendations
- "Plant X kg of tomatoes by [date] to cover [delivery week]"
- "You have a shortfall of 5kg spinach for next week — act now or source externally"

---

## Vegetable Grow Times (reference — confirm with Connie)

Each vegetable needs its growth time configured so the system can count backwards from delivery dates:

| Vegetable | Approx. grow time |
|-----------|------------------|
| Spinach | 4–6 weeks |
| Lettuce | 4–6 weeks |
| Tomatoes | 8–12 weeks |
| Carrots | 10–12 weeks |
| Green beans | 6–8 weeks |

*Connie to confirm the specific vegetables they grow and their actual grow times.*

---

## Key Questions to Resolve with Connie

1. **Which vegetables do they grow?** Get the full list + grow times.
2. **What packages do they sell?** Get every package type and exactly what's in each.
3. **Delivery schedule?** Weekly? Monthly? Fixed day of week?
4. **Who uses the dashboard?** Just Connie, or staff too? How technical are they?
5. **Client management scope?** Do they want sign-ups and payments here, or just the grow-plan + inventory side?
6. **Do they already track anything?** Spreadsheet, notebook? Get a copy if yes.
7. **Hosting preference?** Web app they open in a browser, or something else?

---

## Tech Stack (recommended)

- **Frontend:** Next.js — clean dashboard UI, easy to deploy
- **Backend:** Node.js / Express or Next.js API routes
- **Database:** PostgreSQL (via Supabase or Railway-hosted)
- **Hosting:** Railway (same stack as BoschAI live system)
- **Auth:** Simple login — they don't need multi-tenant complexity

---

## Phases (rough)

### Phase 1 — Core (MVP)
- Client + order management
- Package contents config
- Demand calculator
- Basic gap view (table format)

### Phase 2 — Growing Tracker
- Plant log with dates + expected yields
- Gap dashboard with color coding
- Planting recommendations / alerts

### Phase 3 — Polish (optional)
- Delivery scheduling view
- Wastage tracking
- Mobile-friendly UI

---

## Pricing Anchor

Their stated pain: R10,000–R20,000/month in lost profit. Even recovering 50% of that is R5,000–R10,000/month. Use this to anchor the value of the build when scoping payment.

---

## Notes

- Keep the UI dead simple — they're farmers, not tech users. Big numbers, color coding, minimal clicks.
- The gap dashboard is the highest-value screen. Build that first.
- Avoid scope creep into e-commerce / payments unless they specifically ask and pay for it.
