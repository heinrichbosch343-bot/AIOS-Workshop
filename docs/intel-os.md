# System: IntelOS

> Fathom meeting transcript collector — pulls recordings into a local SQLite database for AI querying.

## Architecture

```
Fathom API --> collect_fathom.py --> data/intel.db --> classify.py (tags meetings by type)
```

Windows Task Scheduler runs `collect_all.py` every day at 7:05 AM automatically.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/intel/collect_all.py` | Master runner — called by scheduler |
| `scripts/intel/collect_fathom.py` | Pulls transcripts from Fathom REST API |
| `scripts/intel/classify.py` | Tags meetings as client call, team meeting, etc. |
| `scripts/intel/db.py` | SQLite schema and helpers for `data/intel.db` |
| `data/intel.db` | SQLite database with meetings, staff registry, collection log (gitignored) |

## How It Works

1. Scheduler triggers `collect_all.py` at 7:05 AM
2. `collect_fathom.py` calls Fathom API for meetings in the last 7 days
3. Transcripts, summaries, and action items are written to `data/intel.db`
4. `classify.py` tags each new meeting by call type (client, team, external)
5. Claude can query `data/intel.db` to answer questions about past meetings

## Configuration

| Variable | Purpose | Required |
|----------|---------|----------|
| `FATHOM_API_KEY` | Fathom REST API authentication | Yes |

Fathom must have the Chrome extension installed and connected to Google Meet for recordings to be captured automatically.

## Common Operations

**Run collection manually:**
```bash
.venv\Scripts\python.exe scripts\intel\collect_all.py
```

**Search meetings from Claude:**
Ask: "What was discussed in my last client call?" — Claude queries `data/intel.db` directly.

**Re-classify all meetings:**
```bash
.venv\Scripts\python.exe scripts\intel\classify.py --reclassify
```

## Dependencies

- **Depends on:** DataOS venv, Fathom account with Chrome extension active on Google Meet
- **Used by:** Daily Brief (reads meeting summaries for the briefing)

## History

| Date | Change |
|------|--------|
| 2026-05-19 | Initial installation — Fathom collector live, scheduler set to 7:05 AM |
