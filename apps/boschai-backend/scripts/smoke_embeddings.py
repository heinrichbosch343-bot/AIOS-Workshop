"""
M0 smoke test for the Knowledge Pool foundation.

Confirms the Voyage embeddings key works, that document and query embeddings come back,
and prints the vector dimension you must use in the pgvector column. Run this BEFORE
creating the knowledge_chunks table so the schema's vector(N) matches reality.

Run from apps/boschai-backend:
    python scripts/smoke_embeddings.py
"""
import sys
from pathlib import Path

# Allow running as a plain script (so `from services...` resolves).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import EMBEDDING_MODEL, EMBEDDING_DIM  # noqa: E402
from services.embeddings import embed_documents, embed_query  # noqa: E402


def main() -> None:
    docs = embed_documents([
        "The board raised concerns about audit independence at the last meeting.",
        "Heinrich will deliver the AIOS build plan to the client next week.",
    ])
    query = embed_query("What did the board say about auditing?")

    dim = len(docs[0])
    print(f"Model:             {EMBEDDING_MODEL}")
    print(f"Documents embedded: {len(docs)}")
    print(f"Query embedded:     1")
    print(f"Vector dimension:   {dim}")

    consistent = all(len(v) == dim for v in docs) and len(query) == dim
    if not consistent:
        raise SystemExit("FAIL: vectors came back with inconsistent dimensions.")
    if dim != EMBEDDING_DIM:
        print(
            f"\nNOTE: EMBEDDING_DIM in config is {EMBEDDING_DIM} but the model returned "
            f"{dim}. Set EMBEDDING_DIM={dim} (or vector({dim}) in the schema)."
        )

    print(f"\nOK — embeddings working. Use this in the pgvector schema:  embedding vector({dim})")


if __name__ == "__main__":
    main()
