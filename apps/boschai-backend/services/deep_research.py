"""
Deep Research engine — a backend port of the multi-agent deep-research module.

Method (faithful to .claude/skills/deep-research): recon picks angles, parallel
topic agents research each angle deeply with source scoring + triangulation, a
critic flags weak claims, and a synthesis agent produces a confidence-weighted
master dossier. Self-contained: uses Firecrawl (web) + OpenAlex (academic) as
agent tools, so it runs anywhere the backend runs.
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from config import ANTHROPIC_API_KEY
from services import academic
from services.research import _search as firecrawl_search, _scrape as firecrawl_scrape

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-6"      # agents + recon + critic
MODEL_SYNTH = "claude-sonnet-4-6"  # master synthesis

MAX_ANGLES = 4
MAX_TOOL_ROUNDS = 6              # per topic agent

# ── Source scoring rubric, ported verbatim from the module ──
_SCORING = (
    "Score every source before going deep:\n"
    "RECENCY: primary work any date 2 | <30d 3 | <90d 2 | <1yr 1 | older current-tech 0\n"
    "SOURCE_TYPE: primary/academic 3 | named practitioner 2 | journalism 1 | aggregator 0\n"
    "SPECIFICITY: numbers/code/failure modes 2 | some specifics 1 | generic 0\n"
    "INDEPENDENCE: not citing existing 1 | cites existing 0.5 | same org 0\n"
    "TOTAL >=5 pursue | 3-4 include with caveat | <3 drop.\n"
    "Triangulate: no factual claim without 2 independent sources. Label "
    "[SINGLE SOURCE], [UNVERIFIED], or [CONFLICTING] when that bar isn't met. "
    "If no reliable source exists for a claim, say so — do not invent."
)

# ── Tools available to topic agents ──
TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web and get page content (markdown). Your main tool. Run several focused queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "description": "How many results (default 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "scrape_url",
        "description": "Fetch the full content of a specific URL (company page, article, thread).",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "academic_search",
        "description": "Search peer-reviewed papers (OpenAlex) for evidence and sector/governance research.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "year_from": {"type": "integer", "description": "Earliest publication year (default 2021)"},
            },
            "required": ["query"],
        },
    },
]


def _run_tool(name: str, inp: dict) -> dict:
    try:
        if name == "web_search":
            return {"results": firecrawl_search(inp["query"], limit=min(inp.get("limit", 5), 6))}
        if name == "scrape_url":
            r = firecrawl_scrape(inp["url"])
            return r or {"error": "scrape returned nothing"}
        if name == "academic_search":
            return {"papers": academic.search(inp["query"], year_from=inp.get("year_from", 2021))}
        return {"error": f"unknown tool {name}"}
    except Exception as e:
        return {"error": str(e)}


def _agent_loop(system: str, user: str, max_rounds: int = MAX_TOOL_ROUNDS,
                use_tools: bool = True, max_tokens: int = 2200) -> str:
    """Run one agentic Claude conversation to completion. Returns final text."""
    messages = [{"role": "user", "content": user}]
    for _ in range(max_rounds):
        resp = client.messages.create(
            model=MODEL, max_tokens=max_tokens, system=system,
            tools=TOOLS if use_tools else [], messages=messages,
        )
        if use_tools and resp.stop_reason == "tool_use":
            assistant = []
            for b in resp.content:
                if b.type == "text":
                    assistant.append({"type": "text", "text": b.text})
                elif b.type == "tool_use":
                    assistant.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
            messages.append({"role": "assistant", "content": assistant})
            results = []
            for b in resp.content:
                if b.type == "tool_use":
                    results.append({
                        "type": "tool_result", "tool_use_id": b.id,
                        "content": json.dumps(_run_tool(b.name, b.input or {}), default=str)[:9000],
                    })
            messages.append({"role": "user", "content": results})
            continue
        return "".join(b.text for b in resp.content if b.type == "text")
    # Out of rounds — ask for a final writeup using what's gathered.
    messages.append({"role": "user", "content": "Stop searching. Write your final report now from what you have."})
    resp = client.messages.create(model=MODEL, max_tokens=max_tokens, system=system, messages=messages)
    return "".join(b.text for b in resp.content if b.type == "text")


# ════════ Phase 1: Recon ════════
def recon(topic: str, time_period: str = "last 12 months") -> dict:
    """Map the topic into 3-4 research angles. Returns {angles:[{title,slug,focus}], notes}."""
    schema_hint = (
        'Return ONLY JSON: {"angles":[{"title":"...","focus":"one line on what this agent '
        'investigates"}],"notes":"one line on where the signal likely lives"}'
    )
    sys = (
        "You are a research recon agent for BoschAI (a custom AIOS agency in South Africa). "
        "Do a fast shallow pass to decide the best 3-4 angles for a deeper multi-agent "
        "investigation of the subject. Angles must be distinct and non-overlapping. For a company, good "
        "angles include: what they do & market position; leadership & ownership; operations, tooling & "
        "automation maturity; reputation, news & red flags. " + schema_hint
    )
    out = _agent_loop(
        sys,
        f"Subject: {topic}\nTime focus: {time_period}\nPropose the angle roster now.",
        max_rounds=2, use_tools=True, max_tokens=900,
    )
    data = {}
    try:
        start, end = out.find("{"), out.rfind("}")
        data = json.loads(out[start:end + 1])
        angles = data.get("angles", [])[:MAX_ANGLES]
    except Exception:
        angles = []
    if not angles:  # fallback roster
        angles = [
            {"title": "Business & market position", "focus": "what they do, sector, size, clients"},
            {"title": "Leadership & ownership", "focus": "founders, executives, board, owners"},
            {"title": "Operations, tooling & automation maturity", "focus": "team size, processes, tech stack, manual workload, data sources"},
            {"title": "Reputation, news & red flags", "focus": "recent news, litigation, controversy"},
        ]
    for i, a in enumerate(angles, 1):
        a["slug"] = f"{i:02d}-" + "-".join(a["title"].lower().split())[:40]
    return {"angles": angles, "notes": data.get("notes", "")}


# ════════ Phase 2: Topic agent ════════
def topic_agent(topic: str, angle: dict, time_period: str) -> dict:
    """Research one angle deeply. Returns {angle, slug, report}."""
    sys = (
        "You are a deep research agent for BoschAI (custom AIOS agency, South Africa). "
        f"Investigate one angle of the subject exhaustively, following signal across the web and "
        f"academic sources.\n\n{_SCORING}\n\n"
        "Method: (1) run 3-5 varied web searches for your angle; (2) scrape the most promising pages "
        "in full; (3) chase specifics — names, numbers, dates, primary documents; (4) actively look for "
        "contradictions and red flags. Prefer primary sources over commentary. Don't pad.\n\n"
        "Then write a tight markdown report with these sections: Executive Summary; Key Findings (each "
        "with a Confidence: High/Medium/Low and the sources it rests on); Tensions & Contradictions; "
        "Gaps & Unknowns (say what you could NOT verify); Citations (table: source | type | URL). "
        "Every claim must trace to a source you actually read. Do not use em dashes."
    )
    user = (
        f"SUBJECT (big picture): {topic}\n"
        f"YOUR ANGLE: {angle['title']} — {angle.get('focus','')}\n"
        f"Time focus: {time_period}\n\nBegin researching this angle now."
    )
    report = _agent_loop(sys, user, max_rounds=MAX_TOOL_ROUNDS, use_tools=True, max_tokens=2400)
    return {"angle": angle["title"], "slug": angle["slug"], "report": report}


# ════════ Phase 3: Critic ════════
def critic(topic: str, reports: list[dict]) -> str:
    joined = "\n\n".join(f"=== REPORT: {r['angle']} ===\n{r['report']}" for r in reports)
    sys = (
        "You are a research critic. Read the topic-agent reports and flag quality problems before "
        "synthesis. Do not do new research. Check for: unlabeled single-source claims, echo chambers, "
        "claim/evidence weight mismatch, unsupported generalisations, cross-report contradictions, and "
        "gaps synthesised over instead of flagged. Output concise markdown: Critical Flags, Minor Flags, "
        "Cross-Report Contradictions, Verification Queue. Reference the specific report and claim."
    )
    return _agent_loop(sys, f"Subject: {topic}\n\n{joined[:60000]}", use_tools=False, max_tokens=1500)


# ════════ Phase 4: Synthesis ════════
def synthesis(topic: str, reports: list[dict], critic_notes: str, time_period: str) -> str:
    joined = "\n\n".join(f"=== {r['angle']} ===\n{r['report']}" for r in reports)
    sys = (
        "You are a research synthesis agent for BoschAI. Merge the topic-agent reports and the "
        "critic notes into one authoritative dossier. Weight confidence honestly — do not flatten "
        "everything to the same level. Required markdown structure:\n"
        "# Deep Research Dossier: {subject}\n"
        "## The Short Version (5-10 bullets, each tagged [HIGH]/[MEDIUM]/[LOW])\n"
        "## High-Confidence Findings\n## Medium-Confidence Findings\n"
        "## Tensions & Contradictions\n## Key People & Entities\n"
        "## What We Don't Know (gaps, unverified, needs-verification)\n"
        "## Angle for BoschAI (how a custom AIOS build from BoschAI could help them, and how to open)\n"
        "## Source Registry (table: source | type | URL)\n"
        "Do not use em dashes. Be specific and concrete."
    )
    resp = client.messages.create(
        model=MODEL_SYNTH, max_tokens=4000, system=sys,
        messages=[{"role": "user", "content":
                   f"Subject: {topic}\nTime period: {time_period}\n\nCRITIC NOTES:\n{critic_notes}\n\n"
                   f"TOPIC REPORTS:\n{joined[:80000]}"}],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


# ════════ Orchestrator ════════
def run_deep_research(topic: str, time_period: str = "last 12 months", on_progress=None) -> dict:
    """Run the full pipeline. on_progress(phase, detail, pct) is called as it advances."""
    def prog(phase, detail, pct):
        if on_progress:
            on_progress(phase, detail, pct)

    prog("recon", "Scoping research angles", 8)
    rec = recon(topic, time_period)
    angles = rec["angles"]
    prog("agents", f"Researching {len(angles)} angles in parallel", 20)

    reports = [None] * len(angles)
    with ThreadPoolExecutor(max_workers=len(angles)) as ex:
        futures = {ex.submit(topic_agent, topic, a, time_period): i for i, a in enumerate(angles)}
        done = 0
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                reports[i] = fut.result()
            except Exception as e:
                reports[i] = {"angle": angles[i]["title"], "slug": angles[i]["slug"],
                              "report": f"(agent failed: {e})"}
            done += 1
            prog("agents", f"{done}/{len(angles)} angle reports complete", 20 + int(55 * done / len(angles)))

    reports = [r for r in reports if r]
    prog("critic", "Reviewing findings for weak claims", 80)
    critic_notes = critic(topic, reports)

    prog("synthesis", "Writing the master dossier", 90)
    dossier = synthesis(topic, reports, critic_notes, time_period)

    prog("done", "Complete", 100)
    return {
        "topic": topic,
        "time_period": time_period,
        "angles": [a["title"] for a in angles],
        "dossier": dossier,
        "critic_notes": critic_notes,
        "reports": reports,
    }
