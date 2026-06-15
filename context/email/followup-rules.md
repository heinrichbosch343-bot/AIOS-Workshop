# Email Follow-up Rules

Active rules for the auto-follow-up engine (`services/followup.py`).

---

## Current Mode: WARMUP (draft-only)

The engine saves follow-ups as Gmail drafts for Heinrich to review. Flip to live sending only after reviewing the drafts and confirming they're good.

## Rules

| Setting | Default | Env Var |
|---------|---------|---------|
| Enabled | Off | `FOLLOWUP_ENABLED=true` |
| Allowlist | Empty (no one) | `FOLLOWUP_ALLOWLIST=user@example.com,@domain.com` |
| Delay before follow-up | 3 days | `FOLLOWUP_DELAY_DAYS=3` |
| Daily send/draft cap | 5 | `FOLLOWUP_DAILY_CAP=5` |
| Kill switch | Off | `FOLLOWUP_KILL_SWITCH=true` |
| Warmup (draft-only) | On | `FOLLOWUP_WARMUP=true` |
| Max attempts per thread | 3 | `FOLLOWUP_MAX_ATTEMPTS=3` |

## How It Works

1. Scheduler runs at 08:00, 11:00, and 14:00 SAST
2. Scans sent emails from the last ~10 days for threads with no reply past the delay
3. For each eligible thread:
   - Recipient must be on the allowlist (exact email or @domain)
   - Under the daily cap
   - Kill switch not engaged
   - Not already at max attempts
4. Claude drafts a short, warm follow-up in Heinrich's voice
5. In warmup mode: saved as Gmail draft. In live mode: actually sent.
6. Heinrich gets a Telegram notification listing what was drafted/sent

## Allowlist Format

Comma-separated in `.env`. Supports:
- Full addresses: `john@example.com`
- Domain wildcards: `@example.com` (matches anyone at that domain)

## Telegram Commands

- `/followups` — show pending threads, today's count, engine status
- `/killswitch on` — immediately pause all follow-ups
- `/killswitch off` — resume follow-ups

## Safety Guarantees

- **Warmup default**: Nothing sends until Heinrich switches `FOLLOWUP_WARMUP=false`
- **Allowlist**: Only pre-approved contacts receive follow-ups
- **Daily cap**: Hard limit on how many follow-ups per day
- **Kill switch**: Instant stop, no questions asked (via Telegram or env var)
- **Max attempts**: Each thread gets at most 3 follow-ups before auto-stopping
