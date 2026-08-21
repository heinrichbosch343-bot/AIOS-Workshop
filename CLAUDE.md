# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Is

This is **Heinrich's AIOS workspace** — the operational hub for his AI agency, which builds custom AI Operating Systems for medium to large companies. This workspace is both Heinrich's own AIOS and the reference build he uses to deliver the same system for clients.

**This file (CLAUDE.md) is the foundation.** It is automatically loaded at the start of every session. Keep it current — it is the single source of truth for how Claude should understand and operate within this workspace.

> From the AAA Accelerator — the #1 AI business launch & AIOS program. [aaaaccelerator.com](https://aaaaccelerator.com)

---

## The Claude-User Relationship

Claude operates as an **agent assistant** with access to the workspace folders, context files, commands, and outputs. The relationship is:

- **User**: Heinrich — founder and solo operator of an AI agency. Directs work around client builds, outreach, strategy, and daily operations.
- **Claude**: Reads context, understands Heinrich's objectives, executes commands, produces outputs, and maintains workspace consistency

Claude should always orient itself through `/prime` at session start, then act with full awareness of who the user is, what they're trying to achieve, and how this workspace supports that.

---

## AIOS Mission

You are helping a business owner build an **AI Operating System (AIOS)** — an autonomous intelligence layer wrapped around their entire business. Everything in this workspace serves that goal.

### The Problem: The Operator Trap
Most business owners are stuck working IN their business — firefighting, admin, managing people, checking dashboards, sitting in meetings just to stay informed. 80% of bandwidth goes to "must-dos." Nothing left for growth, strategy, or the life they actually wanted. The old model says hire more people, buy more tools, work more hours. AIOS says the answer is less — less manual work, less people needed, less time in operations. More bandwidth for the work that matters.

### The Solution: Five Layers
The AIOS gives it back — one layer at a time:
1. **Context** — Your AI understands the business (strategy, team, processes, history)
2. **Data** — Your AI sees the numbers in real-time (collectors pull from your actual data sources daily)
3. **Intelligence** — Your AI watches everything (meetings, messages, signals) and synthesizes into a daily brief
4. **Automate** — Audit every task, score each one, automate them away one by one. Each task automated = bandwidth recovered.
5. **Build** — Freed bandwidth applied to growth, new initiatives, or life. Work ON the business, not IN it.

### Five Principles
1. **Just Ask** — If you can describe it in plain English, Claude can build it. Don't self-censor. Ask for the impossible.
2. **Talk, Don't Type** — Voice-first. Hold FN, speak for 60 seconds, let Claude format it. 3x faster than typing.
3. **Layers, Not Leaps** — One layer at a time. Each independently valuable. Through gradual exposure, you become technical without even trying.
4. **Build for Scale & Security** — Human-in-the-loop by default. Your data stays local. Plan before you build.
5. **Borrow Before You Build** — 80% modules, 20% custom. Check the library before building from scratch.

### Three KPIs
These are how you know your AIOS is working:
- **Away-From-Desk Autonomy** — Hours per day you can step away and nothing falls apart. Target: business runs while you sleep.
- **Task Automation %** — Percentage of recurring tasks automated. Use the Task Audit (`context/task-audit.md`) as your scoreboard.
- **Revenue Per Employee** — Total revenue ÷ team members. Not bigger companies — leaner, faster, more profitable ones.

### How You Should Help
- Be patient. Assume the user is non-technical unless told otherwise.
- Explain what you're doing in plain English BEFORE doing it.
- Celebrate wins — every module installed, every task automated is real progress toward freedom.
- When suggesting solutions, check existing modules and the community first (Borrow Before You Build).
- Keep the three KPIs in mind — every automation should move at least one KPI.
- Never dump error logs or technical jargon. Find the problem, explain it simply, fix it.

---

## Workspace Structure

```
.
├── CLAUDE.md                # This file — core context, always loaded
├── .env                     # API keys and credentials (gitignored, never commit)
├── .claude/
│   └── commands/            # Slash commands Claude can execute
│       ├── prime.md         # /prime — session initialization
│       ├── install.md       # /install — install an AIOS module
│       ├── create-plan.md   # /create-plan — create implementation plans
│       ├── implement.md     # /implement — execute plans
│       └── share.md         # /share — package systems for sharing
├── context/                 # Background context about the user and business
│   ├── business-info.md     # What the business does
│   ├── personal-info.md     # Who you are, your role
│   ├── strategy.md          # Current priorities and goals
│   ├── current-data.md      # Key metrics and current state
│   └── import/              # Drop documents here for Claude to analyze
├── module-installs/         # AIOS modules — drop module folders here, install with /install
├── plans/                   # Implementation plans created by /create-plan
├── outputs/                 # Work products and deliverables
├── reference/               # Templates, examples, reusable patterns
├── scripts/                 # Automation scripts (added by modules)
└── shares/                  # Packaged systems for sharing (created by /share)
```

**Key directories:**

