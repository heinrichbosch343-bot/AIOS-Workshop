# Plan: Deepgram Meeting Intelligence Demo Dashboard

**Created:** 2026-06-25
**Status:** Implemented 2026-06-25 (code corrected to Deepgram SDK v7 — see Build Notes)
**Request:** Build a Deepgram speech-to-text demo dashboard for LinkedIn — same Streamlit pattern as the invoice and drive demos. Upload a meeting audio file, get a speaker-labeled transcript, AI summary, and action items. Story: "Every conversation works for you after it ends."

---

## ⚠️ Build Notes — corrections applied during implementation (2026-06-25)

**The code blocks in the step-by-step section below were written against the OLD Deepgram SDK and are superseded.** The live files in `demos/meeting-intelligence/` are the source of truth. What changed once the current SDK was verified by installing it (7.3.1) and introspecting the real API:

- **SDK is v7, not v2/v3.** `PrerecordedOptions`, `BufferSource`, `client.listen.prerecorded.v("1")`, and `client.speak.v("1").stream_memory()` do not exist. The real calls are:
  - STT: `client.listen.v1.media.transcribe_file(request=<bytes>, model="nova-3", diarize=True, utterances=True, punctuate=True, smart_format=True)` — kwargs, not an options object. Audio format is auto-detected, so **no mimetype is passed**.
  - Read back: `response.results.utterances[*]` → `.speaker` (int, 0-based), `.transcript`, `.start`, `.end`; `response.metadata.duration` (float).
  - TTS: `client.speak.v1.audio.generate(text=..., model="aura-2-apollo-en"|"aura-2-asteria-en", encoding="linear16", container="wav", sample_rate=24000)` → returns `Iterator[bytes]`, so `b"".join(...)`.
- **Model is nova-3** (newest/most accurate), not nova-2.
- **Voices are aura-2** (`aura-2-apollo-en` male, `aura-2-asteria-en` female), not the aura-1 names.
- **pydub + ffmpeg dropped entirely.** TTS emits `container="wav"`, so segments are stitched with Python's built-in `wave` module. `requirements.txt` is just `deepgram-sdk`, `streamlit`, `anthropic`, `python-dotenv`.
- **Demo audio is `demo_meeting.wav`** (not `.mp3`) as a result.
- **Environment:** `deepgram-sdk` was installed into the project `.venv` (the runtime the other demos use). The global Python310 also has it. Run everything via `.venv/Scripts/python`.
- **Verified without a key:** all three modules byte-compile; a smoke test confirms the SDK call paths and voice names resolve against 7.3.1; the dashboard boots headless on 8504 and serves its health check. The only step needing the live key is generating the demo audio + a real transcription (see Step 7).

---

## Overview

### What This Plan Accomplishes

A new Streamlit dashboard at `demos/meeting-intelligence/` (port 8504) that takes an uploaded audio file, sends it to Deepgram for speaker-diarized transcription, then runs the transcript through Claude to extract a meeting summary and action items — all displayed in a clean two-column layout identical in visual style to the existing drive and invoice demos. A companion `generate_demo.py` script auto-generates a realistic two-speaker fake meeting using Deepgram Aura TTS so the demo audio is ready before filming.

### Why This Matters

This is the third LinkedIn demo in the API-primitives series. The Drive demo showed "ask your documents." The invoice demo showed "kill data entry." This one shows "never lose what was said in a meeting" — a pain every business owner recognises instantly. The Deepgram $200 free credit covers hundreds of hours of audio; the whole demo costs nothing to build.

---

## Current State

### Relevant Existing Structure

```
demos/
  drive-intelligence/
    dashboard.py          # Port 8502 — ask your Drive in plain English
  invoice-extraction/
    dashboard.py          # Port 8503 — invoices → spreadsheet
    invoice_extract.py    # LlamaParse backend logic
    generate_samples.py   # Generates fake PDF invoices
    generate_bulk.py      # Bulk generates 100 invoices
    warm_cache.py         # Pre-warms the extraction cache
    requirements.txt
```

