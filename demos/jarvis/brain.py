"""
brain.py — the thinking part of Johan.

    answer(question, history) -> {"say": str, "card": dict | None}

Claude with one tool: a read-only SQL SELECT against the Meridian demo database.
The schema lives in the system prompt; Claude writes its own queries. The final
answer is strict JSON: a short spoken line ("say") plus an optional visual card
spec ("card") rendered beside the orb — one model pass, no second call.
"""
import json
import os
from datetime import date
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# Walk up from this file to the workspace root and load .env (same pattern as the other demos).
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

import store

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

BRAIN_MODEL = "claude-sonnet-5"
MAX_TOKENS = 2000  # detailed cards need room; the spoken line stays short
MAX_TOOL_ITERATIONS = 8

QUERY_TOOL = {
    "name": "query_db",
    "description": (
        "Run one read-only SQL SELECT against the Meridian Manufacturing company database. "
        "Returns rows as JSON. Only SELECT (or WITH...SELECT) is allowed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "A single SQL SELECT statement."}},
        "required": ["sql"],
    },
}

CARD_TYPES = ("bar", "line", "table", "stat", "list")


def _system_prompt() -> str:
    today = date.today().isoformat()
    return f"""You are Johan, the AI for Meridian Manufacturing (Pty) Ltd, a mid-size industrial pumps and valves manufacturer in Cape Town. Today's date is {today}.

You answer questions from the leadership team using the company database, via the query_db tool.

PERSONA:
- Direct, confident, warm — a sharp Afrikaans businessman. South African English with light Afrikaans flavour: "ja", "nee", "lekker" where they fit naturally. Never force them into every answer, never write full Afrikaans sentences.
- Quick like a top executive assistant: headline number first, zero filler.

{store.SCHEMA_DESCRIPTION}

RULES FOR ANSWERING:
- Always query the database before answering any question about company data. Never invent numbers.
- Your spoken line will be READ ALOUD by a voice engine: 1 to 2 short punchy sentences, at most about 25 spoken words. The screen card carries the detail — do not read out lists of numbers.
- Round large numbers the way a person would say them: "twenty four and a half million rand", not "R24,600,000.00".
- If the data doesn't cover something, say so plainly and briefly.
- For questions about meetings or documents, query the relevant table (use LIKE for text search) and paraphrase what was actually said.
- If a SQL query errors, read the error, fix your query, and try again.

OUTPUT FORMAT — your final answer MUST be a single JSON object and NOTHING ELSE: no text before it, no text after it, no markdown, no code fences. The very first character of your final message must be {{ and the last must be }}:
{{"say": "<the spoken line>", "card": <card object or null>}}

Every answer that draws on the database MUST include a card. Pure conversation (greetings, clarifications, "we don't have that data") uses "card": null.

THE CARD CARRIES THE DETAIL. Put EVERY relevant detail from your query results into the card — dates, names, people, owners, values, statuses, notes, action items. The user READS the card while you SPEAK only the headline. Never make the user ask a follow-up for a detail you already queried.

Any card may also include "facts" — key facts shown as chips above the body:
"facts": [{{"label": "Date", "value": "2026-06-12"}}, {{"label": "Attendees", "value": "Willem, Thandi, Pieter"}}]

CARD TYPES (pick the one that best backs the answer):

1. bar — categories compared side by side:
{{"type": "bar", "title": "Revenue by quarter", "labels": ["2025-Q3","2025-Q4","2026-Q1","2026-Q2"], "values": [21.2, 22.0, 22.6, 24.6], "unit": "R m"}}

2. line — a trend over time:
{{"type": "line", "title": "Gross margin trend", "labels": ["2025-Q1","2025-Q2","2025-Q3","2025-Q4"], "values": [34.1, 34.8, 35.2, 36.0], "unit": "%"}}

3. table — spreadsheet-style records, up to 12 rows and 6 columns; include the columns that carry real information (names, owners, dates, values, status, notes); highlight_row (0-based) flags the row you're talking about:
{{"type": "table", "title": "Open pipeline deals", "columns": ["Deal", "Company", "Stage", "Value", "Owner", "Last activity"], "rows": [["Pump station retrofit", "Transnet", "Negotiation", "R8.4m", "Sipho", "2026-05-02"]], "highlight_row": 0}}

4. stat — one headline number:
{{"type": "stat", "title": "Q2 revenue", "value": "R24.6m", "label": "quarter ending June 2026", "delta": "+9% vs Q1"}}

5. list — detailed narrative breakdown (meetings, documents, discussions, decisions), up to 10 items; each item gets a short label and the full detail:
{{"type": "list", "title": "Exec meeting — Durban plant expansion", "facts": [{{"label": "Date", "value": "2026-06-12"}}, {{"label": "Type", "value": "Exec"}}, {{"label": "Attendees", "value": "Willem, Thandi, Pieter, Anika"}}], "items": [{{"label": "Decision", "text": "Approved R6.5m phase-one budget for the Durban plant"}}, {{"label": "Discussed", "text": "Load-shedding mitigation: generator capex vs solar PPA for the new line"}}, {{"label": "Action", "text": "Pieter to finalise the contractor shortlist by 10 July"}}]}}

For questions about a meeting or document, ALWAYS use "list": facts = date, type, attendees (all of them); items = every decision, discussion point, and action item from the record — quote or closely paraphrase what was actually said. Charts stay at up to 8 data points; values in charts are plain numbers (already scaled, e.g. millions) with the scale in "unit"."""


