"""
voice.py — Johan's ears and mouth.

    speech_to_text(audio_bytes) -> str      Deepgram Nova-3 (unchanged from Phase 1)
    text_to_speech(text) -> bytes           ElevenLabs Flash v2.5 (Johan's SA voice, 1.1x speed)
                                            -> falls back to Deepgram Aura-2 if the
                                               ElevenLabs key/voice is missing or a call fails

STT uses DEEPGRAM_API_KEY; TTS prefers ELEVENLABS_API_KEY (both in the workspace .env).
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

import requests
from dotenv import load_dotenv

# Walk up from this file to the workspace root and load .env (same pattern as the other demos).
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")

STT_MODEL = "nova-3"

# --- ElevenLabs: Johan's voice -------------------------------------------------
# "Marcel — South African" (middle-aged Afrikaans man), picked by Heinrich
# 2026-07-05 (previously Hendrik Vorster JbAJPrBwqw2dm8hxfklG). Empty means
# "not set" and TTS uses the Deepgram fallback voice.
ELEVEN_VOICE_ID = "Kbmk5ZFvBwyoQIcE8k3j"
ELEVEN_MODEL = "eleven_flash_v2_5"
ELEVEN_SPEED = 1.1  # 0.7-1.2 supported; bump to 1.15 if Johan should be punchier
ELEVEN_TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVEN_TTS_WORKERS = 2  # free-tier concurrency is low; answers are 1-2 sentences anyway

# --- Deepgram Aura fallback voice ----------------------------------------------
TTS_MODEL = "aura-2-orion-en"
TTS_URL = "https://api.deepgram.com/v1/speak"
TTS_PARALLEL_WORKERS = 6

# Synthesis time scales with chunk length, so chunks stay single-sentence sized
# and run in parallel.
MAX_TTS_CHARS = 140


def speech_to_text(audio_bytes: bytes) -> str:
    """Send recorded audio to Deepgram Nova-3 and return the transcript text."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY is missing from .env")
    if not audio_bytes:
        return ""

    from deepgram import DeepgramClient

    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
    response = client.listen.v1.media.transcribe_file(
        request=audio_bytes,
        model=STT_MODEL,
        punctuate=True,
        smart_format=True,
    )
    try:
        transcript = response.results.channels[0].alternatives[0].transcript or ""
    except (AttributeError, IndexError):
        transcript = ""
    return transcript.strip()


def _sentence_chunks(text: str, limit: int) -> List[str]:
    """Split text into <=limit chunks on sentence boundaries (falls back to hard split)."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # A single sentence longer than the limit gets hard-split.
        while len(sentence) > limit:
            chunks.append(sentence[:limit])
            sentence = sentence[limit:]
        current = sentence
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def _tts_elevenlabs(text: str) -> bytes:
    """Johan's real voice: ElevenLabs Flash v2.5, parallel per-sentence chunks."""
    chunks = _sentence_chunks(text, MAX_TTS_CHARS)
    session = requests.Session()

    def synthesize(chunk: str) -> bytes:
        resp = session.post(
            f"{ELEVEN_TTS_URL}/{ELEVEN_VOICE_ID}?output_format=mp3_44100_128",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={
                "text": chunk,
                "model_id": ELEVEN_MODEL,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": ELEVEN_SPEED},
            },
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:300]}")
        return resp.content

    # Chunks synthesize concurrently but join in order; mp3 frames are
    # self-contained, so concatenated chunks play back-to-back.
    with ThreadPoolExecutor(max_workers=ELEVEN_TTS_WORKERS) as pool:
        audio_parts: List[bytes] = list(pool.map(synthesize, chunks))
    return b"".join(audio_parts)


def _tts_deepgram(text: str) -> bytes:
    """Fallback voice: Deepgram Aura-2 (the Phase 1 voice)."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY is missing from .env")

    chunks = _sentence_chunks(text, MAX_TTS_CHARS)
    session = requests.Session()

    def synthesize(chunk: str) -> bytes:
        resp = session.post(
            f"{TTS_URL}?model={TTS_MODEL}",
            headers={
                "Authorization": f"Token {DEEPGRAM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={"text": chunk},
            timeout=60,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Deepgram TTS failed ({resp.status_code}): {resp.text[:300]}")
        return resp.content

    with ThreadPoolExecutor(max_workers=TTS_PARALLEL_WORKERS) as pool:
        audio_parts: List[bytes] = list(pool.map(synthesize, chunks))
    return b"".join(audio_parts)


def text_to_speech(text: str) -> bytes:
    """Turn answer text into mp3 bytes — ElevenLabs first, Deepgram as the safety net."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Nothing to say — empty answer text.")

    if ELEVENLABS_API_KEY and ELEVEN_VOICE_ID:
        try:
            return _tts_elevenlabs(text)
        except (RuntimeError, requests.RequestException) as exc:
            print(f"[johan] ElevenLabs TTS failed ({exc}) — falling back to Deepgram voice")
    else:
        print("[johan] ElevenLabs key or voice not set — using Deepgram fallback voice")
    return _tts_deepgram(text)
