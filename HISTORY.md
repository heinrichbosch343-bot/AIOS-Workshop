# Workspace History

> Chronological log of all work done in this workspace. Updated every session.
> Most recent entries at the top. Each entry has a date, title, and bullet points.
>
> **How it works:** When you run `/commit` after meaningful work, Claude adds an entry here
> automatically. You don't need to write this file yourself.

---

## 2026-07-05

### Johan Orb v2 — Fullscreen Plasma Render
- Diagnosed the "boxed-in" look: the orb's glow was clipping at the edges of its 480px square canvas. Canvas is now fullscreen behind the UI (z-index 0, pointer-events none); the scene anchors itself to an invisible circular `#orb-space` hold-target every frame, so the orb sits in the layout but its glow/particles bleed across the whole screen
- Core rebuilt as a plasma shader: simplex-noise displaced sphere (living surface), fbm volumetric energy wisps in the fragment shader, semi-transparent everywhere (never a solid ball), plus a glassy fresnel shell; solid white "heart" mesh replaced with a soft glow sprite
- 2D fallback updated for the non-square fullscreen canvas

### Johan Visual Detail Pass — Deep Cards, Karaoke Captions, Orb Transitions
- Cards now carry EVERY detail while Johan speaks only headlines: new `list` card type (meetings/documents → date, attendees, each decision/discussion/action as labelled items), `facts` chips on any card, tables up to 12 rows; brain `MAX_TOKENS` 1000→2000
- Karaoke captions: the spoken answer appears word-by-word in sync with the audio, current word glowing — no more pile of text
- De-boxed the card panel: floats on a soft radial pool of light that fades into the dark space (no border/box), staggered element reveal, Chart.js bars/points animate in sequence
- Orb transition flare: bright core burst that decays ~0.6s on every state change (biggest when the answer starts)
- Fixed brain JSON parsing: scan for the JSON object anywhere in the reply so stray prose can never make Johan read raw JSON aloud
- Voice: swapped to **Marcel — South African** (middle-aged Afrikaans man, voice ID via ElevenLabs web app since the key is TTS-only scoped); verified live end-to-end, Hendrik Vorster kept in comments as the previous pick

### Johan Upgrade — SA Persona, Visual Cards, 3D Energy Orb (Jarvis Phase 2)
- Upgraded `demos/jarvis/` (port 8505, folder name unchanged) into **Johan**: Afrikaans-flavoured persona, 1–2 sentence punchy answers, headline number first
- Visual card engine: the brain now returns strict JSON `{say, card}` in one Claude pass — bar/line charts (vendored Chart.js), tables with stuck-deal highlight, and stat tiles slide in beside the orb (`static/cards.js`)
- 3D energy orb: Three.js WebGL orb (`static/orb3d.js`) — fresnel energy core, 2,500-particle swirl field, layered additive glow (fake bloom, no post-processing chain), floating drift, four reactive states; FPS watchdog + `?lowfx=1` fallback; old 2D orb kept as WebGL-unavailable fallback (`orb2d.js`)
- ElevenLabs TTS wired in `voice.py` (Flash v2.5 at 1.1× speed) with automatic Deepgram Aura fallback so the demo can never die on camera; Deepgram stays for STT
- Johan's voice: **Hendrik Vorster** (SA, upbeat) live via ElevenLabs Flash v2.5 @ 1.1× (Heinrich upgraded to Starter — free plan 402-blocks library voices over the API); Deepgram fallback verified as the on-camera safety net; full voice-to-voice round trip now **~6s** (Phase 1 was 10–16s)
- Validated end-to-end: all four card types + null-card conversation verified via `/api/ask`; vendored libs serve locally (offline-capable)
- Plan: `plans/2026-07-05-johan-upgrade.md` · Concept: `plans/explore-2026-07-05-johan-upgrade.md`

