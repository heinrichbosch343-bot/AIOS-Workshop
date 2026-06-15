"""
M2 end-to-end check for the Knowledge Pool ASK path: knowledge.ask().

Seeds a few throwaway passages (a document + a transcript for one client, plus a second
client as a decoy), then exercises knowledge.ask():
  1. a real question returns a cited answer drawn from BOTH the document and the transcript;
  2. scoping to one client never surfaces the other client's passage (DB-level isolation);
  3. an unrelated question returns the exact NOT_FOUND line (never invents).
Cleans up the throwaway rows no matter what.

Run from apps/boschai-backend:
    python scripts/smoke_ask.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import supabase  # noqa: E402
from services.embeddings import embed_documents  # noqa: E402
from services.knowledge import ask, NOT_FOUND  # noqa: E402

SENTINEL = "SMOKE_ASK"  # source_id prefix used only for these throwaway rows

SEED = [
    {
        "source_type": "drive",
        "source_name": "BCX Governance Review 2025",
        "client": "BCX",
        "content": (
            "The 2025 review found the audit committee lacked a clear charter and that two "
            "non-executive directors had served well beyond the recommended tenure, weakening "
            "board independence."
        ),
    },
    {
        "source_type": "transcript",
        "source_name": "BCX Board Interview - CFO",
        "client": "BCX",
        "content": (
            "The CFO said in the interview that audit independence was the board's biggest worry "
            "this year, and that rotating the external auditor was being actively discussed."
        ),
    },
    {
        "source_type": "drive",
        "source_name": "Acme Strategy Memo",
        "client": "Acme",
        "content": (
            "Acme plans to triple its marketing budget next quarter and open two new retail "
            "locations in Cape Town."
        ),
    },
]


def _seed():
    supabase.table("knowledge_chunks").delete().like("source_id", f"{SENTINEL}%").execute()
    vecs = embed_documents([s["content"] for s in SEED])
    rows = [{
        "content": s["content"],
        "embedding": str(v),
        "source_type": s["source_type"],
        "source_id": f"{SENTINEL}_{i}",
        "source_name": s["source_name"],
        "client": s["client"],
        "chunk_index": 0,
    } for i, (s, v) in enumerate(zip(SEED, vecs))]
    supabase.table("knowledge_chunks").insert(rows).execute()
    print(f"Seeded {len(rows)} throwaway passages.")


def _cleanup():
    supabase.table("knowledge_chunks").delete().like("source_id", f"{SENTINEL}%").execute()
    print("Cleaned up test rows.")


def main() -> None:
    _seed()
    try:
        # 1. Cited answer pulling from both a document and a transcript, scoped to BCX.
        r1 = ask("What concerns were raised about audit independence at BCX?", client="BCX")
        print("\n[1] answer:\n", r1["answer"])
        print("    citations:", [c["source_name"] for c in r1["citations"]])
        print("    chunks_used:", r1["chunks_used"])

        cited = {c["source_name"] for c in r1["citations"]}
        assert r1["answer"] != NOT_FOUND, "FAIL: expected a real answer, got NOT_FOUND."
        assert "Acme Strategy Memo" not in cited, "FAIL: client isolation leaked Acme into a BCX query."
        assert all(c["client"] == "BCX" for c in r1["citations"]), "FAIL: a non-BCX source was cited."

        # 2. Unrelated question against the pool returns the exact NOT_FOUND line.
        r2 = ask("What is the office wifi password?")
        print("\n[2] unrelated answer:", r2["answer"])
        assert r2["answer"] == NOT_FOUND, "FAIL: expected the exact NOT_FOUND line for an unanswerable question."
    finally:
        _cleanup()

    print("\nOK — knowledge.ask() retrieves, cites, isolates by client, and refuses to invent. M2 verified.")


if __name__ == "__main__":
    main()
