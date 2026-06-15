# Plan: BoschAI Own-Agency System — Fork, LinkedIn Engine, Auto Follow-ups, Pipeline

**Created:** 2026-06-13
**Status:** Draft
**Request:** Fork the proven Connie backend into a BoschAI backend, then layer a LinkedIn growth engine, an auto-sending email follow-up bot, and pipeline management. Local-first now, Railway later.

---

## Overview

### What This Plan Accomplishes

This builds Heinrich's own always-on AI operator by forking the working Connie backend (`apps/connie-backend` from the Osun Consulting workspace) into a `boschai-backend` running locally in this workspace. On that foundation it adds a LinkedIn growth engine first, then upgrades the existing email tooling into a rule-bound auto-follow-up bot, then sharpens the pipeline tracking that the fork already ships with.

### Why This Matters

This is the BoschAI AIOS itself, the reference build Heinrich uses to run his agency and to sell the same system to clients. It moves two of the three KPIs directly: Away-From-Desk Autonomy (the bot watches the inbox and follows up without him) and Task Automation % (LinkedIn drafting, follow-ups, and pipeline nudges stop being manual). Forking proven code instead of starting cold is Borrow Before You Build in action.

---

## Current State

### Relevant Existing Structure

**This workspace (`c:\Users\gamin\BoschAI\BoschAI\aios-starter-kit`):**
- `apps/command/` — a lighter "Command OS" Telegram bot (agent_sdk.py, orchestrator.py, worker.py, session_manager.py). Currently autostarts via `scripts/start-command-os.bat` and `scripts/AIOS-CommandOS-Bot.vbs`.
- `scripts/` — loose automation: `daily_brief.py`, `collect.py`, `collect_gmail.py`, `collect_fx_rates.py`, `generate_metrics.py`, `dashboard.py`, `refresh_dashboard.py`, `inbox_writer.py`, plus `intel/` collectors.
- `context/` — `business-info.md`, `personal-info.md`, `strategy.md`, `current-data.md`, `funnel.md`, `clients/`, `group/key-metrics.md`.
- `credentials/boschai-5cc0962ede62.json` — a Google service-account / OAuth credential already present.
- `.env` (configured, secret), `.venv/`, `docs/`, `outputs/daily-brief/`, `module-installs/` (10 AIOS modules), `.claude/skills/` (writing-style and frontend-design now installed).
- `plans/` exists and is empty.

**Fork source (`c:\Users\gamin\BoschAI\Osun Consulting\aios-starter-kit\apps\connie-backend`):**
- FastAPI app (`main.py`) with 11 routers, per-IP rate limiting, `/health`.
- `services/` (24+ modules): `agent.py` (24 tools), `email.py`, `autodraft.py`, `daily_brief.py`, `signoff.py`, `signoff_watcher.py`, `scheduler.py`, `knowledge.py`, `indexer.py`, `embeddings.py`, `drive.py`, `context_store.py`, `notify.py`, `calendar.py`, plus the report pipeline (`compiler.py`, `scaffolder.py`, `design_brief.py`) and research (`research.py`, `deep_research.py`, `academic.py`).
- `bot/command_os.py` — 8 slash commands + free-text agent routing, chat allowlist.
- `core/prime.py` (system prompt builder), `core/writing_style.py`, `prompts/writing_style.md`.
- `db/` — Supabase client + migrations (`001_knowledge_pool.sql`, `002_scoped_search.sql`).
- `scripts/seed_context.py` — seeds context facts + clients into Supabase.
- `railway.toml`, `requirements.txt`.

### Gaps or Problems Being Addressed

- No BoschAI-branded backend exists here. The only hub running is the lighter Command OS bot, which lacks the email/CRM/brief/sign-off engine Heinrich wants.
- No LinkedIn capability exists anywhere (confirmed: `grep -ri linkedin` on the Connie backend returns nothing). It is net-new.
- The Connie email tooling drafts but never auto-sends. Heinrich wants rule-bound auto follow-ups with guardrails.
- The Connie backend is hardcoded to Connie / Osun Consulting in ~20 places (system prompt, seed context, voice, research prompts, timezone, User-Agent). All must be rebranded.
- Two bots cannot poll the same Telegram token at once, so the running Command OS bot must be reconciled with the new fork.

---

