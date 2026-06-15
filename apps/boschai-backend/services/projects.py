from datetime import datetime, timezone
from typing import Optional
from db.client import supabase


def create_project(
    name: str,
    client_id: Optional[str] = None,
    drive_folder_id: Optional[str] = None,
    client_name: Optional[str] = None,
) -> dict:
    row = {"name": name}
    if client_name and not client_id:
        existing = (
            supabase.table("clients")
            .select("id")
            .eq("name", client_name)
            .limit(1)
            .execute()
        ).data
        if existing:
            client_id = existing[0]["id"]
        else:
            new_client = supabase.table("clients").insert({"name": client_name}).execute().data[0]
            client_id = new_client["id"]
    if client_id:
        row["client_id"] = client_id
    if drive_folder_id:
        row["drive_folder_id"] = drive_folder_id
    result = supabase.table("projects").insert(row).execute()
    return result.data[0]


def list_projects() -> list[dict]:
    result = (
        supabase.table("projects")
        .select("*, clients(name)")
        .neq("status", "archived")
        .order("created_at", desc=True)
        .execute()
    )
    rows = result.data
    for row in rows:
        row["pipeline"] = _pipeline_status(row)
        # flatten client name
        if row.get("clients"):
            row["client_name"] = row["clients"]["name"]
        else:
            row["client_name"] = None
        row.pop("clients", None)
    return rows


def get_project(project_id: str) -> Optional[dict]:
    result = (
        supabase.table("projects")
        .select("*, clients(name)")
        .eq("id", project_id)
        .single()
        .execute()
    )
    if not result.data:
        return None
    row = result.data

    # flatten client name
    if row.get("clients"):
        row["client_name"] = row["clients"]["name"]
    else:
        row["client_name"] = None
    row.pop("clients", None)

    row["pipeline"] = _pipeline_status(row)

    # fetch linked documents
    docs = (
        supabase.table("documents")
        .select("id, document_type, status, created_at")
        .eq("project_id", project_id)
        .order("created_at", desc=True)
        .execute()
    ).data
    row["documents"] = docs

    # fetch open signoffs
    signoffs = (
        supabase.table("signoffs")
        .select("*")
        .eq("project_id", project_id)
        .is_("resolved_at", "null")
        .order("sent_at", desc=False)
        .execute()
    ).data
    now = datetime.now(timezone.utc)
    for s in signoffs:
        sent = datetime.fromisoformat(s["sent_at"].replace("Z", "+00:00"))
        s["days_waiting"] = (now - sent).days
    row["open_signoffs"] = signoffs

    return row


def update_project(project_id: str, updates: dict) -> dict:
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("projects")
        .update(updates)
        .eq("id", project_id)
        .execute()
    )
    return result.data[0]


def _pipeline_status(row: dict) -> dict:
    """Return a summary of which pipeline stages are complete."""
    return {
        "transcription": row.get("transcription_done_at"),
        "compilation": row.get("compilation_done_at"),
        "scaffold": row.get("scaffold_done_at"),
        "brief": row.get("brief_sent_at"),
    }
