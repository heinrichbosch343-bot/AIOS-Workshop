-- 015_quote_payments.sql — the payment link on a quote.
--
-- A quote that gets a "yes" and then waits for someone to send banking details is
-- the same failure as a quote that never arrives, one step later. So the link is
-- created at the moment the quote is issued and travels with it.
--
-- Money is stored in CENTS (integer) wherever it touches Paystack, because that is
-- the unit their API speaks and converting in two places is how you end up charging
-- someone R115 000 for an R11 500 job. `deposit_amount` here is the human figure in
-- rand, kept alongside the quote total; the cents conversion happens once, in
-- services/payments.py, and nowhere else.

alter table quotes add column if not exists deposit_amount    numeric(12, 2);
alter table quotes add column if not exists payment_reference text;
alter table quotes add column if not exists payment_url       text;

-- unpaid | paid | failed | skipped. `skipped` means no link was created at all —
-- payments switched off, or the gateway refused — and is deliberately distinct from
-- `unpaid`, which means a link exists and nobody has used it yet.
alter table quotes add column if not exists payment_status    text default 'skipped';
alter table quotes add column if not exists payment_error     text;
alter table quotes add column if not exists paid_at           timestamptz;
alter table quotes add column if not exists paid_amount       numeric(12, 2);
alter table quotes add column if not exists paid_channel      text;

-- How a Paystack webhook finds its quote: the reference we generated at issue time.
create unique index if not exists quotes_payment_reference_idx
    on quotes (payment_reference) where payment_reference is not null;

-- Quoted, accepted, and still not paid. The chase list, one step further along than
-- quotes_open_idx.
create index if not exists quotes_unpaid_idx on quotes (sent_at)
    where payment_status = 'unpaid';


-- Every webhook Paystack sends us, kept raw.
--
-- Same reasoning as quote_messages: `event_id` is UNIQUE, so a Paystack retry inserts
-- zero rows and the handler stops. Payment webhooks retry aggressively, and marking a
-- quote paid twice is how a customer gets told twice and the office reconciles wrong.

create table if not exists payment_events (
    id          uuid primary key default gen_random_uuid(),
    event_id    text unique,
    event       text,
    reference   text,
    amount      numeric(12, 2),
    currency    text,
    status      text,
    payload     jsonb,
    created_at  timestamptz not null default now()
);

create index if not exists payment_events_ref_idx on payment_events (reference, created_at desc);
