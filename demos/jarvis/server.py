"""
server.py — FastAPI backend for the BoschAI Johan voice demo (port 8505).

Routes:
    GET  /            the orb page
    GET  /api/health  key + DB status (booleans only, never values)
    POST /api/ask     multipart: audio file OR text field, plus history JSON
                      -> {"transcript", "answer", "card", "audio_b64"} or {"error"}

Errors always come back as {"error": "<plain English>"} with HTTP 200 so the
front end can show them gracefully — full detail goes to the server log only.
"""
import base64
import json
import sys
import traceback
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent))
import brain
import seed_demo_company
import store
import voice

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_HISTORY_TURNS = 12

app = FastAPI(title="BoschAI Johan Demo")


@app.on_event("startup")
def startup() -> None:
    store.ensure_db()
    if not store.is_seeded():
        result = seed_demo_company.seed()
        print(f"[johan] Seeded Meridian Manufacturing demo data: {result}")
    else:
        print(f"[johan] Demo DB ready at {store.DB_PATH}")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "db_seeded": store.is_seeded(),
        "anthropic_key": bool(brain.ANTHROPIC_API_KEY),
        "deepgram_key": bool(voice.DEEPGRAM_API_KEY),
        "elevenlabs_key": bool(voice.ELEVENLABS_API_KEY),
        "elevenlabs_voice": bool(voice.ELEVEN_VOICE_ID),
    }


def _parse_history(raw: str) -> list:
    """History must be a list of {'role': 'user'|'assistant', 'content': str}; else empty."""
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    clean = [
        {"role": t["role"], "content": t["content"]}
        for t in parsed
        if isinstance(t, dict)
        and t.get("role") in ("user", "assistant")
        and isinstance(t.get("content"), str)
    ]
    return clean[-MAX_HISTORY_TURNS:]


@app.post("/api/ask")
async def ask(
    audio: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    history: str = Form(default="[]"),
) -> JSONResponse:
    turns = _parse_history(history)

    try:
        if audio is not None:
            audio_bytes = await audio.read()
            transcript = voice.speech_to_text(audio_bytes)
            if not transcript:
                return JSONResponse({"error": "I didn't catch that — try holding the orb and speaking a bit longer."})
        elif text and text.strip():
            transcript = text.strip()
        else:
            return JSONResponse({"error": "Send either recorded audio or a text question."})

        result = brain.answer(transcript, turns)
        audio_b64 = base64.b64encode(voice.text_to_speech(result["say"])).decode("ascii")
        return JSONResponse({
            "transcript": transcript,
            "answer": result["say"],
            "card": result["card"],
            "audio_b64": audio_b64,
        })

    except Exception as exc:
        traceback.print_exc()
        message = str(exc)
        if "API_KEY is missing" in message:
            friendly = message  # already plain English from voice.py / brain.py
        else:
            friendly = "Something went wrong answering that — check the server window for details and try again."
        return JSONResponse({"error": friendly})


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