## Proposed Changes

### Summary of Changes

- Fork `connie-backend` into `apps/boschai-backend` in this workspace and rebrand every Connie/Osun coupling to Heinrich / BoschAI.
- Stand up a separate BoschAI Supabase project (or isolated schema) and run the seed script with Heinrich's real context.
- Point the fork at Heinrich's Gmail, a new BoschAI Telegram bot token, and the existing Google credential.
- Retire the standalone Command OS bot and the loose `scripts/` collectors that the fork supersedes, to avoid token clashes and double daily briefs.
- Build a LinkedIn growth engine: a drafting service, a voice profile, new agent tools and Telegram commands, and a content-ops file set (pillars, idea backlog, accounts-to-engage, cadence).
- Extend email tooling into an auto-sending follow-up engine gated by an allowlist, daily cap, kill switch, and a draft-only warmup phase.
- Add a stale-deal watcher to the pipeline that the fork already tracks.
- Keep CLAUDE.md, HISTORY.md, and docs/ current as the workspace changes.

### New Files to Create

| File Path | Purpose |
| --------- | ------- |
| `apps/boschai-backend/**` | The forked, rebranded backend (full directory copy of connie-backend, then edited) |
| `apps/boschai-backend/services/linkedin.py` | LinkedIn drafting service: posts, replies, comments in Heinrich's voice; idea generation |
| `apps/boschai-backend/services/followup.py` | Auto-send email follow-up engine with allowlist, cap, kill switch, warmup |
| `apps/boschai-backend/prompts/linkedin_voice.md` | Heinrich's LinkedIn voice profile, built from his past posts |
| `apps/boschai-backend/db/migrations/003_followups.sql` | Tracks follow-up state (thread id, last_sent_at, attempts, status) |
| `apps/boschai-backend/db/migrations/004_linkedin.sql` | Optional: stores drafted posts / idea backlog if not kept as flat files |
| `context/linkedin/content-pillars.md` | Heinrich's LinkedIn pillars + target audience |
| `context/linkedin/idea-backlog.md` | Running list of post ideas |
| `context/linkedin/accounts-to-engage.md` | People/accounts to engage with for growth |
| `context/linkedin/cadence.md` | Weekly posting cadence + simple content calendar |
| `context/email/followup-rules.md` | Human-readable record of the follow-up rules (allowlist, timings, caps) |
| `docs/boschai-backend.md` | Doc entry describing the new hub |
| `docs/linkedin-engine.md` | Doc entry for the LinkedIn workflow |
| `plans/2026-06-13-boschai-system-build.md` | This plan |

### Files to Modify

| File Path | Changes |
| --------- | ------- |
| `apps/boschai-backend/core/prime.py` | Replace "Connie's AI assistant / Osun Consulting Group" prompt prefix with Heinrich / BoschAI |
| `apps/boschai-backend/services/agent.py` | Rebrand docstrings/BEHAVIOUR block; add LinkedIn tools (`draft_linkedin_post`, `draft_linkedin_reply`, `suggest_linkedin_ideas`); add follow-up controls if surfaced to agent |
| `apps/boschai-backend/services/autodraft.py` | Rebrand voice ("Heinrich Bosch / BoschAI"); feed into followup.py |
| `apps/boschai-backend/services/scheduler.py` | Rebrand; set timezone; add follow-up job and stale-deal watcher; keep jobs gated to hosted/enabled env |
| `apps/boschai-backend/services/daily_brief.py` | Rebrand recipient and voice |
| `apps/boschai-backend/services/research.py`, `deep_research.py`, `academic.py` | Rebrand business context and the hardcoded `research@osunconsulting.co.za` User-Agent |
| `apps/boschai-backend/bot/command_os.py` | Rebrand `/start` greeting; add LinkedIn commands (`/post`, `/reply`, `/ideas`); add `/followups` and a `/killswitch` control |
| `apps/boschai-backend/scripts/seed_context.py` | Replace Connie bio/business/strategy/key_metric with Heinrich's BoschAI facts |
| `apps/boschai-backend/config.py` | Add follow-up env vars (enabled, allowlist, cap, kill switch, warmup) and LinkedIn settings |
| `apps/boschai-backend/.env.example` | Document all new and existing env keys for BoschAI |
| `apps/boschai-backend/railway.toml` | Rename service to boschai-backend for the later migration |
| `scripts/start-command-os.bat`, `scripts/AIOS-CommandOS-Bot.vbs` | Repoint to launch boschai-backend, or retire once cutover is verified |
| `CLAUDE.md` | Document the boschai-backend hub, new commands, workspace structure, and the LinkedIn/follow-up capabilities |
| `HISTORY.md` | Log the fork and each phase |
| `docs/_index.md` | Link the two new doc entries |

