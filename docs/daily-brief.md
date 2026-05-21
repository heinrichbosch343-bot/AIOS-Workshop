# System: Daily Brief

> Gemini-powered morning intelligence brief — pipeline metrics + AI synthesis delivered to Telegram daily.

## Architecture

```
context/funnel.md --> metrics.py --> pipeline_daily (SQLite)
                                           |
                                      prompt.py (mega-prompt)
                                           |
                                    Gemini API (flash-lite)
                                           |
                          deliver.py --> Telegram (@BoschAI_bot)
                          dashboard.py --> funnel image (optional)
```

## Key Files

| File | Purpose |
|------|---------|
| `scripts/daily_brief.py` | Orchestrator — runs the full brief end-to-end |
| `scripts/metrics.py` | Reads `funnel.md`, queries `pipeline_daily` SQLite view |
| `scripts/prompt.py` | Builds the Gemini mega-prompt with preset sections |
| `scripts/deliver.py` | Sends brief to Telegram (two-message format) |
| `scripts/dashboard.py` | Generates vertical funnel chart (dark theme) |
| `context/funnel.md` | Defines pipeline stages, targets, and column mappings |

## How It Works

1. `metrics.py` parses `context/funnel.md` to find stage → column mappings
2. Queries the `pipeline_daily` SQLite view (today's date) for counts per stage
3. `prompt.py` builds a mega-prompt with metrics, targets, and context
4. Calls Gemini API (`gemini-2.5-flash-lite`) to synthesize the brief
5. `deliver.py` sends two messages to Telegram: brief text + optional dashboard image

## Configuration

| Variable | Purpose | Required |
|----------|---------|----------|
| `GEMINI_API_KEY` | Gemini API access | Yes |
| `BRIEF_MODEL` | Override model (default: `gemini-2.5-flash-lite`) | No |
| `BRIEF_PRESET` | Prompt preset (`solo`) | No |
| `TELEGRAM_BOT_TOKEN` | Bot token for delivery | Yes (if delivering) |
| `TELEGRAM_CHAT_ID` | Target chat/group ID | Yes (if delivering) |

## Common Operations

**Run manually:**
```bash
venv\Scripts\python scripts\daily_brief.py
```

**Run without Telegram delivery:**
```bash
venv\Scripts\python scripts\daily_brief.py --no-deliver
```

**Override date:**
```bash
venv\Scripts\python scripts\daily_brief.py --date 2026-05-21
```

**Important:** `pipeline_daily` view returns today's date only — always uses today by default.

## Dependencies

- **Depends on:** DataOS (`data/data.db`, `pipeline_daily` view), CommandOS (Telegram bot), `context/funnel.md`
- **Used by:** Nothing else — standalone output system

## History

| Date | Change |
|------|--------|
| 2026-05-21 | Initial installation — scripts, funnel definition, end-to-end tested |