**Design pattern both demos follow:**
- Dark theme: `#02040e` background, blue grid overlay, `Space Grotesk` + `JetBrains Mono` fonts
- Centred layout, `max-width: 760–880px`
- Monospaced eyebrow → large title → subtitle tagline → `hdr-line` divider
- Idle state with symbolic placeholder (◈ ◈ ◈ / ▦ ▦ ▦) and mono hint text
- `@st.cache_resource` for heavy one-time setup, `@st.cache_data` for per-file results
- Backend logic lives in a separate module (`invoice_extract.py`), not inline in `dashboard.py`
- A seed/generate script produces the demo data before filming

**Environment:**
- `.env` in workspace root holds all API keys
- `dotenv` loads it by walking up from `__file__`
- `ANTHROPIC_API_KEY` already present
- `DEEPGRAM_API_KEY` — needs to be added

### Gaps or Problems Being Addressed

- No audio/transcription demo exists yet
- No Deepgram integration anywhere in the workspace
- The LinkedIn content gap between the invoice demo and the next module needs filling

---

## Proposed Changes

### Summary of Changes

- Create `demos/meeting-intelligence/` with four files: `dashboard.py`, `transcribe.py`, `generate_demo.py`, `requirements.txt`
- Add `DEEPGRAM_API_KEY=` to `.env` (user fills in the value)
- Add `demos/meeting-intelligence/demo_meeting.mp3` to `.gitignore` (generated, not committed)

### New Files to Create

| File Path | Purpose |
|-----------|---------|
| `demos/meeting-intelligence/dashboard.py` | Streamlit UI — upload audio, show transcript + summary + actions |
| `demos/meeting-intelligence/transcribe.py` | Deepgram STT wrapper + Claude post-processor (summary + action items) |
| `demos/meeting-intelligence/generate_demo.py` | Generates `demo_meeting.mp3` via Deepgram Aura TTS — two speakers, realistic meeting script |
| `demos/meeting-intelligence/requirements.txt` | `deepgram-sdk`, `streamlit`, `anthropic`, `python-dotenv`, `pydub` |

### Files to Modify

| File Path | Changes |
|-----------|---------|
| `.env` | Add `DEEPGRAM_API_KEY=` placeholder line |
| `.gitignore` | Add `demos/meeting-intelligence/demo_meeting.mp3` |

---

## Design Decisions

### Key Decisions Made

1. **Symbol ◎** — follows ◈ (drive) and ▦ (invoice). Circle fits "recording / loop / capture."
2. **Two-column layout after processing** — left 60% = scrollable transcript with speaker labels, right 40% = summary card + action items. Viewer sees the transformation in one glance.
3. **Metrics row above columns** — Duration · Speakers detected · Words captured. Three numbers that prove the system worked, visible immediately.
4. **"LOG TO CRM" is a demo-mode toast** — shows a realistic success message and a preview of what would be written (speaker count, action count, duration). No real Supabase write; the point is the story, not the plumbing. Keeps the demo self-contained.
5. **Deepgram Nova-3 model with diarize + utterances** — Nova-3 is Deepgram's newest/most accurate general model (corrected from Nova-2). `diarize=True` gives speaker IDs. `utterances=True` gives pre-chunked speaker turns — this is what drives the transcript display, not raw words.
6. **Claude Haiku for post-processing** — summary and action items don't need deep reasoning; Haiku is fast and cheap, which matters when the demo is on camera and the viewer is watching a spinner.
7. **Deepgram Aura-2 TTS for `generate_demo.py`** — two voices (`aura-2-apollo-en` male, `aura-2-asteria-en` female), WAV segments stitched with the built-in `wave` module (no pydub/ffmpeg). Generates a ~2-minute fake client discovery call. Uses a tiny fraction of the $200 free credit.
8. **Port 8504** — follows the established sequence (8502 drive, 8503 invoice).
9. **Accepted audio formats: mp3, wav, m4a, mp4, ogg, webm** — covers everything a phone or Zoom export would produce.

### Alternatives Considered

- **Real-time streaming transcription** — Deepgram supports WebSocket streaming. Rejected for now; batch mode is simpler, camera-friendly, and the ~10-second wait is actually a good "wow moment" beat.
- **Actual Supabase CRM write** — rejected; requires the full BoschAI backend running. The demo should work standalone on any machine with just a Deepgram key.
- **Third-party meeting recording (Otter, Fireflies)** — not applicable; we're building the primitive, not comparing to it.
- **AssemblyAI** — also excellent and free-tier, but Deepgram's $200 no-expiry credit is more generous and the SDK is slightly simpler. Either works.

