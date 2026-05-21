# System: CommandOS

> Telegram bot that connects your AIOS to your phone — send messages, voice notes, and photos to interact with Claude agents from anywhere.

## Architecture

```
Telegram app (phone)
       |
   aiogram polling
       |
   bot.py (router)
       |
   orchestrator.py
   /             \
General topic   Spawned topics (/new)
(persistent)    (isolated per thread)
       |
   agent_sdk.py
       |
   Claude Agent SDK → Claude Code subprocess
```

## Key Files

| File | Purpose |
|------|---------|
| `apps/command/main.py` | Entry point — boot, config load, start polling |
| `apps/command/bot.py` | Telegram message handlers |
| `apps/command/orchestrator.py` | Session routing, topic management, bot commands |
| `apps/command/agent_sdk.py` | Claude Agent SDK wrapper |
| `apps/command/worker.py` | System prompts and agent task execution |
| `apps/command/session_manager.py` | Persistent session storage (survives restarts) |
| `apps/command/cost_tracker.py` | API usage cost logging (JSONL) |
| `apps/command/config.py` | Config loader from `.env` |
| `scripts/start-command-os.bat` | Windows launcher script |

## How It Works

1. Bot starts, loads config from `.env`, connects to Telegram via long-polling
2. Messages in the **General** topic go to a persistent Claude session
3. `/new` in any topic spawns a fresh isolated Claude agent in that thread
4. Voice notes are transcribed via OpenAI Whisper, then sent to Claude
5. Claude can read workspace files, run code, and send formatted replies back

## Configuration

| Variable | Purpose | Required |
|----------|---------|----------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Yes |
| `TELEGRAM_GROUP_ID` | Group chat ID (negative number) | Yes |
| `ANTHROPIC_API_KEY` | Claude API access | Yes |
| `OPENAI_API_KEY` | Voice note transcription (Whisper) | No |
| `COMMAND_GENERAL_MODEL` | Default model (`sonnet` or `opus`) | No |
| `COMMAND_GENERAL_MAX_BUDGET` | Max $ per message (default: 5.00) | No |

## Common Operations

**Start the bot manually:**
```bat
scripts\start-command-os.bat
```

**Bot commands in Telegram:**
- `/new` — spawn a fresh Sonnet agent in the current topic
- `/new opus` — spawn an Opus agent
- `/reset` — clear the current session
- `/compact` — compress context (saves tokens)
- `/name <title>` — rename the current topic
- `/help` — list all commands

**Auto-start:** `AIOS-CommandOS-Bot.vbs` in Windows Startup folder runs the bot silently on every login.

**Logs:** `data/command/costs.jsonl` (API costs), `data/command.log` (general log)

## Dependencies

- **Depends on:** ContextOS (CLAUDE.md must exist for agents to prime correctly)
- **Used by:** Direct user interaction via Telegram

## History

| Date | Change |
|------|--------|
| 2026-05-21 | Initial installation — Windows compatibility fixes (fcntl shim, UTF-8 stdout) |
