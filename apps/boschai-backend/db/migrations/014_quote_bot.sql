-- 014_quote_bot.sql — the WhatsApp quote bot, rebuilt.
--
-- Supersedes 013_quotes.sql, which was written but never run. The two drops below
-- are safe: no quote was ever successfully issued by the old build, so there is no
-- data in either table. If you are reading this in future and `quotes` DOES hold
-- real quotes, stop and migrate the columns instead.
--
-- The first build kept the technician's in-progress quote in the web process's
-- memory. Railway restarts on every deploy, so a quote he was looking at simply
-- stopped existing and the bot answered "nothing to send". That is the whole reason
-- this file is not optional.

drop table if exists quote_drafts;
drop table if exists quotes cascade;


-- ─────────────────────────────────────────────────────────────── the conversation
--
-- One row per technician. `job` is what we have assembled so far; `history` is the
-- last few turns, so the model can read a reply as a reply rather than as a fresh
-- instruction.
--
-- state:  collecting → he is still telling us about the job
--         ready      → he has SEEN the card, so an approval means something
--         sent       → the last quote went out; the next job starts clean
--
-- Nothing is ever sent from `collecting`. Confirmation is the step that stops a
-- mistyped digit putting one customer's quote on a stranger's phone.

create table if not exists quote_sessions (
    technician_phone  text primary key,
    state             text not null default 'collecting',
    job               jsonb not null default '{}'::jsonb,
    history           jsonb not null default '[]'::jsonb,
    last_quote_number text,
    updated_at        timestamptz not null default now()
);


-- ────────────────────────────────────────────────────────────────── the audit log
--
-- Every message, both directions. `message_sid` is Twilio's own id and is UNIQUE:
-- an insert that touches 0 rows means Twilio is redelivering something already
-- handled, and we stop there. That one constraint removes double-sends and reply
-- loops as a category rather than as a series of bugs.
--
-- It also replaces the in-memory ring buffer the old build used for diagnostics.
-- That buffer showed the last 6 records while every message wrote 2 of them, so it
-- displayed only the last 3 messages — which I misread as evidence of a bug that
-- did not exist. A table does not have a length I can forget about.

create table if not exists quote_messages (
    id           uuid primary key default gen_random_uuid(),
    message_sid  text unique,              -- null for our own outbound messages
    direction    text not null,            -- in | out
    role         text,                     -- technician | customer | bot
    from_number  text,
    to_number    text,
    body         text,
    decision     jsonb,                    -- what the bot concluded, and why
    created_at   timestamptz not null default now()
);

create index if not exists quote_messages_at_idx on quote_messages (created_at desc);
create index if not exists quote_messages_from_idx on quote_messages (from_number, created_at desc);


-- ────────────────────────────────────────────────────────────────────── the record
--
-- `token` is the unguessable part of the public quote URL. Twilio fetches the PDF
-- from that URL in order to attach it, so the route cannot be authenticated — the
-- token is the secret.
--
-- Delivery is tracked per channel. A quote that failed to reach the customer is
-- precisely what this system exists to make visible, so a failure gets a row like
-- anything else.

create table if not exists quotes (
    id               uuid primary key default gen_random_uuid(),
    quote_number     text not null unique,
    token            text not null unique,

    customer_name    text not null,
    customer_phone   text,
    customer_email   text,
    site_address     text,

    line_items       jsonb not null default '[]'::jsonb,
    total            numeric(12, 2) not null,
    currency         text not null default 'ZAR',
    notes            text,

    quoted_by_number text,
    quoted_by_name   text,

    issued_date      date not null,
    valid_until      date,

    whatsapp_status  text,                 -- sent | failed | skipped
    whatsapp_error   text,
    email_status     text,                 -- sent | failed | skipped
    email_error      text,

    sent_at          timestamptz,
    -- Set when the customer replies yes. Everything still null here after a few
    -- days is the follow-up list — the unchased quote is the problem this whole
    -- system was built to remove.
    accepted_at      timestamptz,
    followed_up_at   timestamptz,
    customer_reply   text,

    created_at       timestamptz not null default now()
);

create index if not exists quotes_token_idx on quotes (token);
create index if not exists quotes_issued_idx on quotes (issued_date desc);

-- How an inbound message from an unknown number is recognised as a customer:
-- the most recent quote issued to that phone.
create index if not exists quotes_customer_idx on quotes (customer_phone, created_at desc);

-- What has gone quiet.
create index if not exists quotes_open_idx on quotes (sent_at) where accepted_at is null;
