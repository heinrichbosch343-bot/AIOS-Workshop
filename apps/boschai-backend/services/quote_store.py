"""Everything the quote bot remembers, in Postgres.

The first build kept the technician's in-progress quote in a module-level dict.
Railway restarts the web process on every deploy and cycles containers on its own
schedule, so a quote he was looking at on his phone had already stopped existing by
the time he replied SEND — and the bot told him there was nothing to send. No amount
of cleverness above this layer could have fixed that.

So: sessions, messages and issued quotes all live in Supabase, and this module is the
only place that talks to it. Anything above here works with plain dicts, which is also
what makes it testable without a database.
"""
import secrets
from datetime import date, datetime, timedelta

from services.quote_doc import TZ

HISTORY_LIMIT = 20          # turns kept for the model to read back
SESSION_STALE_HOURS = 12    # after this, a half-finished job is not resumed


def _db():
    """Imported late so this module can be exercised without Supabase credentials."""
    from db.client import supabase
    return supabase


def _is_duplicate(exc: Exception) -> bool:
    """Postgres 23505 — unique_violation. On quote_messages.message_sid that means
    Twilio is redelivering a message we have already dealt with."""
    text = str(exc)
    return "23505" in text or "duplicate key" in text.lower()


# ────────────────────────────────────────────────────────────── the conversation

def blank_session(technician: str) -> dict:
    return {"technician_phone": technician, "state": "collecting",
            "job": {}, "history": [], "last_quote_number": None}


def get_session(technician: str) -> dict:
    """The technician's open conversation, or a fresh one.

    A session older than SESSION_STALE_HOURS is not resumed. Coming back the next
    morning and having yesterday's half-finished job silently merged into today's is
    worse than starting clean, because the wrong price is invisible and a blank one
    is not.
    """
    rows = (_db().table("quote_sessions").select("*")
            .eq("technician_phone", technician).limit(1).execute()).data
    if not rows:
        return blank_session(technician)

    row = rows[0]
    updated = row.get("updated_at")
    if updated:
        try:
            age = datetime.now(TZ) - datetime.fromisoformat(updated)
            if age > timedelta(hours=SESSION_STALE_HOURS):
                return blank_session(technician)
        except (ValueError, TypeError):
            pass

    return {"technician_phone": technician,
            "state": row.get("state") or "collecting",
            "job": row.get("job") or {},
            "history": row.get("history") or [],
            "last_quote_number": row.get("last_quote_number")}


def save_session(session: dict) -> None:
    _db().table("quote_sessions").upsert({
        "technician_phone": session["technician_phone"],
        "state": session.get("state", "collecting"),
        "job": session.get("job") or {},
        "history": (session.get("history") or [])[-HISTORY_LIMIT:],
        "last_quote_number": session.get("last_quote_number"),
        "updated_at": datetime.now(TZ).isoformat(),
    }, on_conflict="technician_phone").execute()


def clear_session(technician: str, last_quote_number: str = None) -> dict:
    """Wipe the job but keep the thread. `last_quote_number` is what lets the bot
    answer "already sent that one — FQ-2026-004" instead of starting a new quote
    when he taps SEND twice."""
    session = blank_session(technician)
    session["last_quote_number"] = last_quote_number
    session["state"] = "sent" if last_quote_number else "collecting"
    save_session(session)
    return session


# ────────────────────────────────────────────────────────────────── the audit log

def log_inbound(*, message_sid: str, from_number: str, to_number: str,
                body: str, role: str) -> bool:
    """Record an inbound message. Returns False if we have already handled it.

    message_sid is UNIQUE, so a Twilio redelivery raises 23505 here and stops the
    turn before anything is sent. That single constraint is what removes double-sends
    and reply loops as a category rather than as a series of individual bugs.

    A message with no sid (a test, a manual poke) is always treated as new.
    """
    row = {"direction": "in", "role": role, "from_number": from_number,
           "to_number": to_number, "body": body}
    if message_sid:
        row["message_sid"] = message_sid
    try:
        _db().table("quote_messages").insert(row).execute()
        return True
    except Exception as exc:
        if _is_duplicate(exc):
            return False
        # A logging failure must never cost the technician his message, so the turn
        # continues. The duplicate check is the only part that is load-bearing.
        print(f"[quotebot] could not log inbound: {exc}", flush=True)
        return True


