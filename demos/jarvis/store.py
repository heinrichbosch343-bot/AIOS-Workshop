"""
store.py — demo company database for the BoschAI Jarvis voice demo.

A dedicated SQLite file (data/jarvis_demo.db) holding one fictional client company,
Meridian Manufacturing (Pty) Ltd, so the demo is fully isolated from the real
DataOS/IntelOS databases. Same conventions as the other demo stores.

The brain talks to this DB through exactly one door: run_readonly_sql(), which
enforces SELECT-only twice (statement inspection + a read-only SQLite connection).
"""
import re
import sqlite3
from pathlib import Path
from typing import List

# demos/jarvis/store.py -> parents[2] = workspace root
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = WORKSPACE_ROOT / "data" / "jarvis_demo.db"

MAX_ROWS = 200

SCHEMA = """
CREATE TABLE IF NOT EXISTS financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quarter TEXT NOT NULL,
    revenue_zar REAL NOT NULL,
    cogs_zar REAL NOT NULL,
    opex_zar REAL NOT NULL,
    gross_margin_pct REAL NOT NULL,
    net_profit_zar REAL NOT NULL,
    headcount INTEGER NOT NULL,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS pipeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_name TEXT NOT NULL,
    company TEXT NOT NULL,
    stage TEXT NOT NULL,
    value_zar REAL NOT NULL,
    owner TEXT NOT NULL,
    expected_close TEXT,
    last_activity TEXT,
    notes TEXT
);
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_date TEXT NOT NULL,
    title TEXT NOT NULL,
    meeting_type TEXT NOT NULL,
    attendees TEXT NOT NULL,
    summary TEXT NOT NULL,
    action_items TEXT NOT NULL,
    transcript TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_date TEXT NOT NULL,
    title TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    content TEXT NOT NULL
);
"""

# Handed to the brain's system prompt so Claude can write its own SELECTs.
SCHEMA_DESCRIPTION = """The Meridian Manufacturing (Pty) Ltd database (SQLite). All money values are South African Rand (ZAR). Today's data is current through 2026-Q2 (the quarter ending June 2026 — "this quarter").

TABLE financials — one row per quarter, 2024-Q3 through 2026-Q2 (8 rows):
  quarter (TEXT, e.g. '2026-Q2'), revenue_zar, cogs_zar, opex_zar,
  gross_margin_pct (e.g. 36.0), net_profit_zar, headcount, notes (one-line story of the quarter)

TABLE pipeline — one row per sales deal (10 rows):
  deal_name, company, stage ('Lead'|'Qualified'|'Proposal'|'Negotiation'|'Closed Won'|'Closed Lost'),
  value_zar, owner (salesperson first name), expected_close (YYYY-MM-DD),
  last_activity (YYYY-MM-DD — old dates mean a stalled deal), notes

TABLE meetings — one row per recorded meeting (12 rows, last ~10 weeks):
  meeting_date (YYYY-MM-DD), title, meeting_type ('exec'|'sales'|'ops'|'client'),
  attendees (comma-separated names), summary, action_items (JSON array as text),
  transcript (full speaker-labeled transcript — use LIKE to search it)

TABLE documents — one row per document (10 rows):
  doc_date (YYYY-MM-DD), title, doc_type ('invoice'|'contract'|'report'|'proposal'), content (full text)

QUERY EFFICIENCY (answers are spoken live — speed matters):
- Prefer ONE targeted query that answers the question; only query again if truly needed.
- Never SELECT * on meetings or documents. transcript/content are very long — select them
  only when you must quote a specific meeting/document, and filter to the fewest rows first
  (summary and action_items usually suffice for meetings).
"""

_FORBIDDEN = re.compile(
    r"\b(ATTACH|PRAGMA|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)


def ensure_db() -> None:
    """Create the DB file and tables if they don't exist yet."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def is_seeded() -> bool:
    """True once the seeder has populated the financials table."""
    if not DB_PATH.exists():
        return False
    conn = sqlite3.connect(str(DB_PATH))
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='financials'"
        ).fetchone()
        if not row or row[0] == 0:
            return False
        count = conn.execute("SELECT COUNT(*) FROM financials").fetchone()
        return bool(count and count[0] > 0)
    finally:
        conn.close()


def _strip_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", " ", without_block)
    return without_line.strip()


def _validate_select(sql: str) -> str:
    """Return the cleaned statement, or raise ValueError with a plain reason."""
    cleaned = _strip_comments(sql)
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned:
        raise ValueError("Empty SQL statement.")
    if ";" in cleaned:
        raise ValueError("Only a single SELECT statement is allowed (no chained statements).")
    if not re.match(r"^(SELECT|WITH)\b", cleaned, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if _FORBIDDEN.search(cleaned):
        raise ValueError("Only read-only SELECT queries are allowed.")
    return cleaned


def run_readonly_sql(sql: str) -> List[dict]:
    """Execute one SELECT against the demo DB and return rows as list-of-dicts.

    Raises ValueError for disallowed statements and sqlite3.Error for bad SQL —
    callers surface these messages to the model so it can correct itself.
    """
    cleaned = _validate_select(sql or "")
    # Second enforcement layer: the connection itself is read-only.
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(cleaned).fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        result = [dict(r) for r in rows[:MAX_ROWS]]
        if truncated:
            result.append({"_notice": f"Results truncated to {MAX_ROWS} rows."})
        return result
    finally:
        conn.close()
