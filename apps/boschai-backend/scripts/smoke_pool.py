"""
M0 end-to-end check for the Knowledge Pool: embeddings + Supabase pgvector + match_chunks.

Inserts two throwaway passages, embeds a question, runs the similarity search, confirms
the relevant passage ranks first, then deletes the test rows. Proves the whole foundation
works together.

Run from apps/boschai-backend:
    python scripts/smoke_pool.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import supabase  # noqa: E402
from services.embeddings import embed_documents, embed_query  # noqa: E402

SENTINEL = "SMOKE_TEST"  # source_id used only for these throwaway rows


def main() -> None:
    # Clear any leftovers from a previous run.
    supabase.table("knowledge_chunks").delete().eq("source_id", SENTINEL).execute()

    docs = [
        "The board raised concerns about audit independence at the last meeting.",
        "The office coffee machine is broken again and needs replacing.",
    ]
    vecs = embed_documents(docs)
    rows = [
        {
            "content": d,
            "embedding": str(v),           # pgvector accepts the "[...]" text form
            "source_type": "transcript",
            "source_id": SENTINEL,
            "source_name": "Smoke Test Meeting",
            "chunk_index": i,
        }
        for i, (d, v) in enumerate(zip(docs, vecs))
    ]
    supabase.table("knowledge_chunks").insert(rows).execute()
    print(f"Inserted {len(rows)} test passages into knowledge_chunks.")

    qvec = embed_query("What did the board say about auditing?")
    res = supabase.rpc(
        "match_chunks", {"query_embedding": str(qvec), "match_count": 2}
    ).execute()
    matches = res.data or []

    print(f"match_chunks returned {len(matches)} rows:")
    for m in matches:
        print(f"  {m['similarity']:.3f}  {m['content']}")

    # Clean up the throwaway rows no matter what.
    supabase.table("knowledge_chunks").delete().eq("source_id", SENTINEL).execute()
    print("Cleaned up test rows.")

    if not matches:
        raise SystemExit("FAIL: match_chunks returned nothing — check the SQL ran.")
    if "audit" not in matches[0]["content"].lower():
        raise SystemExit("FAIL: the audit passage should have ranked first.")

    print("\nOK — embeddings + pgvector + match_chunks all work end to end. M0 complete.")


if __name__ == "__main__":
    main()
