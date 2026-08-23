-- Recurring invoicing: monthly maintenance invoices generated + sent automatically.
-- Run once in the Supabase SQL editor. Safe to re-run (all IF NOT EXISTS).
-- Seeds the 3 invoices already sent manually (BOSCHLY-2026-001..003) so the automated
-- numbering picks up at 004 instead of colliding with real, already-sent invoice numbers.

-- ── 1. Every invoice ever issued (manual or automated) ─────────────────────────
create table if not exists invoices (
    id                  uuid primary key default gen_random_uuid(),
    invoice_number      text not null unique,        -- e.g. BOSCHLY-2026-004
    recurring_billing_id uuid,                        -- null for one-off / historical invoices
    client_name         text not null,
    client_email        text not null,
    description         text not null,                -- item heading, e.g. "Website maintenance, September 2026"
    amount              numeric(12, 2) not null,
    currency            text not null default 'ZAR',
    issued_date         date not null,
    due_date            date not null,
    status              text not null default 'sent',  -- sent | paid | void
    sent_at             timestamptz,
    created_at          timestamptz not null default now()
);
create index if not exists invoices_recurring_idx on invoices (recurring_billing_id);
create index if not exists invoices_issued_idx    on invoices (issued_date desc);

-- ── 2. Standing monthly billing arrangements ────────────────────────────────────
create table if not exists recurring_billing (
    id                  uuid primary key default gen_random_uuid(),
    client_name         text not null,
    client_email        text not null,
    client_address      text,                          -- one line per row, newline-separated
    client_phone        text,
    item_heading         text not null,                 -- e.g. "Website maintenance" (month/year appended at send time)
    item_description     text not null,                 -- the fixed paragraph under the heading
    amount              numeric(12, 2) not null,
    currency            text not null default 'ZAR',
    billing_day         int not null default 1,         -- day of month to invoice on
    payment_terms_days  int not null default 7,
    active              boolean not null default true,
    next_invoice_date   date not null,
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now()
);
create index if not exists recurring_billing_active_idx on recurring_billing (active, next_invoice_date);

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'invoices_recurring_billing_fkey'
    ) then
        alter table invoices
            add constraint invoices_recurring_billing_fkey
            foreign key (recurring_billing_id) references recurring_billing(id) on delete set null;
    end if;
end $$;

-- ── 3. Seed: the 3 invoices already sent by hand, so numbering continues at 004 ─
insert into invoices (invoice_number, client_name, client_email, description, amount, issued_date, due_date, status)
values
    ('BOSCHLY-2026-001', '24 Hour Glass', 'sales@24hourglass.co.za',
     'AI Opportunity Audit', 7500.00, '2026-07-29', '2026-08-05', 'sent'),
    ('BOSCHLY-2026-002', 'Chillipepper Projects', 'chillipepperprojects@gmail.com',
     'Website maintenance, April-August 2026 (5 months)', 1000.00, '2026-08-04', '2026-08-11', 'sent'),
    ('BOSCHLY-2026-003', 'RSST Splicing and Technologies', 'stefan@rsst.co.za',
     'RSST website build + Website maintenance, August 2026', 3200.00, '2026-08-06', '2026-08-13', 'sent')
on conflict (invoice_number) do nothing;

-- ── 4. Seed: Chillipepper's standing R200/month arrangement, starting 1 Sept 2026 ─
-- (per BOSCHLY-2026-002's own terms: "The next invoice is due on 1 September 2026
-- and monthly from then on"). Inactive clients or a wrong amount can be fixed with
-- a plain UPDATE — this table is meant to be hand-edited as billing changes.
insert into recurring_billing (
    client_name, client_email, client_address, client_phone,
    item_heading, item_description, amount, billing_day, payment_terms_days,
    active, next_invoice_date
)
select
    'Chillipepper Projects', 'chillipepperprojects@gmail.com',
    E'Plot 115 Cableway Road\nHartbeespoort, 0216', '+27 79 174 4114',
    'Website maintenance',
    'Monthly upkeep of chilipepperprojects.com: keeping the site online and running, content and product updates on request, and fixes as they come up. Billed monthly in advance from the first of the month.',
    200.00, 1, 7, true, '2026-09-01'
where not exists (
    select 1 from recurring_billing where client_email = 'chillipepperprojects@gmail.com'
);
