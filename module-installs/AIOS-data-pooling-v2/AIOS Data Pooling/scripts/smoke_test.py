"""
End-to-end check of the whole pool: embeddings + Supabase pgvector + scoped search.

Inserts throwaway passages for two fake clients (one with two projects), then verifies
every scope level returns only what it should:

    no filter        -> sees both clients
    client           -> one client only
    client + project -> one project only
    file (source_id) -> one file only

Cleans up its test rows no matter what. Needs only VOYAGE_API_KEY + Supabase keys
(no Google Drive, no Anthropic). Run:
    python smoke_test.py
"""
from embeddings import embed_documents, embed_query
from store import search, supabase

SENTINEL_IDS = ["SMOKE_A1", "SMOKE_A2", "SMOKE_B1"]

# (source_id, client, project, source_name, content)
ROWS = [
    ("SMOKE_A1", "SmokeCo", "Alpha Review", "alpha-notes.md",
     "The Alpha review flagged a gap in supplier vetting procedures."),
    ("SMOKE_A2", "SmokeCo", "Beta Audit", "beta-notes.md",
     "The Beta audit found the supplier vetting procedures fully compliant."),
    ("SMOKE_B1", "OtherCorp", "Gamma Project", "gamma-notes.md",
     "OtherCorp's supplier vetting procedures were never reviewed."),
]


def _cleanup() -> None:
    for sid in SENTINEL_IDS:
        supabase().table("knowledge_chunks").delete().eq("source_id", sid).execute()


def _ids(matches: list[dict]) -> set[str]:
    return {m["source_id"] for m in matches if m["source_id"] in SENTINEL_IDS}


def main() -> None:
    _cleanup()
    vecs = embed_documents([r[4] for r in ROWS])
    supabase().table("knowledge_chunks").insert([
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
        everything = _ids(search(qvec, k=10))
        assert everything == set(SENTINEL_IDS), f"unscoped should see all 3, got {everything}"
        print("  unscoped          -> all 3 passages  OK")

        one_client = _ids(search(qvec, k=10, client="SmokeCo"))
        assert one_client == {"SMOKE_A1", "SMOKE_A2"}, f"client scope leaked: {one_client}"
        print("  client=SmokeCo    -> 2 passages, OtherCorp excluded  OK")

        one_project = _ids(search(qvec, k=10, client="SmokeCo", project="Alpha Review"))
        assert one_project == {"SMOKE_A1"}, f"project scope leaked: {one_project}"
        print("  + project=Alpha   -> 1 passage  OK")

        one_file = _ids(search(qvec, k=10, source_id="SMOKE_B1"))
        assert one_file == {"SMOKE_B1"}, f"file scope leaked: {one_file}"
        print("  file=B1           -> 1 passage  OK")
    finally:
        _cleanup()
        print("Cleaned up test rows.")

    print("\nOK — embeddings, storage, and scoped search all work end to end.")


if __name__ == "__main__":
    main()