### Files to Delete (if any)

- None deleted outright during the build. After cutover is verified (Phase 5), retire the superseded standalone scripts (`scripts/daily_brief.py`, `scripts/collect_gmail.py`, the Command OS autostart) by disabling their triggers rather than deleting, so there is a rollback path. Final removal is a follow-up once the fork is trusted.

---

## Design Decisions

### Key Decisions Made

1. **Fork connie-backend, not the existing Command OS bot.** Per Heinrich's decision and Borrow Before You Build. The Connie backend already delivers email read/draft/send, CRM/clients, daily brief, sign-off watcher, and Knowledge Pool. The Command OS bot is lighter and would need far more new code to match.
2. **Copy into `apps/boschai-backend/` rather than rename in place.** Keeps the Osun workspace untouched and gives a clean rollback. The name signals ownership and avoids confusion with `apps/command/`.
3. **Separate BoschAI Supabase project (recommended).** Clean data isolation from Connie's client data. Same schema and migrations, fresh rows. Avoids any chance of cross-contaminating client data, which matters for an agency.
4. **New BoschAI Telegram bot via @BotFather.** Two bots cannot share one token, and the Command OS / Connie bots already hold tokens. A dedicated BoschAI bot also keeps Heinrich's personal hub separate.
5. **LinkedIn is assisted drafting, not auto-posting.** No official API for personal-profile posting or replies, and automation tools risk account restrictions. The loop is: Claude drafts in Heinrich's voice via Telegram, he copies to LinkedIn. Reuses the already-vendored writing-style rules plus a new `linkedin_voice.md`.
6. **Email follow-ups auto-send, but behind hard rails.** Heinrich chose auto-send within rules. The rails are non-negotiable: recipient allowlist, daily send cap, global kill switch, and a draft-only warmup week so he watches the rules behave before live send. `autodraft.py` already proves the drafting half; `followup.py` adds the send decision.
7. **Pipeline is mostly extend, not build.** The fork ships `clients`, `set_client_pipeline_stage`, `list_clients`, `projects`, and `business_events`. The net-new part is a stale-deal watcher (nudge when a deal has not moved in N days) and a `/pipeline` view.
8. **Local-first, Railway-ready.** Keep the existing env gating (`DISABLE_TELEGRAM_BOT`, scheduler `BOT_ENABLED`) so the same code runs locally now and on Railway later with no rewrite. "24/7" is honest only after the Railway move.

### Alternatives Considered

- **Build fresh from the AIOS modules in `module-installs/`.** Rejected: far more work to reach parity with the fork, and Heinrich already chose the fork.
- **Reuse Connie's Supabase with extra tables/columns scoped by owner.** Rejected as default: cheaper but risks mixing agency-internal data with client data. Offered as a fallback if Heinrich wants to avoid a second Supabase project.
- **Pursue LinkedIn automation tools (browser bots, unofficial APIs).** Rejected for now: account-restriction risk outweighs the time saved. Revisit later if he accepts the risk.
- **Rename `connie_context` table to a generic name.** Deferred: a rename adds migration risk for little gain. Keep the table name, change only the seeded values. Revisit if it bothers him.

### Open Questions (need Heinrich's input before or during implementation)

1. **Supabase:** new dedicated BoschAI project (recommended), or reuse Connie's with isolation? Provisioning a new project needs his login.
2. **Telegram:** confirm I should create a new BoschAI bot via @BotFather, and confirm his Telegram chat ID for the allowlist (the `/myid` command discovers it).
3. **Gmail:** confirm `heinrichbosch343@gmail.com` is the inbox the bot reads and sends from, and whether `credentials/boschai-5cc0962ede62.json` already grants Gmail scope or needs re-consent.
4. **LinkedIn voice:** 5 to 10 of his best past posts, plus his content pillars and target audience (AI-agency owners? business owners weighing an AIOS?).
5. **Follow-up rules:** initial allowlist (who can be auto-followed-up), the no-reply delay (e.g. 3 days), the daily send cap, and how long the draft-only warmup runs.
6. **Command OS:** retire the existing Command OS bot and loose daily-brief/collector scripts as part of cutover, or keep them running in parallel for a transition window?

