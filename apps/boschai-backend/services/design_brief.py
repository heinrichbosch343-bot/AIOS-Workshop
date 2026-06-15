import re
from datetime import datetime, timezone

import anthropic
from config import ANTHROPIC_API_KEY
from db.client import supabase

_BRIEF_PROMPT = """Generate a design brief for a graphic design agency.

Project: {project_name}
Client: {client_name}

Approved report scaffold:
{scaffold_text}

Generate:
1. Scope statement — what the design covers
2. Page estimate and layout breakdown (section by section)
3. Required visual elements — charts, tables, callout boxes, infographics (list each by section)
4. Brand/style notes — professional, authoritative, consistent with governance consulting
5. Deliverable format — print-ready PDF + editable source files (InDesign preferred)
6. Suggested timeline — 3 working days for first draft

Be specific. The agency will quote from this document."""


def generate_brief(project_id: str) -> dict:
    """
    Generate a design brief from the approved scaffold for a project.

    Raises ValueError if no approved scaffold exists.
    Returns: document_id, brief_text, page_estimate, section_count
    """
    scaffold_docs = (
        supabase.table("documents")
        .select("id, content")
        .eq("project_id", project_id)
        .eq("document_type", "scaffold")
        .eq("status", "approved")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if not scaffold_docs:
        raise ValueError(
            "No approved scaffold found for this project. "
            "Generate and approve the report scaffold before creating a design brief."
        )

    scaffold_text = scaffold_docs[0]["content"] or ""
    section_count = len(re.findall(r"^#{1,2} .+", scaffold_text, re.MULTILINE))
    page_estimate = max(section_count * 2, 10)

    project_row = (
        supabase.table("projects")
        .select("name, clients(name)")
        .eq("id", project_id)
        .single()
        .execute()
    ).data
    project_name = project_row.get("name", "Governance Report") if project_row else "Governance Report"
    client_data = (project_row or {}).get("clients")
    client_name = client_data.get("name", "Client") if client_data else "Client"

    ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = ai.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": _BRIEF_PROMPT.format(
                project_name=project_name,
                client_name=client_name,
                scaffold_text=scaffold_text,
            ),
        }],
    )
    brief_text = response.content[0].text
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    doc = supabase.table("documents").insert({
        "project_id": project_id,
        "document_type": "design_brief",
        "filename": f"design-brief-{project_name}-{today}.md",
        "content": brief_text,
        "status": "pending_review",
    }).execute().data[0]

    return {
        "document_id": doc["id"],
        "brief_text": brief_text,
        "page_estimate": page_estimate,
        "section_count": section_count,
    }
