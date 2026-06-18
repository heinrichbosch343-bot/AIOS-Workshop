# Plan: Remove the Google Drive Knowledge Base

**Created:** 2026-06-19
**Status:** Ready to execute (one decision pending — see Scope)
**Owner:** Heinrich + Claude

---

## Why

The old "Knowledge Pool" indexes Google Drive documents into AI-searchable vector
memory (via Voyage AI embeddings). Heinrich **isn't using it**, the Voyage key was
never configured, and it **throws config errors** whenever the bot reaches for it.
Worse, it *competes* with the new Supabase client memory — when Heinrich asks about a
client, the agent sometimes calls the broken Drive search instead of the Supabase brief.

The new **Supabase client memory** (built 2026-06-18) fully replaces it:
- `clients` — CRM record (name, stage, email, notes)
- `client_transcripts` — full meeting transcript + summary, per client
- `client_briefs` — living brief (what they do / problems / building / next steps), per client

So: rip out the Drive knowledge base, keep everything in Supabase.

---

## Scope decision (confirm before executing)

How far to cut the Google Drive side:

1. **All Drive + knowledge base (RECOMMENDED)** — remove the Knowledge Pool AND the Drive
   file browsing/search tools. Cleanest; nothing Drive-related left to error or confuse the bot.
2. **Only the broken pool** — remove the semantic search + nightly re-index, but keep basic
   Drive file browsing (`list_drive_folders` / `list_drive_files`) for later.
3. **Just stop the errors** — disable the job + auto-calls, leave dead code. Least clean.

Default if unspecified: **Option 1**.

**Keep no matter what:** Gmail, Google Calendar, the Supabase client memory, and
`services/drive_extract.py` (the transcript upload reuses its PDF/DOCX/XLSX parsers).
`services/drive.py` stays too (Gmail/Calendar/transcripts use `get_credentials`).

---

## Files to DELETE

- `services/knowledge.py` — knowledge pool Q&A
- `services/indexer.py` — Drive re-indexer
- `services/embeddings.py` — Voyage embeddings client
- `services/drive_query.py` — Drive folder Q&A (used by `search_documents`)
- `routes/knowledge.py` — `/knowledge/ask`, `/knowledge/reindex`
- `scripts/smoke_ask.py`, `scripts/backfill_pool.py` — knowledge-pool dev scripts
- *(Option 1 only)* `routes/drive.py` — `/drive/folders|files|extract|query`

> Leave migrations `001_knowledge_pool.sql` / `002_scoped_search.sql` and their DB tables
> in place (non-destructive). They can be dropped later if desired.

## Files to EDIT

- `main.py` — remove `knowledge_router` import + `include_router`. *(Option 1: also remove `drive_router`.)*
- `services/scheduler.py` — drop `indexer` from the import, delete `_run_reindex()`, delete the
  `knowledge_reindex` job, update the startup print string.
- `services/agent.py` — remove tools `ask_knowledge_base` + `search_documents` (*Option 1: also
  `list_drive_folders` + `list_drive_files`*); remove their `run_tool` branches; remove now-unused
  imports (`query_folder`, `knowledge_service`, and `gbuild`/`get_credentials` if only the Drive
  tools used them); delete the "Looking INSIDE documents" + "Knowledge Pool" paragraphs in `_BEHAVIOUR`.
- `config.py` — remove `VOYAGE_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIM`, `POOL_CLIENT_ROOTS`,
  `EMBED_BATCH_SIZE`, `EMBED_REQUEST_INTERVAL`.
- `routes/extract.py` — confirm it doesn't import `drive_query`/`knowledge` (grep says it doesn't); leave if clean.

## KEEP (do not touch)

- `services/drive.py` (OAuth + download — Gmail/Calendar/transcripts depend on it)
- `services/drive_extract.py` (transcript file parsing)
- `services/email.py`, `services/calendar.py` (Gmail + Calendar)
- `services/transcripts.py`, `services/pipeline.py`, `services/context_store.py` (Supabase memory + CRM)

---

## Verification

1. `python -m py_compile` on every edited file.
2. Grep to confirm zero remaining references: `knowledge`, `indexer`, `drive_query`, `query_folder`,
   `VOYAGE`, `ask_knowledge_base`, `search_documents`.
3. `python -c "import main"` (or boot locally with `DISABLE_TELEGRAM_BOT=1`) — confirm no import errors.
4. Confirm the agent still answers client questions via `get_client_brief` / `search_client_transcripts`.

## Deploy

- Commit + `git push origin main` → Railway auto-deploys from GitHub. **Do NOT use `railway up`** (CLI).
- Watch logs for a clean boot (no knowledge-reindex job, no Voyage/config errors).

---

## OPEN ITEM (carried over) — Telegram bot conflict

A **second bot was polling** the same token: the local dev backend (uvicorn on port 8000) was
running with the bot enabled, conflicting with Railway → `telegram.error.Conflict`. Fix: run the
local backend with `DISABLE_TELEGRAM_BOT=1` in the root `.env` (API-only for CRM dev), OR stop it,
so **only Railway** polls. Confirm the live bot is clean before/after tomorrow's deploy.

---

## Notes / housekeeping

- Deploy method going forward: **git push only** (GitHub auto-deploy). CLI `railway up` conflicts.
- CRM stages are synced to the board (incl. `contact_again`). UI must store snake_case stage keys.
- `scripts/smoke_context.py` still references the old `anchor` stage — stale, fix or delete someday.
