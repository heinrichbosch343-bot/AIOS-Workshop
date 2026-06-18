"""
context_store.py — the write-back layer for Heinrich's living context.

This is what lets Heinrich keep his AI OS current just by talking to it (from Telegram or
the dashboard): add/update clients, move pipeline stages, record business facts, and keep
a timeline of what changed. Everything lives in Supabase, so the deployed brain on Railway
stays current with no local files involved.

Every mutation also appends a `business_events` row, so the daily brief and the agent can
see recent history ("you added Standard Bank yesterday").

Immutable style: functions build NEW dicts and return the new row from the DB; they never
mutate their inputs.
"""
from typing import Optional

from db.client import supabase

# The pipeline a client moves through. 'won' clients (signed, on retainer) are the KPI.
PIPELINE_STAGES = (
    "interested", "no_reply", "meeting_booked",
    "follow_up_meeting", "proposal", "won", "lost",
)
EVENT_TYPES = ("client_added", "stage_changed", "context_updated", "milestone", "note")


# ── timeline ─────────────────────────────────────────────────────────────────

def log_event(event_type: str, summary: str, client_id: Optional[str] = None,
              source: Optional[str] = None) -> dict:
    """Append one row to the business_events timeline. Returns the new row."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown event_type '{event_type}'. Expected one of {EVENT_TYPES}.")
    if not (summary or "").strip():
        raise ValueError("Event summary is required.")
    row = {"event_type": event_type, "summary": summary.strip()}
    if client_id:
        row["client_id"] = client_id
    if source:
        row["source"] = source
    return supabase.table("business_events").insert(row).execute().data[0]


def recent_events(limit: int = 10, since: Optional[str] = None) -> list[dict]:
    """Most recent events first. `since` is an ISO timestamp to filter from (optional)."""
    q = (
        supabase.table("business_events")
        .select("event_type, summary, created_at")
        .order("created_at", desc=True)
    )
    if since:
        q = q.gte("created_at", since)
    return q.limit(limit).execute().data


# ── clients & pipeline ───────────────────────────────────────────────────────

def _find_client_by_name(name: str) -> Optional[dict]:
    """Case-insensitive exact lookup by name (no wildcards)."""
    res = (
        supabase.table("clients")
        .select("*")
        .ilike("name", (name or "").strip())
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def _stage_fields(stage: str) -> dict:
    """Stage drives both pipeline_stage and the `active` flag, kept in sync."""
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"Unknown stage '{stage}'. Expected one of {PIPELINE_STAGES}.")
    return {"pipeline_stage": stage, "active": stage not in ("won", "lost")}


def upsert_client(name: str, *, stage: Optional[str] = None, industry: Optional[str] = None,
                  notes: Optional[str] = None, next_step: Optional[str] = None,
                  drive_folder_id: Optional[str] = None, source: Optional[str] = None) -> dict:
    """Insert a client by name, or update the matching one. Logs the change. Returns the row.

    Only the fields you pass are touched — omitted fields are left as they were.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Client name is required.")

    fields: dict = {}
    if stage is not None:
        fields.update(_stage_fields(stage))
    if industry is not None:
        fields["industry"] = industry
    if notes is not None:
        fields["relationship_notes"] = notes
    if next_step is not None:
        fields["next_step"] = next_step
    if drive_folder_id is not None:
        fields["google_drive_folder_id"] = drive_folder_id

    existing = _find_client_by_name(name)

    if existing:
        if not fields:
            return existing  # nothing to change, nothing to log
        row = supabase.table("clients").update(fields).eq("id", existing["id"]).execute().data[0]
        log_event("context_updated", f"Updated client {row['name']}", client_id=row["id"], source=source)
        return row

    row = supabase.table("clients").insert({"name": name, **fields}).execute().data[0]
    stage_note = f" at stage '{row.get('pipeline_stage')}'" if row.get("pipeline_stage") else ""
    log_event("client_added", f"Added client {name}{stage_note}", client_id=row["id"], source=source)
    return row


def set_client_stage(name: str, stage: str, source: Optional[str] = None) -> dict:
    """Move a client to a pipeline stage. Creates the client if it doesn't exist yet."""
    fields = _stage_fields(stage)  # validates stage
    existing = _find_client_by_name(name)
    if not existing:
        return upsert_client(name, stage=stage, source=source)

    prev = existing.get("pipeline_stage")
    if prev == stage:
        return existing  # already there — no-op, no event
    row = supabase.table("clients").update(fields).eq("id", existing["id"]).execute().data[0]
    log_event("stage_changed", f"{row['name']}: {prev or 'unknown'} → {stage}",
              client_id=row["id"], source=source)
    return row


def list_clients(stage: Optional[str] = None) -> list[dict]:
    """List clients (optionally filtered to one stage), ordered by stage then name."""
    q = supabase.table("clients").select(
        "id, name, industry, pipeline_stage, next_step, relationship_notes"
    )
    if stage:
        if stage not in PIPELINE_STAGES:
            raise ValueError(f"Unknown stage '{stage}'. Expected one of {PIPELINE_STAGES}.")
        q = q.eq("pipeline_stage", stage)
    return q.order("pipeline_stage").order("name").execute().data


def pipeline_summary() -> dict:
    """{'counts': {stage: n}, 'won': n, 'clients': [...]} — used by the prompt and brief."""
    clients = list_clients()
    counts: dict = {}
    for c in clients:
        s = c.get("pipeline_stage") or "interested"
        counts[s] = counts.get(s, 0) + 1
    return {"counts": counts, "won": counts.get("won", 0), "clients": clients}


# ── freeform business facts (connie_context key/value) ───────────────────────

def update_context_fact(key: str, value: str, source: Optional[str] = None) -> dict:
    """Upsert one fact into connie_context (the brain reads this on every call).

    Use a NEW descriptive key for a new fact (e.g. 'pricing_model') rather than
    overwriting the core 'bio'/'business' blurbs.
    """
    key = (key or "").strip()
    if not key:
        raise ValueError("Context key is required.")
    if value is None:
        raise ValueError("Context value is required.")
    row = (
        supabase.table("connie_context")
        .upsert({"key": key, "value": value}, on_conflict="key")
        .execute()
        .data[0]
    )
    log_event("context_updated", f"Context '{key}' updated", source=source)
    return row