| Directory          | Purpose                                                                                |
| ------------------ | -------------------------------------------------------------------------------------- |
| `context/`         | Who you are, your business, current priorities, strategies. Read by `/prime`.           |
| `context/import/`  | Drop any docs here (business plans, ChatGPT exports, etc.) for Claude to analyze.      |
| `module-installs/` | AIOS modules go here. Install them with `/install module-installs/{module-name}`.      |
| `plans/`           | Detailed implementation plans. Created by `/create-plan`, executed by `/implement`.    |
| `outputs/`         | Deliverables, analyses, reports, and work products.                                    |
| `reference/`       | Helpful docs, templates and patterns to assist in various workflows.                   |
| `scripts/`         | Automation scripts — added by modules as you install them.                             |
| `diagrams/`        | Architecture diagrams (Diagram Engine module). `.d2` text sources + rendered PNGs. Just ask Claude to create or update a diagram; render all with `bash scripts/generate_diagrams.sh`. Skill: `.claude/skills/d2-diagrams/`. |
| `outputs/crm/`     | The outreach CRM data layer: `crm.csv` (all contacts), `activity-log.csv` (every touch), `goals.json` (weekly targets). Viewed live in the CRM dashboard — see "Outreach CRM" below. |
| `outputs/linkedin/` | LinkedIn content-ops data: `ideas.csv` (post ideas + weekly plan), `stats.csv` (impressions/followers log), `analytics/` (drop LinkedIn .xlsx exports here to import). Viewed in the CRM dashboard's LinkedIn tab. |
| `shares/`          | Packaged systems for sharing. Created by `/share`, ready to hand off.                  |
| `claude-vault/`    | **The module library.** Every system Boschly can build, packaged as a drag-and-drop folder that installs itself (INSTALL.md + `_connectors/` + `_patterns/`). Start with [claude-vault/README.md](claude-vault/README.md) for the format, [CATALOGUE.md](claude-vault/CATALOGUE.md) for what exists, [BUILD-PLAN.md](claude-vault/BUILD-PLAN.md) for the order. Planned 2026-07-27, Wave 0 not yet started. |

---

## Context Summary

**Business:** Solo AI agency — builds and maintains custom AI Operating Systems (AIOS) for medium to large companies using the AAA Accelerator module stack.
**Role:** Heinrich is the founder and sole operator — responsible for sales, delivery, outreach, and client management.
**Current focus:** Hit $50,000 in revenue within 3 months. Close first clients via warm referrals and launch cold outreach (Instantly AI + Apollo) within 2 weeks.
**Key metric to watch:** Total revenue vs. $50k target / Active clients on retainer.

---

## Commands

### /install [module-path]

**Purpose:** Install an AIOS module into this workspace.

Point it at a module folder in `module-installs/` and Claude walks you through the guided setup. Each module adds a new capability to your AIOS.

Example: `/install module-installs/context-os`

### /prime

**Purpose:** Initialize a new session with full context awareness.

Run this at the start of every session. Claude will:

1. Read CLAUDE.md and context files
2. Summarize understanding of the user, workspace, and goals
3. Confirm readiness to assist

### /create-plan [request]

**Purpose:** Create a detailed implementation plan before making changes.

Use when adding new functionality, commands, scripts, or making structural changes. Produces a thorough plan document in `plans/` that captures context, rationale, and step-by-step tasks.

Example: `/create-plan add a competitor analysis command`

### /implement [plan-path]

**Purpose:** Execute a plan created by /create-plan.

Reads the plan, executes each step in order, validates the work, and updates the plan status.

Example: `/implement plans/2026-01-28-competitor-analysis-command.md`

### /share [system or feature]

**Purpose:** Package a system or feature from your workspace for sharing.

Deep-dives the code first to fully understand it, then produces a self-contained, beginner-friendly package with a Claude-guided installer (INSTALL.md + README.md + scripts). The recipient gives the folder to Claude Code and says "read INSTALL.md and set this up" — Claude walks them through everything step by step. Runs a 6-stage interactive flow: Research → Scope → Frame → Write → Validate → Deliver. Outputs to `shares/`.

Example: `/share the daily brief system`

### /process

**Purpose:** Process the GTD inbox to zero using the decision tree.

Routes each captured item to projects, next-actions, waiting-for, someday-maybe, or trash. Refreshes the dashboard when done.

### /review

**Purpose:** Run a guided GTD weekly review (30-60 minutes).

Walks through GET CLEAR → GET CURRENT → GET CREATIVE → REBUILD. Processes inbox, reviews all project and action lists, scans areas and someday-maybe, updates the dashboard. Run weekly (Fridays recommended).

### /brainstorm [topic]

**Purpose:** Workspace scanner and opportunity finder.

Scans your tasks, processes, and current setup to find manual work that could be automated. Ranks opportunities by impact and feasibility, deep-dives the top picks, and points you to `/explore` or `/implement` for the next step. Run without arguments to scan everything, or with a topic to focus on a specific area.

### /explore [idea]

**Purpose:** Interactive feature discovery and shaping.

Takes an idea and walks you through shaping it into a clear, scoped concept through 5 stages: Discovery → Research → Shape → Scope → Output. Produces a feature doc in `plans/` ready for `/implement` or `/create-plan`.

### /video [idea]

**Purpose:** Create a LinkedIn video package end to end.

Runs the proven talking-head + whiteboard slides + screen-share format: confirms the concept, offers hook quotes, writes 6 whiteboard slide prompts (2 per slide, generated in Higgsfield), builds the 3-slide PowerPoint once images are picked, and writes the concept doc + spoken script into `outputs/content/`.

Example: `/video showcase the invoice processing demo`

### /slides [topic]

**Purpose:** Create a LinkedIn carousel (document post) package end to end — free.

Runs the proven 7-slide Boschly visual-story format: locks the story arc (hook → problem → cost → solution → how → new reality → outcome/CTA), writes billboard-style slide copy, writes Higgsfield image prompts (one visual world in different states), then STOPS while Heinrich generates the images free in the Higgsfield web app (Nano Banana, 4:5). Once images are in, it composes the branded 1080×1350 portrait PDF (hero slide approved first), verifies the actual PDF pages, and delivers the file + ≤58-char title + caption. Never spends Higgsfield credits.

Example: `/slides the invoice processing system`

### /slides-auto [topic]

**Purpose:** Same as `/slides`, but Claude generates the images itself via the Higgsfield integration (~7 credits per carousel, Nano Banana only, spend confirmed first). Use when Heinrich wants it fully hands-off.

