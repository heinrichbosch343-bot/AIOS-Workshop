-- CRM Pipeline upgrade: richer lead tracking for Heinrich's sales pipeline.
-- Run once in the Supabase SQL editor. Safe to re-run (all IF NOT EXISTS / ADD IF NOT EXISTS).
--
-- New pipeline stages: interested | no_reply | meeting_booked | follow_up_meeting | proposal | won | lost
-- (replaces the old lead | pipeline | anchor | inactive)

-- ── 1. Add new columns to clients ──────────────────────────────────────────────
alter table clients add column if not exists email            text;
alter table clients add column if not exists lead_source      text;       -- campaign | referral | inbound | other
alter table clients add column if not exists meeting_date     timestamptz;
alter table clients add column if not exists proposal_sent_at timestamptz;
alter table clients add column if not exists last_contacted   timestamptz;
alter table clients add column if not exists lost_reason      text;
alter table clients add column if not exists stage_changed_at timestamptz not null default now();

-- ── 2. Index for pipeline queries ──────────────────────────────────────────────
create index if not exists clients_pipeline_stage_idx on clients (pipeline_stage);
create index if not exists clients_stage_changed_idx on clients (stage_changed_at);

-- ── 3. Migrate existing data to new stages ─────────────────────────────────────
-- anchor  → won    (signed clients)
-- pipeline → meeting_booked (active pursuit → assume at least a meeting)
-- lead    → interested
-- inactive → lost
update clients set pipeline_stage = 'won'            where pipeline_stage = 'anchor';
update clients set pipeline_stage = 'meeting_booked' where pipeline_stage = 'pipeline';
update clients set pipeline_stage = 'interested'     where pipeline_stage = 'lead';
update clients set pipeline_stage = 'lost'           where pipeline_stage = 'inactive';

-- Update stage_changed_at for migrated rows
update clients set stage_changed_at = now() where stage_changed_at is null;