---

## Step-by-Step Tasks

### Step 0: Provisioning and inputs (gate before code)

Collect the answers to the six open questions. Create the BoschAI Telegram bot, confirm Gmail access, and stand up the Supabase project. Gather LinkedIn voice samples and starting follow-up rules.

**Actions:**
- Create a new Telegram bot with @BotFather; capture the token.
- Run `/myid` against the new bot to capture Heinrich's chat ID.
- Create the BoschAI Supabase project; capture URL + service-role key.
- Confirm the Google credential's scope covers Gmail read/send and Drive; re-consent if needed.
- Collect 5 to 10 past LinkedIn posts, content pillars, target audience, and starting follow-up rules.

**Files affected:**
- `.env` (Heinrich populates secrets; never committed)
- `context/linkedin/*`, `context/email/followup-rules.md` (drafted from his inputs)

---

### Step 1: Fork and rebrand the backend (foundation)

Copy the Connie backend into this workspace and strip every Connie/Osun coupling.

**Actions:**
- Copy `Osun Consulting/aios-starter-kit/apps/connie-backend/` to `apps/boschai-backend/` (exclude `__pycache__/`, `.venv/`).
- Rebrand the hardcoded couplings identified in research:
  - `core/prime.py`: system-prompt prefix to "Heinrich's AI assistant, the brain for BoschAI."
  - `services/agent.py`: docstring + BEHAVIOUR block; "Connie" to "Heinrich", "Osun Consulting" to "BoschAI."
  - `services/autodraft.py`: triage + voice instructions, sign as Heinrich.
  - `services/daily_brief.py`: recipient + voice.
  - `services/research.py`, `services/deep_research.py`: business context and "Angle for Osun" framing to BoschAI's offer (custom AIOS builds).
  - `services/academic.py`: User-Agent email to Heinrich's address.
  - `services/scheduler.py`: timezone (confirm SAST `Africa/Johannesburg` vs his preference); brief/auto-draft times.
  - `bot/command_os.py`: `/start` greeting to Heinrich.
  - `scripts/seed_context.py`: bio/business/writing_style/report_format/strategy/key_metric rewritten for BoschAI (solo AI agency, $50k-in-3-months goal, custom AIOS delivery).
- Point `config.py` / `.env` at the BoschAI Supabase, Gmail, Telegram token, and credential path.
- Create a `.venv` for the backend (or reuse the workspace `.venv`) and install `requirements.txt`.

**Files affected:**
- `apps/boschai-backend/**` (copy + the edits above)

---

### Step 2: Database setup and context seed

Apply migrations to the BoschAI Supabase and seed Heinrich's real context.

**Actions:**
- Run `db/migrations/001_knowledge_pool.sql` and `002_scoped_search.sql` against the BoschAI Supabase.
- Run `scripts/seed_context.py` to load BoschAI context facts and any starting clients (e.g. Connie as a client record, Lourens as a lead).
- Smoke-test the Supabase client connection.

**Files affected:**
- BoschAI Supabase (schema + rows), no local files changed beyond the seed script edits from Step 1.

---

### Step 3: Boot the fork locally and verify parity

Get the rebranded backend running on Heinrich's machine before adding anything new.

**Actions:**
- Start the FastAPI app locally with `DISABLE_TELEGRAM_BOT=0` and the new bot token.
- Verify `/health` returns ok.
- From Telegram: confirm `/start` greets Heinrich, free-text reaches the agent, `list_recent_emails` returns his inbox, `list_clients` returns seeded clients.
- Confirm the scheduler registers jobs without firing errors (daily brief, sign-off watcher).

**Files affected:**
- None (runtime verification). Log results in `HISTORY.md`.

---

### Step 4: LinkedIn growth engine (first new capability)

Add the drafting service, voice profile, tools, commands, and content-ops files.

