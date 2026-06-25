"""
One-time script: seeds the farming project for Connie into Supabase.
- Upserts a client record for "Connie Farming Co"
- Inserts a client_brief with the project plan
- Adds a connie_context key so it appears in the Telegram system prompt
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "boschai-backend"))

from db.client import supabase

BRIEF = """
# Farming Dashboard — Connie's Vegetable Subscription Business

## The Problem
Connie's farming company grows vegetables and sells weekly/monthly subscription packages
to 30–50 clients per month. They constantly grow too little and have to buy from a store
to fulfill orders (~R300 per store run). Estimated profit loss: R10,000–R20,000/month
from not tracking what to grow correctly.

## The Solution Being Built
A backend + dashboard that:
1. Tracks active client subscriptions and what each package contains
2. Calculates total vegetable demand for the next 4–8 weeks
3. Compares demand against what is growing and when it will be ready
4. Surfaces gaps early enough to plant more or plan a store run

## Core Modules
- Client & order management (subscription type, delivery schedule)
- Package contents config (maps each box type to exact vegetable quantities)
- Growing tracker (what's planted, harvest date, expected yield)
- Demand calculator (auto: orders × package contents = total kg needed)
- Gap dashboard (needed vs. available per vegetable per week, color coded)
- Alerts ("plant X kg of tomatoes by [date] to cover [week]")

## Key Questions Still to Resolve with Connie
1. Which vegetables do they grow? (need full list + grow times)
2. What packages do they sell? (exact contents per box type)
3. Delivery schedule? (weekly / monthly / fixed day)
4. Who uses the dashboard? (how technical are they?)
5. Scope: grow-plan + inventory only, or also client sign-ups and payments?
6. Do they already track anything? (spreadsheet, notebook — get a copy)

## Tech Stack
Next.js frontend, PostgreSQL (Supabase or Railway), hosted on Railway.

## Phases
- Phase 1 MVP: client/order management, package config, demand calculator, basic gap view
- Phase 2: growing tracker, color-coded gap dashboard, planting alerts
- Phase 3 (optional): delivery scheduling, wastage tracking, mobile UI

## Pricing Anchor
Their stated pain is R10–20k/month in lost profit. Even recovering 50% = R5–10k/month.
Use this to anchor value when scoping the retainer or project fee.

## Notes
- UI must be dead simple — they are farmers, not tech users
- Gap dashboard is the highest-value screen — build it first
- Avoid scope creep into e-commerce/payments unless specifically requested
""".strip()

def run():
    # 1. Upsert client
    existing = supabase.table("clients").select("id").eq("name", "Connie Farming Co").execute()
    if existing.data:
        client_id = existing.data[0]["id"]
        print(f"Client already exists: {client_id}")
    else:
        result = supabase.table("clients").insert({
            "name": "Connie Farming Co",
            "pipeline_stage": "pipeline",
            "active": True,
            "industry": "Agriculture / Farming",
            "relationship_notes": "Connie is also the contact for Osun Consulting Group. This is her separate farming business.",
            "next_step": "Resolve scoping questions (vegetable list, package contents, delivery schedule) before building"
        }).execute()
        client_id = result.data[0]["id"]
        print(f"Created client: {client_id}")

    # 2. Upsert client brief
    supabase.table("client_briefs").upsert({
        "client_id": client_id,
        "brief": BRIEF
    }).execute()
    print("Client brief saved.")

    # 3. Upsert connie_context key for system prompt visibility
    supabase.table("connie_context").upsert({
        "key": "farming_project",
        "value": BRIEF
    }).execute()
    print("connie_context key 'farming_project' saved.")

    print("\nDone. Connie's farming project is now in Supabase.")

if __name__ == "__main__":
    run()
