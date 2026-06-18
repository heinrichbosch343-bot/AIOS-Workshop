-- Client memory: meeting transcripts + a living per-client brief.
-- Run once in the Supabase SQL editor. Safe to re-run (all IF NOT EXISTS).
--
-- Lets Heinrich upload a meeting transcript and have the brain remember, per client:
-- what they do, their problems, what we're building, and next steps. Kept in their own
-- tables (keyed by client_id) so they never collide with the CRM columns on `clients`.

-- ── 1. Full transcripts — one row per uploaded meeting ───────────────────────
create table if not exists client_transcripts (
    id           uuid primary key default gen_random_uuid(),
    client_id    uuid references clients(id) on delete cascade,
    title        text,                       -- filename or a short label
    content      text not null,              -- full extracted transcript text
    summary      text,                       -- short per-meeting summary
    meeting_date date,                       -- best-effort date the meeting happened
    source       text default 'telegram',    -- where it came from
    created_at   timestamptz not null default now()
);
create index if not exists client_transcripts_client_idx
    on client_transcripts (client_id, created_at desc);

-- ── 2. Living brief — exactly one per client (what they do / problems / building / next) ──
create table if not exists client_briefs (
    client_id  uuid primary key references clients(id) on delete cascade,
    brief      text not null,
    updated_at timestamptz not null default now()
);
