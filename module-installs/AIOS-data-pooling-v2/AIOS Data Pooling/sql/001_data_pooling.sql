-- AIOS Data Pooling — full schema (run ONCE in the Supabase SQL editor).
--
-- Creates the searchable pool of document passages and the scoped similarity-search
-- function. Vector dimension is 1024 (voyage-law-2 and voyage-3.5 both output 1024).
-- If you use a different embedding model, change every `1024` below to its dimension.

-- 1. Enable pgvector (Supabase ships it; this just turns it on).
create extension if not exists vector;

-- 2. The pool: one row per passage, with its meaning fingerprint + provenance.
create table if not exists knowledge_chunks (
    id            uuid primary key default gen_random_uuid(),
    content       text not null,                 -- the passage itself
    embedding     vector(1024) not null,         -- meaning fingerprint
    source_type   text not null,                 -- 'drive' | 'transcript' | your own types
    source_id     text not null,                 -- Drive file id (or any unique source id)
    source_name   text not null,                 -- file name (used in citations)
    client        text,                          -- top-level folder = client/company
    project       text,                          -- first subfolder = project (nullable)
    source_date   timestamptz,                   -- file modified time
    chunk_index   int not null default 0,        -- position within the document
    content_hash  text,                          -- skip re-embedding unchanged content
    indexed_at    timestamptz not null default now(),
    unique (source_type, source_id, chunk_index)
);

-- 3. Indexes: fast nearest-neighbour search + cheap upserts/filtering.
create index if not exists knowledge_chunks_embedding_idx
    on knowledge_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists knowledge_chunks_source_idx
    on knowledge_chunks (source_type, source_id);
create index if not exists knowledge_chunks_client_idx
    on knowledge_chunks (client);

-- 4. Scoped similarity search. Each filter narrows the scope (all enforced in the DB,
--    so a question scoped to one client can never surface another client's content):
--      no filters          -> search everything
--      filter_client       -> one client only
--      + filter_project    -> one subfolder within that client
--      + filter_source_id  -> one specific file
drop function if exists match_chunks(vector, int, text);
drop function if exists match_chunks(vector, int, text, text, text);

create function match_chunks(
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
