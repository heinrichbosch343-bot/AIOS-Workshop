"""
transcripts.py — client meeting memory.

Upload a meeting transcript (via Telegram or the dashboard) and this:
  1. extracts the text (txt / md / csv / vtt / srt / docx / pdf / xlsx),
  2. uses Claude to pull out WHO the client is, WHAT they do, their PROBLEMS,
     what we're BUILDING for them, and the NEXT STEPS,
  3. stores the FULL transcript (client_transcripts) for deep questions, and
  4. merges the findings into a short LIVING BRIEF per client (client_briefs),
     so Heinrich can ask "what are we building for X?" any time and get a current,
     accurate refresher.

Recall is exposed to the agent brain as two tools (CLIENT_MEMORY_TOOLS), so it works
in normal chat on both Telegram and the dashboard. Mirrors the LinkedIn tool pattern.

Immutable style: functions build NEW dicts and return DB rows; inputs are never mutated.
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional, Union

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY
from db.client import supabase
from services import context_store as cs
from services.drive_extract import _pdf_to_text, _docx_to_text, _xlsx_to_text

client = Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-6"
MAX_TRANSCRIPT_CHARS = 100_000   # safety cap for a single uploaded file
MAX_SEARCH_CHARS = 120_000       # cap on the corpus handed to Claude for deep search


# ── text extraction from an uploaded file (raw bytes) ────────────────────────

def extract_text_from_bytes(raw: bytes, filename: str = "") -> str:
    """Extract readable text from uploaded file bytes. Reuses the Drive extractors."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        text = _pdf_to_text(raw)
    elif name.endswith(".docx"):
        text = _docx_to_text(raw)
    elif name.endswith(".xlsx"):
        text = _xlsx_to_text(raw)
    else:
        # txt / md / csv / vtt / srt / unknown -> best-effort UTF-8 decode
        text = raw.decode("utf-8", "ignore")
    return (text or "").strip()[:MAX_TRANSCRIPT_CHARS]


# ── Claude: analyse a transcript into structured intelligence ─────────────────

_ANALYZE_SYSTEM = (
    "You extract structured client intelligence from a meeting transcript for Heinrich at "
    "BoschAI (he builds custom AI Operating Systems for businesses). Return ONLY valid JSON, "
    "no prose, no code fences."
)


