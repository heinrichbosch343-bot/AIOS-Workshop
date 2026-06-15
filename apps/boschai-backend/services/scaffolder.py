import re
from datetime import datetime, timezone

import anthropic
from config import ANTHROPIC_API_KEY
from db.client import supabase

_SCAFFOLD_PROMPT = """You are helping Heinrich structure a report for a client.

CRITICAL CONSTRAINTS — violating these makes the output unusable:
1. Every bullet point or finding must include a citation: [Source: document name, timestamp/page]
2. If no source supports a claim, write: ⚠️ SOURCE NEEDED: [describe what's missing]
3. Do not infer, extrapolate, or use general knowledge about the subject
4. Do not synthesize beyond what the sources directly state
5. Placeholder sections with no source material get: ⚠️ NO SOURCES FOR THIS SECTION

Report format:
{report_format}

Writing style:
{writing_style}

Approved source material:
{source_package}

Generate the full report scaffold now. Include every section header, sub-heading, and bullet point. Citations on everything."""


def scaffold_report(project_id: str) -> dict:
    """
    Generate a report scaffold from the approved source package for a project.

    Raises ValueError if no approved source package exists.
    Returns: document_id, scaffold_text, gap_count, gaps_list
    """
    source_docs = (
        supabase.table("documents")
        .select("id, content, filename")
        .eq("project_id", project_id)
        .eq("document_type", "source_package")
        .eq("status", "approved")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    ).data

    if not source_docs:
        raise ValueError(
            "No approved source package found for this project. "
            "Compile and approve sources before generating a scaffold."
        )

    source_package = source_docs[0]["content"] or ""

    # Load Heinrich's report format and writing style
    try:
        context_rows = (
            supabase.table("connie_context")
            .select("key, value")
            .in_("key", ["report_format", "writing_style"])
            .execute()
        ).data
        ctx = {r["key"]: r["value"] for r in context_rows}
    except Exception:
        ctx = {}

    ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = ai.messages.create(
        model="claude-opus-4-6",
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": _SCAFFOLD_PROMPT.format(
                report_format=ctx.get(
                    "report_format",
                    "Tight, scannable report structured with an executive summary, thematic findings, "
                    "recommendations, and appendices.",
                ),
                writing_style=ctx.get(
                    "writing_style",
                    "Sharp, direct, and concrete. Sounds like a sharp human operator, not an AI.",
                ),
                source_package=source_package,
            ),
        }],
    )
    scaffold_text = response.content[0].text

    gaps = re.findall(
        r"⚠️ (?:SOURCE NEEDED|NO SOURCES FOR THIS SECTION)[^\n]*",
        scaffold_text,
    )
    gap_count = len(gaps)

    row = (
        supabase.table("projects").select("name").eq("id", project_id).single().execute()
    ).data
    project_name = row.get("name", project_id) if row else project_id
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    doc = supabase.table("documents").insert({
        "project_id": project_id,
        "document_type": "scaffold",
        "filename": f"report-scaffold-{project_name}-{today}.md",
        "content": scaffold_text,
        "status": "pending_review",
    }).execute().data[0]

    return {
        "document_id": doc["id"],
        "scaffold_text": scaffold_text,
        "gap_count": gap_count,
        "gaps_list": gaps,
    }