**Actions:**
- Write `prompts/linkedin_voice.md` from Heinrich's past posts: tone, sentence rhythm, opening styles, topics, what he never says. Reference the installed writing-style rules.
- Create `services/linkedin.py` with functions: `draft_post(topic_or_note)`, `draft_reply(context_text)`, `draft_comment(post_text)`, `suggest_ideas(n, pillar=None)`. Each loads `linkedin_voice.md` + writing-style and returns plain text ready to paste.
- Add agent tools in `services/agent.py`: `draft_linkedin_post`, `draft_linkedin_reply`, `suggest_linkedin_ideas`, wired to `services/linkedin.py`.
- Add Telegram commands in `bot/command_os.py`: `/post <topic>`, `/reply <pasted text>`, `/ideas [pillar]`. Keep free-text working too ("draft a post about X").
- Create the content-ops files: `context/linkedin/content-pillars.md`, `idea-backlog.md`, `accounts-to-engage.md`, `cadence.md`. The agent reads and appends to these (e.g. logs new ideas to the backlog).
- Optional `db/migrations/004_linkedin.sql` only if he wants drafted posts stored in Supabase rather than flat files. Default to flat files first.

**Files affected:**
- `apps/boschai-backend/services/linkedin.py` (new)
- `apps/boschai-backend/prompts/linkedin_voice.md` (new)
- `apps/boschai-backend/services/agent.py`, `bot/command_os.py` (modify)
- `context/linkedin/*` (new)

---

### Step 5: Email follow-up auto-send with guardrails

Turn the existing draft-only tooling into a rule-bound auto-follow-up engine.

**Actions:**
- Add `db/migrations/003_followups.sql`: a `followups` table tracking thread id, contact, last_sent_at, attempt_count, status (pending/sent/replied/stopped).
- Create `services/followup.py`: scans for sent emails with no reply after the configured delay, drafts a follow-up via existing email/autodraft logic, then applies the gate:
  - recipient must be on the allowlist
  - under the daily send cap
  - kill switch not engaged
  - if in warmup mode, save as draft instead of send