def _run_tool(sql: str) -> str:
    """Execute the query tool; return JSON rows or the error text so Claude can self-correct."""
    try:
        rows = store.run_readonly_sql(sql)
        return json.dumps(rows, default=str)
    except Exception as exc:  # surfaced to the model, never raised to the caller
        return f"SQL error: {exc}"


def _valid_card(card) -> Optional[dict]:
    """Return a cleaned card if it looks renderable, else None — never let a bad card break the voice loop."""
    if not isinstance(card, dict):
        return None
    kind = card.get("type")
    if kind not in CARD_TYPES:
        return None
    card = dict(card)  # cleaned copy — the original is never mutated
    if kind in ("bar", "line"):
        labels, values = card.get("labels"), card.get("values")
        if not (isinstance(labels, list) and isinstance(values, list) and labels and len(labels) == len(values)):
            return None
        if not all(isinstance(v, (int, float)) for v in values):
            return None
    elif kind == "table":
        columns, rows = card.get("columns"), card.get("rows")
        if not (isinstance(columns, list) and isinstance(rows, list) and columns and rows):
            return None
        if not all(isinstance(r, list) and len(r) == len(columns) for r in rows):
            return None
    elif kind == "stat":
        if not isinstance(card.get("value"), (str, int, float)):
            return None
    elif kind == "list":
        items = card.get("items")
        if not (isinstance(items, list) and items):
            return None
        clean_items = []
        for item in items:
            if isinstance(item, str) and item.strip():
                clean_items.append({"text": item.strip()})
            elif isinstance(item, dict) and isinstance(item.get("text"), str) and item["text"].strip():
                clean_items.append({"label": str(item.get("label") or "").strip(), "text": item["text"].strip()})
        if not clean_items:
            return None
        card["items"] = clean_items
    # "facts" chips are optional on every type; drop them if malformed.
    facts = card.get("facts")
    if facts is not None:
        clean_facts = [
            {"label": str(f["label"]), "value": str(f["value"])}
            for f in facts
            if isinstance(f, dict) and f.get("label") and f.get("value") is not None
        ] if isinstance(facts, list) else []
        if clean_facts:
            card["facts"] = clean_facts
        else:
            card.pop("facts", None)
    return card


def _parse_answer(text: str) -> dict:
    """Parse the strict-JSON answer; tolerate stray prose/fences around the JSON object.

    The model occasionally writes a sentence before the JSON — scan every '{'
    and take the first decodable object with a "say" key, so raw JSON is never
    spoken aloud. Fall back to plain speech with no card.
    """
    raw = (text or "").strip()
    decoder = json.JSONDecoder()
    start = raw.find("{")
    while start != -1:
        try:
            parsed, _ = decoder.raw_decode(raw, start)
        except json.JSONDecodeError:
            start = raw.find("{", start + 1)
            continue
        if isinstance(parsed, dict):
            say = parsed.get("say")
            if isinstance(say, str) and say.strip():
                return {"say": say.strip(), "card": _valid_card(parsed.get("card"))}
        start = raw.find("{", start + 1)
    # No usable JSON anywhere — speak the text as-is (minus any code fences).
    return {"say": raw.strip("`").strip() or "I wasn't able to find an answer to that.", "card": None}


def _no_answer(say: str) -> dict:
    return {"say": say, "card": None}


def answer(question: str, history: List[dict]) -> dict:
    """Answer one spoken question, given prior text-only turns [{'role','content'}, ...]."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is missing from .env")
    question = (question or "").strip()
    if not question:
        return _no_answer("I didn't catch that. Say it again?")

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # History is plain text turns from the browser; tool exchanges are never persisted.
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
    ]
    messages.append({"role": "user", "content": question})

    for iteration in range(MAX_TOOL_ITERATIONS + 1):
        # On the last pass, keep the tool declared (history references it) but forbid
        # calling it again so the model must answer with what it has.
        last_pass = iteration == MAX_TOOL_ITERATIONS
        response = client.messages.create(
            model=BRAIN_MODEL,
            max_tokens=MAX_TOKENS,
            system=_system_prompt(),
            tools=[QUERY_TOOL],
            tool_choice={"type": "none"} if last_pass else {"type": "auto"},
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            text = "".join(b.text for b in response.content if b.type == "text").strip()
            if not text:
                return _no_answer("I wasn't able to find an answer to that in the company data.")
            return _parse_answer(text)

        # Execute every tool call in this turn and feed the results back.
        messages.append({"role": "assistant", "content": response.content})
        tool_results = [
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": _run_tool(block.input.get("sql", "")),
            }
            for block in response.content
            if block.type == "tool_use"
        ]
        if iteration == MAX_TOOL_ITERATIONS - 1:
            tool_results.append({
                "type": "text",
                "text": 'That was the last query allowed. Answer now with what you have, in the required JSON format: {"say": "1-2 short sentences", "card": {...} or null}.',
            })
        messages.append({"role": "user", "content": tool_results})

    return _no_answer("I wasn't able to find an answer to that in the company data.")
