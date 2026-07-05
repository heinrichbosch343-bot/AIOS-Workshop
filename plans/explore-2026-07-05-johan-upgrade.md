# Explore: Johan — Fast Afrikaans AI + 3D Energy Orb + Visual Statistics

**Created:** 2026-07-05
**Status:** Built — see `plans/2026-07-05-johan-upgrade.md` (voice ID wiring pending ElevenLabs key permissions)
**Origin:** Upgrade the Jarvis demo: rename the AI to Johan with an Afrikaans boer accent, make him talk faster and punchier (Ironman-Jarvis quick), pull up statistics as charts/tables beside the orb, and replace the placeholder orb with a crazy high-detail 3D rendered flying energy orb (reference image supplied: blue/white volumetric energy burst with particles and lens flares).

---

## Vision

Turn the working-but-plain Phase 1 talking loop into the showpiece: a cinematic 3D energy orb named **Johan** who answers business questions in a quick, confident South African voice — "Ja, record quarter — 24.6 million rand, lekker" — while bar charts, trend lines, and deal tables slide in beside him. This is the version that gets filmed for LinkedIn and shown in sales calls.

## Problem Statement

Phase 1 proved the voice loop works, but it doesn't yet *sell*: the voice is American and slow-paced, answers are a bit long, there are no visuals backing the numbers, and the placeholder orb looks like a screensaver, not Ironman tech. For SA corporate prospects, an Afrikaans-flavoured AI with movie-grade visuals is the difference between "neat demo" and "I want that in my company."

## Proposed Solution

### What It Does

Four upgrades to `demos/jarvis/` (which becomes Johan):

1. **Johan persona** — renamed everywhere (system prompt, page title, footer, status text). Speaks SA English with boer directness and sprinkled Afrikaans ("ja", "nee", "lekker"), ultra-short answers: 1–2 punchy sentences, headline first, screen visuals carry the detail.
2. **Real Afrikaans-accented voice, faster** — TTS swaps from Deepgram Aura to **ElevenLabs** (Flash model): audition South African male voices from their library, run at ~1.1–1.15× speed. Deepgram stays for speech-to-text.
3. **Visual statistic cards** — with each answer the brain returns a card spec; the front end renders it sliding in beside the orb via locally-bundled **Chart.js**: bar chart (e.g. revenue by quarter), line/trend, deal table (stuck Transnet row highlighted), or big-number stat tile.
4. **3D energy orb** — replace the 2D canvas placeholder with a **Three.js** WebGL orb matching the supplied reference image: volumetric blue/white energy core, swirling particle field, light streaks, bloom/glow post-processing, gentle floating drift ("flying"). State-reactive: calm drift (idle), particles drawn inward pulsing with the mic (listening), fast internal swirl (thinking), core flaring with speech energy (speaking).

### How It Works

1. `run.bat` → browser opens to Johan floating in dark space (3D orb, ~60fps)
2. Hold orb/spacebar, ask: "How did we do this quarter?"
3. Deepgram STT → Claude brain (unchanged SQL tool over Meridian DB) now returns BOTH a short spoken answer and a card spec
4. ElevenLabs synthesizes Johan's fast SA-accented reply; orb flares as he speaks
5. The matching chart/table slides in beside the orb, staying on screen until the next question

### What It Produces

- Spoken answers in Johan's voice with synchronized 3D orb animation
- One strong visual per answer: bar/line chart, table, or stat tile
- A filmable, repeatable sales demo — the LinkedIn hero asset

## Scope

### Minimum Viable Version

Voice swap + Johan persona + card engine on the existing 2D orb — already a big visible upgrade if the 3D orb takes longer than expected.

### Full Vision (this round)

All four components: Johan persona, ElevenLabs voice, visual cards, and the 3D energy orb.

### Components

| Component | Description | Effort | Dependencies |
|-----------|-------------|--------|--------------|
| ElevenLabs voice swap | New `text_to_speech()` backend in voice.py; audition SA voices; speed ~1.1×; keep Deepgram STT | S | Heinrich creates free ElevenLabs account, adds `ELEVENLABS_API_KEY` to `.env` |
| Johan persona | System prompt rewrite: name, boer directness, Afrikaans flavour, 1–2 sentence ultra-short answers; UI rename | S | none |
| Visual card engine | Brain returns card spec (bar/line/table/stat) with each answer; Chart.js (vendored locally) renders slide-in cards | M | none |
| 3D energy orb | Three.js (vendored) WebGL orb per reference image: particle field, energy core, bloom, floating drift, 4 reactive states behind the existing `setState`/`setLevel` API | M–L | none (API designed for this swap) |

### Out of Scope

- Tabbed command-centre dashboard (cards may evolve into it later)
- Wake word ("Hey Johan") and continuous conversation
- Streaming TTS latency work beyond what ElevenLabs Flash gives for free (full streaming remains Phase 3)
- Real-data connectors (still all Meridian demo data)
- Report writer (still Phase 3)

## Technical Considerations

- **New service: ElevenLabs** — free tier ~10 min generated speech/month, no card; $5/month starter if filming burns through it. Flash model is sub-second, which should also cut total answer latency from 10–16s to roughly 7–9s. THE ONE MANUAL STEP: Heinrich signs up and adds `ELEVENLABS_API_KEY` to `.env`.
- **Existing keys unchanged:** Deepgram (STT only now), Anthropic (brain).
- Chart.js and Three.js are each a single JS file vendored into `demos/jarvis/static/vendor/` — demo stays fully local/offline-capable.
- Card spec design (tool call vs structured output from the brain) is a /create-plan decision; requirement is: one model pass, no second Claude call per question.
- 3D orb performance target: 60fps on a mid-range laptop; bloom is the heaviest effect — needs a quality toggle fallback.
- Voice audition step: generate the same test line with 3–4 SA voices from the ElevenLabs library, Heinrich picks Johan's voice before it's wired in.

## Connections

- Direct upgrade of `demos/jarvis/` (Phase 1, port 8505) — DB, seeder, guardrails, STT, server flow all unchanged
- Fulfils and expands the original Phase 2 from `plans/explore-2026-07-05-jarvis-voice-orb.md` (premium orb + cards), adding the persona/voice/accent layer
- ElevenLabs aligns with the "voice API" primitive on Heinrich's API-primitives-to-build-on list — this demo doubles as his testbed for it

## Next Steps

Run:

```
/create-plan build the Johan upgrade per plans/explore-2026-07-05-johan-upgrade.md — ElevenLabs SA voice, Johan persona, visual card engine, Three.js 3D energy orb
```

Before or during the build: create the free ElevenLabs account and add `ELEVENLABS_API_KEY` to `.env` (Claude will walk through it).

## Discovery Notes

- Deepgram has no South African voice — ElevenLabs chosen over Azure (needs card) and over faking it with playback speed; Deepgram kept for STT
- Persona level: SA English + Afrikaans flavour words (not heavy bilingual, not neutral) — understood by all prospects, unmistakably South African
- Visuals: one card per answer sliding in beside the orb (not a tabbed dashboard — deferred)
- Answer length: ultra-short (1–2 sentences) chosen as default since visuals carry detail — matches the "quick like Ironman's Jarvis" ask
- 3D orb art direction locked by Heinrich's reference image: blue/white volumetric energy burst, particles, lens-flare glow, floating/flying motion
- Build order safety: voice + persona + cards land first (MVP), 3D orb is the polish pass on top
