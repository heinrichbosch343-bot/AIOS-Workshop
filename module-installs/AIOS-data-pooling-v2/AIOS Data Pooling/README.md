# AIOS Data Pooling — v2

Turn a Google Drive full of client documents into a **searchable knowledge pool** you can
ask questions in plain English — with every answer cited back to the exact source files,
never invented.

> **New in v2:** answers now use **Anthropic prompt caching** — ask several questions about
> the same client / project / file and the document text is reused from cache at ~10% of the
> input cost. Same answers, a fraction of the price. The answer model is configurable too
> (set `ANSWER_MODEL=claude-haiku-4-5` for the cheapest runs). See *What's new in v2* below.

## What it does

1. **Crawls** your Google Drive client folders (each top-level folder = one client, each
   subfolder = a project)
2. **Extracts** the text from Docs, PDFs, Word files, and plain text
3. **Slices** each document into overlapping passages and turns each one into a *meaning
   fingerprint* (a vector embedding via Voyage AI)
4. **Stores** everything in Supabase (pgvector), keyed by client / project / file
5. **Answers questions** by meaning, not keywords — scoped as wide or narrow as you want,
   with the source text cached so follow-up questions are cheap:

```
python ask.py "What did the board decide about audit independence?"                  # everything
python ask.py "..." --client "Acme Corp"                                            # one client
python ask.py "..." --client "Acme Corp" --project "2026 Governance Review"         # one project
python ask.py "..." --file-id 1AbC...                                               # one file
```

The deeper you scope, the more specific the search. Scoping is enforced **in the
database**, so a question about one client can never surface another client's content.

## What's new in v2

- **Prompt caching on every answer** — the retrieved document text is sent as a cached
  prefix. The first question on a given scope primes the cache; every follow-up within ~5
  minutes reuses it at ~10% of the input cost. Identical answers, far lower spend.
- **Configurable answer model** — set `ANSWER_MODEL` in `.env`. Default is
  `claude-sonnet-4-6`; use `claude-haiku-4-5` for the lowest cost, or an Opus model for the
  deepest reasoning.
- Same drop-in pipeline, schema, and one-time setup as v1 — nothing else to relearn.

## What's in the box

| File | Role |
| --- | --- |
| `sql/001_data_pooling.sql` | The database schema + scoped search function (run once in Supabase) |
| `scripts/pool_config.py` | All settings in one place (reads your `.env`) |
| `scripts/drive_client.py` | Google Drive auth + text extraction (`python drive_client.py` = one-time connect) |
| `scripts/chunker.py` | Splits documents into overlapping passages |
| `scripts/embeddings.py` | Voyage AI meaning fingerprints (rate-limit safe) |
| `scripts/store.py` | Supabase storage + scoped similarity search |
| `scripts/indexer.py` | The crawl→extract→chunk→embed→store engine |
| `scripts/reindex.py` | **Run this to (re)build the pool** — incremental, safe to re-run |
| `scripts/ask.py` | **Run this to ask questions** — CLI or import `ask()` |
| `scripts/smoke_test.py` | Proves the whole pipeline works (self-cleaning) |

## Keys you need

| Key | Where to get it | Used for |
| --- | --- | --- |
| `VOYAGE_API_KEY` | [dashboard.voyageai.com](https://dashboard.voyageai.com) | embeddings (free tier works) |
| `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` | Supabase project → Settings → API | storage + search |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) | answering (only `ask.py` needs it) |
| `credentials.json` | Google Cloud Console OAuth client (Desktop app) | Drive access |

## Install

Give this folder to Claude Code and say **"read INSTALL.md and set this up"** — or follow
INSTALL.md yourself. Setup is: install requirements → run the SQL → add keys to `.env` →
connect Google → `python reindex.py` → ask away.

## Costs (typical)

- **Voyage embeddings**: free tier covers a small consultancy's documents; indexing is
  incremental so you only pay for new/changed files
- **Claude answers**: ~$0.01–0.05 per question on the default model — and **follow-up
  questions on the same scope cost a fraction of that**, thanks to prompt caching. Set
  `ANSWER_MODEL=claude-haiku-4-5` to cut it further.
- **Supabase**: free tier is plenty for tens of thousands of passages