- Add config/env: `FOLLOWUP_ENABLED`, `FOLLOWUP_ALLOWLIST`, `FOLLOWUP_DELAY_DAYS`, `FOLLOWUP_DAILY_CAP`, `FOLLOWUP_KILL_SWITCH`, `FOLLOWUP_WARMUP` (draft-only).
- Add a scheduler job (e.g. hourly during work hours) calling `followup.run()`.
- Add Telegram controls: `/followups` (list pending + today's sent count), `/killswitch on|off`.
- Record the active rules in `context/email/followup-rules.md`.
- Default to warmup (draft-only) for the first week. Flip to live send only after Heinrich reviews the drafts.

**Files affected:**
- `apps/boschai-backend/services/followup.py` (new), `db/migrations/003_followups.sql` (new)
- `apps/boschai-backend/services/scheduler.py`, `config.py`, `bot/command_os.py` (modify)
- `context/email/followup-rules.md` (new)

---

### Step 6: Pipeline management (extend the fork)

Sharpen the CRM the fork already provides.

**Actions:**
- Add a stale-deal watcher to the scheduler: if a client/deal has not changed stage in N days, notify Telegram with a suggested next step.
- Add a `/pipeline` Telegram command that prints the current stages and recent changes (reuses `list_clients` + `business_events`).
- Confirm `add_or_update_client`, `set_client_pipeline_stage`, and `log_business_event` behave against the BoschAI Supabase.

**Files affected:**
- `apps/boschai-backend/services/scheduler.py`, `bot/command_os.py` (modify)

---

### Step 7: Cutover and consolidation

Make the fork the single hub and stop the overlapping bot/scripts.

**Actions:**
- Repoint `scripts/start-command-os.bat` and `scripts/AIOS-CommandOS-Bot.vbs` to launch `apps/boschai-backend`, or create a `scripts/start-boschai.bat`.
- Disable the standalone `scripts/daily_brief.py` and Gmail collectors that the fork now covers (comment out the trigger / scheduled task; do not delete yet).
- Confirm only one bot polls the BoschAI Telegram token.

**Files affected:**
- `scripts/start-command-os.bat`, `scripts/AIOS-CommandOS-Bot.vbs` (modify), new `scripts/start-boschai.bat` (optional)

---

### Step 8: Documentation and history

Keep the workspace's own context current.

**Actions:**
- Update `CLAUDE.md`: document `apps/boschai-backend` as the hub, list the new Telegram commands and capabilities, update the workspace structure table.
- Add `docs/boschai-backend.md` and `docs/linkedin-engine.md`; link both in `docs/_index.md`.
- Log the fork and each phase in `HISTORY.md`.

**Files affected:**
- `CLAUDE.md`, `HISTORY.md`, `docs/_index.md`, `docs/boschai-backend.md`, `docs/linkedin-engine.md`

---

## Connections & Dependencies

### Files That Reference This Area

- `scripts/start-command-os.bat` and `AIOS-CommandOS-Bot.vbs` launch the current bot; both must change so the new hub starts and the old one stops.
- `scripts/daily_brief.py` and `scripts/collect_gmail.py` overlap with the fork's `daily_brief.py` and `email.py` services; they get retired at cutover.
- `context/` files feed the system prompt via the seed script; the LinkedIn and email-rule files become live inputs to the agent.

### Updates Needed for Consistency

- `CLAUDE.md` Commands and Workspace Structure sections.
- `docs/_index.md` plus the two new doc pages.
- `.env.example` in the backend to mirror every new key.

### Impact on Existing Workflows

- The daily brief moves from the loose `scripts/daily_brief.py` to the fork's scheduler. Expect one brief, not two, after cutover.
- The Telegram interface gains LinkedIn, follow-up, and pipeline commands on top of the existing set.
- Data writes now target the BoschAI Supabase, not any Connie project.

---

## Validation Checklist

- [ ] `apps/boschai-backend` boots locally; `/health` returns ok.
- [ ] No "Connie" or "Osun" strings remain in prompts, greetings, voice, research, or User-Agent (`grep -ri "connie\|osun"` on the backend comes back clean except where intentional, e.g. Connie as a client record).
- [ ] BoschAI Supabase has the schema applied and seeded context; `list_clients` works from Telegram.
- [ ] Only one bot polls the BoschAI Telegram token.
- [ ] `/post`, `/reply`, `/ideas` return drafts in Heinrich's voice with no AI tells (writing-style passes).
- [ ] Follow-up engine respects allowlist, cap, kill switch, and warmup (verified with a test thread; warmup produces a draft, not a send).
- [ ] `/followups` and `/killswitch` behave; stale-deal watcher fires a test notification.
- [ ] One daily brief arrives (no duplicate from the retired script).
- [ ] CLAUDE.md, HISTORY.md, and docs updated.

## Success Criteria

The implementation is complete when:

1. A BoschAI-branded backend runs locally and answers on its own Telegram bot, reading Heinrich's inbox and his seeded pipeline.
2. Heinrich can ask for a LinkedIn post or reply and get a paste-ready draft in his voice, with ideas logged to the backlog.
3. The follow-up engine auto-sends within his rules after the warmup, and a wrong send is prevented by allowlist + cap + kill switch.
4. The pipeline nudges him on stale deals, and the standalone Command OS bot and duplicate scripts are retired.
5. The same code is ready to deploy to Railway with only env changes when credits are available.

---

## Notes

- **Railway migration (later):** when credits land, deploy `apps/boschai-backend` using its `railway.toml`, set the env vars, and flip `DISABLE_TELEGRAM_BOT=0` on the host so the bot and scheduler run 24/7. The local instance then shuts down to avoid double-polling. This is out of scope for this plan but the code stays migration-ready throughout.
- **Knowledge Pool is optional now.** The fork ships Drive indexing + semantic search (Voyage embeddings). It is not required for LinkedIn, follow-ups, or pipeline, so it can stay dormant (no `VOYAGE_API_KEY`) until Heinrich wants document Q&A for his own business.
- **Report pipeline (compile/scaffold/design brief) carries over but is Connie-shaped.** Leave it intact and dormant; repurpose later if BoschAI ever produces long-form deliverables.
- **Email campaigns (Instantly AI + Apollo)** start after Connie's payment and are a separate outbound system from this inbox follow-up bot. Worth integrating later (e.g. pipeline picks up Instantly replies), noted for a future plan.
- **Voice quality depends on real samples.** The LinkedIn engine is only as good as the past posts Heinrich provides; thin samples mean generic drafts.
