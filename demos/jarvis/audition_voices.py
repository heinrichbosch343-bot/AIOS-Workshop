"""
audition_voices.py — find Johan's voice in the ElevenLabs shared-voice library.

Search mode (default):
    python audition_voices.py [search terms...]
    Finds South African / Afrikaans male voices, downloads their free preview
    MP3s to outputs/johan-voice-auditions/, writes candidates.json.

Adopt mode:
    python audition_voices.py --adopt <voice_id>
    Adds the picked voice to the ElevenLabs workspace as "Johan", synthesizes
    the test line with Flash v2.5 at 1.1x speed, and prints the constant to
    paste into voice.py.

Costs nothing in search mode (previews are free); adopt mode uses one voice
slot and a few hundred characters of TTS quota.
"""
import json
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# Walk up from this file to the workspace root and load .env (same pattern as voice.py).
_HERE = Path(__file__).resolve()
WORKSPACE_ROOT = _HERE.parents[2]
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

import os

API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
BASE = "https://api.elevenlabs.io"
OUT_DIR = WORKSPACE_ROOT / "outputs" / "johan-voice-auditions"
TEST_LINE = "Ja, record quarter — twenty four point six million rand. Lekker. Want me to pull up the numbers?"
MAX_CANDIDATES = 6


def _headers() -> dict:
    return {"xi-api-key": API_KEY}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "voice"


def _search_shared(term: str) -> list:
    """Query the shared-voice library; tolerate v2/v1 path differences."""
    params = {"page_size": 30, "search": term, "gender": "male"}
    for path in ("/v2/shared-voices", "/v1/shared-voices"):
        resp = requests.get(f"{BASE}{path}", headers=_headers(), params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json().get("voices", [])
        if resp.status_code == 401:
            raise RuntimeError("ElevenLabs rejected the API key (401) — check ELEVENLABS_API_KEY in .env.")
    return []


def _is_sa(voice: dict) -> bool:
    text = json.dumps(voice).lower()
    return "south african" in text or "afrikaans" in text


def search_mode(terms: list) -> None:
    queries = terms or ["south african", "afrikaans", "Marcel south african"]
    seen: dict = {}
    for term in queries:
        for v in _search_shared(term):
            vid = v.get("voice_id")
            if vid and vid not in seen and _is_sa(v):
                seen[vid] = v

    if not seen:
        print("No South African / Afrikaans male voices found in the shared library.")
        print("Try different search terms, or audition premade voices instead.")
        return

    ranked = sorted(seen.values(), key=lambda v: v.get("cloned_by_count", 0), reverse=True)[:MAX_CANDIDATES]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = []
    for rank, v in enumerate(ranked, start=1):
        name = v.get("name", "unknown")
        preview_file = ""
        preview_url = v.get("preview_url", "")
        if preview_url:
            try:
                mp3 = requests.get(preview_url, timeout=30)
                if mp3.status_code == 200 and mp3.content:
                    preview_file = f"{rank}-{_slug(name)}.mp3"
                    (OUT_DIR / preview_file).write_bytes(mp3.content)
            except requests.RequestException:
                pass  # preview is a nice-to-have; keep the candidate either way
        candidates.append({
            "rank": rank,
            "name": name,
            "voice_id": v.get("voice_id", ""),
            "public_owner_id": v.get("public_owner_id", ""),
            "accent": v.get("accent") or (v.get("labels") or {}).get("accent", ""),
            "description": v.get("description", ""),
            "cloned_by_count": v.get("cloned_by_count", 0),
            "preview_file": preview_file,
        })
        print(f"  {rank}. {name}  ({v.get('voice_id','')})  previews: {preview_file or 'none'}")

    (OUT_DIR / "candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    print(f"\nSaved {len(candidates)} candidates to {OUT_DIR}")
    print("Listen to the MP3s, then run:  python audition_voices.py --adopt <voice_id>")


def adopt_mode(voice_id: str) -> None:
    candidates_path = OUT_DIR / "candidates.json"
    if not candidates_path.exists():
        raise RuntimeError("Run search mode first — candidates.json not found.")
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))
    match = next((c for c in candidates if c["voice_id"] == voice_id), None)
    if not match:
        raise RuntimeError(f"voice_id {voice_id} is not in candidates.json — run search mode again.")

    # Add the shared voice to this workspace (idempotent-ish: 400 if already added).
    resp = requests.post(
        f"{BASE}/v1/voices/add/{match['public_owner_id']}/{voice_id}",
        headers={**_headers(), "Content-Type": "application/json"},
        json={"new_name": "Johan"},
        timeout=30,
    )
    if resp.status_code == 200:
        added_id = resp.json().get("voice_id", voice_id)
        print(f"Added '{match['name']}' to the workspace as 'Johan' (voice_id: {added_id})")
    elif "already" in resp.text.lower():
        added_id = voice_id
        print(f"'{match['name']}' is already in the workspace.")
    else:
        raise RuntimeError(f"Could not add voice ({resp.status_code}): {resp.text[:300]}")

    # One paid test line to confirm the pick.
    tts = requests.post(
        f"{BASE}/v1/text-to-speech/{added_id}?output_format=mp3_44100_128",
        headers={**_headers(), "Content-Type": "application/json"},
        json={
            "text": TEST_LINE,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.1},
        },
        timeout=60,
    )
    if tts.status_code != 200:
        raise RuntimeError(f"Test-line TTS failed ({tts.status_code}): {tts.text[:300]}")
    out = OUT_DIR / "johan-test-line.mp3"
    out.write_bytes(tts.content)
    print(f"Test line saved: {out}")
    print(f'\nPaste into voice.py:  ELEVEN_VOICE_ID = "{added_id}"')


def main() -> None:
    if not API_KEY:
        print("ELEVENLABS_API_KEY is missing from .env — add it, then rerun this script.")
        sys.exit(1)
    args = sys.argv[1:]
    try:
        if args and args[0] == "--adopt":
            if len(args) < 2:
                print("Usage: python audition_voices.py --adopt <voice_id>")
                sys.exit(1)
            adopt_mode(args[1])
        else:
            search_mode(args)
    except (RuntimeError, requests.RequestException) as exc:
        print(f"Problem: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