Example: `/slides-auto the meeting intelligence demo`

### /ad-video [topic]

**Purpose:** Create a faceless, narrated, enterprise-style motion-graphics video end to end.

This is the polished "consultancy ad" format (McKinsey or Palantir feel): an ElevenLabs voiceover over animated charts and diagrams built in Remotion, near-black look with one accent colour, 60 to 90 seconds, anchored in real citable data, with a soft brand sign-off and a LinkedIn caption. It runs the proven pipeline: shape the thesis → write the scene script → synthesize the narration (`scripts/ad_narration.py`) → build the scenes in Remotion → verify each scene by rendering stills → render the final MP4 → write the post caption. Distinct from `/video` (talking-head + whiteboard + demo). Reference build lives in `outputs/content/ai-system-ad/`.

Example: `/ad-video what an AI system really is, using the McKinsey study`

### /motion [topic]

**Purpose:** Create a vertical fast-cut motion-graphics video for LinkedIn end to end.

The evolved short-form version of `/ad-video`: 1080×1920 mobile format, 35 to 50 seconds, fast narration (speed 1.12), dense word-synced motion, authority-name-first hooks when built on a study, a quiet dark music bed (0.08), and 2 to 4 cue-synced sound effects. Two approved endings, both without a brand sign-off: the **engagement cut** (question + comment-word CTA pill) and the **educational-authority cut** (the question alone, landing on a principle — used on `nineteen-systems-ad` and `eliza-secretary-ad`). Loads the content strategy layer before scripting (see "Content cycle" below) and pulls studies from `outputs/research/ai-business-studies-vault-2026-07-13.md`. Reference builds: `outputs/content/stanford-canaries-ad/`, `pwc-worth3x-ad/`, `ai-compounding-ad/`.

**The look layer** (added 2026-07-28, lives in the scaffold source `outputs/content/stanford-canaries-ad/src/`) is what stops these reading as stock AI explainers, and is mandatory on every new build:

- `easings.ts` — a motion curve per ROLE (`E.snap` type, `E.draw` data, `E.weight` objects, `E.camera` frame, `E.exit` everything leaving) plus `stagger()` and `useBreathe()`. One curve for a whole video is the loudest template tell.
- `camera.tsx` — `Camera` (push / pull / drift / rise, centred on 1.0 so nothing gets cropped), `Parallax` depth planes, `ScaleThrough` and `MaskWipe` and `Whip` in place of cross-fades. The frame is never locked off.
- `optical.tsx` — `Optics` overlay (film grain in shadow mode, halation, breathing vignette) plus per-element `Bloom` and `Fringe`. Drop `<Optics accent={...} />` as the last child of the master.
- `LookTest.tsx` — `LookBefore` / `LookAfter` compositions for A/B stills when tuning.

**Voice** is provider-pluggable via `scripts/ad_narration.py`: `minimax` (default, `speech-2.8-hd`, word timestamps from `subtitle_enable`) or `elevenlabs` (character timestamps). Both emit the same `words` + `cues` into `narration.json`, so `cueFrame()` is unaffected by a voice change. Heinrich's own cloned voice is created with `scripts/ad_voice_clone.py` — note MiniMax deletes a cloned voice after 7 days unused. Needs `MINIMAX_API_KEY` in `.env` and credit on the MiniMax account.

Example: `/motion the Harvard jagged frontier study`

### /develop [idea or idea-id]

**Purpose:** Turn a raw content idea into a strategically positioned, packaged concept ready to hand to a production command.

Loads the strategy layer and the context window, then runs positioning → packaging → priority score, and writes the result into `outputs/linkedin/ideas.csv`. Ends by naming which command builds it (`/motion`, `/video`, `/slides`, `/ad-video`).

**This also runs implicitly.** Whenever Heinrich asks for content, load the strategy layer and the context window first, whether or not the command was typed. See "Content cycle" below.

Example: `/develop the speed-to-lead voice agent`

---

## Content cycle

Every piece of content runs through the same layer. This is the Content Pipeline module, adapted so it drives the existing production commands rather than a parallel system.

**The strategy layer** — read all five before writing anything:

| File | What it decides |
|---|---|
| `context/linkedin/content-pillars.md` | The eight engines, the five pillars, the Strategy Scorecard |
| `context/linkedin/brand-and-audience.md` | The five audience segments (mapped to `context/icp.md`), want vs need, proof points by reader stage, standing content rules |
| `context/linkedin/dream-outcomes.md` | **The concept bank.** 7 dream outcomes per buyer on one shared spine, what blocks each, the system that removes it, the how-to title and the hook. Start here when the topic isn't already chosen |
| `context/linkedin/offers-and-funnels.md` | Offer ladder, funnel, segment→offer map, CTA bank |
| `context/linkedin/cadence.md` | Which slot and format it lands in |

**Which segment gets a video is decided by the Video score in `context/icp.md`, not the Revenue score.** They rank differently on purpose. Content order is Buyer 3, then 2, then 4. Buyer 1 is the best buyer in the workspace and is reached by phone, never by post, so his entries in the bank are cold-call openers.

**The context window** — run it, and reference it out loud:

```bash
uv run --no-project --system-certs python scripts/content_context.py --full
```

`scripts/content_context.py` assembles: what was posted recently, **the angle history from every `outputs/content/video-*-explainer.md`** (the repetition guard), the idea board, recent performance from `stats.csv`, **what prospects actually said** (notes in `activity-log.csv` — the best idea source in the workspace), and who is live in the pipeline. Stdlib only, no venv needed.

**The flow:**

```
idea  →  /develop  →  ideas.csv (positioned, scored)  →  /motion | /video | /slides | /ad-video
                                     ^                                    |
                                     +--- concept_doc path written back --+
```

