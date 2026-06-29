"""
store.py — local CRM-style store for the Meeting Intelligence demo.

A dedicated SQLite file (data/meeting_demo.db) so the demo is fully isolated from the
real IntelOS pipeline DB, yet still a plain local file this Claude CLI can read directly.

Two tables:
  clients   — the roster you click when logging ("save it for this person")
  meetings  — one row per logged transcript/recording, always DATED

Everything is immutable-friendly: functions take values and return new rows; nothing
mutates a passed-in object.
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# demos/meeting-intelligence/store.py -> parents[2] = workspace root
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = WORKSPACE_ROOT / "data" / "meeting_demo.db"

# Pre-seeded so the client picker looks like a real CRM on camera, even on a fresh DB.
# These are Heinrich's actual pipeline names — feel free to add more by typing in the UI.
SEED_CLIENTS = ["Osun Consulting Group", "Lourens Delport", "Cape Agri Cooperative"]

# Budget for the text handed to Claude when answering (matches the backend's cap).
MAX_CORPUS_CHARS = 120_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meetings (
    meeting_id       TEXT PRIMARY KEY,
    client           TEXT NOT NULL,
    title            TEXT,
    meeting_date     TEXT NOT NULL,       -- YYYY-MM-DD (when the meeting happened)
    source           TEXT,                -- "audio" | "transcript"
    duration_minutes INTEGER,
    speaker_count    INTEGER,
    transcript_text  TEXT NOT NULL,
    summary          TEXT,
    action_items     TEXT,                -- JSON array of strings
    logged_at        TEXT NOT NULL        -- ISO timestamp (when it was saved to the CRM)
);
"""


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_db() -> None:
    """Create tables if needed and seed demo clients on a fresh DB."""
    conn = _conn()
    try:
        conn.executescript(SCHEMA)
        existing = {r["name"] for r in conn.execute("SELECT name FROM clients")}
        for name in SEED_CLIENTS:
            if name not in existing:
                conn.execute(
                    "INSERT OR IGNORE INTO clients (name, created_at) VALUES (?, ?)",
                    (name, _now_iso()),
                )
        conn.commit()
    finally:
        conn.close()


def list_clients() -> List[str]:
    """Client roster, alphabetical."""
    ensure_db()
    conn = _conn()
    try:
        return [r["name"] for r in conn.execute("SELECT name FROM clients ORDER BY name")]
    finally:
        conn.close()


def add_client(name: str) -> str:
    """Add a client by name (no-op if it already exists). Returns the cleaned name."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Client name cannot be empty.")
    ensure_db()
    conn = _conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO clients (name, created_at) VALUES (?, ?)",
            (name, _now_iso()),
        )
        conn.commit()
        return name
    finally:
        conn.close()


def log_meeting(
    client: str,
    transcript_text: str,
    meeting_date: str,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    action_items: Optional[List[str]] = None,
    source: str = "transcript",
    duration_minutes: Optional[int] = None,
    speaker_count: Optional[int] = None,
) -> dict:
    """Save one meeting against a client. Auto-registers the client if new."""
    client = (client or "").strip()
    if not client:
        raise ValueError("Pick or name a client to log this meeting for.")
    if not (transcript_text or "").strip():
        raise ValueError("There's no transcript text to log.")
    add_client(client)

    logged_at = _now_iso()
    # Deterministic-ish id from content + client + time so re-logging the same file twice is distinct.
    import hashlib
    mid = "mtg_" + hashlib.md5(f"{client}|{logged_at}|{transcript_text[:200]}".encode()).hexdigest()[:16]

    conn = _conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO meetings "
            "(meeting_id, client, title, meeting_date, source, duration_minutes, "
            " speaker_count, transcript_text, summary, action_items, logged_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, client, title or "Meeting", meeting_date, source, duration_minutes,
             speaker_count, transcript_text, summary, json.dumps(action_items or []), logged_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {"meeting_id": mid, "client": client, "meeting_date": meeting_date, "logged_at": logged_at}


def get_meetings(client: Optional[str] = None) -> List[dict]:
    """Return logged meetings (newest first), optionally scoped to one client."""
    ensure_db()
    conn = _conn()
    try:
        if client:
            rows = conn.execute(
                "SELECT * FROM meetings WHERE client = ? ORDER BY meeting_date DESC, logged_at DESC",
                (client,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM meetings ORDER BY meeting_date DESC, logged_at DESC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["action_items"] = json.loads(d.get("action_items") or "[]")
            except (TypeError, json.JSONDecodeError):
                d["action_items"] = []
            out.append(d)
        return out
    finally:
        conn.close()


def build_corpus(client: Optional[str] = None) -> str:
    """Build the dated text the AI reads to answer questions.

    Always starts with a one-line INDEX of EVERY meeting (date · client · title · summary)
    so broad/date questions work even with no client selected, then appends FULL records
    (transcript included) for the in-scope meetings up to the character budget.
    """
    all_meetings = get_meetings()
    if not all_meetings:
        return ""

    # 1) Index of everything — lets the AI answer "what was on the 25th / with who / about what".
    index_lines = ["MEETING INDEX (every logged meeting):"]
    for m in all_meetings:
        index_lines.append(
            f"- {m['meeting_date']} · {m['client']} · {m.get('title') or 'Meeting'} "
            f":: {(m.get('summary') or '').strip()[:160]}"
        )
    index_block = "\n".join(index_lines)

    # 2) Full records for the in-scope subset (selected client, or all).
    scoped = get_meetings(client) if client else all_meetings
    full_blocks = []
    budget = MAX_CORPUS_CHARS - len(index_block)
    for m in scoped:
        actions = "; ".join(m.get("action_items") or []) or "-"
        block = (
            f"\n=== {m['meeting_date']} · {m['client']} · {m.get('title') or 'Meeting'} ===\n"
            f"Logged: {(m.get('logged_at') or '')[:10]} | Source: {m.get('source')}\n"
            f"Summary: {m.get('summary') or '-'}\n"
            f"Action items: {actions}\n"
            f"Transcript:\n{m.get('transcript_text') or ''}\n"
        )
        if budget - len(block) < 0:
            full_blocks.append(f"\n[... {len(scoped) - len(full_blocks)} more meeting(s) omitted for length ...]")
            break
        full_blocks.append(block)
        budget -= len(block)

    return index_block + "\n" + "".join(full_blocks)