### Jarvis Voice Orb Demo — Phase 1 (The Talking Loop)
- Built `demos/jarvis/` (port 8505): hold the orb or spacebar, ask a business question out loud, hear a spoken answer — mic → Deepgram Nova-3 STT → Claude Sonnet 5 with a read-only SQL tool → Deepgram Aura-2 TTS ("Orion" voice)
- Seeded fictional client company **Meridian Manufacturing (Pty) Ltd** into `data/jarvis_demo.db`: 8 quarters of financials, 10-deal pipeline (R14.7M open, one deliberately stuck Transnet deal), 12 meeting transcripts, 10 documents — all cross-referenced so the six on-camera questions land
- SQL guardrails verified: SELECT-only statement inspection + read-only SQLite connection; 7 attack patterns blocked in testing
- All six curated demo questions answer correctly by voice, including cross-source ("why did margins improve?") and history follow-ups; full voice-to-voice round trip verified at ~10-16s
- Latency work: parallel per-sentence Aura TTS chunks (TTS 9.8s → ~5s); remaining gap to the ~6s target needs streaming TTS — scheduled for Phase 3
- Runs entirely on existing `.env` keys (Anthropic + Deepgram free credit), zero new spend
- Plan: `plans/2026-07-05-jarvis-phase1-voice-loop.md` (implemented) · Concept: `plans/explore-2026-07-05-jarvis-voice-orb.md`

---

## 2026-06-24

### Invoice Extraction Demo (LlamaParse) + Drive Demo Fix
- Built `outputs/invoice-demo/` — "Paperwork → Data" Streamlit demo (port 8503): drag invoice PDFs → LlamaExtract (FAST mode) → clean table → download CSV
- `invoice_extract.py` — schema-based extraction with an on-disk result cache (pre-warm so samples are instant on camera); `warm_cache.py` primes it
- Sample data: `generate_samples.py` (4 invoices) + `generate_bulk.py` (100 invoices in `demo-invoices-100/`, R4.93M combined); one-in-twelve omit the invoice number on purpose for the "leaves blanks, never guesses" trust beat
- Added `LLAMA_CLOUD_API_KEY` to `.env`; FAST mode keeps it to ~6 credits/page (~600 credits to warm all 100, 6% of the free 10k/month)
- Fixed the Drive Intelligence demo (`outputs/demo-dashboard/`): installed missing `python-docx`/`pypdf`/`anthropic` into `.venv` so .docx/.pdf extraction works; identified "Proposals Demo" as the good folder
- Explore + full film plan: `plans/explore-2026-06-24-llamaparse-invoice-demo.md`. Both videos queued to film 2026-06-25
- Hardened `.gitignore`: token.json/token_write.json/credentials.json + invoice-demo cache

## 2026-06-15

### LinkedIn Growth Engine (Lane A)
- Built `services/linkedin.py` — draft_post, draft_reply, draft_comment, suggest_ideas using Claude API + voice profile
- Created `prompts/linkedin_voice.md` — Heinrich's LinkedIn tone, pillars, what he never says
- Added Telegram commands: `/post`, `/reply`, `/ideas` for on-demand drafting
- Added agent tools: `draft_linkedin_post`, `draft_linkedin_reply`, `suggest_linkedin_ideas`
- Created `context/linkedin/` content-ops files: pillars, idea backlog, accounts to engage, weekly cadence
- All shared-file edits in marked `# === BoschAI: LinkedIn (lane A) ===` blocks for clean merge with lane B

## 2026-05-25

### Slash Commands, Gmail Connector, and Task Scheduler Fix
- Installed `/brainstorm` and `/explore` discovery commands from `slash-commands-v1` module
- Built `scripts/collect_gmail.py` — Gmail IMAP collector feeding `emails` table into `data.db`
- Wired email data into daily brief pipeline: `load_email_summary()` in `prompt.py`, new `email_digest` section (solo preset)
- Fixed CommandOS launch: removed duplicate Startup folder VBS, created `scripts/AIOS-CommandOS-Bot.vbs`, migrated to Task Scheduler (consistent with all other AIOS tasks)
- Created branded pre-meeting HTML briefs for prospects Lourens Delport and Connie (Osun Consulting)