**One source of truth: `outputs/linkedin/ideas.csv`.** The CRM dashboard's LinkedIn tab reads it live. Never create a second idea store. Columns: the original eleven plus `priority` (1-10), `funnel` (awareness/consideration/conversion), `segment`, `offer` (audit/build/retainer/brand), `concept_doc`.

---

## Installed Modules

- **AuditOS** module installed at `auditos/` - AI-strategy-audit + proposal system. Entry points: `/auditos` (dispatcher) + `/audit-*` phase commands. For any audit/proposal/blueprint work, read `auditos/CLAUDE.md` and follow it as the operating spec for that tree.
- **Content Pipeline** (`module-installs/content-pipeline-v1/`) installed **adapted** on 2026-07-29. Ported: the strategy docs (`brand-and-audience.md`, `offers-and-funnels.md`), the context window (`scripts/content_context.py`), the `/develop` staged flow, and priority scoring on `ideas.csv`. Deliberately **not** installed: `data/content.db` (would fork the idea board away from the CRM dashboard), `/capture` (duplicates "add idea:" and the dashboard's idea form), `/schedule` (duplicates the dashboard's weekly calendar), `notion_sync.py` (no Notion here), and `packaging-strategy.md` (YouTube titles and thumbnails; this is a LinkedIn workspace). See "Content cycle" above.

---

## Outreach CRM (weekly work dashboard)

**Launch:** double-click the **BoschAI CRM** icon on the desktop → opens at **http://localhost:8510**. (The icon runs `scripts/crm_app.vbs` → `crm_app.ps1`, which starts the dashboard silently only if it isn't already running, then opens the browser — clicking twice won't spawn a duplicate. `scripts/start-crm.bat` still works as a visible-console fallback.) Eight tabs:

