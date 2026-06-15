# Email Auto-Reply & Follow-up Rules

Two separate systems, both in `services/`.

---

## System 1: Campaign Auto-Responder (`services/campaign_responder.py`)

Monitors 5-10 outreach email accounts. When a prospect replies to a campaign email, it classifies the reply and auto-responds within minutes.

### Config

| Setting | Default | Env Var |
|---------|---------|---------|
| Enabled | Off | `CAMPAIGN_ENABLED=true` |
| Accounts | None | `CAMPAIGN_ACCOUNTS=[{"email":"...","password":"...","imap_host":"...","smtp_host":"..."}]` |
| Reply delay | 10 min | `CAMPAIGN_REPLY_DELAY_MINUTES=10` |
| Daily cap per account | 50 | `CAMPAIGN_DAILY_CAP_PER_ACCOUNT=50` |
| Kill switch | Off | `CAMPAIGN_KILL_SWITCH=true` |

### Account JSON Format

```json
[
  {
    "email": "heinrich@boschai.com",
    "password": "app-password-here",
    "imap_host": "imap.provider.com",
    "imap_port": 993,
    "smtp_host": "smtp.provider.com",
    "smtp_port": 465
  }
]
```

### How It Works

1. Polls each campaign inbox every 10 minutes via IMAP
2. Classifies each reply: interested / not_interested / unsubscribe / out_of_office / bounce
3. Interested replies get an auto-response in Heinrich's voice via SMTP
4. Everything else is flagged and skipped
5. All actions logged to `campaign_replies` table
6. Telegram notification with summary

### Telegram Commands

- `/campaigns` — show status, account counts, today's activity
- `/campaignkill on|off` — emergency stop for campaign replies

---

## System 2: Personal Nudge Drafter (`services/followup.py`)

For Heinrich's personal Gmail only. Creates silent drafts for threads where contacts haven't replied.

### Config

| Setting | Default | Env Var |
|---------|---------|---------|
| Enabled | Off | `FOLLOWUP_ENABLED=true` |
| Allowlist | Empty | `FOLLOWUP_ALLOWLIST=user@example.com,@domain.com` |
| Delay | 3 days | `FOLLOWUP_DELAY_DAYS=3` |
| Daily cap | 5 | `FOLLOWUP_DAILY_CAP=5` |
| Kill switch | Off | `FOLLOWUP_KILL_SWITCH=true` |
| Warmup (draft-only) | On | `FOLLOWUP_WARMUP=true` |
| Max attempts | 3 | `FOLLOWUP_MAX_ATTEMPTS=3` |

### How It Works

1. Runs at 08:00, 11:00, 14:00 SAST
2. Scans sent emails for threads with no reply past the delay
3. Recipient must be on the allowlist
4. Claude drafts a follow-up in Heinrich's voice
5. Saved as Gmail draft (warmup) — Heinrich reviews and sends himself

### Telegram Commands

- `/followups` — show pending threads, today's count
- `/killswitch on|off` — pause/resume personal follow-ups

---

## Migrations Required

- `003_followups.sql` — personal follow-up tracking
- `005_campaign_replies.sql` — campaign reply logging