## 2026-05-21

### Daily Brief Installed — Pipeline Metrics Delivered to Telegram
- Gemini-powered morning brief using `gemini-2.5-flash-lite` (free tier, 1 call/day)
- 6-stage sales funnel defined in `context/funnel.md` — Prospect to Handoff Complete, targets in ZAR
- `scripts/` module installed: `metrics.py`, `prompt.py`, `deliver.py`, `dashboard.py`, `daily_brief.py`
- Pipeline data live: 1 Active Prospect (Lourens Delport) confirmed in `pipeline_daily` SQLite view
- First client context file added: `context/clients/lourens-delport.md`
- Scheduled task still needed — currently runs manually via `venv\Scripts\python scripts\daily_brief.py`

### CommandOS Installed — Telegram Bot Live
- Telegram group "AIOS Workplace" created, bot (@HeinrichAIOS_bot) connected and verified
- `apps/command/` installed: aiogram bot with Claude Agent SDK — persistent sessions, voice notes, PDF/chart support
- Windows compatibility fixes applied: `fcntl` shim, UTF-8 stdout, Python 3.10 f-string fix
- Auto-start configured via Windows Startup folder (silent background launch on login)
- `TELEGRAM_GROUP_ID` and `TELEGRAM_CHAT_ID` set in `.env`
- CommandOS documented in `docs/command-os.md`

## 2026-05-19

### DataOS and IntelOS Installed
- DataOS pipeline live: SQLite database collecting FX rates daily at 7:00 AM via Windows Task Scheduler
- IntelOS installed: Fathom transcript collector pulling meeting recordings into `data/intel.db` at 7:05 AM daily
- Fixed .env encoding corruption (Windows-1252 to UTF-8) and Google credential variable mismatch in config.py
- Fathom signed up, Chrome extension installed, connected to Google Meet
- Command OS and Daily Brief module packages added to `module-installs/` ready for next sessions

## 2026-05-18

### InfraOS Setup
- Initialized Git repository in workspace
- Configured Git identity (Heinrich / heinrichbosch343@gmail.com)
- Created .gitignore to protect secrets and exclude generated files
- Created .env.example as a public template for required API keys
- Set up three core AI API keys: Anthropic, OpenAI, Gemini
- Created HISTORY.md changelog (this file)
- Created docs/ system with routing index and templates
- Installed /commit command for structured commits with auto-documentation
- Updated /prime to load HISTORY.md and docs/_index.md each session

### ContextOS Setup
- Completed full interview to build business context layer
- Wrote context/business-info.md — AI agency overview, module stack, pricing model
- Wrote context/personal-info.md — Heinrich's role, responsibilities, workspace use cases
- Wrote context/strategy.md — $50k revenue target, warm referrals + cold outreach strategy
- Wrote context/current-data.md — baseline metrics, KPIs to track, Instantly AI as data source
- Personalized CLAUDE.md with Context Summary section

## 2026-05-22

### ProductivityOS Install
- Installed ProductivityOS GTD module: inbox, projects, next-actions, waiting-for, someday-maybe, areas, dashboard
- Added /process command for GTD inbox processing with decision tree
- Added /review command for weekly GTD review (GET CLEAR → GET CURRENT → GET CREATIVE → REBUILD)
- Added inbox_writer.py and refresh_dashboard.py automation scripts
- Added reference/gtd-methodology.md as GTD reference
- Updated docs/_index.md and created docs/productivity-os.md

### CommandOS Bot Stability
- Added single-instance PID file guard to apps/command/main.py — prevents duplicate bot processes
- Added auto-restart loop to scripts/start-command-os.bat for resilience after crashes

### Client Pipeline
- Added context/clients/ directory with profiles for Connie (Osun Consulting Group) and Lourens Delport
- Updated strategy.md to reflect R1,000,000 ZAR revenue target by 17 August 2026
