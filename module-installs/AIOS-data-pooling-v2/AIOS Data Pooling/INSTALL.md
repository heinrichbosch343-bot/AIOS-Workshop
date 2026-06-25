# Installing AIOS Data Pooling — v2

> **If you are Claude Code:** walk the user through these steps one at a time, in plain
> English. Run the commands for them where you can, and verify each step before moving on.
> Don't dump all the steps at once.

This module turns a Google Drive of client documents into a searchable, citable knowledge
pool. Answers use Anthropic prompt caching, so repeat questions about the same documents run
cheaply. Setup takes about 15 minutes; most of it is collecting keys.

---

## Step 0 — What you need before starting

- A **Supabase** project (free tier is fine) — [supabase.com](https://supabase.com)
- A **Voyage AI** key (free tier is fine) — [dashboard.voyageai.com](https://dashboard.voyageai.com)
- An **Anthropic** key — [console.anthropic.com](https://console.anthropic.com)
- A **Google account** whose Drive holds the client folders, organised like:

```
My Drive/
├── Acme Corp/              <- one folder per client
│   ├── 2026 Governance Review/    <- one subfolder per project
│   │   ├── Interview transcript.docx
│   │   └── Final report.pdf
└── Beta Industries/
    └── ...
```

## Step 1 — Install the Python requirements

From this module's `scripts/` folder:

```
pip install -r requirements.txt
```

(Use the project's virtual environment if it has one.)

## Step 2 — Connect Google Drive (one time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create (or pick) a
   project → **APIs & Services**
2. Enable the **Google Drive API**
3. **Credentials → Create credentials → OAuth client ID → Desktop app**
4. Download the JSON and save it as `credentials.json` inside this module's `scripts/` folder
5. Run the one-time connect (a browser window opens; sign in and approve):

```
python drive_client.py
```

You should see `Connected to Google Drive as you@example.com.` A `token.json` appears next
to the script — that's your saved session; you won't need the browser again.

## Step 3 — Create the database (one time)

1. Open your Supabase project → **SQL Editor**
2. Paste the entire contents of `sql/001_data_pooling.sql` and **Run**

This creates the `knowledge_chunks` table and the `match_chunks` search function.

## Step 4 — Add your keys to .env

In your **project root** `.env` (create it if needed — and make sure `.env` is gitignored):

```
VOYAGE_API_KEY=...
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
ANTHROPIC_API_KEY=...

# Optional: limit indexing to specific top-level Drive folders (comma-separated names).
# Leave unset to index every non-excluded top-level folder.
POOL_CLIENT_ROOTS=Acme Corp,Beta Industries

# Optional: choose the answer model (default claude-sonnet-4-6).
# claude-haiku-4-5 = cheapest; an Opus model = deepest reasoning.
# ANSWER_MODEL=claude-haiku-4-5

# Optional: on a PAID Voyage tier, index at full speed:
# EMBED_REQUEST_INTERVAL=0
```

## Step 5 — Prove it works

```
python smoke_test.py
```

Expected: four `OK` lines ending with
`OK — embeddings, storage, and scoped search all work end to end.`
(It inserts a few fake passages, checks every scope level, and cleans up after itself.)

## Step 6 — Build the pool

See what would be indexed first (no cost, no writes):

```
python reindex.py --dry-run
```

If the list looks right, index for real (first run can take a while on Voyage's free
tier — it paces itself to respect the rate limit):

```
python reindex.py
```

## Step 7 — Ask your first question

```
python ask.py "What were the key findings in the latest report?" --client "Acme Corp"
```

You get a concise answer with a `Sources:` list of the exact files it came from. If the
answer isn't in the documents, it says exactly that — it never invents. Ask more questions
about the same client / project / file and they run cheaper: the document text is reused
from cache for ~5 minutes.

---

## Day-to-day use

- **Added or changed files in Drive?** → `python reindex.py` (only new/changed work is done)
- **Ask anything** → `python ask.py "..."` with `--client` / `--project` / `--file-id` to
  narrow the scope. The deeper you scope, the more specific the answer.
- **From your own code** → `from ask import ask` and call
  `ask(question, client=..., project=..., source_id=...)` — returns
  `{answer, citations, chunks_used}`.

## Customising

- **What gets skipped**: edit `EXCLUDE_FOLDERS` / `EXCLUDE_NAME_BITS` in `scripts/indexer.py`
  (admin, invoices, archives etc. are skipped by default)
- **File types**: `INCLUDE_MIMES` / `INCLUDE_EXTS` in `scripts/indexer.py`
- **Answer style**: the `_SYSTEM` prompt in `scripts/ask.py`
- **Answer model / cost**: `ANSWER_MODEL` in `.env` (default `claude-sonnet-4-6`;
  `claude-haiku-4-5` is cheapest)
- **Embedding model**: `EMBEDDING_MODEL` in `.env` (change the SQL's `1024` if the
  dimension differs, then re-index)

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Missing required settings: ...` | Add the named keys to `.env` (Step 4) |
| `Google credentials not found` | Step 2 — `credentials.json` goes in `scripts/` |
| `Could not find the function match_chunks` | Step 3 — run the SQL in Supabase |
| Indexing is slow | Normal on Voyage's free tier (3 requests/min). Paid tier: set `EMBED_REQUEST_INTERVAL=0` |
| A file was skipped | Check the exclude lists in `indexer.py` — invoices, archives, etc. are skipped on purpose |
