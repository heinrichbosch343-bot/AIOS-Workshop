from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from db.client import supabase

# Local GTD mirror file at repo-root /gtd. Optional — it does not exist on hosted
# deploys (Railway runs only apps/boschai-backend), so resolve it safely and treat
# it as absent there instead of crashing at import with an IndexError.
_PARENTS = Path(__file__).resolve().parents
GTD_WAITING_FOR = (_PARENTS[3] / "gtd" / "waiting-for.md") if len(_PARENTS) > 3 else None


def create_signoff(waiting_on: str, item: str, project_id: Optional[str] = None,
                   due_at: Optional[str] = None, contact_email: Optional[str] = None) -> dict:
    row = {"waiting_on": waiting_on, "item": item}
    if project_id:
        row["project_id"] = project_id
    if due_at:
        row["due_at"] = due_at
    if contact_email:
        row["contact_email"] = contact_email
    result = supabase.table("signoffs").insert(row).execute()
    signoff = result.data[0]
    sync_gtd_waiting_for()
    return signoff


def get_open_signoffs() -> list[dict]:
    result = (
        supabase.table("signoffs")
        .select("*")
        .is_("resolved_at", "null")
        .order("sent_at", desc=False)
        .execute()
    )
    rows = result.data
    now = datetime.now(timezone.utc)
    for row in rows:
        sent = datetime.fromisoformat(row["sent_at"].replace("Z", "+00:00"))
        row["days_waiting"] = (now - sent).days
    return rows


def resolve_signoff(signoff_id: str) -> dict:
    result = (
        supabase.table("signoffs")
        .update({"resolved_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", signoff_id)
        .execute()
    )
    sync_gtd_waiting_for()
    return result.data[0]


def sync_gtd_waiting_for():
    open_items = (
        supabase.table("signoffs")
        .select("waiting_on, item, sent_at")
        .is_("resolved_at", "null")
        .order("sent_at", desc=False)
        .execute()
    ).data

    now = datetime.now(timezone.utc)
    lines = ["# Waiting For", "", "> Auto-generated from Supabase. Use /waiting to add, /done to resolve.", ""]

    if open_items:
        lines.append("## Active")
        lines.append("")
        for item in open_items:
            sent = datetime.fromisoformat(item["sent_at"].replace("Z", "+00:00"))
            days = (now - sent).days
            age = f"{days}d" if days > 0 else "today"
            lines.append(f"- **{item['waiting_on']}** — {item['item']} ({age})")
        lines.append("")
    else:
        lines.append("## Active")
        lines.append("")
        lines.append("_(Nothing pending)_")
        lines.append("")

    lines.append("## Completed")
    lines.append("")
    lines.append("_(Resolved items are archived in Supabase)_")
    lines.append("")

    # Local-only mirror; skip silently on hosted deploys where /gtd isn't present.
    if GTD_WAITING_FOR and GTD_WAITING_FOR.parent.exists():
        try:
            with open(GTD_WAITING_FOR, "w") as f:
                f.write("\n".join(lines))
        except OSError:
            pass
