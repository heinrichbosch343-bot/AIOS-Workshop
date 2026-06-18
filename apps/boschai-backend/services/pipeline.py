"""
pipeline.py — CRM pipeline service for Heinrich's sales funnel.

Stages: interested → no_reply → meeting_booked → follow_up_meeting → proposal → won | lost

Provides formatted output for Telegram commands, the daily brief, and nudge
detection (leads sitting in a stage too long).

Immutable style: every function builds a NEW dict; inputs are never mutated.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.client import supabase
from services import context_store as cs

# Stage order for display and validation
STAGES = (
    "interested", "no_reply", "meeting_booked",
    "follow_up_meeting", "proposal", "won", "lost",
)

# Active stages (excludes terminal states)
ACTIVE_STAGES = ("interested", "no_reply", "meeting_booked", "follow_up_meeting", "proposal")

# How many days in each stage before we nudge Heinrich
NUDGE_THRESHOLDS = {
    "interested": 2,
    "no_reply": 5,
    "meeting_booked": 1,       # remind day-of
    "follow_up_meeting": 3,
    "proposal": 5,
}

NUDGE_MESSAGES = {
    "interested": "Book a meeting with {name}?",
    "no_reply": "Follow up with {name}?",
    "meeting_booked": "{name} has a meeting coming up — prep needed?",
    "follow_up_meeting": "Send a proposal to {name}?",
    "proposal": "Chase {name} on the proposal?",
}

STAGE_LABELS = {
    "interested": "Interested",
    "no_reply": "No Reply",
    "meeting_booked": "Meeting Booked",
    "follow_up_meeting": "Follow-up Meeting",
    "proposal": "Proposal",
    "won": "Won",
    "lost": "Lost",
}


def _parse_dt(val: Optional[str]) -> Optional[datetime]:
    """Parse an ISO timestamp from Supabase, returning None on failure."""
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ── Lead management ──────────────────────────────────────────────────────────

def add_lead(name: str, email: Optional[str] = None,
             source: Optional[str] = None, notes: Optional[str] = None,
             stage: str = "interested", origin: str = "telegram") -> dict:
    """Add a new lead to the pipeline. Returns the created/updated client row."""
    if stage not in STAGES:
        raise ValueError(f"Unknown stage '{stage}'. Expected one of {STAGES}.")

    fields = {
        "pipeline_stage": stage,
        "active": stage not in ("won", "lost"),
    }
    if email:
        fields["email"] = email.strip()
    if source:
        fields["lead_source"] = source.strip()

    existing = cs._find_client_by_name(name)
    if existing:
        # Only reset stage timer when the stage actually changes
        if existing.get("pipeline_stage") != stage:
            fields["stage_changed_at"] = datetime.now(timezone.utc).isoformat()
        row = supabase.table("clients").update(fields).eq("id", existing["id"]).execute().data[0]
        if notes:
            _append_notes(row["id"], notes)
        cs.log_event("context_updated", f"Updated lead {row['name']} → {stage}",
                     client_id=row["id"], source=origin)
        return row

    fields["name"] = name.strip()
    fields["stage_changed_at"] = datetime.now(timezone.utc).isoformat()
    if notes:
        fields["relationship_notes"] = notes.strip()
    row = supabase.table("clients").insert(fields).execute().data[0]
    cs.log_event("client_added", f"New lead: {name} ({stage})",
                 client_id=row["id"], source=origin)
    return row


def move_stage(name: str, new_stage: str, source: str = "telegram") -> dict:
    """Move a lead to a new pipeline stage. Returns the updated row."""
    if new_stage not in STAGES:
        raise ValueError(f"Unknown stage '{new_stage}'. Expected one of {STAGES}.")

    existing = cs._find_client_by_name(name)
    if not existing:
        raise ValueError(f"No lead found with name '{name}'.")

    prev = existing.get("pipeline_stage", "unknown")
    if prev == new_stage:
        return existing

    fields = {
        "pipeline_stage": new_stage,
        "active": new_stage not in ("won", "lost"),
        "stage_changed_at": datetime.now(timezone.utc).isoformat(),
    }

    # Auto-set timestamps based on stage
    if new_stage == "proposal" and not existing.get("proposal_sent_at"):
        fields["proposal_sent_at"] = datetime.now(timezone.utc).isoformat()
    if new_stage in ("meeting_booked", "follow_up_meeting"):
        fields["last_contacted"] = datetime.now(timezone.utc).isoformat()

    row = supabase.table("clients").update(fields).eq("id", existing["id"]).execute().data[0]
    cs.log_event("stage_changed", f"{name}: {prev} → {new_stage}",
                 client_id=row["id"], source=source)
    return row


def add_note(name: str, note_text: str, source: str = "telegram") -> dict:
    """Append a note to a lead's relationship notes."""
    existing = cs._find_client_by_name(name)
    if not existing:
        raise ValueError(f"No lead found with name '{name}'.")
    _append_notes(existing["id"], note_text)
    cs.log_event("note", f"Note on {name}: {note_text[:80]}",
                 client_id=existing["id"], source=source)
    return supabase.table("clients").select("*").eq("id", existing["id"]).execute().data[0]


