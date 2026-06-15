"""
End-to-end check for SCOPED search: match_chunks with client / project / file filters.

Requires db/migrations/002_scoped_search.sql to have been run in the Supabase SQL Editor.
Inserts throwaway passages for two fake clients (one with two projects, one project with
two files), then verifies every scope level returns only what it should:

    no filter        -> sees both clients
    client           -> one client only
    client + project -> one project only
    file (source_id) -> one file only

Cleans up its test rows no matter what. Run from apps/boschai-backend:
    python scripts/smoke_scoped.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.client import supabase  # noqa: E402
from services.embeddings import embed_documents, embed_query  # noqa: E402

SENTINEL_IDS = ["SMOKE_SCOPED_A1", "SMOKE_SCOPED_A2", "SMOKE_SCOPED_B1"]

# (source_id, client, project, source_name, content)
ROWS = [
    ("SMOKE_SCOPED_A1", "SmokeCo", "Alpha Review", "alpha-notes.md",
     "The Alpha review flagged a gap in supplier vetting procedures."),
    ("SMOKE_SCOPED_A2", "SmokeCo", "Beta Audit", "beta-notes.md",
     "The Beta audit found the supplier vetting procedures fully compliant."),
    ("SMOKE_SCOPED_B1", "OtherCorp", "Gamma Project", "gamma-notes.md",
     "OtherCorp's supplier vetting procedures were never reviewed."),
]


def _cleanup() -> None:
    for sid in SENTINEL_IDS:
        supabase.table("knowledge_chunks").delete().eq("source_id", sid).execute()


def _search(qvec, **filters) -> set[str]:
    params = {"query_embedding": str(qvec), "match_count": 10, **filters}
    res = supabase.rpc("match_chunks", params).execute()
    return {m["source_id"] for m in (res.data or []) if m["source_id"] in SENTINEL_IDS}


def main() -> None:
    _cleanup()
    vecs = embed_documents([r[4] for r in ROWS])
    supabase.table("knowledge_chunks").insert([
        {
            "content": content, "embedding": str(v), "source_type": "drive",
            "source_id": sid, "source_name": name, "client": client,
            "project": project, "chunk_index": 0,
        }
        for (sid, client, project, name, content), v in zip(ROWS, vecs)
    ]).execute()
    print(f"Inserted {len(ROWS)} test passages (2 clients, 3 projects/files).")

    qvec = embed_query("What happened with supplier vetting?")
    try:
        everything = _search(qvec)
        assert everything == set(SENTINEL_IDS), f"unscoped should see all 3, got {everything}"
        print("  unscoped          -> all 3 passages  OK")

        one_client = _search(qvec, filter_client="SmokeCo")
        assert one_client == {"SMOKE_SCOPED_A1", "SMOKE_SCOPED_A2"}, \
            f"client scope leaked: {one_client}"
        print("  client=SmokeCo    -> 2 passages, OtherCorp excluded  OK")

        one_project = _search(qvec, filter_client="SmokeCo", filter_project="Alpha Review")
        assert one_project == {"SMOKE_SCOPED_A1"}, f"project scope leaked: {one_project}"
        print("  + project=Alpha   -> 1 passage  OK")

        one_file = _search(qvec, filter_source_id="SMOKE_SCOPED_B1")
        assert one_file == {"SMOKE_SCOPED_B1"}, f"file scope leaked: {one_file}"
        print("  file=B1           -> 1 passage  OK")
    finally:
        _cleanup()
        print("Cleaned up test rows.")

    print("\nOK — scoped search works: everything / client / project / single file. ")


if __name__ == "__main__":
    main()
