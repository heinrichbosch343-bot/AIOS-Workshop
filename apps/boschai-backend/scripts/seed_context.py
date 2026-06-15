"""
seed_context.py — push Heinrich's canonical context into Supabase so the DEPLOYED brain
(on Railway) reflects reality. This is what makes Supabase the single source of truth at
handover: after this runs, Heinrich works entirely from Railway and the local context/*.md
files become dev-only.

    cd apps/boschai-backend
    python scripts/seed_context.py

Idempotent — safe to run repeatedly. Run it once at handover, and again any time his core
context materially changes.

What it writes:
  • connie_context facts (bio, business, writing style, report format, strategy, key metric)
    — the foundation the brain loads on every call. Context facts are written directly (no
    timeline spam on re-runs).
  • Any clients in CLIENTS below. Seeded with the current pipeline up front; Heinrich can add
    more just by talking to the bot ("we signed X"), which is the whole point of this feature.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import supabase  # noqa: E402
from services import context_store as cs  # noqa: E402


# ── Core context facts (the brain reads ALL of these every call) ──────────────
# bio/business/writing_style/report_format are surfaced in named sections; the rest
# appear under "More About His Business". Edit freely as the business evolves.
CONTEXT_FACTS = {
    "bio": (
        "Heinrich Bosch, founder and sole operator of BoschAI, a solo AI agency. He builds and "
        "maintains custom AI Operating Systems (AIOS) for medium-to-large companies. He personally "
        "handles every part of the business — sales, delivery, outreach, and client management."
    ),
    "business": (
        "BoschAI builds custom AIOS — an autonomous intelligence layer wrapped around a client's "
        "entire business (context, data, intelligence/daily-brief, automation) using the AAA "
        "Accelerator module stack. The work runs end-to-end: discovery, building the context and "
        "data layers, wiring up the daily brief, and automating recurring tasks one by one. As a "
        "solo operator, Heinrich handles sales, delivery, outreach, and client management himself."
    ),
    "writing_style": (
        "Sharp, direct, and concrete. No fluff, no filler, no hedging. Sounds like a sharp human "
        "operator who knows his stuff — never generic AI output. Every piece must sound like "
        "Heinrich wrote it."
    ),
    "report_format": (
        "Heinrich produces AIOS proposals and build plans rather than long-form reports. Tight and "
        "scannable: the problem, the proposed AIOS layers/modules, what gets automated, the rollout, "
        "and the expected bandwidth or revenue impact. Concrete and specific throughout."
    ),
    "strategy": (
        "Hit $50,000 in revenue within 3 months. Close first clients via warm referrals; launch "
        "cold outreach (Instantly AI + Apollo) within 2 weeks. Land and deliver AIOS builds fast, "
        "then convert them into ongoing retainers."
    ),
    "key_metric": (
        "Total revenue vs the $50k target, and the number of active clients on retainer. This is "
        "the headline metric — every signed build and retainer moves it. The biggest constraint on "
        "growth is filling the top of the pipeline (warm referrals + cold outreach) while still "
        "delivering current builds solo."
    ),
}


# ── Clients (edit to match reality; Heinrich can add more by talking to the bot) ──
# Each entry: {"name": str, "stage": lead|pipeline|anchor|inactive,
#              "industry"?: str, "notes"?: str, "next_step"?: str}
CLIENTS: list[dict] = [
    {
        "name": "Osun Consulting Group",
        "stage": "anchor",
        "industry": "Corporate governance consulting",
        "notes": (
            "Connie Osun, CEO. Governance-report client — BoschAI delivered an AIOS-adjacent build "
            "(context + Drive knowledge pool + daily brief) to cut her manual delivery overhead. "
            "Johannesburg."
        ),
        "next_step": "Final sign-off on the delivered build, then convert to a retainer.",
    },
    {
        "name": "Lourens Delport",
        "stage": "lead",
        "notes": "Early-stage prospect from a warm referral. Consulting firm owner.",
        "next_step": "Run the discovery call and scope an initial AIOS build.",
    },
]


def seed_facts() -> None:
    rows = [{"key": k, "value": v} for k, v in CONTEXT_FACTS.items()]
    supabase.table("connie_context").upsert(rows, on_conflict="key").execute()
    print(f"✓ seeded {len(rows)} context facts: {', '.join(CONTEXT_FACTS)}")


def seed_clients() -> None:
    if not CLIENTS:
        print("• no clients to seed (CLIENTS is empty) — Heinrich can add them by talking to the bot")
        return
    for c in CLIENTS:
        row = cs.upsert_client(
            c["name"], stage=c.get("stage"), industry=c.get("industry"),
            notes=c.get("notes"), next_step=c.get("next_step"), source="seed",
        )
        print(f"  ✓ client: {row['name']} [{row.get('pipeline_stage')}]")


def main() -> None:
    seed_facts()
    seed_clients()
    summary = cs.pipeline_summary()
    print(f"\nDone. Anchor clients now: {summary['anchor']}  (all stages: {summary['counts'] or 'none'})")
    print("Supabase is now the single source of truth — Heinrich runs entirely from Railway.")


if __name__ == "__main__":
    main()
