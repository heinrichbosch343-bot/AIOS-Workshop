# Explore: CRM Pipeline System

**Created:** 2026-06-18
**Status:** Built
**Origin:** Internal CRM that auto-updates from email campaigns and is controllable via Telegram

---

## Vision

A lightweight, Telegram-first CRM pipeline that tracks every lead from first interested reply through to closed deal. No external CRM tool needed — everything lives in Supabase, is controllable from Telegram, and feeds into the daily brief automatically.

## Problem Statement

Heinrich is about to launch cold email campaigns via Instantly AI. When prospects reply with interest, he needs to track them through a sales pipeline — from first response to discovery call to proposal to closed deal. Currently the `clients` table only has 4 stages (lead/pipeline/anchor/inactive) with no meeting tracking, no follow-up nudges, and no Telegram pipeline commands.

## Proposed Solution

### What It Does

A 7-stage sales pipeline integrated into the existing AIOS:

```
INTERESTED → NO_REPLY → MEETING_BOOKED → FOLLOW_UP_MEETING → PROPOSAL → WON | LOST
```

- **Telegram commands** to view, add, move, and annotate leads
- **Free-text chat** also understands pipeline operations via the agent
- **Daily brief** includes pipeline status and nudge reminders
- **Scheduled nudges** at 08:30 SAST remind Heinrich when leads go stale

### How It Works

1. Heinrich adds a lead: `/addlead "John Smith" john@acme.com`
2. Bot confirms and starts the nudge timer (2 days for interested stage)
3. After 2 days, Telegram notification: "Book a meeting with John Smith?"
4. Heinrich moves them: `/move John meeting_booked`
5. Pipeline summary available anytime: `/pipeline`
6. Free-text also works: "move John to proposal, sent it today"
7. Morning brief includes: "Pipeline: 4 active deals. John's proposal is 3 days old."

### What It Produces

- Pipeline summaries grouped by stage
- Nudge reminders for stale leads
- Timestamped notes on each lead
- Full audit trail via business_events table
- Pipeline data in the daily brief

## Scope

### What Was Built

| Component | File | What Changed |
|-----------|------|-------------|
| DB Migration | `db/migrations/007_crm_pipeline.sql` | New columns (email, lead_source, meeting_date, proposal_sent_at, lost_reason, stage_changed_at), new indexes, data migration |
| Pipeline Service | `services/pipeline.py` | NEW — lead management, stage moves, notes, nudges, formatted output |
| Context Store | `services/context_store.py` | Updated PIPELINE_STAGES, _stage_fields, pipeline_summary |
| Telegram Bot | `bot/command_os.py` | 6 new commands: /pipeline, /addlead, /move, /note, /lead, /removelead |
| Agent Brain | `services/agent.py` | Updated tool enums, added get_pipeline_summary + add_pipeline_note tools, updated behaviour prompt |
| Daily Brief | `services/daily_brief.py` | Pipeline stats, nudge counts, detailed pipeline text for Claude |
| Scheduler | `services/scheduler.py` | Pipeline nudge check at 08:30 SAST |
| Seed Script | `scripts/seed_context.py` | Migrated stages (anchor→won, lead→interested) |

### Future: Instantly AI Integration

When Heinrich sets up Instantly campaigns:
1. Subscribe to `lead_interested` webhook from Instantly
2. Add a `/api/webhook/instantly` endpoint to the backend
3. Auto-create leads when interested replies come in
4. Notify on Telegram for confirmation

This is a bolt-on addition — the CRM works independently now.

### Out of Scope

- Instantly webhook integration (deferred until campaigns are live)
- Pipeline analytics/reporting dashboard
- Automated email sending from CRM
- Multi-user access / team features

## Technical Considerations

- **No new dependencies** — uses existing Supabase, Telegram, APScheduler stack
- **Migration required** — run `007_crm_pipeline.sql` in Supabase SQL editor
- **Seed script updated** — re-run `seed_context.py` to migrate existing clients to new stages
- **Backwards compatible** — old API endpoints still work, agent tools updated in place

## Connections

- **Supabase `clients` table** — single source of truth (extended with new columns)
- **Supabase `business_events`** — every stage change logged
- **Telegram bot** — 6 new commands registered
- **Agent brain** — free-text chat understands all CRM operations
- **Daily brief** — pipeline summary + nudges included
- **Scheduler** — daily nudge check at 08:30 SAST

## Deployment Steps

1. Run `007_crm_pipeline.sql` in Supabase SQL editor
2. Deploy updated backend to Railway
3. Re-run `seed_context.py` to update existing client stages
4. Test: `/pipeline`, `/addlead Test test@test.com`, `/move Test meeting_booked`

## Discovery Notes

- Heinrich wants Telegram-first control — commands + free-text both work
- The system should suggest stage changes but ALWAYS ask permission before moving
- Nudges are suggestions, not auto-moves
- Instantly AI webhook integration deferred — will bolt on when campaigns go live
- Pipeline stages designed around Heinrich's actual sales process: cold campaign → interested reply → discovery call → follow-up → proposal → close
