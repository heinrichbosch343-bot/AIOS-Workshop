-- Migration 011: drafts-to-drip, drip auto-reply, and the cloud CRM mirror.
-- Safe to re-run (IF NOT EXISTS everywhere).
--
-- 1. draft_queue    — Gmail drafts staged for the drip. The scheduler sends them
--                     via Gmail drafts.send, so a draft written as a reply stays
--                     in its original thread.
-- 2. drip_replies   — every prospect reply the drip responder has handled:
--                     classified, auto-answered (once per thread) or flagged.
-- 3. crm_contacts / crm_activity / crm_goals — cloud mirror of the local
--                     outreach CRM CSVs, powering the 24/7 /crm dashboard.
--                     scripts/crm_cloud_sync.py keeps both sides in step.

create table if not exists draft_queue (
  id              bigint generated always as identity primary key,
  draft_id        text unique not null,             -- Gmail draft id (dedupe key)
  to_email        text not null default '',
  subject         text not null default '',
  snippet         text not null default '',
  status          text not null default 'queued',   -- queued | sent | failed | gone
  error           text not null default '',
  queued_at       timestamptz not null default now(),
  sent_at         timestamptz,
  sent_message_id text not null default '',
  sent_thread_id  text not null default '',
  synced          boolean not null default false    -- mirrored to the local CSVs yet?
);
create index if not exists draft_queue_status_idx on draft_queue (status);

-- The plain email queue also needs the sent thread id so the responder can
-- watch those threads for replies.
alter table email_queue add column if not exists sent_thread_id text not null default '';

create table if not exists drip_replies (
  id                 bigint generated always as identity primary key,
  source             text not null default '',      -- draft | queue
  thread_id          text not null default '',
  prospect_email     text not null default '',
  prospect_name      text not null default '',
  inbound_message_id text unique not null,          -- dedupe: one row per inbound email
  subject            text not null default '',
  category           text not null default '',      -- interested | question | not_interested | unsubscribe | out_of_office | bounce | other
  action             text not null default '',      -- replied | drafted | flagged | logged
  reply_body         text not null default '',
  inbound_preview    text not null default '',
  synced             boolean not null default false,
  created_at         timestamptz not null default now()
);
create index if not exists drip_replies_thread_idx on drip_replies (thread_id);

create table if not exists crm_contacts (
  id          text primary key,                     -- id column from crm.csv
  data        jsonb not null default '{}'::jsonb,   -- the full CSV row
  status      text not null default '',
  cloud_dirty boolean not null default false,       -- edited in the cloud dashboard, waiting to sync down
  updated_at  timestamptz not null default now()
);
create index if not exists crm_contacts_status_idx on crm_contacts (status);

create table if not exists crm_activity (
  id         bigint generated always as identity primary key,
  dedupe_key text unique,                           -- hash of the local CSV row (push dedupe)
  date       text not null default '',
  channel    text not null default '',
  qty        int  not null default 1,
  name       text not null default '',
  firm       text not null default '',
  action     text not null default '',
  outcome    text not null default '',
  notes      text not null default '',
  origin     text not null default 'local',         -- local (pushed up) | cloud (logged in the dashboard)
  synced     boolean not null default false,        -- cloud rows mirrored down to the CSV yet?
  created_at timestamptz not null default now()
);
create index if not exists crm_activity_origin_idx on crm_activity (origin, synced);
create index if not exists crm_activity_date_idx on crm_activity (date);

create table if not exists crm_goals (
  id         int primary key,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
