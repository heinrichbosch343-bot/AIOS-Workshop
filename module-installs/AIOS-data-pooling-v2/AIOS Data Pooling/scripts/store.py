"""
Supabase storage for the pool — the ONE place that talks to the database.

Holds the shared client plus the three operations everything else needs: replace a file's
chunks, look up a file's content hash (for change detection), and run the scoped
similarity search (match_chunks).
"""
from supabase import Client, create_client

import pool_config

_client: Client | None = None


def supabase() -> Client:
    global _client
    if _client is None:
        pool_config.require("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        _client = create_client(
            pool_config.SUPABASE_URL, pool_config.SUPABASE_SERVICE_ROLE_KEY
        )
    return _client


def existing_hash(source_id: str) -> str | None:
    """Content hash of a file's stored chunks — None if the file was never indexed."""
    res = supabase().table("knowledge_chunks").select("content_hash").eq(
        "source_id", source_id).limit(1).execute()
    return res.data[0]["content_hash"] if res.data else None


def replace_chunks(file: dict, chunks: list[str], vectors: list[list[float]], h: str) -> None:
    """Replace every stored chunk for one file with the new set (delete + insert)."""
    supabase().table("knowledge_chunks").delete().eq("source_id", file["id"]).execute()
    rows = [{
        "content": c,
        "embedding": str(v),               # pgvector accepts the "[...]" text form
        "source_type": "drive",
        "source_id": file["id"],
        "source_name": file["name"],
        "client": file["company"],
        "project": file.get("project"),
        "source_date": file.get("modified"),
        "chunk_index": i,
        "content_hash": h,
    } for i, (c, v) in enumerate(zip(chunks, vectors))]
    for i in range(0, len(rows), 50):      # modest pages keep request bodies small
        supabase().table("knowledge_chunks").insert(rows[i:i + 50]).execute()


def search(query_vector: list[float], k: int = 15, client: str | None = None,
           project: str | None = None, source_id: str | None = None) -> list[dict]:
    """Scoped similarity search. Each filter narrows the scope (enforced in the DB)."""
    params: dict = {"query_embedding": str(query_vector), "match_count": k}
    if client:
        params["filter_client"] = client
    if project:
        params["filter_project"] = project
    if source_id:
        params["filter_source_id"] = source_id
    res = supabase().rpc("match_chunks", params).execute()
    return res.data or []
