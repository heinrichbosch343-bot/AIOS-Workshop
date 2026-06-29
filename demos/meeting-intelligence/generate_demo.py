"""
Generate demo_meeting.wav — a ~2-minute fake discovery call between
Heinrich (BoschAI) and a prospect (Sarah, an ops manager).

Run this ONCE before filming:
    .venv/Scripts/python demos/meeting-intelligence/generate_demo.py

How it works:
  - Each line is synthesised with Deepgram Aura-2 TTS (one male voice, one female voice).
  - Segments are stitched into a single WAV with Python's built-in `wave` module —
    no pydub, no ffmpeg. Every segment is linear16 / mono / 24 kHz, so the frames
    concatenate cleanly with a short silence between turns.

Verified against Deepgram Python SDK v7 (7.3.1):
  client.speak.v1.audio.generate(text=..., model=..., encoding="linear16",
                                 container="wav", sample_rate=24000) -> Iterator[bytes]
"""
import io
import wave
from pathlib import Path

from dotenv import load_dotenv

_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

import os
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
OUT = _HERE.parent / "demo_meeting.wav"

SAMPLE_RATE = 24000
GAP_MS = 350  # pause between speaker turns

# Two clearly distinct Aura-2 voices so diarization has an easy, obvious split.
HEINRICH = "aura-2-apollo-en"    # male
SARAH = "aura-2-asteria-en"      # female

# (voice, text) — a realistic SaaS discovery call that naturally surfaces action items.
SCRIPT = [
    (HEINRICH, "Hi Sarah, thanks for making the time. I just wanted to understand how your team currently handles meeting notes and follow-ups."),
    (SARAH,    "Sure. Honestly it's a bit of a mess. We record most of our calls, but nobody ever goes back and listens to them. The notes end up scattered across random Slack messages."),
    (HEINRICH, "That's really common. How many calls a week would you say end with a decision or a task coming out of them?"),
    (SARAH,    "Probably fifteen to twenty. And in at least half of them, something falls through the cracks. We had a supplier call last month where we agreed on a price, and two weeks later nobody could remember what we actually said."),
    (HEINRICH, "So the cost is the time to reconstruct the conversation, and sometimes the deal itself. What does your team do as a workaround right now?"),
    (SARAH,    "Someone types up notes after each meeting. It takes about twenty minutes a call, and it's always incomplete, because they're also trying to listen at the same time."),
    (HEINRICH, "What if the recording just became the notes automatically? Every speaker identified, a summary of what was decided, and the action items already pulled out."),
    (SARAH,    "That would be a game changer. Can it also push those action items into our project tool?"),
    (HEINRICH, "Yes, that's the next layer. The transcription and the intelligence is the foundation. Once the data is structured, routing it into your CRM or your task board is straightforward."),
    (SARAH,    "Okay, I'm interested. What does this actually look like in practice?"),
    (HEINRICH, "I'll send you a short demo after this call, and let's book a follow-up for next week to walk through it properly. I'll also put together a one-page summary of what we'd set up for your team."),
    (SARAH,    "Perfect. Let's do Thursday if you're free. I'll loop in our operations lead so she can see it too."),
]


def tts_wav_bytes(client, voice: str, text: str) -> bytes:
    """Synthesise one line and return a complete WAV file as bytes."""
    chunks = client.speak.v1.audio.generate(
        text=text,
        model=voice,
        encoding="linear16",
        container="wav",
        sample_rate=SAMPLE_RATE,
    )
    return b"".join(chunks)


def build():
    if not DEEPGRAM_API_KEY:
        raise SystemExit("DEEPGRAM_API_KEY is missing from .env — add it before running.")

    from deepgram import DeepgramClient
    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)

    print(f"Generating {len(SCRIPT)} segments via Deepgram Aura-2…")
    params = None          # (nchannels, sampwidth, framerate) from the first segment
    frames = []
    for i, (voice, text) in enumerate(SCRIPT, 1):
        print(f"  [{i:>2}/{len(SCRIPT)}] {voice:<18} {text[:48]}…")
        wav_bytes = tts_wav_bytes(client, voice, text)
        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            if params is None:
                params = (w.getnchannels(), w.getsampwidth(), w.getframerate())
            frames.append(w.readframes(w.getnframes()))

    nchannels, sampwidth, framerate = params
    silence = b"\x00" * int(framerate * GAP_MS / 1000) * sampwidth * nchannels

    with wave.open(str(OUT), "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        for fr in frames:
            out.writeframes(fr)
            out.writeframes(silence)

    total_frames = sum(len(fr) for fr in frames) // (sampwidth * nchannels)
    secs = total_frames / framerate
    print(f"\nSaved {OUT.name}  —  {int(secs // 60)}m {int(secs % 60)}s, {framerate} Hz, {OUT.stat().st_size // 1024} KB")
    print("Upload it in the dashboard to demo the system.")


if __name__ == "__main__":
    build()
