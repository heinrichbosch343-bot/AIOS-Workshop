# Plan: Johan Upgrade — SA Voice, Persona, Visual Cards, 3D Energy Orb

**Created:** 2026-07-05
**Status:** Complete (2026-07-05) — Johan live with "Hendrik Vorster" SA voice (ElevenLabs Starter plan), ~6s voice-to-voice verified
**Request:** Build the Johan upgrade per `plans/explore-2026-07-05-johan-upgrade.md` — ElevenLabs SA voice, Johan persona, visual card engine, Three.js 3D energy orb.

---

## Overview

### What This Plan Accomplishes

Upgrades the working Phase 1 Jarvis talking loop (`demos/jarvis/`, port 8505) into **Johan**: a cinematic 3D energy orb that answers Meridian Manufacturing questions in a fast, Afrikaans-accented South African voice, in 1–2 punchy sentences, while a matching chart, table, or stat card slides in beside the orb. The result is the filmable LinkedIn hero asset and the sales-call showpiece.

### Why This Matters

Phase 1 proved the pipeline works but doesn't *sell*. For SA corporate prospects, an unmistakably South African AI with movie-grade visuals is the difference between "neat demo" and "I want that in my company." This directly serves the $50k revenue push: it's the demo that gets filmed for the audit-niche LinkedIn campaign and shown in discovery calls.

---

## Current State

### Relevant Existing Structure

- `demos/jarvis/` — complete Phase 1 build:
  - `voice.py` — Deepgram Nova-3 STT + Deepgram Aura-2 TTS (parallel sentence-chunk synthesis)
  - `brain.py` — Claude (`claude-sonnet-5`) tool-use loop with one read-only `query_db` SQL tool; spoken-style answers (2–3 sentences, ~55 words)
  - `server.py` — FastAPI on 8505; `POST /api/ask` returns `{transcript, answer, audio_b64}`; errors as `{"error"}` with HTTP 200
  - `store.py` / `seed_demo_company.py` — Meridian Manufacturing SQLite DB at `data/jarvis_demo.db` (financials, pipeline, meetings, documents)
  - `static/index.html` + `app.js` — push-to-talk (orb hold / spacebar), history in browser, `?debug=1` text fallback
  - `static/orb.js` — 2D canvas placeholder orb; public API `Orb.setState('idle'|'listening'|'thinking'|'speaking')` + `Orb.setLevel(0..1)` — **explicitly designed to survive this WebGL swap**
  - `static/style.css` — dark space theme, orb centered in `#stage` flex column
- `plans/explore-2026-07-05-johan-upgrade.md` — the shaped concept (all scope/voice/visual decisions locked)
- `plans/explore-2026-07-05-jarvis-voice-orb.md` — original phased vision (this plan fulfils and expands its Phase 2)
- `outputs/johan-voice-auditions/candidates.json` — exists but empty (`[]`); audition folder already created
- `.env` — has `ANTHROPIC_API_KEY` + `DEEPGRAM_API_KEY`; **`ELEVENLABS_API_KEY` must be added by Heinrich** (the one manual step)

### Gaps or Problems Being Addressed

- Voice is American (Aura-2 Orion) and paced for long answers — not the quick SA persona
- Answers are 2–3 sentences with all detail spoken — nothing on screen backs the numbers
- The orb is a flat 2D gradient circle — reads as screensaver, not Ironman tech
- No name/persona: "Jarvis" is generic and borrowed; Johan is ownable and local

---

## Proposed Changes

### Summary of Changes

