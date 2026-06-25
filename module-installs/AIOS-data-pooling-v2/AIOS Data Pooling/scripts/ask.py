"""
Ask the pool a question — semantic search + cited answer.

Embeds the question, finds the most relevant passages across everything indexed (optionally
scoped to one client, project, or file), then answers with a strict citation prompt: cite
every claim by source name, or say it isn't there. Never invents.

The retrieved document text is sent as a cached prefix, so repeat/follow-up questions about
the same scope reuse it at ~10% of input cost (Anthropic prompt caching, ~5-minute window).
Set ANSWER_MODEL in .env to trade cost for depth (claude-haiku-4-5 = cheapest).

CLI:
    python ask.py "What did the board decide about audit independence?"
    python ask.py "..." --client "Acme Corp"
    python ask.py "..." --client "Acme Corp" --project "2026 Governance Review"
"""
import argparse

from anthropic import Anthropic

import pool_config
from embeddings import embed_query
from store import search

DEFAULT_K = 15      # how many passages to retrieve and feed the answerer
MAX_TOKENS = 1500   # answer length cap

NOT_FOUND = "This was not found in any of the provided documents."

_SYSTEM = (
    "You are a research assistant. "
    "Answer the question using ONLY the source documents provided by the user.\n"
    "Rules (violating them makes the answer unusable and is professionally dangerous):\n"
    "1. Do not invent, infer, or add anything not present in the documents.\n"
    "2. Cite the source for every claim in brackets with the file name, "
    "e.g. [Acme_Session2_Transcript].\n"
    f'3. If the answer is not found in any document, reply with exactly: "{NOT_FOUND}"\n'
    "4. Be concise and structured. Use bullet points for multi-part answers."
)


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
    Answer a question from the pool with citations.

    The scope narrows with each filter: `client` restricts to one client, `project` to one
    subfolder within it, `source_id` to a single file. Returns {answer, citations,
    chunks_used}; `answer` is the exact NOT_FOUND line when nothing relevant is retrieved.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty")
    pool_config.require("ANTHROPIC_API_KEY")

    matches = search(embed_query(question), k=k, client=client,
                     project=project, source_id=source_id)
    if not matches:
        return {"answer": NOT_FOUND, "citations": [], "chunks_used": 0}

    blocks = [f"[{m['source_name']}]\n{m['content']}" for m in matches]
    # Documents go first in their own block, marked for caching; the question (which varies)
    # goes last. Ask another question about the same scope within ~5 minutes and the document
    # text is reused from cache at ~10% of input cost — identical answer, a fraction of the price.
    resp = Anthropic(api_key=pool_config.ANTHROPIC_API_KEY).messages.create(
        model=pool_config.ANSWER_MODEL,
        max_tokens=MAX_TOKENS,
        system=_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "text",
             "text": "Source documents:\n\n" + "\n\n---\n\n".join(blocks),
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": f"\n\nQuestion: {question}"},
        ]}],
    )
    answer = "".join(b.text for b in resp.content if b.type == "text").strip()

    return {
        "answer": answer or NOT_FOUND,
        "citations": _citations(matches),
        "chunks_used": len(matches),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Ask the data pool a question.")
    p.add_argument("question", help="The question to answer from the indexed documents")
    p.add_argument("--client", help="Limit the search to one client (top-level folder name)")
    p.add_argument("--project", help="Limit further to one project (subfolder name)")
    p.add_argument("--file-id", dest="source_id", help="Limit to a single Drive file id")
    p.add_argument("-k", type=int, default=DEFAULT_K, help="Passages to retrieve (default 15)")
    a = p.parse_args()

    result = ask(a.question, client=a.client, project=a.project,
                 source_id=a.source_id, k=a.k)
    print(f"\n{result['answer']}\n")
    if result["citations"]:
        print("Sources:")
        for c in result["citations"]:
            bits = [c.get("source_type"), c.get("client"), c.get("project")]
            meta = " · ".join(b for b in bits if b)
            print(f"  - {c['source_name']}" + (f"  ({meta})" if meta else ""))


if __name__ == "__main__":
    main()
