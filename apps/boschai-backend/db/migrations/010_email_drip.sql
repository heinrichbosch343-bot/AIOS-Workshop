-- Email drip queue: personalized outreach emails sent one at a time with
-- random 3-9 minute gaps by the scheduler (services/email_drip.py), instead
-- of Heinrich sending 25 drafts by hand in inconsistent bursts.
-- Run once in the Supabase SQL editor. Safe to re-run.

create table if not exists email_queue (
  id          bigint generated always as identity primary key,
  local_id    text unique,                      -- id from the local CRM queue CSV (dedupe key)
  to_email    text not null,
  name        text not null default '',
  firm        text not null default '',
  subject     text not null,
  body        text not null,
  status      text not null default 'queued',   -- queued | sent | failed | skipped
  error       text not null default '',
  queued_at   timestamptz not null default now(),
  sent_at     timestamptz
);

create index if not exists email_queue_status_idx  on email_queue (status);
create index if not exists email_queue_sent_at_idx on email_queue (sent_at);
