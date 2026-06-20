-- Client build deadlines — powers the "Builds & deadlines" section of the daily brief.
-- Run once in the Supabase SQL editor. Safe to re-run.
--
-- `next_step` already holds WHAT is being built for a client; this adds WHEN it's due.
-- Set it from the dashboard, by telling the bot ("set Connie's deadline to 26 June"),
-- or directly here. The brief lists engaged clients soonest-deadline-first.

alter table clients add column if not exists deadline date;

create index if not exists clients_deadline_idx on clients (deadline);