### Open Questions

None — all decisions are locked. If the user wants to add a real Supabase write later, that's a one-function swap in `transcribe.py`.

---

## Step-by-Step Tasks

### Step 1: Add Deepgram API key to .env

Add a placeholder line to `.env` so the user knows to fill it in. The key comes from [console.deepgram.com](https://console.deepgram.com) — free account, $200 credit, no card.

**Actions:**
- Read `.env`, append `DEEPGRAM_API_KEY=` as a new line (leave value blank for user to fill)
- Read `.gitignore`, add `demos/meeting-intelligence/demo_meeting.mp3` under the existing demo ignores (or create a demo section)

**Files affected:**
- `.env`
- `.gitignore`

---

### Step 2: Create requirements.txt

**Actions:**
- Create `demos/meeting-intelligence/requirements.txt` with exact content below

```
deepgram-sdk>=3.4
streamlit>=1.35
anthropic>=0.28
python-dotenv>=1.0
pydub>=0.25
```

**Note:** `pydub` is only needed by `generate_demo.py` (audio stitching). It also requires `ffmpeg` to be available on PATH for MP3 handling. Add a comment to `generate_demo.py` noting this.

**Files affected:**
- `demos/meeting-intelligence/requirements.txt`

---

### Step 3: Build transcribe.py — Deepgram STT + Claude post-processor

This is the backend module, mirroring `invoice_extract.py`. It exposes two clean functions that `dashboard.py` calls.

**Actions:**
- Create `demos/meeting-intelligence/transcribe.py` with the following structure:

```python
"""
Meeting Intelligence — Deepgram STT + Claude post-processor.

transcribe(audio_bytes, mime_type) -> TranscriptResult
    Sends audio to Deepgram Nova-2 with speaker diarization.
    Returns utterances (speaker-labeled turns), duration, speaker count, word count.

summarise(transcript_text) -> SummaryResult
    Sends the plain transcript to Claude Haiku.
    Returns a 2-3 sentence summary + a list of action items.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Walk up to workspace root to load .env
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SPEAKER_LABELS = [
    "Speaker 1", "Speaker 2", "Speaker 3",
    "Speaker 4", "Speaker 5", "Speaker 6",
]


@dataclass
class Utterance:
    speaker: str        # e.g. "Speaker 1"
    text: str
    start: float        # seconds
    end: float


@dataclass
class TranscriptResult:
    utterances: List[Utterance]
    duration_seconds: float
    speaker_count: int
    word_count: int

    @property
    def plain_text(self) -> str:
        return "\n".join(f"{u.speaker}: {u.text}" for u in self.utterances)


@dataclass
class SummaryResult:
    summary: str
    action_items: List[str] = field(default_factory=list)


def transcribe(audio_bytes: bytes, mime_type: str = "audio/mp3") -> TranscriptResult:
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY is missing from .env")

    from deepgram import DeepgramClient, PrerecordedOptions, BufferSource

    client = DeepgramClient(DEEPGRAM_API_KEY)
    source = BufferSource(buffer=audio_bytes, mimetype=mime_type)
    options = PrerecordedOptions(
        model="nova-2",
        diarize=True,
        punctuate=True,
        utterances=True,
        smart_format=True,
    )
    response = client.listen.prerecorded.v("1").transcribe_file(source, options)

    raw_utterances = response.results.utterances or []
    speakers_seen = set()
    utterances = []
    for u in raw_utterances:
        label = SPEAKER_LABELS[u.speaker] if u.speaker < len(SPEAKER_LABELS) else f"Speaker {u.speaker + 1}"
        speakers_seen.add(label)
        utterances.append(Utterance(
            speaker=label,
            text=u.transcript.strip(),
            start=u.start,
            end=u.end,
        ))

    # Word count from the main channel alternative
    try:
        words = response.results.channels[0].alternatives[0].words or []
        word_count = len(words)
    except Exception:
        word_count = sum(len(u.text.split()) for u in utterances)

    duration = response.metadata.duration if response.metadata else (
        utterances[-1].end if utterances else 0.0
    )

    return TranscriptResult(
        utterances=utterances,
        duration_seconds=duration,
        speaker_count=len(speakers_seen),
        word_count=word_count,
    )


def summarise(transcript_text: str) -> SummaryResult:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is missing from .env")

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=(
            "You are a meeting assistant. Given a meeting transcript, return a JSON object with two keys:\n"
            "- \"summary\": a 2-3 sentence plain-English summary of what was discussed and decided.\n"
            "- \"action_items\": a list of strings, each one a concrete next action identified in the meeting.\n"
            "Return ONLY valid JSON. No markdown, no explanation."
        ),
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript_text}"}],
    )

    import json
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    # Strip markdown code fences if the model adds them
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    data = json.loads(text)

    return SummaryResult(
        summary=data.get("summary", ""),
        action_items=data.get("action_items", []),
    )
```

**Files affected:**
- `demos/meeting-intelligence/transcribe.py`

---

### Step 4: Build generate_demo.py — two-speaker fake meeting via Deepgram TTS

This script is run once before filming to produce `demo_meeting.mp3`. It writes a realistic 2-minute discovery call script, then generates each speaker turn as audio using Deepgram Aura TTS, and stitches them together with `pydub`.

**Actions:**
- Create `demos/meeting-intelligence/generate_demo.py` with the following structure:

```python
"""
Generates demo_meeting.mp3 — a fake 2-minute business discovery call
between Heinrich (BoschAI) and a prospect (Sarah, ops manager).

Uses Deepgram Aura TTS: aura-orion-en (Heinrich), aura-asteria-en (Sarah).
Requires: DEEPGRAM_API_KEY in .env, pydub, ffmpeg on PATH.

Run once before filming:
    python generate_demo.py
"""

import io
import os
from pathlib import Path
from dotenv import load_dotenv

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
OUT = Path(__file__).parent / "demo_meeting.mp3"

# Conversation script: (voice_id, text)
# aura-orion-en  = male  (Heinrich)
# aura-asteria-en = female (Sarah, prospect)
SCRIPT = [
    ("aura-orion-en",   "Hi Sarah, thanks for making the time. I just wanted to understand a bit about how your team currently handles meeting notes and follow-ups."),
    ("aura-asteria-en", "Sure, no problem. Honestly it's a bit of a mess right now. We record most of our calls but nobody ever goes back and listens to them. The notes end up in random Slack messages."),
    ("aura-orion-en",   "That's really common. How many calls a week would you say you're having where something important gets decided or a task comes out of it?"),
    ("aura-asteria-en", "Probably fifteen to twenty. And at least half of them — something falls through the cracks. We had a supplier meeting last month where we agreed on a price, and then two weeks later nobody could remember what we actually said."),
    ("aura-orion-en",   "So the cost there is time to reconstruct the conversation, and sometimes the deal or the relationship. What does your team do right now as a workaround?"),
    ("aura-asteria-en", "Someone manually types up notes after each meeting. It takes about twenty minutes per call, and it's always incomplete because they're also in the meeting trying to listen."),
    ("aura-orion-en",   "What if the recording just became the notes automatically — with every speaker identified, a summary of what was decided, and the actions already pulled out?"),
    ("aura-asteria-en", "That would be amazing. That's basically what we need. Can it also push those action items into our project management tool?"),
    ("aura-orion-en",   "Yes, that's the next layer. The transcription and intelligence is the foundation. Once the data is structured, routing it anywhere — your CRM, your task board, a Slack message — is straightforward."),
    ("aura-asteria-en", "Okay, I'm interested. What does this actually look like in practice?"),
    ("aura-orion-en",   "It looks like what I'm about to show you. You upload a recording, or later we can set it to pull automatically from your recording tool. Then you get a speaker-by-speaker transcript, a one-paragraph summary, and a clean action item list — all in about thirty seconds."),
    ("aura-asteria-en", "Let's see it."),
]


def tts_segment(voice: str, text: str) -> bytes:
    """Generate one audio segment via Deepgram Aura TTS. Returns MP3 bytes."""
    from deepgram import DeepgramClient, SpeakOptions
    client = DeepgramClient(DEEPGRAM_API_KEY)
    options = SpeakOptions(model=voice, encoding="mp3")
    response = client.speak.v("1").stream_memory({"text": text}, options)
    # response.stream is a BytesIO-like object
    buf = io.BytesIO()
    for chunk in response.stream:
        buf.write(chunk)
    buf.seek(0)
    return buf.read()


def build_audio():
    from pydub import AudioSegment

    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY missing from .env")

    print(f"Generating {len(SCRIPT)} segments...")
    combined = AudioSegment.empty()
    silence_between = AudioSegment.silent(duration=400)   # 400 ms gap between turns

    for i, (voice, text) in enumerate(SCRIPT):
        print(f"  [{i+1}/{len(SCRIPT)}] {voice[:12]}... '{text[:50]}...'")
        mp3_bytes = tts_segment(voice, text)
        seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
        combined += seg + silence_between

    combined.export(OUT, format="mp3")
    duration = len(combined) / 1000
    print(f"\nSaved: {OUT}  ({duration:.0f}s / {len(combined)//1000//60}m {len(combined)//1000%60}s)")


if __name__ == "__main__":
    build_audio()
```

**Files affected:**
- `demos/meeting-intelligence/generate_demo.py`

---

### Step 5: Build dashboard.py — the Streamlit UI

This is the main file. Mirrors the invoice dashboard's structure exactly: same CSS variables, same idle state, same button style, same `@st.cache_data` pattern.

**Layout spec (post-processing):**

```
[HEADER]
◎  AIOS · Meeting Intelligence
"Drop a meeting recording.
 Get your minutes."
speakers detected · transcribed · nothing missed
[hdr-line]

[File uploader — audio formats]
[TRANSCRIBE button — disabled until file uploaded]

--- after processing ---

[Metrics row]
  | 2:14        | 2          | 412         |
  | duration    | speakers   | words       |

[Two columns 60/40]
LEFT: TRANSCRIPT                    RIGHT: SUMMARY
  Speaker 1: Hello Sarah...           [2-3 sentences]
  Speaker 2: Thanks for...
  Speaker 1: So tell me...          ACTION ITEMS
  ...                                 ○ Book follow-up call
  (scrollable, max-height 380px)      ○ Send pricing deck
                                      ○ Check integration spec

[LOG TO CRM button — full width]

--- idle ---
◎  ◎  ◎
drop a recording · transcribe · get your minutes
```

**Actions:**
- Create `demos/meeting-intelligence/dashboard.py` with full implementation

Full content of `dashboard.py`:

```python
"""
AIOS · Meeting Intelligence — Deepgram demo.
Drop a meeting recording, get a speaker-labeled transcript, summary, and action items.
"""
import hashlib
import io
import math

import streamlit as st
import transcribe as tx

st.set_page_config(
    page_title="AIOS · Meeting Intelligence",
    page_icon="◎",
    layout="centered",
    initial_sidebar_state="collapsed",
)

MIME_MAP = {
    "mp3": "audio/mp3",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
}

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500&display=swap');
*, *::before, *::after { box-sizing: border-box; }
html, body, [class*="css"] { font-family: 'Space Grotesk', sans-serif; background: #02040e !important; color: #c8d8f8; }
.stApp { background: #02040e !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 0 !important; max-width: 900px !important; }
.stApp::before {
    content: ''; position: fixed; inset: 0;
    background-image: linear-gradient(rgba(37,99,235,0.035) 1px, transparent 1px),
                      linear-gradient(90deg, rgba(37,99,235,0.035) 1px, transparent 1px);
    background-size: 52px 52px; pointer-events: none; z-index: 0;
}

/* Header */
.hdr { padding: 56px 0 30px; text-align: center; }
.hdr-mono { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 5px; text-transform: uppercase; color: #1d4ed8; margin-bottom: 20px; }
.hdr-title { font-size: 46px; font-weight: 700; color: #f0f6ff; letter-spacing: -2px; line-height: 1.08; margin-bottom: 14px; }
.hdr-title .g { background: linear-gradient(100deg, #3b82f6 0%, #818cf8 60%, #c084fc 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }
.hdr-sub { font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #1e3a6e; letter-spacing: 1.5px; }
.hdr-line { width: 1px; height: 34px; background: linear-gradient(to bottom, transparent, #1d4ed8, transparent); margin: 26px auto 30px; }

/* Uploader */
.stFileUploader label { font-family: 'JetBrains Mono', monospace !important; font-size: 9px !important; letter-spacing: 3px !important; text-transform: uppercase !important; color: #1e3a6e !important; }
.stFileUploader > div { background: #030712 !important; border: 1px dashed #1d4ed8 !important; border-radius: 4px !important; }

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #1d4ed8 0%, #4f46e5 100%) !important; border: none !important; border-radius: 3px !important;
    color: #e0eaff !important; font-family: 'JetBrains Mono', monospace !important; font-size: 11px !important; letter-spacing: 4px !important;
    text-transform: uppercase !important; padding: 14px 0 !important; width: 100%; box-shadow: 0 0 32px rgba(29,78,216,0.25);
}
.stButton > button:hover { box-shadow: 0 0 48px rgba(29,78,216,0.4) !important; }
.stButton > button:disabled { opacity: 0.2 !important; box-shadow: none !important; }

/* Metrics */
.metrics { display: flex; gap: 14px; margin: 30px 0 24px; }
.metric { flex: 1; background: #030712; border: 1px solid #0d1e42; border-top: 2px solid #1d4ed8; border-radius: 3px; padding: 18px; text-align: center; }
.metric .v { font-size: 26px; font-weight: 700; color: #f0f6ff; letter-spacing: -1px; }
.metric .l { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 2.5px; text-transform: uppercase; color: #3b82f6; margin-top: 5px; }

/* Section tags */
.tag { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 4px; text-transform: uppercase; color: #3b82f6; margin: 0 0 10px; }

/* Transcript panel */
.transcript-box {
    background: #030712; border: 1px solid #0d1e42; border-top: 2px solid #1d4ed8;
    border-radius: 3px; padding: 20px 22px; height: 380px; overflow-y: auto;
    font-size: 13px; line-height: 1.9; color: #7090c8;
}
.spk { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 2px; color: #3b82f6; text-transform: uppercase; margin-right: 8px; }

/* Summary + actions panel */
.summary-card {
    background: #030712; border: 1px solid #0d1e42; border-top: 2px solid #1d4ed8;
    border-radius: 3px; padding: 20px 22px; font-size: 13px; line-height: 1.9; color: #7090c8;
    margin-bottom: 14px;
}
.actions-card {
    background: #030712; border: 1px solid #0d1e42; border-top: 2px solid #4f46e5;
    border-radius: 3px; padding: 20px 22px;
}
.action-item { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; font-size: 13px; color: #7090c8; line-height: 1.6; }
.action-dot { font-size: 10px; color: #4f46e5; margin-top: 4px; flex-shrink: 0; }

/* CRM button (green-ish override) */
.crm-btn > button {
    background: linear-gradient(135deg, #065f46 0%, #064e3b 100%) !important;
    box-shadow: 0 0 32px rgba(16,185,129,0.12) !important;
}
.crm-btn > button:hover { box-shadow: 0 0 48px rgba(16,185,129,0.25) !important; }

/* Idle */
.idle { text-align: center; padding: 60px 0; }
.idle-sym { font-family: 'JetBrains Mono', monospace; font-size: 22px; letter-spacing: 12px; color: #0a1428; margin-bottom: 18px; }
.idle-hint { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: 2.5px; color: #0d1e3a; text-transform: uppercase; }
</style>
""", unsafe_allow_html=True)

# ── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hdr">
  <div class="hdr-mono">◎ &nbsp; A I O S &nbsp; · &nbsp; M e e t i n g &nbsp; I n t e l l i g e n c e</div>
  <div class="hdr-title">Drop a meeting recording.<br><span class="g">Get your minutes.</span></div>
  <p class="hdr-sub">speakers detected &nbsp;·&nbsp; transcribed &nbsp;·&nbsp; nothing missed</p>
</div>
<div class="hdr-line"></div>
""", unsafe_allow_html=True)


# ── Cached processing ────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def process_audio(file_hash: str, audio_bytes: bytes, mime_type: str):
    result = tx.transcribe(audio_bytes, mime_type)
    summary = tx.summarise(result.plain_text)
    return result, summary


# ── Upload + button ──────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Drop a recording here (mp3, wav, m4a, mp4, ogg, webm)",
    type=list(MIME_MAP.keys()),
    label_visibility="visible",
)

go = st.button("TRANSCRIBE", use_container_width=True, disabled=not uploaded)

# ── Process + render ─────────────────────────────────────────────────────────
if go and uploaded:
    audio_bytes = uploaded.getvalue()
    ext = uploaded.name.rsplit(".", 1)[-1].lower()
    mime = MIME_MAP.get(ext, "audio/mp3")
    fhash = hashlib.md5(audio_bytes).hexdigest()

    with st.spinner("Transcribing your recording…"):
        transcript, summary = process_audio(fhash, audio_bytes, mime)

    # Metrics row
    mins = int(transcript.duration_seconds // 60)
    secs = int(transcript.duration_seconds % 60)
    dur_str = f"{mins}:{secs:02d}"
    st.markdown(f"""
<div class="metrics">
  <div class="metric"><div class="v">{dur_str}</div><div class="l">duration</div></div>
  <div class="metric"><div class="v">{transcript.speaker_count}</div><div class="l">speakers</div></div>
  <div class="metric"><div class="v">{transcript.word_count:,}</div><div class="l">words captured</div></div>
</div>
""", unsafe_allow_html=True)

    # Two columns: transcript | summary + actions
    col_left, col_right = st.columns([6, 4], gap="medium")

    with col_left:
        st.markdown('<div class="tag">transcript</div>', unsafe_allow_html=True)
        lines_html = "".join(
            f'<div><span class="spk">{u.speaker}</span>{u.text}</div>'
            for u in transcript.utterances
        )
        st.markdown(f'<div class="transcript-box">{lines_html}</div>', unsafe_allow_html=True)

    with col_right:
        st.markdown('<div class="tag">summary</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="summary-card">{summary.summary}</div>', unsafe_allow_html=True)

        st.markdown('<div class="tag" style="margin-top:18px">action items</div>', unsafe_allow_html=True)
        items_html = "".join(
            f'<div class="action-item"><span class="action-dot">◉</span><span>{item}</span></div>'
            for item in summary.action_items
        ) or '<div style="color:#1e3a6e;font-size:12px;">No action items detected.</div>'
        st.markdown(f'<div class="actions-card">{items_html}</div>', unsafe_allow_html=True)

    # Log to CRM button
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="crm-btn">', unsafe_allow_html=True)
    crm = st.button("LOG TO CRM", use_container_width=True, key="crm")
    st.markdown('</div>', unsafe_allow_html=True)

    if crm:
        fname = uploaded.name.rsplit(".", 1)[0].replace("_", " ").title()
        st.success(
            f"✓  Meeting logged — {fname} · {transcript.speaker_count} speakers · "
            f"{len(summary.action_items)} action items · {dur_str}"
        )
        with st.expander("Preview CRM entry", expanded=True):
            st.json({
                "title": fname,
                "duration": dur_str,
                "speakers": transcript.speaker_count,
                "summary": summary.summary,
                "action_items": summary.action_items,
                "transcript_preview": transcript.utterances[0].text[:120] + "..." if transcript.utterances else "",
            })

else:
    st.markdown("""
<div class="idle">
  <div class="idle-sym">◎ &nbsp; ◎ &nbsp; ◎</div>
  <div class="idle-hint">drop a recording &nbsp;·&nbsp; transcribe &nbsp;·&nbsp; get your minutes</div>
</div>
""", unsafe_allow_html=True)
```

**Files affected:**
- `demos/meeting-intelligence/dashboard.py`

---

### Step 6: Update .env and .gitignore

**Actions:**
- Read `.env` → append `DEEPGRAM_API_KEY=` (blank for user to fill)
- Read `.gitignore` → add `demos/meeting-intelligence/demo_meeting.mp3` (generated audio not committed)

**Files affected:**
- `.env`
- `.gitignore`

---

### Step 7: Run generate_demo.py to produce the demo audio

Before filming, the user runs this once to create `demo_meeting.mp3`.

**Actions:**
- Ensure `DEEPGRAM_API_KEY` is filled in `.env`
- Install requirements: `pip install -r demos/meeting-intelligence/requirements.txt`
- Ensure `ffmpeg` is on PATH (needed by pydub for MP3 export). Install via `winget install FFmpeg` or `choco install ffmpeg`
- Run: `cd demos/meeting-intelligence && python generate_demo.py`
- Verify `demo_meeting.mp3` appears and is ~2 minutes long

---

### Step 8: Boot the dashboard and verify end-to-end

**Actions:**
- Run: `streamlit run demos/meeting-intelligence/dashboard.py --server.port 8504`
- Open browser at `http://localhost:8504`
- Upload `demo_meeting.mp3`
- Click TRANSCRIBE — verify:
  - Metrics row shows correct duration, 2 speakers, word count
  - Transcript column shows "Speaker 1" / "Speaker 2" turns
  - Summary is coherent 2-3 sentences
  - Action items list is populated (should be 3-5 items from the script)
- Click LOG TO CRM — verify success toast + JSON expander appears
- Test idle state (load without file) — verify ◎ ◎ ◎ placeholder shows

---

### Step 9: Film the LinkedIn demo

**Filming flow (2-3 minutes on camera):**
1. Open dashboard at `http://localhost:8504` — show idle state briefly
2. Drop `demo_meeting.mp3` into the uploader
3. Click TRANSCRIBE — let the spinner run (~10–15 seconds)
4. Camera close-up on the metrics row first (Duration · Speakers · Words)
5. Scroll the transcript a little — show speaker labels
6. Point to Summary card — "This is the whole call in three sentences"
7. Point to Action Items — "Every task, already pulled out"
8. Click LOG TO CRM — show the green toast + JSON entry
9. Cut. Voiceover/caption: "Every conversation works for you after it ends."

---

## Connections & Dependencies

### Files That Reference This Area

- `CLAUDE.md` — workspace overview (no specific demo references, but structure section documents `demos/` — no update needed)
- `reference/api-primitives-to-build-on.md` — Deepgram is primitive #2; this build delivers on that plan
- Memory: `project_api_primitives.md` — tracks the 5 primitives; update after build to mark Deepgram as done

### Updates Needed for Consistency

- `reference/api-primitives-to-build-on.md` — optionally add a "Status: built" note next to Deepgram after the demo is filmed
- `C:\Users\gamin\.claude\projects\...\memory\project_api_primitives.md` — update to reflect Deepgram demo built

### Impact on Existing Workflows

None. The demo is fully self-contained in `demos/meeting-intelligence/`. It does not touch the BoschAI backend, Supabase, or Railway.

---

## Validation Checklist

- [ ] `demos/meeting-intelligence/` folder exists with all four files
- [ ] `DEEPGRAM_API_KEY=` line present in `.env`
- [ ] `demos/meeting-intelligence/demo_meeting.mp3` listed in `.gitignore`
- [ ] `pip install -r demos/meeting-intelligence/requirements.txt` completes without error
- [ ] `python generate_demo.py` produces `demo_meeting.mp3` (~2 minutes)
- [ ] `streamlit run dashboard.py --server.port 8504` boots without error
- [ ] Uploading `demo_meeting.mp3` and clicking TRANSCRIBE shows metrics, transcript, summary, and action items
- [ ] Transcript shows "Speaker 1" and "Speaker 2" labels (diarization working)
- [ ] Action items list is non-empty
- [ ] LOG TO CRM button shows success toast and JSON preview
- [ ] Idle state (no file uploaded) shows ◎ ◎ ◎ placeholder

---

## Success Criteria

The implementation is complete when:

1. `streamlit run demos/meeting-intelligence/dashboard.py --server.port 8504` boots and the idle state renders correctly
2. Uploading the generated `demo_meeting.mp3` produces a speaker-labeled transcript with summary and action items in under 20 seconds
3. The dashboard is visually indistinguishable in style from the drive and invoice demos — same fonts, same dark theme, same metric card pattern
4. The LOG TO CRM interaction shows a complete, realistic CRM entry preview in the expander

---

## Notes

- **Cost estimate:** Generating `demo_meeting.mp3` (TTS, ~2 min) costs ~$0.06 from the $200 free credit. Transcribing it (STT) costs ~$0.03. Total demo cost: under $0.10.
- **If ffmpeg is not available:** pydub can export WAV without ffmpeg. Change `generate_demo.py` to export `demo_meeting.wav` instead of `.mp3` and update the uploader accept list accordingly.
- **Future upgrade — streaming:** Deepgram's WebSocket API enables real-time word-by-word transcript display. That would make the transcription step more dramatic on camera. Not in scope now, but `transcribe.py` is structured so a `transcribe_stream()` function could be added alongside `transcribe()` without changing the dashboard logic.
- **Next primitive after this:** Nixtla/TimeGPT (#5) — the farming dashboard for Connie. Same LinkedIn demo pattern, but the "wow moment" is showing a demand forecast chart instead of a transcript.