- **Voice audition script** — fetch South African male voices from the ElevenLabs shared-voice library, download their preview MP3s to `outputs/johan-voice-auditions/`, write `candidates.json`; Heinrich picks; the chosen voice is added to his ElevenLabs workspace and its ID wired into `voice.py`
- **ElevenLabs TTS swap** — `voice.py` gains an ElevenLabs Flash v2.5 backend at 1.1× speed; Deepgram Aura stays as automatic fallback when `ELEVENLABS_API_KEY` is absent (demo never breaks); Deepgram STT unchanged
- **Johan persona** — `brain.py` system prompt rewritten (Johan, boer directness, sprinkled Afrikaans, 1–2 sentence answers, headline first); all UI text renamed (title, footer, status, aria-label, server title, run.bat)
- **Visual card engine** — the brain now returns strict JSON `{say, card}` in one model pass (no extra Claude call); `server.py` passes `card` through; new `static/cards.js` renders bar/line charts (vendored Chart.js), tables (stuck-deal row highlight), and big-number stat tiles, sliding in beside the orb
- **3D energy orb** — new `static/orb3d.js` (ES module) renders a Three.js WebGL orb per the reference art direction: volumetric blue/white energy core (fresnel shader), swirling particle field, additive glow sprites (fake bloom — no post-processing chain), gentle floating drift, four reactive states behind the existing `Orb.setState`/`setLevel` API; existing 2D renderer kept as automatic fallback when WebGL is unavailable
- Vendor `chart.umd.js` (Chart.js 4) and `three.module.min.js` (Three.js) into `static/vendor/` — demo stays fully local/offline-capable
- Update explore-doc statuses + `HISTORY.md`

### New Files to Create

| File Path | Purpose |
| --------- | ------- |
| `demos/jarvis/audition_voices.py` | One-shot script: search ElevenLabs shared voices (SA/Afrikaans male), download preview MP3s + write `candidates.json` to `outputs/johan-voice-auditions/`; `--adopt <voice_id>` flag adds the picked voice to the workspace and prints the line to paste into `voice.py` |
| `demos/jarvis/static/cards.js` | `Cards.show(cardSpec)` / `Cards.clear()` — renders bar/line/table/stat cards with slide-in animation; validates spec, silently skips malformed cards |
| `demos/jarvis/static/orb3d.js` | Three.js energy orb (ES module): particle field, fresnel core, glow sprites, drift; exports the same `setState`/`setLevel` API; falls back to the 2D renderer if WebGL init fails |
| `demos/jarvis/static/orb2d.js` | The current `orb.js` renamed — becomes the WebGL-unavailable fallback (exported as a factory instead of auto-running) |
| `demos/jarvis/static/vendor/chart.umd.js` | Vendored Chart.js 4 (single UMD file, already minified) |
| `demos/jarvis/static/vendor/three.module.min.js` | Vendored Three.js core (ES module build) |

### Files to Modify

| File Path | Changes |
| --------- | ------- |
| `demos/jarvis/voice.py` | Add ElevenLabs Flash TTS (voice ID constant, speed 1.1, `xi-api-key` header); `text_to_speech()` routes to ElevenLabs when key present, else Deepgram Aura with a one-line console notice; parallel chunk synthesis kept (2 workers for ElevenLabs free-tier concurrency) |
| `demos/jarvis/brain.py` | Johan persona system prompt; strict-JSON `{say, card}` answer contract with card-type reference; `answer()` returns `{"say": str, "card": dict|None}` with robust JSON parsing (fallback: whole text as `say`, `card: null`) |
| `demos/jarvis/server.py` | `/api/ask` response gains `"card"`; answer/history plumbing uses `result["say"]`; `/api/health` adds `"elevenlabs_key"`; app title → "BoschAI Johan Demo" |
| `demos/jarvis/static/index.html` | Title/footer/status → Johan; add `#card-panel` container; load `orb3d.js` + `app.js` as `<script type="module">`; add `cards.js` + vendored Chart.js |
| `demos/jarvis/static/app.js` | Convert to ES module importing `Orb` from `orb3d.js`; render `data.card` via `Cards.show()` on each answer (card persists until next question); status text → Johan wording |
| `demos/jarvis/static/style.css` | Card panel layout (slides in right of orb on desktop, below on narrow screens), slide-in keyframes, table highlight row, stat tile typography |
| `demos/jarvis/run.bat` | Echo text → "Starting BoschAI Johan Demo..." |
| `plans/explore-2026-07-05-johan-upgrade.md` | Status: `Explored` → `Planned` (→ `Built` at completion) |
| `plans/explore-2026-07-05-jarvis-voice-orb.md` | Note that Phase 2 is fulfilled/expanded by the Johan upgrade |
| `HISTORY.md` | Entry for the Johan upgrade |

