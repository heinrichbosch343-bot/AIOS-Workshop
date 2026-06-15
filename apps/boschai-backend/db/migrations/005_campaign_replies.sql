-- Campaign auto-responder — logs every inbound reply and what action was taken.
-- Run once in the Supabase SQL editor.

create table if not exists campaign_replies (
    id                  uuid primary key default gen_random_uuid(),
    account_email       text not null,              -- which campaign account received the reply
    prospect_email      text not null,              -- who replied
    subject             text,
    category            text not null,              -- interested / not_interested / unsubscribe / out_of_office / bounce
    action              text not null,              -- replied / flagged
    prospect_body_preview text,                     -- first 500 chars of their reply
    replied_at          timestamptz not null default now(),
    created_at          timestamptz not null default now()
);

create index if not exists campaign_replies_account_idx on campaign_replies (account_email);
create index if not exists campaign_replies_prospect_idx on campaign_replies (prospect_email);
create index if not exists campaign_replies_date_idx on campaign_replies (replied_at);
