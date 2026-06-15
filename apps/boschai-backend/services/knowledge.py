"""
Knowledge Pool — answer a question from the semantic pool of indexed Drive docs + transcripts.

This is the ASK side of the pool (the indexer is the build side). It embeds the question,
finds the most relevant passages across EVERYTHING already indexed via the `match_chunks`
similarity search, then answers with the SAME strict citation prompt as drive_query — cite
every claim by source name, or say it isn't there. Never invents.

Client isolation is enforced at the DB layer: pass `client` and `match_chunks` filters to that
company's passages only, so a question scoped to one client can never surface another's.
"""
from anthropic import Anthropic

from config import ANTHROPIC_API_KEY
from db.client import supabase
from services.embeddings import embed_query
# Reuse the proven, governance-safe citation prompt unchanged (one source of truth for the rules).
from services.drive_query import _SYSTEM, NOT_FOUND, MODEL

DEFAULT_K = 15      # how many passages to retrieve and feed the answerer
MAX_TOKENS = 1500   # answer length cap (matches drive_query)


def _match(question: str, client: str | None, project: str | None,
           source_id: str | None, k: int) -> list[dict]:
    """Embed the question and return the k most similar passages within the given scope."""
    qvec = embed_query(question)
    params = {"query_embedding": str(qvec), "match_count": k}
    if client:
        params["filter_client"] = client
    if project:
        params["filter_project"] = project
    if source_id:
        params["filter_source_id"] = source_id
    try:
        res = supabase.rpc("match_chunks", params).execute()
    except Exception as e:
        # PGRST202 = the 5-argument match_chunks doesn't exist yet (only the old 3-arg one).
        if "PGRST202" in str(e) and (project or source_id):
            raise RuntimeError(
                "Folder/file-scoped search isn't enabled in the database yet — run "
                "db/migrations/002_scoped_search.sql in the Supabase SQL Editor, then retry."
            )
        raise
    return res.data or []


def _citations(matches: list[dict]) -> list[dict]:
    """Distinct sources behind the answer, in order of first appearance (provenance trail)."""
    seen: dict[str, dict] = {}
    for m in matches:
        name = m.get("source_name")
        if name and name not in seen:
            seen[name] = {
                "source_name": name,
                "source_type": m.get("source_type"),
                "client": m.get("client"),
                "project": m.get("project"),
                "source_date": m.get("source_date"),
            }
    return list(seen.values())


def ask(question: str, client: str | None = None, project: str | None = None,
        source_id: str | None = None, k: int = DEFAULT_K) -> dict:
    """
    Answer a question from the Knowledge Pool with citations.

    Searches every indexed document and transcript by meaning (not folder or keyword). The
    scope narrows with each filter you pass: `client` (a company/folder name) restricts to one
    client, `project` (a subfolder name) to one project within it, and `source_id` (a Drive
    file id) to a single file. Returns {answer, citations, chunks_used}. `answer` is the exact
    NOT_FOUND line when nothing relevant is retrieved.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty")

    matches = _match(question, client, project, source_id, k)
    if not matches:
        return {"answer": NOT_FOUND, "citations": [], "chunks_used": 0}

    blocks = [f"[{m['source_name']}]\n{m['content']}" for m in matches]
    user_content = f"Question: {question}\n\nSource documents:\n\n" + "\n\n---\n\n".join(blocks)

    resp = Anthropic(api_key=ANTHROPIC_API_KEY).messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    answer = "".join(b.text for b in resp.content if b.type == "text").strip()

    return {
        "answer": answer or NOT_FOUND,
        "citations": _citations(matches),
        "chunks_used": len(matches),
    }