### Files to Delete (if any)

| File Path | Reason |
| --------- | ------ |
| `demos/jarvis/static/orb.js` | Renamed to `orb2d.js` (content preserved as the fallback renderer) |

---

## Design Decisions

### Key Decisions Made

1. **Card spec via strict-JSON final answer, not a second tool call**: the explore doc requires one model pass. The brain's final message must be a single JSON object `{"say": "...", "card": {...}|null}`. This adds zero round trips (a `show_card` tool would add one API turn per question). Parsing is defensive: strip whitespace/code fences, `json.loads`, on failure treat the whole text as `say` with no card — the voice loop can never break because of a malformed card.
2. **Card spec shape** — four types, minimal fields, all validated in `cards.js`:
   - `bar` / `line`: `{type, title, labels: [...], values: [...], unit?}`
   - `table`: `{type, title, columns: [...], rows: [[...]], highlight_row?: int}` (e.g. stuck Transnet deal)
   - `stat`: `{type, title, value: "R24.6m", label?, delta?: "+9% vs Q1"}`
   The system prompt includes one worked example per type and the instruction: every data answer should carry a card; conversational answers may use `card: null`.
3. **ElevenLabs Flash v2.5 at speed 1.1**: `POST https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}?output_format=mp3_44100_128`, header `xi-api-key`, body `{"text", "model_id": "eleven_flash_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.1}}`. Flash is ElevenLabs' low-latency model — cuts TTS time and total answer latency. Speed 1.1 is within the supported 0.7–1.2 range; 1.15 is the fallback-up option if Heinrich wants punchier (constant at top of `voice.py`).
4. **Graceful TTS fallback, not a hard requirement**: if `ELEVENLABS_API_KEY` is missing or the ElevenLabs call fails, `text_to_speech()` falls back to the existing Deepgram Aura path and logs one plain-English line. The demo must never be dead on camera because of a quota or key issue.
5. **Audition via free preview MP3s, adopt only the winner**: the ElevenLabs shared-voice library returns a `preview_url` per voice — downloading previews costs zero credits and zero voice slots. The script filters shared voices for South African/Afrikaans-accented male voices, saves the top 4–6 previews locally, and only the voice Heinrich picks is added to his workspace (free tier has ~3 custom-voice slots). Then one paid test line ("Ja, record quarter — 24.6 million rand, lekker.") confirms the pick before wiring in.
6. **3D orb without a post-processing chain**: true `UnrealBloomPass` bloom drags in the whole Three.js addons dependency chain (EffectComposer, RenderPass, ShaderPass, OutputPass) and is the single heaviest GPU cost. Instead: fresnel-glow core shader + 2–3 layered additive-blended radial-gradient glow sprites + additive particle points. Visually matches the reference (volumetric blue/white burst, lens-flare feel) at a fraction of the cost, keeps the vendor footprint to **one file** (`three.module.min.js`), and comfortably hits 60fps on a mid-range laptop. Quality toggle: particle count halves via `?lowfx=1` and auto-drops if measured FPS < 45 for 3 seconds.
7. **Orb states map to existing API — no `app.js` state-logic changes**: idle = calm drift + slow particle orbit; listening = particles drawn inward, core pulsing with `setLevel`; thinking = fast internal swirl + hue shift toward violet; speaking = core flaring with `setLevel`. The floating "flying" motion is a slow Lissajous drift of the whole orb group.
8. **ES modules for the front end**: `orb3d.js` imports Three.js as a module (`import * as THREE from './vendor/three.module.min.js'`); `app.js` becomes a module importing `Orb` — guarantees load order without globals races. `cards.js` + Chart.js stay classic scripts (Chart.js UMD sets `window.Chart`), loaded before the modules run.
9. **Folder stays `demos/jarvis/`, port stays 8505**: renaming the folder churns paths in plans, memory, and muscle memory for zero user-visible gain — Johan is a user-facing rename (page, voice, prompt, footer). Noted in HISTORY.md so nobody looks for `demos/johan/`.
10. **TTS parallelism drops to 2 workers on the ElevenLabs path**: free-tier concurrency is limited; answers are now 1–2 sentences so chunking rarely triggers anyway. Deepgram fallback path keeps 6 workers.
11. **`MAX_TOKENS` stays 1000**: the JSON envelope + card data fits comfortably; no change needed.

