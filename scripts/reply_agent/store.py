"""Everything the agent remembers, in one SQLite file. It holds real people's mail, so it is gitignored.

A mail and the draft written for it are saved in ONE transaction: if the process dies halfway, neither exists and the
mail is simply handled again. Every time-based method takes an explicit timestamp so the agent's clock, not the wall
clock, decides (and tests can move it).
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import Decision, Draft, InboundMail
from .trust import base_address

SCHEMA = """
CREATE TABLE IF NOT EXISTS mails (
    message_id TEXT PRIMARY KEY,
    uid TEXT, received_at TEXT, from_addr TEXT, from_name TEXT, mailbox TEXT, subject TEXT, body TEXT,
    in_reply_to TEXT, refs TEXT, category TEXT, confidence REAL, reason TEXT, source TEXT, handled_at TEXT,
    verified INTEGER NOT NULL DEFAULT 0, trust TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL REFERENCES mails(message_id),
    body TEXT NOT NULL, problems TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,            -- pending, held, approved, sending, sent, skipped, failed
    created_at TEXT NOT NULL, send_after TEXT, sent_at TEXT, sent_message_id TEXT, note TEXT,
    forced INTEGER NOT NULL DEFAULT 0, approved_at TEXT
);
CREATE TABLE IF NOT EXISTS suppression (addr TEXT PRIMARY KEY, reason TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS attention (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS retries (
    key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, first_at TEXT NOT NULL, last_at TEXT NOT NULL, last_error TEXT
);
CREATE INDEX IF NOT EXISTS drafts_status ON drafts(status);
"""

# Columns added after the first release. An existing database gets them on open.
_ADDED_COLUMNS = (
    ("mails", "verified", "INTEGER NOT NULL DEFAULT 0"),
    ("mails", "trust", "TEXT NOT NULL DEFAULT ''"),
    ("drafts", "forced", "INTEGER NOT NULL DEFAULT 0"),
    ("drafts", "approved_at", "TEXT"),
)
_UPDATABLE = {"body", "status", "send_after", "sent_at", "sent_message_id", "note", "problems", "forced", "approved_at"}
IN_FLIGHT = ("approved", "sending", "sent")  # a reply that is queued, going out, or gone


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._migrate()
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")  # a manual command can run beside a watcher

    def _migrate(self) -> None:
        for table, column, ddl in _ADDED_COLUMNS:
            if column not in {r["name"] for r in self._conn.execute(f"PRAGMA table_info({table})")}:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- mails and the first save --------------------------------------------------------------
    def seen(self, message_id: str) -> bool:
        return self._conn.execute("SELECT 1 FROM mails WHERE message_id = ?", (message_id,)).fetchone() is not None

    def get_mail(self, message_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM mails WHERE message_id = ?", (message_id,)).fetchone()

    def record_outcome(self, mail: InboundMail, decision: Decision, *, verified: bool, trust: str,
                       suppress: tuple[tuple[str, str], ...] = (), keep_body: bool = True, draft: Draft | None = None,
                       draft_status: str = "pending", send_after: str | None = None,
                       attention: tuple[str, str] | None = None, at: str | None = None) -> int | None:
        """Save the mail, whom to stop writing to, its draft and any note for a person: all together or not at all."""
        stamp = at or now()
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO mails (message_id, uid, received_at, from_addr, from_name, mailbox, subject, body, "
                "in_reply_to, refs, category, confidence, reason, source, handled_at, verified, trust) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (mail.message_id, mail.uid, mail.received_at, mail.from_addr, mail.from_name, decision.mailbox,
                 mail.subject if keep_body else mail.subject[:60], mail.body if keep_body else "", mail.in_reply_to,
                 " ".join(mail.references), decision.category, decision.confidence, decision.reason, decision.source,
                 stamp, 1 if verified else 0, trust),
            )
            for addr, reason in suppress:
                self._conn.execute("INSERT OR IGNORE INTO suppression VALUES (?,?,?)", (base_address(addr), reason, stamp))
            draft_id = None
            if draft is not None:
                cur = self._conn.execute(
                    "INSERT INTO drafts (message_id, body, problems, status, created_at, send_after, approved_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (mail.message_id, draft.body, " | ".join(draft.problems), draft_status, stamp, send_after,
                     stamp if draft_status == "approved" else None),
                )
                draft_id = int(cur.lastrowid)
            if attention is not None:
                kind, note = attention
                self._conn.execute("INSERT OR IGNORE INTO attention (message_id, kind, note, created_at) VALUES (?,?,?,?)",
                                   (mail.message_id, kind, note[:300], stamp))
        return draft_id

    # --- the do-not-write list ------------------------------------------------------------------
    def suppressed(self) -> frozenset:
        return frozenset(r["addr"] for r in self._conn.execute("SELECT addr FROM suppression"))

    def suppression_rows(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT addr, reason, at FROM suppression ORDER BY at, addr"))

    def suppressions_since(self, reason: str, since_iso: str) -> int:
        """How many addresses were put on the do-not-write list for exactly this reason since the given time."""
        with closing(self._conn.execute("SELECT COUNT(*) FROM suppression WHERE reason = ? AND at >= ?", (reason, since_iso))) as cur:
            return int(cur.fetchone()[0])

    def suppress(self, addr: str, reason: str, at: str | None = None) -> None:
        with self._conn:
            self._conn.execute("INSERT OR REPLACE INTO suppression VALUES (?,?,?)", (base_address(addr), reason, at or now()))

    def unsuppress(self, addr: str) -> bool:
        with self._conn:
            return self._conn.execute("DELETE FROM suppression WHERE addr = ?", (base_address(addr),)).rowcount > 0

    # --- drafts ---------------------------------------------------------------------------------
    _DRAFT_COLUMNS = (
        "SELECT d.*, m.from_addr, m.from_name, m.mailbox, m.subject, m.body AS their_body, m.category, "
        "m.in_reply_to, m.refs, m.verified, m.trust, m.message_id AS their_id "
        "FROM drafts d JOIN mails m ON m.message_id = d.message_id"
    )

    def drafts(self, status: str) -> list[sqlite3.Row]:
        return list(self._conn.execute(f"{self._DRAFT_COLUMNS} WHERE d.status = ? ORDER BY d.id", (status,)))

    def get_draft(self, draft_id: int) -> sqlite3.Row | None:
        return self._conn.execute(f"{self._DRAFT_COLUMNS} WHERE d.id = ?", (draft_id,)).fetchone()

    def update_draft(self, draft_id: int, **fields) -> None:
        bad = set(fields) - _UPDATABLE
        if bad:
            raise ValueError(f"cannot update {bad}")
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._conn:
            self._conn.execute(f"UPDATE drafts SET {sets} WHERE id = ?", (*fields.values(), draft_id))

    def claim_draft(self, draft_id: int, at: str, message_id: str) -> bool:
        """approved -> sending, atomically. Only one caller can win, so a draft can never be sent twice."""
        with self._conn:
            return self._conn.execute(
                "UPDATE drafts SET status = 'sending', sent_at = ?, sent_message_id = ? WHERE id = ? AND status = 'approved'",
                (at, message_id, draft_id),
            ).rowcount == 1

    # --- limits and history ---------------------------------------------------------------------
    def sent_to(self) -> dict:
        """Message-ID of every reply we sent (or are sending) -> the address it went to."""
        rows = self._conn.execute(
            "SELECT d.sent_message_id AS sid, m.from_addr AS addr FROM drafts d JOIN mails m ON m.message_id = d.message_id "
            "WHERE d.status IN ('sent','sending') AND d.sent_message_id IS NOT NULL")
        return {r["sid"]: base_address(r["addr"]) for r in rows}

    def sent_since(self, since_iso: str, mailbox: str | None = None) -> int:
        sql = ("SELECT COUNT(*) FROM drafts d JOIN mails m ON m.message_id = d.message_id "
               "WHERE d.status IN ('sent','sending') AND d.sent_at >= ?")
        args: list = [since_iso]
        if mailbox:
            sql += " AND m.mailbox = ?"
            args.append(mailbox)
        with closing(self._conn.execute(sql, args)) as cur:
            return int(cur.fetchone()[0])

    def replied_to_sender_since(self, addr: str, since_iso: str, *, include_queued: bool, exclude_id: int | None = None) -> bool:
        """Has a reply to this person gone out (or, with include_queued, been lined up) since the given time?"""
        statuses = IN_FLIGHT if include_queued else ("sending", "sent")
        marks = ",".join("?" for _ in statuses)
        rows = self._conn.execute(
            f"SELECT d.id, m.from_addr FROM drafts d JOIN mails m ON m.message_id = d.message_id "
            f"WHERE d.status IN ({marks}) AND COALESCE(d.sent_at, d.approved_at, d.created_at) >= ?", (*statuses, since_iso))
        wanted = base_address(addr)
        return any(r["id"] != exclude_id and base_address(r["from_addr"]) == wanted for r in rows)

    def model_mails_since(self, since_iso: str, sender: str | None = None, verified: bool | None = None) -> int:
        """How many mails the model has read since the given time, optionally only from one sender or only (un)verified ones."""
        sql = "SELECT from_addr FROM mails WHERE source = 'model' AND handled_at >= ?"
        args: list = [since_iso]
        if verified is not None:
            sql += " AND verified = ?"
            args.append(1 if verified else 0)
        rows = self._conn.execute(sql, args)
        if sender is None:
            return len(list(rows))
        wanted = base_address(sender)
        return sum(1 for r in rows if base_address(r["from_addr"]) == wanted)

    def handled_by_category_since(self, since_iso: str) -> dict:
        """Mail handled since the given time, per category (our own handled_at clock, not the sender's Date header)."""
        rows = self._conn.execute("SELECT category, COUNT(*) n FROM mails WHERE handled_at >= ? GROUP BY category", (since_iso,))
        return {r["category"]: int(r["n"]) for r in rows}

    def recent_mails(self, categories: tuple[str, ...], limit: int) -> list[sqlite3.Row]:
        """The newest handled mails in these categories, each with the latest draft written for it (if any)."""
        marks = ",".join("?" for _ in categories)
        return list(self._conn.execute(
            f"SELECT m.handled_at, m.from_addr, m.from_name, m.mailbox, m.subject, m.body, m.category, "
            f"d.status AS draft_status, d.body AS draft_body, d.sent_at "
            f"FROM mails m LEFT JOIN drafts d ON d.id = (SELECT MAX(id) FROM drafts WHERE message_id = m.message_id) "
            f"WHERE m.category IN ({marks}) ORDER BY m.handled_at DESC, m.rowid DESC LIMIT ?", (*categories, limit)))

    def draft_status_counts(self) -> dict:
        return {r["status"]: int(r["n"]) for r in self._conn.execute("SELECT status, COUNT(*) n FROM drafts GROUP BY status")}

    def counts_by_category(self, since_iso: str, until_iso: str | None = None) -> dict:
        sql = "SELECT category, COUNT(*) n FROM mails WHERE received_at >= ?"
        args: list = [since_iso]
        if until_iso:
            sql += " AND received_at < ?"
            args.append(until_iso)
        sql += " GROUP BY category"
        return {r["category"]: r["n"] for r in self._conn.execute(sql, args)}

    # --- things a person needs to look at ------------------------------------------------------
    def add_attention(self, message_id: str, kind: str, note: str, at: str | None = None) -> None:
        with self._conn:
            self._conn.execute("INSERT OR IGNORE INTO attention (message_id, kind, note, created_at) VALUES (?,?,?,?)",
                               (message_id, kind, note[:300], at or now()))

    def open_attention(self) -> list[sqlite3.Row]:
        return list(self._conn.execute(
            "SELECT a.id, a.message_id, a.kind, a.note, a.created_at, m.from_addr, m.from_name, m.subject, m.body, "
            "m.mailbox, m.verified, m.trust FROM attention a LEFT JOIN mails m ON m.message_id = a.message_id "
            "WHERE a.resolved_at IS NULL ORDER BY a.id"))

    def resolve_attention(self, attention_id: int, at: str | None = None) -> bool:
        with self._conn:
            return self._conn.execute("UPDATE attention SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
                                      (at or now(), attention_id)).rowcount == 1

    def attention_count_for_sender_since(self, addr: str, since_iso: str) -> int:
        """Items of any kind listed about one sender since the given time."""
        wanted = base_address(addr)
        rows = self._conn.execute("SELECT m.from_addr FROM attention a JOIN mails m ON m.message_id = a.message_id "
                                  "WHERE a.created_at >= ?", (since_iso,))
        return sum(1 for r in rows if base_address(r["from_addr"]) == wanted)

    def resolve_attention_kind(self, kind: str, at: str | None = None) -> int:
        """Clear every open item of one kind at once (a flood of them). Returns how many were cleared."""
        with self._conn:
            return self._conn.execute("UPDATE attention SET resolved_at = ? WHERE kind = ? AND resolved_at IS NULL",
                                      (at or now(), kind)).rowcount

    def attention_count_since(self, kind: str, since_iso: str, trusted: bool | None = None) -> int:
        """Items of one kind listed since the given time. With `trusted`, only those about senders we know (an exact lead or a
        sender our own server verified) or only the others: strangers must not use up what real leads are allowed."""
        sql = ("SELECT COUNT(*) FROM attention a LEFT JOIN mails m ON m.message_id = a.message_id "
               "WHERE a.kind = ? AND a.created_at >= ?")
        args: list = [kind, since_iso]
        if trusted is not None:
            sql += " AND (COALESCE(m.verified, 0) = 1 OR COALESCE(m.trust, '') = 'exact') = ?"
            args.append(1 if trusted else 0)
        with closing(self._conn.execute(sql, args)) as cur:
            return int(cur.fetchone()[0])

    # --- mail we could not finish ---------------------------------------------------------------
    def bump_retry(self, key: str, error: str, at: str | None = None) -> tuple[int, str]:
        """Count one more failed try for this mail. Returns (tries so far, when the first try failed)."""
        stamp = at or now()
        with self._conn:
            row = self._conn.execute("SELECT attempts, first_at FROM retries WHERE key = ?", (key,)).fetchone()
            if row is None:
                self._conn.execute("INSERT INTO retries VALUES (?,?,?,?,?)", (key, 1, stamp, stamp, error[:300]))
                return 1, stamp
            self._conn.execute("UPDATE retries SET attempts = attempts + 1, last_at = ?, last_error = ? WHERE key = ?",
                               (stamp, error[:300], key))
            return int(row["attempts"]) + 1, row["first_at"]

    def touch_retry(self, key: str, error: str, at: str | None = None) -> None:
        """Note that a mail is waiting although no try was made on it (the pass stopped first). The clock on it starts now."""
        stamp = at or now()
        with self._conn:
            self._conn.execute("INSERT OR IGNORE INTO retries VALUES (?,?,?,?,?)", (key, 0, stamp, stamp, error[:300]))

    def clear_retry(self, key: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM retries WHERE key = ?", (key,))

    def waiting_retries(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT key, attempts, first_at, last_error FROM retries ORDER BY first_at"))