def _analyze(transcript: str, roster: list, hint: Optional[str]) -> dict:
    """Ask Claude for the structured brief AND which EXISTING client this meeting is with
    (matched against the roster), or that it's genuinely new.

    `roster` is the existing client list (with notes) so a person maps to their company and
    spelling variants resolve. `hint` is the optional Telegram caption — treated as a loose
    hint that may be an instruction, NEVER as the authoritative client name."""
    if roster:
        roster_lines = "\n".join(
            f"- {c['name']}"
            + (f" — {(c.get('relationship_notes') or c.get('industry') or '')[:80]}"
               if (c.get('relationship_notes') or c.get('industry')) else "")
            for c in roster
        )
    else:
        roster_lines = "(no existing clients yet)"
    hint_line = f'\nHeinrich\'s note sent with the file: "{hint}"\n' if hint else ""
    prompt = (
        f"Existing clients (match against these):\n{roster_lines}\n"
        f"{hint_line}\n"
        f'Transcript:\n"""\n{transcript}\n"""\n\n'
        "Return ONLY this JSON (use null where genuinely unknown):\n"
        "{\n"
        '  "matched_client": "the EXACT name from the existing-clients list this meeting is with, '
        'or null if it is genuinely a NEW client not already in the list",\n'
        '  "client_name": "if NEW, a clean company or person name to file them under (a NAME, not a '
        'sentence); if matched, repeat the matched name",\n'
        '  "meeting_date": "YYYY-MM-DD if a date is stated, else null",\n'
        '  "summary": "3-5 sentence summary of what was discussed",\n'
        '  "what_they_do": "what the client/business does",\n'
        '  "problems": "their key problems / pains discussed",\n'
        '  "building": "what we are building or proposing to help them",\n'
        '  "next_steps": "agreed next steps / action items"\n'
        "}\n\n"
        "Matching rules: a person maps to THEIR company (a meeting with the owner of a company in "
        "the list = that company). Tolerate spelling variants and mishearings (e.g. Osan = Osun). "
        "Heinrich's note may be an instruction, not a name — always extract the real client from the "
        "transcript content. Set matched_client to null ONLY if truly none of the listed clients fit."
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=1300, system=_ANALYZE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return _parse_json(text)


def _parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model response (tolerates code fences)."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


# ── Claude: merge new findings into the living brief ─────────────────────────

_BRIEF_SYSTEM = (
    "You maintain a short, living brief about ONE of Heinrich's clients. Keep it tight, factual "
    "and current. Plain text with these exact sections, each 1-4 short lines:\n"
    "What they do:\nTheir problems:\nWhat we're building:\nNext steps:\n\n"
    "Merge the new meeting info into the existing brief without losing important prior facts. "
    "Where new info updates or supersedes old info, prefer the new. No preamble — output only the brief."
)


def _rebuild_brief(existing_brief: str, analysis: dict) -> str:
    new_info = (
        f"What they do: {analysis.get('what_they_do') or '-'}\n"
        f"Their problems: {analysis.get('problems') or '-'}\n"
        f"What we're building: {analysis.get('building') or '-'}\n"
        f"Next steps: {analysis.get('next_steps') or '-'}\n"
        f"This meeting summary: {analysis.get('summary') or '-'}"
    )
    prompt = (
        f"EXISTING BRIEF (may be empty):\n{existing_brief or '(none yet)'}\n\n"
        f"NEW MEETING INFO:\n{new_info}\n\n"
        "Produce the updated brief now."
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=800, system=_BRIEF_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


# ── brief storage ────────────────────────────────────────────────────────────

def _get_brief_row(client_id: str) -> Optional[dict]:
    res = supabase.table("client_briefs").select("*").eq("client_id", client_id).limit(1).execute()
    return res.data[0] if res.data else None


def _save_brief(client_id: str, brief: str) -> None:
    supabase.table("client_briefs").upsert(
        {"client_id": client_id, "brief": brief, "updated_at": datetime.now(timezone.utc).isoformat()},
        on_conflict="client_id",
    ).execute()


def _is_iso_date(s: str) -> bool:
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except Exception:
        return False


# ── ingest: the main entry point used by the Telegram upload handler ──────────

def ingest_transcript(raw: Union[bytes, str], filename: str = "",
                      client_hint: Optional[str] = None, source: str = "telegram") -> dict:
    """Process an uploaded transcript end-to-end. Returns a summary dict for the reply.

    `client_hint` (e.g. a Telegram caption) is only a HINT — it is NEVER used verbatim as the
    client name. The real client is resolved by matching the transcript against the existing
    client roster, so 'Connie' / 'Osan' map to the existing 'Osun Consulting Group' rather than
    spawning a junk client.
    """
    text = raw if isinstance(raw, str) else extract_text_from_bytes(raw, filename)
    if not text or len(text) < 20:
        raise ValueError("Could not read any usable text from that file.")

    roster = cs.list_clients()
    analysis = _analyze(text, roster, client_hint)

    roster_by_lower = {c["name"].lower(): c["name"] for c in roster}
    matched = (analysis.get("matched_client") or "").strip()
    proposed = (analysis.get("client_name") or "").strip()

    # Prefer the exact existing client the model matched; else its proposed name if that
    # happens to match an existing client. Never use the raw hint/caption as a name.
    resolved_existing = None
    if matched and matched.lower() in roster_by_lower:
        resolved_existing = roster_by_lower[matched.lower()]
    elif proposed and proposed.lower() in roster_by_lower:
        resolved_existing = roster_by_lower[proposed.lower()]

    if resolved_existing:
        client_row = cs._find_client_by_name(resolved_existing)
        created_client = False
    else:
        new_name = proposed or matched
        # Guard: a caption/sentence must never become a client name.
        if not new_name or len(new_name) > 60 or new_name.count(" ") > 6:
            raise ValueError(
                "I couldn't tell which client this transcript is for. Re-send it with just the "
                "client's name as the caption (e.g. 'Osun')."
            )
        existing = cs._find_client_by_name(new_name)
        if existing:
            client_row, created_client = existing, False
        else:
            from services.pipeline import add_lead
            client_row = add_lead(
                new_name, notes=f"Created from uploaded transcript: {filename or 'meeting'}",
                origin=source,
            )
            created_client = True
    client_id = client_row["id"]

    md = analysis.get("meeting_date")
    meeting_date = md if (isinstance(md, str) and _is_iso_date(md)) else None

    # Store the full transcript for deep questions.
    supabase.table("client_transcripts").insert({
        "client_id": client_id,
        "title": filename or "Meeting transcript",
        "content": text,
        "summary": analysis.get("summary"),
        "meeting_date": meeting_date,
        "source": source,
    }).execute()

    # Merge into the living brief.
    prev = _get_brief_row(client_id)
    brief = _rebuild_brief(prev["brief"] if prev else "", analysis)
    _save_brief(client_id, brief)

    cs.log_event("note", f"Transcript added for {client_row['name']}",
                 client_id=client_id, source=source)

    return {
        "client_name": client_row["name"],
        "client_created": created_client,
        "summary": analysis.get("summary") or "",
        "brief": brief,
        "meeting_date": meeting_date,
    }


# ── recall (exposed to the agent as tools) ───────────────────────────────────

def _resolve_client(name: str) -> Optional[dict]:
    """Resolve a client by exact name, then fuzzily by name OR relationship notes — so 'Connie'
    finds 'Osun Consulting Group' (whose notes name her) and 'Osun' matches the full company
    name. Returns the best-matching row, or None."""
    name = (name or "").strip()
    if not name:
        return None
    exact = cs._find_client_by_name(name)
    if exact:
        return exact
    term = name.replace(",", " ").strip()
    try:
        res = (
            supabase.table("clients").select("*")
            .or_(f"name.ilike.*{term}*,relationship_notes.ilike.*{term}*")
            .execute()
        ).data
    except Exception:
        res = []
    if not res:
        return None
    name_hits = [c for c in res if term.lower() in (c.get("name") or "").lower()]
    if len(name_hits) == 1:
        return name_hits[0]
    return res[0]


def get_client_brief(client_name: str) -> dict:
    """Return the living brief + recent meeting list for a client."""
    row = _resolve_client(client_name)
    if not row:
        return {"found": False, "message": f"No client called '{client_name}' yet."}
    brief_row = _get_brief_row(row["id"])
    meetings = (
        supabase.table("client_transcripts")
        .select("title, summary, meeting_date, created_at")
        .eq("client_id", row["id"]).order("created_at", desc=True).limit(10).execute().data
    )
    return {
        "found": True,
        "client_name": row["name"],
        "stage": row.get("pipeline_stage"),
        "brief": brief_row["brief"] if brief_row else None,
        "meetings": meetings,
        "meeting_count": len(meetings),
    }


def search_client_transcripts(client_name: str, question: str) -> dict:
    """Answer a detailed question from the full text of a client's transcripts."""
    row = _resolve_client(client_name)
    if not row:
        return {"found": False, "message": f"No client called '{client_name}' yet."}
    txs = (
        supabase.table("client_transcripts")
        .select("title, content, meeting_date, created_at")
        .eq("client_id", row["id"]).order("created_at", desc=True).limit(10).execute().data
    )
    if not txs:
        return {"found": True, "answer": f"No transcripts stored for {row['name']} yet."}

    blocks = []
    for t in txs:
        label = t.get("title") or t.get("meeting_date") or (t.get("created_at") or "")[:10]
        blocks.append(f"[{label}]\n{t['content']}")
    corpus = "\n\n---\n\n".join(blocks)[:MAX_SEARCH_CHARS]

    prompt = (
        f"Question about client {row['name']}: {question}\n\n"
        f"Their meeting transcripts:\n\n{corpus}\n\n"
        "Answer ONLY from these transcripts. If the answer isn't in them, say so plainly. Be concise."
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=1000, messages=[{"role": "user", "content": prompt}],
    )
    answer = "".join(b.text for b in resp.content if b.type == "text").strip()
    return {"found": True, "client_name": row["name"], "answer": answer}


# ── agent tool definitions + dispatch (mirrors services.linkedin) ─────────────

CLIENT_MEMORY_TOOLS = [
    {
        "name": "get_client_brief",
        "description": (
            "Get the living brief for a client, built from uploaded meeting transcripts — what they "
            "do, their problems, what BoschAI is building for them, and next steps, plus a list of "
            "their meetings. Use this whenever Heinrich asks 'what are we doing/building for X', "
            "'remind me about X', 'what's the situation with X', or wants a refresher on a client."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"client_name": {"type": "string", "description": "The client/company name"}},
            "required": ["client_name"],
        },
    },
    {
        "name": "search_client_transcripts",
        "description": (
            "Answer a detailed question using the FULL text of a client's uploaded meeting "
            "transcripts (deeper than the brief). Use for specifics: 'what did X say about pricing', "
            "'what were the exact pain points', 'what did we promise in the last meeting with X'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_name": {"type": "string", "description": "The client/company name"},
                "question": {"type": "string", "description": "Heinrich's question, in plain English"},
            },
            "required": ["client_name", "question"],
        },
    },
]


def handle_client_memory_tool(name: str, tool_input: dict) -> dict:
    if name == "get_client_brief":
        return get_client_brief(tool_input["client_name"])
    if name == "search_client_transcripts":
        return search_client_transcripts(tool_input["client_name"], tool_input.get("question", ""))
    return {"error": f"Unknown client-memory tool: {name}"}