1. **Dashboard** — who we're targeting this week, the channel goals (set weekly in `goals.json`; since Week 2 the channels are WhatsApp · Facebook · LinkedIn · cold calls · emails), and "Today's plan": how many are still safe to send per channel today. Daily caps (`goals.json`) prevent rate-locking — WhatsApp ~25/day (new-contact messages; spam-pattern senders get banned), FB ~30/day, LinkedIn ~15/day (platform caps invites ≈100/week), email ~25/day, calls unlimited. WhatsApp cards carry a one-click `wa.me` deep link.
2. **Send queue** — the working tab. Pick a channel; each contact card has the profile link, phone/email, and the personalized message ready to copy (hover the box for the copy button). Click the link, paste, hit "✓ Sent" — it logs the touch and moves them to contacted. Calls get one-click outcomes; clicking "interested" or "booked" pops a capture dialog (name, spoken email auto-detected — "yan at acme dot co dot za" → yan@acme.co.za — WhatsApp/email preference). A **Follow-ups waiting** section below the cards holds every sent LinkedIn connect whose after-accept message is ready: when they accept, copy the follow-up and mark it sent. The queue only shows as many as today's cap allows.
3. **Pipeline** — the deal board. An **"➕ Add someone to the pipeline"** box at the top: search-as-you-type over all CRM contacts (pick stage + note → they're on the board, and the add is counted as a positive reply in the weekly stats), plus a "not in the CRM yet" form that creates a fresh contact (`man-{slug}` id, source=manual — `crm_build.py` preserves manual rows) straight onto the board. Everyone who responded positively lives here as a card in one of five columns, in Heinrich's deal order (2026-07-20): **Interested → Replied → In discussion → Meeting booked → Won**, plus a Lost pile (revivable). Cards show name · segment · **phone** · email · last-contact date, a **⏰ follow-up chip** (`follow_up_date` column — goes red when due; an **"⏰ Follow-ups due" strip** above the board lists everyone due today or overdue), the next action, and a **✏️ Edit contact** panel (name / phone / email / last contacted / follow-up date / next action). Notes render as a proper timeline (date-stamped rows, newest first). **✉️ Draft button** (on cards with an email): queues the contact into `outputs/crm/draft-queue.json`; Heinrich then tells Claude *"create the queued email drafts"* and Claude writes a personalized Gmail draft per contact (from their notes, with the Calendly link `https://calendly.com/heinrichbosch343/30min`) via the Gmail connector, then clears the queue — drafts only, nothing sends itself. Every stage move is logged to the activity log. Pipeline statuses are **sticky**: routine touches (follow-up sent, no answer) never demote a deal off the board; only an explicit stage move or "not interested" does. **Notes are append-only**: every note gets a `DD Mon:` date stamp, appends to the contact (never overwrites), and is mirrored to the activity log (`action=note`) so it survives any later edit — same rule applies when Heinrich tells Claude a note in chat. **Demos**: when Heinrich says "build a demo for {firm}", Claude uses `reference/demo-agent-prompt-template.md` as the brief (fill placeholders from the contact's CRM row + notes) and writes the demo URL into the contact's `demo_link` column when done (shown as 🎬 on the card). Link columns (`website`, `maps_link`) are backfilled from the scrape lists by `scripts/crm_enrich_links.py` (re-runnable, fills empty cells only).
4. **CRM** — pipeline stage counts, "someone replied" quick-logger, a **call-intel box** (paste a rough note; Claude parses name/email/phone/next action into the contact), and views: In the pipeline / To contact / Contacted / Everyone. Cells edit in place and **auto-save** — no save button.
5. **LinkedIn** — content ops (rendered by `scripts/crm_linkedin_tab.py`, data in `outputs/linkedin/`). **Stats**: tiles + impressions trend from `stats.csv`, fed two safe ways — a 30-second quick-entry form, or LinkedIn's own analytics export (.xlsx dropped in `outputs/linkedin/analytics/`, imported with one click). There is **no safe API/scrape for personal-profile analytics** — never automate against Heinrich's account. **Weekly calendar**: Mon–Fri slots on the set cadence (Mon/Wed/Fri = videos Heinrich films, Tue/Thu = motion graphics via `/motion`; see `context/linkedin/cadence.md`); assign an idea to a slot, mark ✓ Posted, paste the post URL. **Idea board**: add-idea form, "✨ Brainstorm 5 with Claude" button (Haiku, reads `content-pillars.md`), drop/posted history. Ideas live in `ideas.csv` (statuses idea → planned → posted, plus dropped) — when Heinrich says "add idea: …" in chat, Claude appends a row there (same dedup-by-title rule as `add_idea()`).

6. **Audits** — the CRM↔AuditOS bridge (rendered by `scripts/crm_audit_tab.py`, registry in `outputs/crm/audits.json`). Pipeline cards carry a **"🔍 Start audit"** button: one click creates the full AuditOS client folder (`auditos/03-active-audits/{slug}/`) + registers it. The tab then tracks each audit: phase chips read LIVE from the folder contents (Research→Kickoff→Interviews→Opportunities→Blueprint — the files are the state), the "Next Step" straight from AUDIT-LOG.md, meetings (date/attendees/talking points, add + mark-held), and stakeholder cards with per-person transcript upload that files straight into `03-interviews/{person}/` (kickoff uploads → `02-kickoff/transcripts/`). Zero API cost by design: the tab tracks and files; after each upload it shows the exact phrase to tell Claude (e.g. "Process kickoff transcript for {client}") and the AI work happens in Claude Code per `auditos/CLAUDE.md`.

7. **Campaign** — the offer-and-objection cockpit for the three locked lanes (rendered by `scripts/crm_campaign_tab.py`). Pick a lane at the top — **Inbound trades** ("Sixty Days, Nothing Missed", owner-operated emergency trades), **Outbound lead-buyers** ("The Sixty-Second Callback", firms that buy leads; sixty *seconds* is the callback speed, its pilot runs sixty days like the rest), **Documents via LinkedIn** ("The Sixty-Day Deadline Audit", audit/law/governance firms with a regulator behind the document) — and the whole tab reloads around it.

   **The sequence is call first, then WhatsApp the same person the same day, ideally inside the hour.** Every message in the tab is written to land after a call has already happened, so the card won't hand one over until the outcome is logged. Send one cold and the first line of it is a lie. Each contact card runs in two steps: **step 1** shows the call context and the dial link, a box for what he said, and four outcome buttons (🗣 spoke to him · 📵 no answer · 🧱 gatekeeper · ⏰ call back later); **step 2** appears once an outcome is logged and shows the matching post-call message picked by that outcome *and* that trade, with the WhatsApp deep link as the primary action, a "↩ Redo the call" escape, and a variant picker where more than one message fits. The outcome persists in the CSV's `call_notes` column (`outcome | date | note`), so a refresh never sends a card back to step one, and anyone phoned but not yet messaged sorts to the top of the list with a count above it. What he types when logging the outcome fills `{call_note}` in the message word for word.

   **Every lane carries an upfront cost**: a free proof step, the R7,500 diagnostic, an upfront build fee, then a monthly. Nothing sells on performance, commission or deferred payment. **Every guarantee runs sixty days** (two full billing cycles and a real seasonal spread) and covers the **monthly only**. The build fee is delivered work and isn't refundable. On the offer card every figure except the R7,500 diagnostic carries a "working estimate" badge, and the free rungs are badged free so they never get quietly charged for. R7,500 is the only price anyone has actually paid: a glass firm paid exactly that on 24 July 2026.

   **The reference client is described, never named.** Never print or say "Alister", "24 Hour Glass" or "Lanseria", not even if a prospect asks. Describe it instead: a family-run glass company, trading since 2008, that answers emergency callouts round the clock with installers around the country, and three people run the whole thing. All true, all checkable. The reason is on the screen: roughly twenty competing glass firms sit on this same target list. The WhatsApp templates go further and don't mention the reference at all. If it's needed it belongs on the phone, after he's been asked who else Heinrich works with.

   The other three sections: **the objection bank**, the reason the tab exists, stress-tested objections in the buyer's own words with a search box and a category filter (price/trust/technical/timing/stall/incumbent) so one is findable in three seconds mid-call, each expanding to what he actually means, the response, the proof point, the next question and the trap; **the list**, ranked by signal score from `outputs/crm/campaign-targets.csv` (785 firms) or `outputs/crm/audit-targets.csv` (135 people), with filters for reach, category, city, minimum score, hide-already-worked, hide-in-CRM, plus **"site promises 24/7"** and **"has a contact name"**; and **call prep** (opener, beats, qualifying questions, disqualifiers) kept on screen while he dials.

   **Enrichment (3 August 2026).** `scripts/campaign_merge_enrichment.py` folded the website scrape (`outputs/crm/enrich-cache.json`) into both target lists, adding `contact_name`, `contact_name_confidence`, `contact_name_source`, `email`, `claims_247`, `claims_247_quote`, `services`, `service_areas`, `years_trading`, `team_size_hint`, `one_true_detail`, `enriched_at`, `enrich_status` and `signal_score_prescrape` to `campaign-targets.csv`, and the firm-level equivalents (`firm_email`, `firm_services`, `firm_service_areas`, `firm_years_trading`, `firm_team_size_hint`, `firm_one_true_detail`, `enriched_at`) to `audit-targets.csv`, where `enrichment_status` flips to `site-enriched` or `enrich-failed`. The card surfaces the contact name with its confidence, the firm's own 24/7 quote, years trading, team size, and the rest behind an expander. **Signal was re-scored** on that evidence: a promise the site makes in its own words now outranks one guessed from the firm's name, and a name-based guess that a properly-parsed site never backs up drops. Every change is logged in `outputs/crm/rescore-log-2026-08-03.csv`, and the pre-scrape score is kept in `signal_score_prescrape`. Only 274 of 687 domains are enriched so far, so most rows still read `not-attempted`.

   Offer copy lives in **`outputs/crm/offers.json`** — edit the promise, ladder, templates, objections or rules there and the tab picks it up, no code change. Messages fill from four tokens only: `{call_note}`, `{one_true_detail}`, `{claims_247_quote}` and `{contact_name}`. `{name}` `{category}` `{city}` `{reviews}` `{rating}` are gone, because Google's category values are singular and title-cased so "the {category} in {city}" rendered as "the Plumber in Johannesburg", and telling a man he's on a list is telling him he's on a list. Any sentence still carrying an unfilled token is dropped whole. A `wa_message` already written in the CSV is used verbatim so Heinrich's own edits are never overwritten. Numbers on **086/087 are flagged "cannot receive WhatsApp, call only"** (they look mobile and fail silently), contacts already in the CRM are flagged before he dials, and the documents lane is badged **pending-scrape** with sending disabled until the enrichment is authorised. Writes are atomic and only touch `status`, `last_touch`, `notes` and `call_notes`; statuses are sticky (a routine touch never demotes a booked or won row) and notes are append-only.

   **The call sheet.** `scripts/campaign_call_sheet.py` writes `outputs/crm/call-sheet-2026-08-03.md`: the top 80 inbound firms by re-scored signal, grouped by region so one sitting covers one area, one printable block per firm with who to ask for, the number and whether WhatsApp reaches it, one line he can say out loud built from that firm's own site, the likeliest objection for that trade with a four-word reminder of the answer, and a blank for the outcome. Re-run it after any re-score.

8. **Voice notes** — the review-mining tab (rendered by `scripts/crm_voice_tab.py`). One card per firm: the dominant **fixable** problem its own worst Google reviews point at, the WhatsApp deep link, and the script Heinrich reads into a voice note about it. Built on the 18 Aug review pull (`outputs/crm/review-cache-2026-08-18.json`, 6,320 reviews across 317 firms).

   **Why it exists:** the manual read of the top 50 (`outputs/research/review-mining-findings-2026-08-18.md`) found the dominant fixable problem is the **unsent quote**, not the missed call — but only 7 of those 50 firms can receive WhatsApp, and 2 of those are do-not-call. The reachable pool was never read. `scripts/review_patterns.py` closes that gap: deterministic regex over every 1–2★ review, no API spend, scoring nine patterns (quote never arrives · booking that isn't a booking · status void · nobody answers · fee nobody mentioned · cancellation that won't stop · listing lies · calls after opt-out · sales answered/service dead). It classifies **150 of 317 firms, 54 of them WhatsApp-ready and callable**. Re-run it any time: `uv run --no-project --system-certs python scripts/review_patterns.py`.

   **Accuracy, honestly:** checked against the 20 firms the manual read settled by hand, it gets the primary pattern **exactly right 11 times and lands in the top three 18 times**. "Nobody answers" co-occurs with everything and swallowed the sharper diagnosis 11 times on raw counts, so `WEIGHT` discounts it (0.65) and `status_void` (0.90). Because it is right about half the time, the card shows a **pattern picker** — every pattern the firm scores 2+ on, one click to switch, script regenerates instantly. The single label is a suggestion, not a verdict. Firms whose reviews are mostly about workmanship or conduct are pushed down the list and badged, because pitching a process fix to a firm whose real problem is the fitting loses the room in two minutes.

   **The scripts** live in **`outputs/crm/voice-scripts.json`** — edit the wording there, no code change, same convention as `offers.json`. **Rewritten 19 Aug** after the first pass came back too long, too polished and with no offer in it. The shape now is: who you are in four words → how you found them (honestly — you saw the reviews) → the problem with its cost in the same breath → **the offer: "in {days} days we fix X so that you get [dream outcome]"** → one soft question. Every script is **48–80 words, 20–30 seconds**, deliberately written slightly rough ("and look", "honestly") so it sounds like a person, not copy. Four tokens: `{speaker}` and `{days}` come from `_meta` so the name and the guarantee window are one edit each; `{contact_name}` fills only on high scrape confidence (only 1 of the 54 has one, so nearly all open "Hey, Heinrich here"); `{trade_phrase}` is legacy. Any sentence with an unfilled token is dropped whole. 1–2 variants per pattern plus `by_trade` overrides for property, repair, glass and solar, so competing firms on the same list don't get identical audio.

   **On mentioning the reviews:** the 18 Aug findings doc said never to. Heinrich overruled that on 19 Aug and he is right that it is what makes the note concrete rather than generic. The line that survived: **reference reviews in the aggregate only** ("I saw a few reviews mentioning…"), never quote one word for word, never name or describe a specific customer, never say how many. Aggregate is a thing a stranger notices; verbatim is surveillance. The evidence quotes on the card are for Heinrich to verify the pattern before recording — they are never for the prospect.

   **`{days}` is set to 30 on Heinrich's instruction**, which departs from the sixty-day guarantee every other lane runs (two billing cycles plus a seasonal spread — see the Campaign tab rules). It is a single `_meta` value, so switching every script back to 60 is one edit.

   **Other standing rules the tab enforces rather than trusts:** the reference client is never named; only 06x/07x/081–084 render a send button, 086/087 are call-only; the six do-not-call firms show a red block and no send button at all; no pricing in a voice note — the offer is the outcome and the timeframe, never the number. Sends log to `activity-log.csv` as `whatsapp_sent` / `voice_note`, so the daily WhatsApp cap on the Dashboard tab counts them; which script went to whom is kept in `outputs/crm/voice-sent.json`.

   **This is a cold voice note, which is a deliberate departure from the Campaign tab's call-first rule.** A voice note carries a person, so it survives cold in a way a text template does not — but if Heinrich wants the sequence back, phone first and use the same script as the opener. If `scripts/classify_target_reviews.py` is ever run (Opus, costs money), it writes `outputs/crm/review-problems-2026-08-18.json` and the tab prefers that file automatically — no rewrite needed.

**Email auto-drip (cloud):** the Railway backend (`apps/boschai-backend`) drains a Supabase `email_queue` table one send at a time — random 3-9 minute gaps, 07:30-15:00 SAST (tightened from 18:30 on 2026-07-22 at Heinrich's request), daily cap `EMAIL_DRIP_DAILY_CAP` (default 25) — through the backend's Gmail connection. Enable with `EMAIL_DRIP_ENABLED=1` on Railway (migration `010_email_drip.sql` must be run once in the Supabase SQL editor). `scripts/crm_cloud_sync.py` bridges local↔cloud: pushes queued rows from `outputs/crm/email-queue.csv` up, mirrors cloud sends back into `activity-log.csv` and contact statuses (needs `BOSCHAI_BACKEND_URL` + `API_SECRET_KEY` in `.env`). The old local sender (`scripts/email_drip.py` + `start-email-drip.bat`) still works as a fallback when the machine is on.

**Recurring invoicing (cloud, added 2026-08-19):** the Railway backend generates and sends monthly maintenance invoices on its own. `recurring_billing` (Supabase) holds one row per client on a standing monthly deal — amount, billing day, next due date; `services/invoicing.py` renders the Boschly-branded template (`templates/invoice.html`) to a PDF via headless Chromium (Playwright), emails it with the invoice attached, logs it to `invoices`, and rolls `next_invoice_date` forward a month. Runs daily at 07:00 SAST (`services/scheduler.py`), gated by `INVOICE_AUTOSEND_ENABLED` (default off, same pattern as the email drip) — off means every due invoice still gets generated and staged as a Gmail draft with a Telegram ping, so nothing is silently missed while it's off. Invoice numbering (`BOSCHLY-{year}-{seq}`) is computed from the highest existing number in `invoices` at send time, so it stays correct whether invoices come from this system or get created by hand. Migration `012_invoicing.sql` seeds the 3 invoices already sent manually (so numbering starts at 004) and activates Chillipepper Projects (R200/month, first automated run 1 Sept 2026) — must be run once in the Supabase SQL editor before this does anything. RSST Splicing and Technologies is on an identical R200/month deal per `BOSCHLY-2026-003` but was **not** activated in the seed; add it with an insert into `recurring_billing` when Heinrich wants it automated too. PDF rendering needs Chromium on Railway, added via `apps/boschai-backend/nixpacks.toml` (`playwright install --with-deps chromium` after the normal pip install) — unverified until the first real Railway deploy, worth checking the build log after push.

**WhatsApp quote bot (rebuilt 2026-08-20):** a technician finishes a site visit, WhatsApps the job to a bot number in whatever words come out, confirms it, and the customer gets a numbered, branded PDF quote on their phone about ten seconds later — on WhatsApp and by email. Built for **FIXITT Glass & Aluminium** (Zaheer) off the review-mining diagnosis: 13 of 20 of their negative reviews are *inspection done, quote never arrived*. Their phones are fine — Zaheer said so and the reviews agree — what fails is the handoff after the phone, so the thesis is **quote at the kerb, not at the office**.

The first build failed and was rewritten from scratch. **The one rule: the model understands and speaks, the code decides and sends.** Every message goes to Claude with the quote on the table and the recent conversation; it returns an intent plus the sentence to reply with. It is never asked to type a price — code renders every figure underneath its words from the stored job, so what he sees is what the PDF says by construction. And it cannot cause a send: it returns `action: "send"` and `services/quote_engine.py` then checks the job is complete, the number can receive WhatsApp, and **he has seen the card**. A first message ending "…and send it now" is still shown to him first.

Files: `routes/whatsapp.py` (HTTP edge only), `services/quote_engine.py` (the conversation + issuing), `services/quote_doc.py` (fpdf2 PDF, web page, all customer copy), `services/quote_store.py` (all Supabase access), `services/quote_selftest.py`, `services/whatsapp.py` (Twilio). All copy and business detail is in **`apps/boschai-backend/quote_business.json`** — edit there, never in code, same convention as `offers.json`.

Three things the rebuild fixed, each of which had been costing days: **(1)** state now lives in Postgres (`014_quote_bot.sql` — sessions, messages, quotes), because Railway restarts the web process on every deploy and the in-memory draft was already gone when he replied SEND; **(2)** every message is logged against Twilio's unique `MessageSid`, so a redelivery inserts zero rows and stops — killing double-sends and reply loops as a category; **(3)** the actual root cause of the whole saga — `routes/whatsapp.py` returned a **module-level `Response` object**, and FastAPI only attaches background tasks to a returned Response `if response.background is None`, so the first request claimed it forever and **every later message re-ran the first message's handler and dropped its own**. Never return a shared Response from a route with background work; see `_ack()`.

PDFs are **fpdf2**, not headless Chromium — pure Python, no system packages, no `nixpacks.toml`, ~30ms, and regenerated on demand from the stored row so the document cannot drift from the record. Customer replies land on the same webhook: routing is by data (anyone holding a recent quote is a customer), a yes stamps `accepted_at`, and the technician plus Telegram are told — that closes the loop the bad reviews are about. Verify without messaging anyone: `GET /quotebot/status?key=…` (live build string, config, which tables exist, last 25 messages) and `GET /quotebot/selftest?key=…` (13 real technician messages through the real model — it lives on the server because that is where the working Anthropic key is). Nothing sends without a human approving it; only 06x/07x/081-084 are accepted (086/087 look mobile and fail silently, and are refused by name before the send). Gated by `QUOTE_BOT_ENABLED` + `QUOTE_TECHNICIANS`. Demo runs on the **Twilio sandbox** (both phones must send the join code, membership lapses after 72h idle). Production is a one-way door on the number — whatever becomes the API sender leaves the WhatsApp Business app permanently, so never use a published line. Full detail in **`apps/boschai-backend/QUOTE-BOT.md`**.

**Payment links (added 2026-08-21).** The quote now arrives with a deposit link already in it — customer taps, pays, and the technician and Telegram both know within seconds. **Paystack**, chosen because it is the only SA gateway with a clean API for creating a link per quote from a server (Yoco is cheaper on card at 2.55% flat vs 2.9% + R1, and PayFast has Instant EFT which Paystack lacks — but neither generates links programmatically as cleanly, and that is the whole job). Files: `services/payments.py`, `routes/payments.py`, migration `015_quote_payments.sql`.

**The deposit policy is `quote_business.json` → `payment`, never code.** `deposit_percent` 50 asks for half; 100 asks for the full amount and the wording flips from "deposit" to "payment" automatically; 0 or `enabled: false` turns links off with no deploy. **This is Zaheer's business decision** — emergency callouts are usually settled on completion, fabricated work needs materials up front.

Non-obvious things worth keeping: **money is `Decimal(str(x))` with `ROUND_HALF_UP`, never float** — in plain floats half of R2 499.99 is R1 249.99 rather than R1 250.00, and the deposit plus balance then don't add up to the quote (a test asserts that invariant across seven awkward totals). **The webhook has three defences** because it marks a customer's money as received: HMAC-SHA512 signature over the raw bytes, `payment_events.event_id` UNIQUE for idempotency, and — most importantly — the webhook body is treated as a *hint only*, with `payments.verify()` asking Paystack directly before anything is written down. **The PDF deliberately never carries the payment link** (a PDF gets forwarded, printed and filed, and a live payment URL in a filing cabinet is a way to be paid twice); it names the deposit, the link lives on WhatsApp and the quote page. **A Paystack outage never withholds the quote** — it goes out anyway, the technician is told there's no link, and that one payment gets chased the old way. Check with `GET /quotebot/payments?key=…`, which shouts **TEST or LIVE**: a test key produces checkout pages indistinguishable from real ones that move no money.

**Reply tracking:** Facebook and LinkedIn have no safe automation for personal accounts (scraping risks the exact bans the caps protect against) — replies are one click in the CRM tab, or tell Claude ("Pearl replied, wants a call"). Gmail reply detection can be automated later via the existing Gmail collector.

**LinkedIn connections:** Heinrich's own connection list can't be read programmatically — it sits behind his login, and driving that session (or handing over the `li_at` cookie) is the exact pattern LinkedIn restricts accounts for. That account is the content distribution channel, so it's never worth the trade. The supported route is LinkedIn's own export: [linkedin.com/mypreferences/d/download-my-data](https://www.linkedin.com/mypreferences/d/download-my-data) → tick **Connections** → archive arrives by email in ~10 min. Drop `Connections.csv` anywhere in the repo and run `uv run --no-project --system-certs python scripts/linkedin_connections_import.py`. It auto-finds the file (repo or Downloads), skips LinkedIn's `Notes:` preamble, scores every connection against the five buyers in `context/icp.md`, drops the Big Four and platform noise, flags anyone already in `crm.csv`, and writes a ranked `outputs/leads/linkedin-connections-<date>.csv`. Stdlib only, no keys, no network. The Apify actor in `scripts/scrape_linkedin_prospects.mjs` is a different thing — it searches *public* profiles by title and location, and can't see who's connected to Heinrich.

**Sunday prep ritual:** Claude writes next week's contact list + personalized messages into the CRM (`message`/`followup` columns) and rolls `outputs/crm/goals.json` forward. `scripts/crm_build.py` re-merges source lists and pulls prepared messages from the outreach pack — it never overwrites statuses, notes, or messages already worked. Do-not-contact names stay flagged (`dnc=yes`) and never appear in the queue.

---

## Getting Started

**First time?** Start here:

1. Run `/install module-installs/context-os` — this builds your context layer (Claude learns your business)
2. After ContextOS is done, run `/prime` — verify Claude knows you
3. Install more modules from `module-installs/` as you're ready

**Returning?** Run `/prime` at the start of every session.

---

## Critical Instruction: Maintain This File

**Whenever Claude makes changes to the workspace, Claude MUST consider whether CLAUDE.md needs updating.**

After any change — adding commands, scripts, workflows, or modifying structure — ask:

1. Does this change add new functionality users need to know about?
2. Does it modify the workspace structure documented above?
3. Should a new command be listed?
4. Does context/ need new files to capture this?

If yes to any, update the relevant sections. This file must always reflect the current state of the workspace so future sessions have accurate context.

---

## Session Workflow

1. **Start**: Run `/prime` to load context
2. **Work**: Use commands or direct Claude with tasks
3. **Install modules**: Use `/install` to add new AIOS capabilities
4. **Plan changes**: Use `/create-plan` before significant additions
5. **Execute**: Use `/implement` to execute plans
6. **Share**: Use `/share` to package systems for team, clients, or community
7. **Maintain**: Claude updates CLAUDE.md and context/ as the workspace evolves

---

## Notes

- Keep context minimal but sufficient — avoid bloat
- Plans live in `plans/` with dated filenames for history
- Outputs are organized by type/purpose in `outputs/`
- Reference materials go in `reference/` for reuse
- API keys go in `.env` — never commit this file
