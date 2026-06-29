"""
ask.py — the "Ask the AI" engine for the Meeting Intelligence demo.

Reads the dated meeting records from the local store and answers questions with Claude:
  - no client selected  -> searches EVERY meeting (date / person / topic questions)
  - a client selected   -> scopes the deep detail to that client

The store always prepends a dated index of all meetings, so even broad questions like
"what was recorded on 2026-06-25 and with who?" work without picking a client.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

import store

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"   # the recall/review answer is the star of the demo — use the strong model

_SYSTEM = (
    "You are the CRM assistant for Heinrich, who runs an AI agency. You answer his questions "
    "about client meetings using ONLY the meeting records provided.\n\n"
    "Each record has a DATE, a CLIENT (who the meeting was with), a TITLE, a SUMMARY, ACTION ITEMS, "
    "and the full TRANSCRIPT.\n\n"
    "Rules:\n"
    "1. Use only the records below — never invent meetings, people, dates, or facts.\n"
    "2. Answer date questions ('what was recorded on <date>, with who, about what'), person questions "
    "('what happened with <client>'), and topic questions.\n"
    "3. When asked for a 'full review', structure it clearly: the date, who it was with, what was "
    "discussed, decisions made, and the action items / next steps.\n"
    "4. Always ground answers in the meeting DATE and CLIENT so it's clear which meeting you mean.\n"
    "5. If the records don't contain the answer, say so plainly — don't guess.\n"
    "Be concise, specific, and useful."
)


def answer(question: str, client: str = None) -> dict:
    """Answer a question against the stored meetings. Returns {answer, meetings_searched, scope}."""
    question = (question or "").strip()
    if not question:
        return {"answer": "Ask a question first.", "meetings_searched": 0, "scope": "none"}
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is missing from .env")

    corpus = store.build_corpus(client)
    all_count = len(store.get_meetings())
    if not corpus:
        return {
            "answer": "No meetings have been logged yet. Log one in the Capture tab first.",
            "meetings_searched": 0,
            "scope": "empty",
        }

    from anthropic import Anthropic

    scope_line = f"(Scope: meetings with {client})" if client else "(Scope: all clients)"
    client_obj = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client_obj.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=_SYSTEM,
        messages=[{"role": "user", "content": (
            f"{scope_line}\n\nMeeting records:\n\n{corpus}\n\n"
            f"Question: {question}"
        )}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return {
        "answer": text,
        "meetings_searched": all_count if not client else len(store.get_meetings(client)),
        "scope": client or "all clients",
    }
