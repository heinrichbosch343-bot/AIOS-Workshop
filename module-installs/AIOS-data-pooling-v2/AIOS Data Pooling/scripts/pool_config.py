"""
AIOS Data Pooling — configuration. The ONE place that reads the environment.

Looks for a .env in the project root (walking up from this folder), so the module works
no matter where you drop it. Every knob has a sensible default; only the three keys
(Voyage, Supabase URL + service key) are required.
"""
import os
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    """Load the nearest .env, walking up from this file (module → project root)."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".env"
        if candidate.exists():
            load_dotenv(candidate)
            return
    load_dotenv()  # fall back to the process CWD


_load_env()

# ── Required ──────────────────────────────────────────────────────────────────
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Needed only for ask.py (answering with citations); indexing works without it.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Embeddings ────────────────────────────────────────────────────────────────
# voyage-law-2 and voyage-3.5 both output 1024-dim vectors. If you change to a model
# with a different dimension, update the SQL schema to match and re-index.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-law-2")
# Model that writes the cited answer in ask.py. Default Sonnet; set ANSWER_MODEL in .env to
# claude-haiku-4-5 for the lowest cost, or an Opus model for the deepest reasoning. ask.py
# sends the document text as a cached prefix, so follow-up questions on the same scope are cheap.
ANSWER_MODEL = os.environ.get("ANSWER_MODEL", "claude-sonnet-4-6")

# Pacing for Voyage's free tier (3 requests/minute). On a paid tier set
# EMBED_REQUEST_INTERVAL=0 in .env to index at full speed.
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "8"))
EMBED_REQUEST_INTERVAL = float(os.environ.get("EMBED_REQUEST_INTERVAL", "20"))

# ── Drive crawl ───────────────────────────────────────────────────────────────
# Comma-separated top-level Drive folder NAMES (or ids) to treat as clients.
# Leave empty to index every non-excluded top-level folder.
POOL_CLIENT_ROOTS = [s.strip() for s in os.environ.get("POOL_CLIENT_ROOTS", "").split(",") if s.strip()]

# Google OAuth files (created by the one-time connect flow in drive_client.py).
_HERE = Path(__file__).resolve().parent
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", str(_HERE / "credentials.json"))
GOOGLE_TOKEN_FILE = os.environ.get("GOOGLE_TOKEN_FILE", str(_HERE / "token.json"))


def require(*names: str) -> None:
    """Fail fast with a clear message when a required key is missing."""
    missing = [n for n in names if not globals().get(n)]
    if missing:
        raise RuntimeError(
            f"Missing required settings: {', '.join(missing)}. "
            "Add them to your project's .env file (see INSTALL.md)."
        )
