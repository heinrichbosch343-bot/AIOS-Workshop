from db.client import supabase


def _recent_context() -> str:
    """
    Pull recent business context so the brain knows 'what happened lately'.
    Currently sources the most recent daily brief. Safe when tables are empty.
    """
    parts = []

    try:
        brief = (
            supabase.table("daily_brief_log")
            .select("brief_date, content")
            .order("brief_date", desc=True)
            .limit(1)
            .execute()
        )
        if brief.data:
            b = brief.data[0]
            parts.append(f"Most recent daily brief ({b['brief_date']}):\n{b['content']}")
    except Exception:
        pass

    return "\n\n".join(parts)


def _pipeline_block() -> str:
    """A live snapshot of Heinrich's clients, their pipeline stages, and recent changes,
    so the brain always knows the current state. Safe when tables are empty."""
    try:
        from services import context_store as cs

        summary = cs.pipeline_summary()
        clients = summary["clients"]
        if not clients:
            return ""
        counts = ", ".join(f"{n} {stage}" for stage, n in sorted(summary["counts"].items()))
        lines = [f"Client pipeline ({counts}):"]
        for c in clients:
            line = f"- {c['name']} [{c.get('pipeline_stage', 'pipeline')}]"
            if c.get("next_step"):
                line += f" — next: {c['next_step']}"
            lines.append(line)
        events = cs.recent_events(limit=5)
        if events:
            lines.append("Recent business changes:")
            lines += [f"- {e['summary']}" for e in events]
        return "\n".join(lines)
    except Exception:
        return ""


async def build_system_prompt(client_id: str = None) -> str:
    rows = supabase.table("connie_context").select("key, value").execute()
    ctx = {r["key"]: r["value"] for r in rows.data}

    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI
    today_line = _dt.now(_ZI("Africa/Johannesburg")).strftime(
        "Current date & time: %A, %d %B %Y, %H:%M (SAST). Use this to resolve relative "
        "dates like 'today', 'tomorrow', 'next Friday' when scheduling or reasoning about time."
    )

    prompt = f"""You are Heinrich's AI assistant — the centralized brain for BoschAI.
You have full context on Heinrich, his business, and recent activity. Be proactive, concise,
and write in his voice. When he asks about his day, emails, notes, or recent work, use the
context below.

{today_line}

About Heinrich:
{ctx.get("bio", "")}

Business:
{ctx.get("business", "")}

Writing Style:
{ctx.get("writing_style", "")}

Report Format:
{ctx.get("report_format", "")}"""

    # Any context facts beyond the core four (e.g. strategy, key_metric, pricing_model) —
    # this is what lets a fact Heinrich records via update_business_fact actually reach the brain.
    core_keys = {"bio", "business", "writing_style", "report_format"}
    extra = {k: v for k, v in ctx.items() if k not in core_keys and v}
    if extra:
        prompt += "\n\nMore About His Business:\n" + "\n".join(
            f"- {k.replace('_', ' ').title()}: {v}" for k, v in sorted(extra.items())
        )

    pipeline = _pipeline_block()
    if pipeline:
        prompt += f"\n\nCurrent Clients & Pipeline:\n{pipeline}"

    recent = _recent_context()
    if recent:
        prompt += f"\n\nRecent Activity & Context:\n{recent}"

    if client_id:
        result = supabase.table("clients").select("*").eq("id", client_id).maybe_single().execute()
        if result.data:
            c = result.data
            prompt += f"""

Current Client: {c.get("name", "")}
Industry: {c.get("industry", "")}
Background: {c.get("background", "")}
Notes: {c.get("relationship_notes", "")}"""

    return prompt
