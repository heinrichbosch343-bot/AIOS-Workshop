from datetime import datetime, timezone

from anthropic import Anthropic
from config import ANTHROPIC_API_KEY
from db.client import supabase

SECTIONS = [
    "Client Background",
    "Key Issues Raised",
    "Governance Gaps Identified",
    "Stakeholder Perspectives",
    "Stated Priorities & Recommendations",
    "Supporting Data & Evidence",
]

_PROMPT = """You are organizing source material for a governance report.

Classify each passage into one of these sections:
- Client Background
- Key Issues Raised
- Governance Gaps Identified
- Stakeholder Perspectives
- Stated Priorities & Recommendations
- Supporting Data & Evidence

Rules — violating these makes the output unusable:
1. Every bullet must cite its source: [Transcript: 14:32] or [Document: filename]
2. Do not infer, extrapolate, or add information not in the source material
3. Do not summarize or paraphrase — quote or close-paraphrase only
4. If a passage doesn't clearly fit any section, place it under "Supporting Data & Evidence"
5. If a section has no source material, write: _(No source material for this section)_

Source material:

{source_block}

Produce the organized source package now. Every bullet must have a citation."""


def _fetch_project_documents(project_id: str) -> list[dict]:
    result = (
        supabase.table("documents")
        .select("id, filename, document_type, content")
        .eq("project_id", project_id)
        .in_("document_type", ["transcript", "source_file"])
        .eq("status", "approved")
        .execute()
    )
    return result.data


def _build_source_block(docs: list[dict], raw_text: str | None) -> str:
    parts = []
    for doc in docs:
        label = f"[Document: {doc['filename']}]"
        content = doc.get("content") or "(empty)"
        parts.append(f"{label}\n{content}")
    if raw_text:
        parts.append(f"[Document: pasted-source]\n{raw_text}")
    return "\n\n---\n\n".join(parts)


def compile_sources(project_id: str, raw_text: str | None = None) -> dict:
    """
    Classify approved source documents for a project into governance report
    sections via Claude. Optionally accepts raw_text as an additional source.

    Returns: document_id, source_package_text, section_counts
    Raises: ValueError if no source material is available
    """
    # Resolve project
    project_result = (
        supabase.table("projects")
        .select("id, client_id, name")
        .eq("id", project_id)
        .single()
        .execute()
    )
    project = project_result.data
    if not project:
        raise ValueError(f"Project {project_id} not found")

    # Gather source material
    docs = _fetch_project_documents(project_id)
    if not docs and not raw_text:
        raise ValueError(
            "No source material found. Approve transcripts or source files for "
            "this project, or provide source text directly."
        )

    source_block = _build_source_block(docs, raw_text)

    # Classify via Claude
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": _PROMPT.format(source_block=source_block)}],
    )
    package_text = response.content[0].text

    # Count which sections have content vs placeholder
    section_counts = {
        s: "No source material for this section" not in package_text.split(f"## {s}")[-1].split("##")[0]
        if f"## {s}" in package_text else False
        for s in SECTIONS
    }

    # Persist to documents table
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = {
        "project_id": project_id,
        "filename": f"source-package-{today}.md",
        "document_type": "source_package",
        "content": package_text,
        "status": "pending_review",
    }
    if project.get("client_id"):
        row["client_id"] = project["client_id"]

    insert_result = supabase.table("documents").insert(row).execute()
    doc_id = insert_result.data[0]["id"]

    sections_found = sum(section_counts.values())
    return {
        "document_id": doc_id,
        "source_package_text": package_text,
        "section_counts": section_counts,
        "sections_found": sections_found,
        "sections_total": len(SECTIONS),
    }
