-- Google OAuth token store — holds the single connected Google account's tokens
-- (Gmail + Drive + Calendar share one sign-in). Written by /auth/google/callback,
-- read + auto-refreshed by services.drive.get_credentials. Run once in the Supabase
-- SQL editor. Only one row is ever kept (the callback deletes any existing row first).

create table if not exists google_tokens (
    id            uuid primary key default gen_random_uuid(),
    access_token  text not null,              -- short-lived access token (auto-refreshed)
    refresh_token text not null,              -- long-lived token used to mint new access tokens
    expires_at    timestamptz,                -- when the access token expires (null = unknown)
    created_at    timestamptz not null default now()
);
