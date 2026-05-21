# System: DataOS

> Local SQLite data warehouse that collects business metrics daily and outputs an AI-readable key-metrics.md.

## Architecture

```
.env (API keys) --> collect.py --> collectors --> data/data.db --> generate_metrics.py --> context/group/key-metrics.md
```

Windows Task Scheduler runs `collect.py` every day at 7:00 AM automatically.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/collect.py` | Orchestrator — runs all collectors in sequence |
| `scripts/db.py` | SQLite connection, schema, and write helpers |
| `scripts/config.py` | Loads `.env` credentials, resolves Google credential path |
| `scripts/collect_fx_rates.py` | Active collector — fetches live FX rates |
| `scripts/generate_metrics.py` | Reads DB, writes `context/group/key-metrics.md` |
| `data/data.db` | SQLite database (gitignored) |
| `context/group/key-metrics.md` | AI-readable metrics output, regenerated daily |

## How It Works

1. Scheduler triggers `collect.py` at 7:00 AM
2. `collect.py` runs each active collector (currently: FX rates)
3. Each collector fetches data and writes rows to `data/data.db`
4. `generate_metrics.py` queries the DB and rewrites `key-metrics.md`
5. Claude reads `key-metrics.md` for current business numbers

## Configuration

| Variable | Purpose | Required |
|----------|---------|----------|
| `GOOGLE_SHEETS_CREDENTIALS` | Path to Google service account JSON | For Sheets collectors |
| `GOOGLE_APPLICATION_CREDENTIALS` | Same path — used by Google libraries directly | For GA4/Sheets |
| `STRIPE_API_KEY` | Stripe revenue data | Optional |
| `YOUTUBE_API_KEY` | YouTube metrics | Optional |

## Common Operations

**Run collection manually:**
```bash
.venv\Scripts\python.exe scripts\collect.py
```

**Regenerate key-metrics.md only:**
```bash
.venv\Scripts\python.exe scripts\generate_metrics.py
```

**Add a new collector:** Create `scripts/collect_<source>.py` with a `collect()` function that returns rows, then register it in `collect.py`.

## Dependencies

- **Depends on:** Python venv, `.env` credentials
- **Used by:** IntelOS (shares the venv), Daily Brief (reads key-metrics.md)

## History

| Date | Change |
|------|--------|
| 2026-05-18 | Initial installation — FX rate collector live |
| 2026-05-19 | Fixed Google credential variable mismatch in config.py; re-encoded .env to UTF-8 |
