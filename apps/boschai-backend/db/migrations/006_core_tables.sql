-- Core tables for the BoschAI backend.
-- Run once in the Supabase SQL editor. Safe to re-run (all IF NOT EXISTS).
-- Order matters: clients first, then tables that reference it.

-- ── 1. Clients & pipeline ────────────────────────────────────────────────────
create table if not exists clients (
    id                    uuid primary key default gen_random_uuid(),
    name                  text not null unique,
    pipeline_stage        text,                       -- lead | pipeline | anchor | inactive
    active                boolean not null default true,
    industry              text,
    relationship_notes    text,
    next_step             text,
    google_drive_folder_id text,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);

-- ── 2. Business events timeline ──────────────────────────────────────────────
create table if not exists business_events (
    id          uuid primary key default gen_random_uuid(),
    event_type  text not null,   -- client_added | stage_changed | context_updated | milestone | note
    summary     text not null,
    client_id   uuid references clients(id) on delete set null,
    source      text,            -- 'telegram' | 'dashboard' | 'scheduler' etc.
    created_at  timestamptz not null default now()
);
create index if not exists business_events_created_idx on business_events (created_at desc);
create index if not exists business_events_client_idx  on business_events (client_id);

-- ── 3. Freeform context store (key/value brain facts) ────────────────────────
create table if not exists connie_context (
    key        text primary key,
    value      text not null,
    updated_at timestamptz not null default now()
);

-- ── 4. Projects ──────────────────────────────────────────────────────────────
create table if not exists projects (
    id                   uuid primary key default gen_random_uuid(),
    name                 text not null,
    client_id            uuid references clients(id) on delete set null,
    drive_folder_id      text,
    status               text not null default 'active',  -- active | archived
    transcription_done_at timestamptz,
    compilation_done_at   timestamptz,
    scaffold_done_at      timestamptz,
    brief_sent_at         timestamptz,
    updated_at            timestamptz not null default now(),
    created_at            timestamptz not null default now()
);
create index if not exists projects_client_idx  on projects (client_id);
create index if not exists projects_status_idx  on projects (status);

-- ── 5. Documents (transcripts, source packages, scaffolds, briefs) ───────────
create table if not exists documents (
    id            uuid primary key default gen_random_uuid(),
    project_id    uuid not null references projects(id) on delete cascade,
    client_id     uuid references clients(id) on delete set null,
    document_type text not null,   -- transcript | source_file | source_package | scaffold | design_brief
    filename      text,
    content       text,
    status        text not null default 'pending',  -- pending | approved
    created_at    timestamptz not null default now()
);
create index if not exists documents_project_idx on documents (project_id);
create index if not exists documents_type_idx    on documents (project_id, document_type, status);

-- ── 6. Sign-offs (waiting-for tracker) ──────────────────────────────────────
create table if not exists signoffs (
    id            uuid primary key default gen_random_uuid(),
    waiting_on    text not null,   -- name of person/company we're waiting on
    item          text not null,   -- what we're waiting for
    project_id    uuid references projects(id) on delete set null,
    due_at        timestamptz,
    contact_email text,
    sent_at       timestamptz not null default now(),
    resolved_at   timestamptz      -- null = still open
);
create index if not exists signoffs_open_idx on signoffs (resolved_at) where resolved_at is null;

-- ── 7. Chat sessions ─────────────────────────────────────────────────────────
create table if not exists sessions (
    id           uuid primary key default gen_random_uuid(),
    session_type text not null default 'chat',
    title        text,
    client_id    uuid references clients(id) on delete set null,
    created_at   timestamptz not null default now()
);

-- ── 8. Chat messages (full turn history incl. tool calls) ───────────────────
create table if not exists messages (
    id         uuid primary key default gen_random_uuid(),
    session_id uuid not null references sessions(id) on delete cascade,
    role       text not null,    -- user | assistant | tool
    content    text not null,
    created_at timestamptz not null default now()
);
create index if not exists messages_session_idx on messages (session_id, created_at);

-- ── 9. Daily brief log ───────────────────────────────────────────────────────
create table if not exists daily_brief_log (
    id         uuid primary key default gen_random_uuid(),
    brief_date date not null unique,
    content    text not null,
    created_at timestamptz not null default now()
);