def log_outbound(*, to_number: str, body: str, role: str = "bot",
                 decision: dict = None) -> None:
    try:
        _db().table("quote_messages").insert({
            "direction": "out", "role": role, "to_number": to_number,
            "body": body, "decision": decision,
        }).execute()
    except Exception as exc:
        print(f"[quotebot] could not log outbound: {exc}", flush=True)


def record_decision(message_sid: str, decision: dict) -> None:
    """Attach what the bot concluded to the message that caused it, so 'why did it do
    that' is a row rather than a guess."""
    if not message_sid:
        return
    try:
        (_db().table("quote_messages").update({"decision": decision})
         .eq("message_sid", message_sid).execute())
    except Exception as exc:
        print(f"[quotebot] could not record decision: {exc}", flush=True)


def recent_messages(limit: int = 25) -> list:
    try:
        return (_db().table("quote_messages")
                .select("created_at,direction,role,from_number,to_number,body,"
                        "message_sid,decision")
                .order("created_at", desc=True).limit(limit).execute()).data or []
    except Exception as exc:
        return [{"error": str(exc)}]


# ────────────────────────────────────────────────────────────────── issued quotes

def next_quote_number(prefix: str, year: int) -> str:
    """{prefix}-{year}-{seq:03d}, continuing from the highest number already issued
    this year. Read at issue time, so it stays correct even when a quote is written
    by hand outside this system."""
    rows = (_db().table("quotes").select("quote_number")
            .like("quote_number", f"{prefix}-{year}-%").execute()).data or []
    seqs = []
    for row in rows:
        try:
            seqs.append(int(row["quote_number"].rsplit("-", 1)[-1]))
        except (ValueError, KeyError, AttributeError):
            continue
    return f"{prefix}-{year}-{(max(seqs) + 1) if seqs else 1:03d}"


def new_token() -> str:
    """The unguessable half of the public quote URL. Twilio fetches the PDF from that
    URL to attach it, so the route cannot require a login — the token is the secret."""
    return secrets.token_urlsafe(12)


def insert_quote(quote: dict) -> dict:
    row = dict(quote)
    row.setdefault("token", new_token())
    row.setdefault("currency", "ZAR")
    row.setdefault("issued_date", date.today().isoformat())
    result = _db().table("quotes").insert(row).execute()
    return (result.data or [row])[0]


def update_quote(quote_id: str, fields: dict) -> None:
    try:
        _db().table("quotes").update(fields).eq("id", quote_id).execute()
    except Exception as exc:
        print(f"[quotebot] could not update quote {quote_id}: {exc}", flush=True)


def get_quote_by_token(token: str):
    rows = (_db().table("quotes").select("*").eq("token", token)
            .limit(1).execute()).data
    return rows[0] if rows else None


def get_quote_by_number(quote_number: str):
    rows = (_db().table("quotes").select("*").eq("quote_number", quote_number)
            .limit(1).execute()).data
    return rows[0] if rows else None


def latest_quote_for_phone(phone: str, within_days: int = 60):
    """How an inbound message from an unrecognised number is identified as a customer:
    the most recent quote issued to that phone. Older than `within_days` and they are
    treated as a stranger, because a reply to a quote from three months ago is not a
    reply to anything the bot is holding."""
    if not phone:
        return None
    cutoff = (datetime.now(TZ) - timedelta(days=within_days)).isoformat()
    rows = (_db().table("quotes").select("*")
            .eq("customer_phone", phone).gte("created_at", cutoff)
            .order("created_at", desc=True).limit(1).execute()).data
    return rows[0] if rows else None


def open_quotes(older_than_days: int = 3) -> list:
    """Sent, never accepted, and going quiet. The unchased quote is the problem this
    whole system was built to remove, so it gets a query of its own."""
    cutoff = (datetime.now(TZ) - timedelta(days=older_than_days)).isoformat()
    return (_db().table("quotes").select("*")
            .is_("accepted_at", "null").lte("sent_at", cutoff)
            .order("sent_at", desc=True).execute()).data or []


# ──────────────────────────────────────────────────────────────────────── health

def health() -> dict:
    """Which tables are actually reachable. When the bot is quiet, the first question
    is always whether the migration was run — this answers it without a browser."""
    out = {}
    for table in ("quote_sessions", "quote_messages", "quotes"):
        try:
            _db().table(table).select("*").limit(1).execute()
            out[table] = "ok"
        except Exception as exc:
            out[table] = f"UNAVAILABLE: {str(exc)[:180]}"
    return out