### Alternatives Considered

- **`show_card` as a second Claude tool** — rejected: adds one full API round trip per question (latency), violates the one-pass requirement.
- **Anthropic structured outputs / `tool_choice` forcing a card tool** — rejected: forcing a tool response complicates the existing multi-turn SQL tool loop; instructed strict-JSON on the final text is simpler and failure-safe.
- **Azure TTS for the SA voice** — rejected in explore: needs a credit card; ElevenLabs free tier doesn't.
- **Playback-rate trick on Aura for speed** — rejected in explore: chipmunk artifacts; ElevenLabs has native speed control.
- **Full EffectComposer bloom** — rejected: 5+ vendored addon files, heaviest GPU cost, and the additive-sprite approach reaches the reference look. Can be revisited if filming demands more.
- **Tabbed command-centre dashboard** — out of scope per explore doc; one card per answer.
- **Wake word / continuous conversation / streaming TTS** — out of scope (Phase 3).

### Open Questions (if any)

None blocking the plan, but two **checkpoints during implementation** require Heinrich:

1. **ELEVENLABS_API_KEY** — Heinrich creates the free account at elevenlabs.io and adds `ELEVENLABS_API_KEY=...` to `.env` before Step 2 can be tested. (Steps 4–7 don't depend on it.)
2. **Voice pick** — after Step 1 generates the audition previews, Heinrich listens and picks Johan's voice before Step 3 hard-codes the voice ID.

---

## Step-by-Step Tasks

Execute in this order — it matches the explore doc's build-order safety: voice + persona + cards land first (MVP), the 3D orb is the polish pass.

### Step 1: Vendor the JS libraries

Download the two library files so the demo stays offline-capable.

**Actions:**

- Create `demos/jarvis/static/vendor/`
- Download Chart.js 4 UMD build → `static/vendor/chart.umd.js` (e.g. `https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.js` — this file is pre-minified)
- Download Three.js module build → `static/vendor/three.module.min.js` (e.g. `https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.min.js`)
- Sanity-check both files are non-trivial size (Chart.js ~200KB, Three.js ~600KB) and start with expected JS content, not an HTML error page

**Files affected:**

- `demos/jarvis/static/vendor/chart.umd.js` (new)
- `demos/jarvis/static/vendor/three.module.min.js` (new)

---

### Step 2: Voice audition script + STOP for Heinrich's pick

Build `audition_voices.py` and run the audition. **Requires `ELEVENLABS_API_KEY` in `.env` — if missing, pause here, walk Heinrich through creating the free ElevenLabs account, then continue.**

**Actions:**

- Write `demos/jarvis/audition_voices.py`:
  - Loads `.env` via the same walk-up pattern as `voice.py`
  - `GET https://api.elevenlabs.io/v2/shared-voices` (fall back to `/v1/shared-voices` if v2 404s) with `xi-api-key` header; query for male voices, searching `"south african"` and `"afrikaans"`; also filter results whose `labels.accent` / `accent` field contains `south african` or `afrikaans`
  - Rank by usage (`cloned_by_count` or equivalent), take top ~6
  - Download each voice's `preview_url` MP3 → `outputs/johan-voice-auditions/{rank}-{voice-name}.mp3`
  - Overwrite `outputs/johan-voice-auditions/candidates.json` with `[{name, voice_id, public_owner_id, accent, description, preview_file}]`
  - `--adopt <voice_id>` mode: `POST /v1/voices/add/{public_owner_id}/{voice_id}` with `{"new_name": "Johan"}`, then synthesize the test line *"Ja, record quarter — twenty four point six million rand. Lekker."* via Flash v2.5 at speed 1.1 → `outputs/johan-voice-auditions/johan-test-line.mp3`, and print the `VOICE_ID` line to paste into `voice.py`
  - All failures print plain-English messages (no tracebacks to the user)
- Run the search mode; confirm preview MP3s landed
- **STOP: Heinrich listens to the previews and picks.** Then run `--adopt` with his pick and confirm the test line sounds right.
- If the shared-library search yields no usable SA male voices, fall back to auditioning ElevenLabs premade voices with the closest register and flag this to Heinrich honestly

**Files affected:**

- `demos/jarvis/audition_voices.py` (new)
- `outputs/johan-voice-auditions/` (preview MP3s, `candidates.json`, `johan-test-line.mp3`)

---

### Step 3: ElevenLabs TTS in voice.py

Swap the speaking path; keep Deepgram STT and the Aura fallback.

**Actions:**

- Add constants: `ELEVENLABS_API_KEY` (from env), `ELEVEN_VOICE_ID` (from Step 2), `ELEVEN_MODEL = "eleven_flash_v2_5"`, `ELEVEN_SPEED = 1.1`, `ELEVEN_TTS_WORKERS = 2`
- New `_tts_elevenlabs(text) -> bytes`: sentence-chunk (reuse `_sentence_chunks`, same 140-char limit), synthesize chunks in parallel (2 workers) via `POST /v1/text-to-speech/{ELEVEN_VOICE_ID}?output_format=mp3_44100_128` with `voice_settings {stability: 0.5, similarity_boost: 0.75, speed: 1.1}`, concatenate MP3 bytes in order
- Rename the existing Aura implementation to `_tts_deepgram(text)` (unchanged behaviour, 6 workers)
- `text_to_speech(text)`: if `ELEVENLABS_API_KEY` and `ELEVEN_VOICE_ID` are set → try ElevenLabs; on any exception, print one line (`[johan] ElevenLabs TTS failed (<reason>) — falling back to Deepgram voice`) and use `_tts_deepgram`; if key absent → `_tts_deepgram` directly with a startup-style notice
- Update the module docstring (Johan's ears and mouth; STT Deepgram, TTS ElevenLabs with Aura fallback)
- Test with `?debug=1` text question or curl: response audio is the SA voice

**Files affected:**

- `demos/jarvis/voice.py`

---

### Step 4: Johan persona + JSON answer contract in brain.py

One rewrite covers both the persona and the card engine's brain side.

**Actions:**

- Rewrite `_system_prompt()`:
  - Identity: *Johan*, Meridian Manufacturing's AI — direct, confident, warm; South African English with light Afrikaans flavour ("ja", "nee", "lekker" where natural — not forced into every answer, never full Afrikaans sentences)
  - Length: **1–2 short punchy sentences, headline number first** (~25 spoken words max); the screen card carries the detail
  - Keep: query-before-answering rule, rounded spoken numbers, plain-English misses, SQL self-correction, schema description
  - New OUTPUT FORMAT section: final answer MUST be a single JSON object `{"say": "...", "card": {...} | null}` — no markdown, no code fences, no text outside the JSON; include the four card-type schemas with one worked example each (bar: revenue by quarter; table: pipeline deals with `highlight_row` for the stalled Transnet deal; stat: single headline number with `delta`; line: trend over quarters); rule: any answer containing numbers from the database should include a card, pure-conversation answers use `card: null`
- Add `_parse_answer(text) -> dict`: strip whitespace and accidental code fences; `json.loads`; validate `say` is a non-empty string and `card` is a dict or None; on any failure return `{"say": <full text>, "card": None}`
- `answer()` returns the parsed dict; the two hard-coded fallback strings ("I didn't catch that…", "I wasn't able to find…") become `{"say": ..., "card": None}`
- Update the "last query allowed" nudge text to demand the JSON format in 1–2 sentences
- Update module docstring

**Files affected:**

- `demos/jarvis/brain.py`

---

### Step 5: Server plumbing for cards + rename

**Actions:**

- `/api/ask`: `result = brain.answer(transcript, turns)`; synthesize speech from `result["say"]`; return `{"transcript", "answer": result["say"], "card": result["card"], "audio_b64"}` — `answer` stays the spoken string so browser history remains text-only
- `/api/health`: add `"elevenlabs_key": bool(voice.ELEVENLABS_API_KEY)`
- FastAPI title → `"BoschAI Johan Demo"`; startup log prefix `[jarvis]` → `[johan]`; docstring update
- `run.bat`: echo → `Starting BoschAI Johan Demo...`
- Test via curl with a text question: response JSON contains a sensible `card` for "How did we do this quarter?"

**Files affected:**

- `demos/jarvis/server.py`
- `demos/jarvis/run.bat`

---

### Step 6: Card renderer front end

**Actions:**

- `index.html`:
  - `<title>Johan — Meridian Manufacturing</title>`; orb aria-label → "Johan orb — hold to talk"; footer → "Meridian Manufacturing (Pty) Ltd · BoschAI Johan demo · all data fictional"
  - Add `<aside id="card-panel" class="hidden"><h3 id="card-title"></h3><div id="card-body"></div></aside>` inside `#stage`
  - Load `/static/vendor/chart.umd.js` then `/static/cards.js` as classic scripts, before the module scripts
- `static/cards.js` (classic script exposing `window.Cards`):
  - `Cards.show(spec)`: validate `spec.type` ∈ {bar, line, table, stat} and required fields per type (arrays same length, rows are arrays, etc.) — invalid specs log to console and are skipped, never thrown
  - bar/line → `<canvas>` in `#card-body`, Chart.js chart in Johan palette (cyan/blue on dark, no gridline clutter, ZAR-aware tick formatting when `unit` provided); destroy the previous Chart instance before creating a new one
  - table → HTML table; `highlight_row` gets an accent-glow row style
  - stat → big value + label + delta (delta green when starting with "+", red when "−"/"-")
  - Re-trigger the slide-in animation on each show; `Cards.clear()` hides the panel
- `static/style.css`:
  - Desktop: `#card-panel` ~400px wide, right of the orb (stage becomes a row at ≥1000px; orb + status stay visually centered-left), vertical-center; slide-in from right (`transform: translateX(40px)` + fade, ~450ms ease-out)
  - Narrow screens: panel full-width below the exchange text
  - Dark glassy card: `#0b111acc` background, 1px `#223044` border, 12px radius, backdrop blur; title in the muted cyan family already used
- `app.js`: on success, `if (data.card) Cards.show(data.card)` — card stays until the next question replaces it (clear on new `sendQuestion` only if a new card arrives; a null card leaves the previous one up, matching "stays on screen until the next question")
  - Decision within step: clear the old card when a *new answer* arrives with `card: null`? No — explore doc says card persists until next question; simplest faithful read: replace when a new card arrives, otherwise leave. Keep this behaviour.
- Test in browser with `?debug=1`: ask the four demo questions (quarter revenue → bar/stat, pipeline → table with Transnet highlight, trend → line, headcount → stat) and confirm each card renders and slides in

**Files affected:**

- `demos/jarvis/static/index.html`
- `demos/jarvis/static/cards.js` (new)
- `demos/jarvis/static/style.css`
- `demos/jarvis/static/app.js`

---

### Step 7: 3D energy orb

The polish pass — everything above must already work on the 2D orb before starting this.

**Actions:**

- Rename `static/orb.js` → `static/orb2d.js`; wrap the current IIFE into `export function createOrb2D(canvas)` returning `{setState, setLevel}` (same internals)
- Write `static/orb3d.js` (ES module):
  - `import * as THREE from './vendor/three.module.min.js'`; try WebGL renderer on the existing `#orb` canvas; on failure (`try/catch` around renderer creation) call `createOrb2D` and export that instead — one exported `Orb` object either way
  - Scene: transparent background over the page's dark space
  - **Core**: sphere with custom fresnel shader — bright white-blue rim, deep blue interior, emissive intensity driven by state + `smoothLevel`
  - **Particle field**: `THREE.Points` (~2,500 particles, additive blending, soft round sprite texture generated on a tiny canvas — no image assets); particles orbit on individual radii/speeds stored in buffer attributes, animated in the vertex shader or per-frame position update
  - **Glow**: 2–3 concentric additive sprite planes (radial gradient canvas textures) billboarded at the core — the fake bloom / lens-flare look
  - **Drift**: whole orb group floats on a slow Lissajous path (±3% of radius, ~9s period)
  - **States** (same smoothing approach as the 2D orb, eased transitions ~0.4s):
    - `idle` — slow particle orbit, gentle core breathing (4s), medium glow
    - `listening` — particles pull inward (orbit radii shrink 25%), core scale + glow pulse with `setLevel`
    - `thinking` — particle orbit speed ×4, hue shifts blue→violet, core shimmer
    - `speaking` — core flare + glow intensity driven by `setLevel`, particles pushed slightly outward on peaks
  - **Performance**: render at `min(devicePixelRatio, 2)`; FPS watchdog — if average FPS < 45 over 3s, halve particle count and drop one glow layer; `?lowfx=1` forces the low setting; keep total draw calls in single digits
  - Handle resize (existing CSS sizes the canvas; match renderer size to client size × DPR)
- `index.html`: `orb.js` script tag replaced by nothing (orb3d is imported by app.js); `app.js` becomes `<script type="module" src="/static/app.js">`
- `app.js`: add `import { Orb } from './orb3d.js'` at top (rest of the file already calls `Orb.*`)
- Test: all four states visibly distinct, mic level visibly drives listening/speaking, ~60fps in Chrome on this machine (check with the FPS meter in DevTools rendering tab), `?lowfx=1` works, and killing WebGL (e.g. temporary `throw` injected during test) lands on the 2D fallback

**Files affected:**

- `demos/jarvis/static/orb2d.js` (renamed + factory-wrapped from `orb.js`)
- `demos/jarvis/static/orb3d.js` (new)
- `demos/jarvis/static/index.html`
- `demos/jarvis/static/app.js`

---

### Step 8: End-to-end validation + docs

**Actions:**

- Full voice run-through of the film script questions: "How did we do this quarter?", "Which deals are stuck?", "What's our revenue trend?", "What did the exec meeting decide about the Durban plant?" — confirm: SA voice, 1–2 sentence answers, correct card each time, orb states tracking, total latency roughly 7–9s
- Confirm `/api/health` shows all three keys true
- Confirm demo works with no network beyond the three APIs (vendored files load from `/static/vendor/`)
- Temporarily rename `ELEVENLABS_API_KEY` in a shell env override (not by editing `.env`) or monkeypatch to verify the Deepgram fallback path still speaks
- Update `plans/explore-2026-07-05-johan-upgrade.md` status → `Built`; add a line to `plans/explore-2026-07-05-jarvis-voice-orb.md` noting Phase 2 fulfilled by the Johan upgrade
- Add `HISTORY.md` entry (Johan upgrade: ElevenLabs SA voice, persona, card engine, 3D orb; folder remains `demos/jarvis/`, port 8505)
- No CLAUDE.md change (demos aren't listed there — same call as Phase 1)

**Files affected:**

- `plans/explore-2026-07-05-johan-upgrade.md`
- `plans/explore-2026-07-05-jarvis-voice-orb.md`
- `HISTORY.md`

---

## Connections & Dependencies

### Files That Reference This Area

- `plans/2026-07-05-jarvis-phase1-voice-loop.md` — Phase 1 plan (unchanged; historical record)
- `plans/explore-2026-07-05-jarvis-voice-orb.md` — original phased vision; its Phase 2 is fulfilled here
- Memory `project_jarvis_demo.md` — describes Phase 1 state; update after implementation (Johan live, Phase 2 done)
- `data/jarvis_demo.db` — untouched; seeder, schema, guardrails all unchanged

### Updates Needed for Consistency

- Explore doc statuses (both), `HISTORY.md`, memory file `project_jarvis_demo.md` (post-implementation)
- `outputs/johan-voice-auditions/candidates.json` gets real content in Step 2

### Impact on Existing Workflows

- None on other demos (isolated folder + port). `/video` and `/slides` workflows gain their hero subject once this is filmable. The `.env` gains one key; existing keys untouched. The `/api/ask` response adds a field — no consumer other than `app.js` exists.

---

## Validation Checklist

- [ ] `run.bat` starts clean; browser opens to Johan page; no console errors
- [ ] `/api/health` → `ok, db_seeded, anthropic_key, deepgram_key, elevenlabs_key` all true
- [ ] Voice question end-to-end: SA-accented fast voice answers in 1–2 sentences
- [ ] Each of the four card types renders correctly at least once (bar, line, table with highlight, stat)
- [ ] Malformed/absent card never breaks the spoken answer (verified via a conversational question → `card: null`)
- [ ] 3D orb: four states visibly distinct; level-reactive in listening/speaking; floating drift visible
- [ ] ~60fps on this laptop; `?lowfx=1` reduces load; FPS watchdog degrades gracefully
- [ ] WebGL-failure path lands on the 2D orb and everything else still works
- [ ] Missing-ElevenLabs-key path falls back to Deepgram voice with a plain-English notice
- [ ] Works offline except the three APIs (no CDN requests in the Network tab)
- [ ] Explore docs + HISTORY.md updated

## Success Criteria

The implementation is complete when:

1. Heinrich can hold the orb, ask "How did we do this quarter?", and hear Johan answer in a fast South African voice within ~7–9 seconds while a revenue card slides in beside a floating 3D energy orb
2. All four film-script questions produce correct spoken answers + correct cards, repeatably
3. The demo degrades gracefully on every failure path (no ElevenLabs key, WebGL unavailable, malformed card) — it can never die on camera

## Notes

- **The one manual step**: Heinrich creates the free ElevenLabs account and adds `ELEVENLABS_API_KEY` to `.env`. Free tier ≈ 10 min of speech/month — enough to build and audition; filming day may need the $5 starter tier.
- Build order is deliberately MVP-first: if the 3D orb (Step 7) runs long, Steps 1–6 already deliver the voice + persona + cards upgrade on the 2D orb — independently filmable.
- The ElevenLabs shared-voices API surface (v1 vs v2 path, filter params) varies; the audition script should be defensive and fall back to broad search + client-side accent filtering. If no good SA male voice exists in the library, surface that honestly and audition closest-register premade voices instead.
- Future (out of scope, noted in explore doc): tabbed command-centre dashboard evolving from the cards, wake word, streaming TTS, real-data connectors, report writer.
- ElevenLabs doubles as the testbed for the "voice API" primitive on the API-primitives list — worth noting results there after filming.
