"""
Meeting Intelligence — Deepgram STT + Claude post-processor.

Two clean functions the dashboard calls:

    transcribe(audio_bytes) -> TranscriptResult
        Sends audio to Deepgram Nova-3 with speaker diarization.
        Returns speaker-labeled turns, duration, speaker count, word count.

    summarise(transcript_text) -> SummaryResult
        Sends the plain transcript to Claude Haiku.
        Returns a short summary + a list of action items.

Written against the Deepgram Python SDK v7 (verified 7.3.1):
  - client.listen.v1.media.transcribe_file(request=<bytes>, ...)  — kwargs, not an options object
  - response.results.utterances[*] has .speaker (int), .transcript, .start, .end
  - audio format is auto-detected from the bytes, so no mimetype is passed
"""
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Walk up from this file to the workspace root and load .env (same pattern as the other demos).
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Nova-3 is Deepgram's most accurate general model — best default for a clean meeting demo.
STT_MODEL = "nova-3"
# Haiku is fast + cheap; summary + action items don't need deeper reasoning, and speed matters on camera.
SUMMARY_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class Utterance:
    speaker: str        # display label, e.g. "Speaker 1"
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
        """Speaker-prefixed transcript — what we hand to Claude for summarising."""
        return "\n".join(f"{u.speaker}: {u.text}" for u in self.utterances)


@dataclass
class SummaryResult:
    summary: str
    action_items: List[str] = field(default_factory=list)


def transcribe(audio_bytes: bytes) -> TranscriptResult:
    """Send audio to Deepgram and return speaker-labeled turns + headline numbers."""
    if not DEEPGRAM_API_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY is missing from .env")

    from deepgram import DeepgramClient

    client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
    response = client.listen.v1.media.transcribe_file(
        request=audio_bytes,
        model=STT_MODEL,
        diarize=True,        # who said what
        utterances=True,     # pre-chunked speaker turns (drives the transcript display)
        punctuate=True,
        smart_format=True,   # tidy numbers, dates, etc.
    )

    raw = response.results.utterances or []
    utterances: List[Utterance] = []
    speakers = set()
    for u in raw:
        text = (u.transcript or "").strip()
        if not text:
            continue
        spk = u.speaker if u.speaker is not None else 0
        speakers.add(spk)
        utterances.append(Utterance(
            speaker=f"Speaker {spk + 1}",   # Deepgram speakers are 0-based
            text=text,
            start=u.start or 0.0,
            end=u.end or 0.0,
        ))

    # Word count from the main channel; fall back to counting the utterance text.
    try:
        words = response.results.channels[0].alternatives[0].words or []
        word_count = len(words)
    except Exception:
        word_count = sum(len(u.text.split()) for u in utterances)

    try:
        duration = float(response.metadata.duration)
    except Exception:
        duration = utterances[-1].end if utterances else 0.0

    return TranscriptResult(
        utterances=utterances,
        duration_seconds=duration,
        speaker_count=len(speakers),
        word_count=word_count,
    )


# Audio formats we send to Deepgram vs text-transcript formats we read directly.
AUDIO_EXTS = {"mp3", "wav", "m4a", "mp4", "ogg", "webm"}
TEXT_EXTS = {"txt", "md", "vtt", "srt", "csv"}


def is_audio(filename: str) -> bool:
    return (filename or "").rsplit(".", 1)[-1].lower() in AUDIO_EXTS


def extract_transcript_text(file_bytes: bytes, filename: str) -> str:
    """Read an already-written transcript file into clean text.

    Handles txt/md/csv/vtt/srt directly. VTT/SRT subtitle timing lines and cue numbers are
    stripped so only the spoken text remains. docx/pdf are supported only if the optional
    readers are installed; otherwise a clear error is raised.
    """
    ext = (filename or "").rsplit(".", 1)[-1].lower()

    if ext in ("docx", "pdf"):
        try:
            if ext == "docx":
                import docx  # python-docx
                import io
                doc = docx.Document(io.BytesIO(file_bytes))
                return "\n".join(p.text for p in doc.paragraphs).strip()
            else:
                import io
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                return "\n".join((pg.extract_text() or "") for pg in reader.pages).strip()
        except ImportError:
            raise RuntimeError(
                f"Reading .{ext} needs an extra library. Use a .txt/.vtt/.srt transcript, "
                "or upload the audio instead."
            )

    text = file_bytes.decode("utf-8", "ignore")

    if ext in ("vtt", "srt"):
        import re
        lines = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.upper() == "WEBVTT":
                continue
            if "-->" in line:                      # timing cue
                continue
            if re.fullmatch(r"\d+", line):          # SRT cue number
                continue
            lines.append(line)
        text = "\n".join(lines)

    return text.strip()


def summarise(transcript_text: str) -> SummaryResult:
    """Turn a transcript into a short summary + a clean action-item list via Claude."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is missing from .env")
    if not transcript_text.strip():
        return SummaryResult(summary="No speech was detected in this recording.", action_items=[])

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=700,
        system=(
            "You are a meeting assistant. Given a meeting transcript, return a JSON object with exactly two keys:\n"
            '- "summary": a 2-3 sentence plain-English summary of what was discussed and decided.\n'
            '- "action_items": an array of strings, each a concrete next action agreed in the meeting. '
            "Use an empty array if there are none.\n"
            "Return ONLY the JSON object. No markdown, no code fences, no commentary."
        ),
        messages=[{"role": "user", "content": f"Transcript:\n\n{transcript_text}"}],
    )

    text = "".join(b.text for b in resp.content if b.type == "text").strip()

    # Strip a stray ```json fence if the model adds one despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Never crash the demo on a parse miss — show the raw text as the summary.
        return SummaryResult(summary=text, action_items=[])

    items = data.get("action_items", []) or []
    items = [str(i).strip() for i in items if str(i).strip()]
    return SummaryResult(summary=str(data.get("summary", "")).strip(), action_items=items)
