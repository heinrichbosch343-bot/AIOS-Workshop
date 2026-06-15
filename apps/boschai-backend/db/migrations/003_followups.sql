-- Follow-up engine — tracks which sent threads are awaiting replies and what
-- follow-up attempts have been made. Run once in the Supabase SQL editor.

create table if not exists followups (
    id              uuid primary key default gen_random_uuid(),
    thread_id       text not null unique,        -- Gmail thread id (one record per thread)
    message_id      text not null,              -- Gmail message id of the original sent message
    contact_email   text not null,              -- recipient address
    contact_name    text,                       -- display name (if known)
    subject         text,                       -- email subject line
    original_sent_at timestamptz not null,      -- when the original email was sent
    last_followup_at timestamptz,               -- when the last follow-up was sent/drafted
    attempt_count   int not null default 0,     -- how many follow-ups have been sent
    status          text not null default 'pending',
        -- pending   = waiting for reply, eligible for follow-up
        -- drafted   = follow-up saved as draft (warmup mode)
        -- sent      = follow-up actually sent
        -- replied   = contact replied, thread closed
        -- stopped   = manually stopped or max attempts reached
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

-- Fast lookups by thread and status.
create index if not exists followups_thread_idx on followups (thread_id);
create index if not exists followups_status_idx on followups (status);
create index if not exists followups_contact_idx on followups (contact_email);
