# Explore: BoschAI Jarvis — Voice Orb Business Assistant

**Created:** 2026-07-05
**Status:** Phase 1 built (2026-07-05) — working voice loop at demos/jarvis, port 8505. Phase 2 fulfilled and expanded by the Johan upgrade (2026-07-05): WebGL energy orb + visual cards + SA persona/voice — see `plans/2026-07-05-johan-upgrade.md`. Next: Phase 3 (report writer, streaming TTS latency, wake word)
**Origin:** A Jarvis-style voice assistant with a visual "center ball" orb UI — voice in, voice out — that answers any question about a company: quarterly numbers, financials, pipeline, meetings, reports.

---

## Vision

A cinematic, voice-first demo of the AIOS: a glowing orb you talk to that answers business questions out loud, pulling live from a company database — financials, pipeline, meetings, documents — with supporting charts and tables sliding in beside it. Built demo-first: a sales asset for LinkedIn videos and client calls that genuinely works end to end.

## Problem Statement

Business owners can't "just ask" their business a question — numbers live in dashboards, meetings live in transcripts, deals live in a CRM. Heinrich sells AIOS builds that fix this, but needs a visceral way to *show* it. A talking orb that answers real business questions in seconds is the most compelling possible demo of the AIOS promise.

## Proposed Solution

### What It Does

"BoschAI Jarvis" — a local web app (same `run.bat` + localhost pattern as the other demos). A glowing orb floats in a dark space. Click it (or hold spacebar), ask a business question out loud; the orb listens (pulses with your voice), thinks (swirls), then speaks a natural-voiced answer while visual cards (charts, tables, quotes) slide in beside it. Conversation is multi-turn — follow-ups work.

### How It Works

1. `run.bat` starts the FastAPI backend and opens the browser to the orb page
2. User holds the orb / spacebar and speaks a question
3. Browser mic audio → **Deepgram STT** (existing key, code adapted from `demos/meeting-intelligence/transcribe.py`) → text
4. **Claude** (existing `ANTHROPIC_API_KEY`) receives the question + conversation history + tools to query the demo SQLite DB (SQL for financials/pipeline, search for meetings/documents)
5. Claude's answer text → **Deepgram Aura TTS** (same key) → audio streamed to browser; orb glow syncs to speech
6. Claude also selects a visual card (revenue chart, deal table, meeting quote, report preview) rendered beside the orb
7. "Write me a report" → formatted report on screen + markdown saved to `outputs/`

### What It Produces

- Spoken answers with synchronized orb animation
- Visual answer cards: charts, tables, meeting quotes
- On request: written reports saved to `outputs/`
- A filmable, repeatable sales demo

## Scope

### Minimum Viable Version (Phase 1)

Working voice loop on seeded demo data: click orb → ask "how did we do this quarter?" → hear a correct spoken answer. Placeholder orb visual. Proves latency and the whole pipeline.

### Full Vision (this build, Phases 1–3)

Premium WebGL orb with four states (idle / listening / thinking / speaking), visual cards, report writer, multi-turn conversation, curated demo script, tuned latency.

### Components

| # | Component | Description | Effort | Dependencies |
|---|-----------|-------------|--------|--------------|
| 1 | Demo DB + seeder | Fictional mid-size client company: 8 quarters of financials, sales pipeline (deals/stages/values), ~15 meeting transcripts with summaries/action items, document set. Seed script per existing `seed_demo_*.py` pattern. | M | none |
| 2 | Brain (backend) | FastAPI server; Claude tool-use loop querying the demo DB; returns answer text + card spec. | M | 1 |
| 3 | Voice in | Browser mic capture (push-to-talk) → Deepgram STT. Adapt `transcribe.py`. | S | 2 |
| 4 | Voice out | Answer → Deepgram Aura TTS → streamed audio playback. | S | 2 |
| 5 | The orb | WebGL shader orb, four states, audio-reactive glow. The showpiece. | M–L | none (parallel) |
| 6 | Visual cards | Slide-in panels: revenue chart, deal table, meeting quote, report preview. Claude picks the card. | M | 2 |
| 7 | Report writer | Voice-triggered formatted report → screen + `outputs/`. | S | 2, 6 |
| 8 | Launcher + polish | `run.bat`, on-camera demo script, latency tuning, error handling. | S | all |

### Phasing

- **Phase 1 — The talking loop:** components 1–4 with placeholder orb. One focused session.
- **Phase 2 — The show:** real orb + visual cards. Filmable after this. One session.
- **Phase 3 — Depth:** report writer, demo script, latency polish, richer seed data. Shorter session.

### Out of Scope (for now)

- Wake word ("Hey Jarvis") and continuous open-mic conversation — later upgrades
- Real data hookups (DataOS `data.db`, IntelOS `intel.db`, Zoho CRM API) — v1 runs entirely on seeded demo data by explicit decision
- Zoho OAuth setup (the claude.ai MCP connector can't be used by a standalone app)
- Hosting / phone access / auth — local-only demo
- Switchable demo personas (dropdown of demo companies) — noted as a future sales tool

## Technical Considerations

- **Keys already in `.env`:** `ANTHROPIC_API_KEY` (Claude), `DEEPGRAM_API_KEY` (STT + Aura TTS — $200 free credit covers both). **No new signups or spend.**
- **Stack:** FastAPI + one custom HTML/JS page (WebGL orb, Web Audio API mic). Streamlit deliberately avoided — can't do real-time voice + animation.
- **Latency is the make-or-break:** target 2–4 s question-to-voice using streaming (start TTS on first sentence while Claude continues). Set expectation: great on camera, not movie-instant.
- **Port:** next in demo sequence (8505; existing demos use 8502–8504).
- **New demo DB** (e.g. `demos/jarvis/demo_company.db`), fully gitignore-safe fictional data.

## Connections

- Reuses Deepgram integration patterns from `demos/meeting-intelligence/transcribe.py`
- Reuses Claude Q&A pattern from `demos/drive-intelligence/dashboard.py`
- Follows demo conventions: folder under `demos/`, `run.bat`, seeder script, localhost port
- Future: swap demo-DB tools for real DataOS/IntelOS/Zoho connectors to turn the demo into Heinrich's daily driver

## Next Steps

Run `/create-plan` for Phase 1 — this is a large multi-session build and deserves a detailed plan:

```
/create-plan build Phase 1 of the Jarvis voice orb demo per plans/explore-2026-07-05-jarvis-voice-orb.md — demo DB + seeder, FastAPI brain with Claude tool use, Deepgram voice in/out, placeholder orb
```

## Discovery Notes

- **Purpose:** demo-first sales asset that genuinely works (LinkedIn video + sales calls), chosen over daily-driver or pure-mockup
- **Platform:** browser app on localhost, matching existing demo pattern
- **Interaction:** click/hold-to-talk chosen for v1; wake word explicitly deferred
- **Data:** ALL demo data (pipeline, financials, meetings) — Heinrich's explicit call; real integrations deferred
- **Demo company:** one fictional mid-size client company (relatable to corporate prospects), not BoschAI-branded
- **Voice stack decision:** Deepgram for both directions (existing key + credit) over ElevenLabs/OpenAI (new signups/cost)