def _append_notes(client_id: str, text: str):
    """Append text to a client's relationship_notes field."""
    data = supabase.table("clients").select("relationship_notes").eq("id", client_id).execute().data
    if not data:
        raise ValueError(f"Client {client_id} not found when appending notes.")
    row = data[0]
    existing_notes = (row.get("relationship_notes") or "").strip()
    timestamp = datetime.now(timezone.utc).strftime("%d %b %Y")
    new_notes = f"{existing_notes}\n[{timestamp}] {text.strip()}".strip()
    supabase.table("clients").update({"relationship_notes": new_notes}).eq("id", client_id).execute()


def remove_lead(name: str, source: str = "telegram") -> dict:
    """Move a lead to 'lost' (soft delete). Returns the updated row."""
    return move_stage(name, "lost", source=source)


def get_lead(name: str) -> Optional[dict]:
    """Get full details for a single lead by name."""
    return cs._find_client_by_name(name)


def get_lead_history(client_id: str, limit: int = 10) -> list[dict]:
    """Get recent business events for a specific client."""
    return (
        supabase.table("business_events")
        .select("event_type, summary, created_at")
        .eq("client_id", client_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )


# ── Pipeline views ───────────────────────────────────────────────────────────

def get_active_pipeline() -> dict:
    """Get all active leads grouped by stage.

    Returns: {stage: [client_rows], "counts": {stage: n}, "total": n}
    """
    rows = (
        supabase.table("clients")
        .select("id, name, email, pipeline_stage, lead_source, relationship_notes, "
                "next_step, meeting_date, proposal_sent_at, stage_changed_at, last_contacted")
        .in_("pipeline_stage", list(ACTIVE_STAGES))
        .order("stage_changed_at", desc=False)
        .execute()
        .data
    )

    grouped = {s: [] for s in ACTIVE_STAGES}
    for row in rows:
        stage = row.get("pipeline_stage", "interested")
        if stage in grouped:
            grouped[stage].append(row)

    counts = {s: len(leads) for s, leads in grouped.items() if leads}
    return {**grouped, "counts": counts, "total": len(rows)}


def format_pipeline_telegram() -> str:
    """Format the pipeline as a clean Telegram message (plain text, no markdown)."""
    data = get_active_pipeline()
    now = datetime.now(timezone.utc)

    if data["total"] == 0:
        return "Pipeline is empty. Add leads with /addlead [name] [email]"

    lines = [f"Pipeline: {data['total']} active deal{'s' if data['total'] != 1 else ''}", ""]

    for stage in ACTIVE_STAGES:
        leads = data.get(stage, [])
        if not leads:
            continue

        lines.append(f"{STAGE_LABELS[stage].upper()} ({len(leads)})")
        for lead in leads:
            name = lead["name"]
            age = _days_in_stage(lead, now)
            age_str = f"{age}d" if age > 0 else "today"

            detail_parts = []
            if lead.get("email"):
                detail_parts.append(lead["email"])
            if lead.get("lead_source"):
                detail_parts.append(lead["lead_source"])
            detail_parts.append(age_str)

            lines.append(f"  {name} — {' / '.join(detail_parts)}")

            if lead.get("next_step"):
                lines.append(f"    Next: {lead['next_step']}")
        lines.append("")

    # Won count
    won_rows = supabase.table("clients").select("id").eq("pipeline_stage", "won").execute().data
    won_count = len(won_rows)
    if won_count:
        lines.append(f"Won clients: {won_count}")

    return "\n".join(lines).strip()


def format_lead_telegram(name: str) -> str:
    """Format a single lead's details for Telegram."""
    lead = cs._find_client_by_name(name)
    if not lead:
        return f"No lead found with name '{name}'."

    now = datetime.now(timezone.utc)
    age = _days_in_stage(lead, now)
    stage = lead.get("pipeline_stage", "unknown")

    lines = [
        f"{lead['name']}",
        f"Stage: {STAGE_LABELS.get(stage, stage)} ({age}d)",
    ]
    if lead.get("email"):
        lines.append(f"Email: {lead['email']}")
    if lead.get("lead_source"):
        lines.append(f"Source: {lead['lead_source']}")
    if lead.get("industry"):
        lines.append(f"Industry: {lead['industry']}")
    if lead.get("next_step"):
        lines.append(f"Next step: {lead['next_step']}")
    if lead.get("meeting_date"):
        lines.append(f"Meeting: {lead['meeting_date']}")
    if lead.get("proposal_sent_at"):
        lines.append(f"Proposal sent: {lead['proposal_sent_at'][:10]}")
    if lead.get("relationship_notes"):
        notes = lead["relationship_notes"]
        if len(notes) > 300:
            notes = notes[-300:]  # show most recent notes
        lines.append(f"\nNotes:\n{notes}")

    # Recent history
    history = get_lead_history(lead["id"], limit=5)
    if history:
        lines.append("\nHistory:")
        for event in history:
            date = event["created_at"][:10]
            lines.append(f"  {date} — {event['summary']}")

    return "\n".join(lines)


# ── Nudges ───────────────────────────────────────────────────────────────────

def check_nudges() -> list[dict]:
    """Find leads that have been in their current stage too long.

    Returns a list of {name, stage, days, message} for each nudge-worthy lead.
    """
    now = datetime.now(timezone.utc)
    nudges = []

    for stage, threshold_days in NUDGE_THRESHOLDS.items():
        leads = (
            supabase.table("clients")
            .select("id, name, pipeline_stage, stage_changed_at, meeting_date")
            .eq("pipeline_stage", stage)
            .execute()
            .data
        )
        for lead in leads:
            days = _days_in_stage(lead, now)
            if days >= threshold_days:
                msg = NUDGE_MESSAGES[stage].format(name=lead["name"])
                nudges.append({
                    "name": lead["name"],
                    "stage": stage,
                    "days": days,
                    "message": msg,
                    "client_id": lead["id"],
                })

    return nudges


def format_nudges_telegram(nudges: list[dict]) -> str:
    """Format nudge reminders for Telegram."""
    if not nudges:
        return ""
    lines = [f"Pipeline reminders ({len(nudges)}):"]
    for n in nudges:
        lines.append(f"  {n['message']} ({n['days']}d in {STAGE_LABELS[n['stage']]})")
    return "\n".join(lines)


# ── Daily brief integration ──────────────────────────────────────────────────

def pipeline_brief_block() -> str:
    """Compact pipeline summary for the daily brief facts section."""
    data = get_active_pipeline()

    if data["total"] == 0:
        return "Pipeline: empty"

    parts = []
    for stage in ACTIVE_STAGES:
        count = data["counts"].get(stage, 0)
        if count:
            names = ", ".join(l["name"] for l in data[stage][:3])
            parts.append(f"{STAGE_LABELS[stage]}: {count} ({names})")

    won_rows = supabase.table("clients").select("id").eq("pipeline_stage", "won").execute().data
    won_count = len(won_rows)
    if won_count:
        parts.append(f"Won: {won_count}")

    nudges = check_nudges()
    nudge_strs = [n["message"] for n in nudges[:3]]

    result = f"Pipeline ({data['total']} active): " + "; ".join(parts)
    if nudge_strs:
        result += "\nPipeline nudges: " + "; ".join(nudge_strs)
    return result


# ── Helpers ──────────────────────────────────────────────────────────────────

def _days_in_stage(lead: dict, now: datetime) -> int:
    """How many days a lead has been in its current stage."""
    changed = _parse_dt(lead.get("stage_changed_at"))
    if not changed:
        created = _parse_dt(lead.get("created_at"))
        changed = created or now
    return (now - changed).days
