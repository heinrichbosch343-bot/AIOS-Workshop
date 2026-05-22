# System: ProductivityOS

> GTD-based task and project management system — capture, process, and review every commitment. No API keys required.

## Architecture

```
gtd/inbox.md --> /process --> gtd/projects.md
                           --> gtd/next-actions.md (@me @claude @calls @team @errands @think @record)
                           --> gtd/waiting-for.md
                           --> gtd/someday-maybe.md
                           --> scripts/refresh_dashboard.py
                                         |
                                   gtd/dashboard.md

/review --> all gtd/ files --> weekly full review --> dashboard rebuild
```

## Key Files

| File | Purpose |
|------|---------|
| `gtd/inbox.md` | Raw capture — everything lands here first |
| `gtd/projects.md` | Master project index (AI Agency, Client Delivery, Sales & Outreach, Personal) |
| `gtd/next-actions.md` | Next actions by context tag |
| `gtd/waiting-for.md` | Delegated items and expectations |
| `gtd/someday-maybe.md` | Back-burner ideas by category |
| `gtd/areas.md` | Areas of responsibility with health notes |
| `gtd/dashboard.md` | Operational hub — counts, flagged, recent completions |
| `gtd/review-checklist.md` | Decision tree, trigger lists, review phases |
| `.claude/commands/process.md` | `/process` command definition |
| `.claude/commands/review.md` | `/review` command definition |
| `scripts/refresh_dashboard.py` | Recomputes dashboard counts from source files |
| `scripts/inbox_writer.py` | Safe inbox appends (Windows-compatible file locking) |
| `reference/gtd-methodology.md` | Full GTD reference guide |

## How It Works

1. **Capture:** Dump anything into `gtd/inbox.md` — tasks, ideas, commitments, reminders
2. **Process:** Run `/process` — Claude walks through each item one-by-one using the GTD decision tree, routes to the correct file, empties inbox to zero
3. **Act:** Work from `gtd/next-actions.md` organized by context — pick based on what you have available right now
4. **Review:** Run `/review` weekly — Claude guides you through GET CLEAR → GET CURRENT → GET CREATIVE → dashboard rebuild

## Configuration

No API keys required. Pure markdown + Python.

| Variable | Purpose | Required |
|----------|---------|----------|
| None | — | — |

## Common Operations

**Process inbox:**
```
/process
```

**Weekly review:**
```
/review
```

**Refresh dashboard manually:**
```bash
venv\Scripts\python scripts\refresh_dashboard.py
```

**Capture to inbox from command line:**
```bash
venv\Scripts\python scripts\inbox_writer.py "Call Lourens to follow up on proposal"
```

## Business Areas (Heinrich's Setup)

| Area | Purpose |
|------|---------|
| AI Agency | Agency operations, systems, AIOS builds |
| Client Delivery | Active client projects, delivery, satisfaction |
| Sales & Outreach | Pipeline, Instantly AI, proposals, referrals |
| Personal | Everything outside the business |

## Context Tags

| Tag | Use For |
|-----|---------|
| @me | Decisions, approvals, creative work only you can do |
| @claude | Work to do in Claude Code sessions |
| @calls | Phone/video calls to make |
| @team | Items to discuss with specific people |
| @errands | Physical, in-person tasks |
| @think | Brainstorming, reflection, strategy |
| @record | Things to capture, document, or write up |

## Dependencies

- **Depends on:** Nothing — fully standalone, no external services
- **Used by:** Nothing else — standalone productivity system

## History

| Date | Change |
|------|--------|
| 2026-05-21 | Initial installation — Custom setup with AI Agency areas and default context tags |
