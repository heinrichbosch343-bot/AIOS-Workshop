-- 013_quotes.sql — the quote log behind the WhatsApp quote bot.
--
-- Not required to run the demo. The bot works entirely from memory without it,
-- which is fine while both phones are ours and wrong the moment a real business
-- depends on it: without this table, quote numbers restart and the office has no
-- record of what went out. Run it in the Supabase SQL editor before go-live.
--
-- The follow-up clock is the reason this table earns its place. A quote sent and
-- never chased is a site visit already paid for in fuel and a technician's
-- afternoon, and `accepted_at IS NULL` plus an ageing `sent_at` is the whole query.

create table if not exists quotes (
    id                uuid primary key default gen_random_uuid(),
    quote_number      text not null unique,

    customer_name     text not null,
    customer_phone    text,
    customer_email    text,
    site_address      text,

    line_items        jsonb not null default '[]'::jsonb,
    total             numeric(12, 2) not null,
    currency          text not null default 'ZAR',
    notes             text,

    -- Who quoted it, as the WhatsApp number it came from. Kept raw so a
    -- technician leaving does not orphan their history.
    quoted_by_number  text,
    quoted_by_name    text,

    issued_date       date not null,
    valid_until       date,

    -- sent | failed | draft. A failed send still gets a row: a quote that did not
    -- reach the customer is the exact thing this system exists to make visible.
    status            text not null default 'sent',
    delivery_error    text,

    sent_at           timestamptz,
    -- Set when the customer says yes. Everything still null here after a few days
    -- is the follow-up list.
    accepted_at       timestamptz,
    followed_up_at    timestamptz,

    created_at        timestamptz not null default now()
);

-- Numbering reads the highest existing number for the year on every issue.
create index if not exists quotes_number_idx on quotes (quote_number);

-- The two queries the business actually asks: what went out lately, and what has
-- gone quiet.
create index if not exists quotes_issued_idx on quotes (issued_date desc);
create index if not exists quotes_open_idx on quotes (sent_at)
    where accepted_at is null;


-- The in-progress draft, one row per technician, cleared when the quote is sent.
--
-- Without this the draft lives only in the web process's memory, so a redeploy or
-- a container cycle loses it -- and the technician's very next word is usually
-- SEND, which then answers "nothing to send" for a quote he is looking at.
-- The bot degrades gracefully if this table is absent, so running it is optional
-- for a demo and not optional for a business.

create table if not exists quote_drafts (
    technician  text primary key,
    draft       jsonb not null,
    updated_at  timestamptz not null default now()
);
