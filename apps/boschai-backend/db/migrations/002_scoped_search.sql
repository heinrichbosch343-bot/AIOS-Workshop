-- Knowledge Pool — scoped search (run once in the Supabase SQL editor, after 001).
--
-- Extends match_chunks so a search can be narrowed to a project (subfolder) or a single
-- file, not just a client. This powers the dashboard's "the deeper you select, the more
-- specific the search" behaviour:
--   no filters            → search everything
--   filter_client         → one client's documents only
--   + filter_project      → one subfolder within that client
--   + filter_source_id    → one specific file
--
-- The old 3-argument function MUST be dropped first: CREATE OR REPLACE with a different
-- argument list creates a second overload, and PostgREST then refuses the RPC as ambiguous.

drop function if exists match_chunks(vector, int, text);

create or replace function match_chunks(
    query_embedding vector(1024),
    match_count int default 15,
    filter_client text default null,
    filter_project text default null,
    filter_source_id text default null
)
returns table (
    id uuid,
    content text,
    source_type text,
    source_id text,
    source_name text,
    client text,
    project text,
    source_date timestamptz,
    similarity float
)
language sql stable
as $$
    select
        kc.id, kc.content, kc.source_type, kc.source_id, kc.source_name,
        kc.client, kc.project, kc.source_date,
        1 - (kc.embedding <=> query_embedding) as similarity
    from knowledge_chunks kc
    where (filter_client is null or kc.client = filter_client)
      and (filter_project is null or kc.project = filter_project)
      and (filter_source_id is null or kc.source_id = filter_source_id)
    order by kc.embedding <=> query_embedding
    limit match_count;
$$;
