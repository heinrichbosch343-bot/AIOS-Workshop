"""
Google Drive OAuth — one-time setup flow.

Usage:
  1. Visit /auth/google in a browser (proxied via the local dashboard on port 7000)
  2. Approve access in Google's consent screen
  3. Token is saved to the `google_tokens` Supabase table
  4. All Drive features are now active. Token refreshes automatically.

This flow only needs to be run once (or when the refresh token is revoked).
"""

from fastapi import APIRouter
from fastapi.responses import RedirectResponse, HTMLResponse
from google_auth_oauthlib.flow import Flow

from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI
from db.client import supabase

router = APIRouter(prefix="/auth", tags=["auth"])

# Outstanding OAuth state tokens (CSRF protection between /google and the callback).
_pending_states: set[str] = set()

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.readonly",
]

CLIENT_CONFIG = {
    "web": {
        "client_id": None,          # populated at request time from config
        "client_secret": None,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [],
    }
}


def _build_flow() -> Flow:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in environment variables "
            "before the Google Drive OAuth flow can be used."
        )

    config = {
        "web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [GOOGLE_REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(
        config,
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )
    return flow


@router.get("/google")
def google_auth_start():
    """
    Step 1: Redirect Heinrich to Google's consent screen.
    Visit this URL once to connect Google Drive.
    """
    try:
        flow = _build_flow()
    except RuntimeError as e:
        return HTMLResponse(
            content=f"<h2>Setup Required</h2><p>{e}</p>",
            status_code=503,
        )

    authorization_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",   # force refresh_token to be returned every time
    )
    if len(_pending_states) > 100:   # bound the set; this is a rare one-time flow
        _pending_states.clear()
    _pending_states.add(state)
    return RedirectResponse(url=authorization_url)


@router.get("/google/callback")
def google_auth_callback(code: str, state: str = ""):
    """
    Step 2: Google redirects here after Heinrich approves access.
    Exchanges the auth code for tokens and saves them to Supabase.
    """
    # CSRF: only accept callbacks for a state we issued in /auth/google.
    if not state or state not in _pending_states:
        return HTMLResponse(
            content="<h2>Invalid or expired sign-in</h2><p>Please start again at /auth/google.</p>",
            status_code=400,
        )
    _pending_states.discard(state)

    try:
        flow = _build_flow()
    except RuntimeError as e:
        return HTMLResponse(
            content=f"<h2>Setup Error</h2><p>{e}</p>",
            status_code=503,
        )

    flow.fetch_token(code=code)
    creds = flow.credentials

    token_row = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at": creds.expiry.isoformat() if creds.expiry else None,
    }

    # Upsert: delete existing single row then insert fresh (only one row needed)
    existing = supabase.table("google_tokens").select("id").limit(1).execute()
    if existing.data:
        supabase.table("google_tokens").delete().eq("id", existing.data[0]["id"]).execute()

    supabase.table("google_tokens").insert(token_row).execute()

    return HTMLResponse(
        content=(
            "<h2>Google Drive Connected</h2>"
            "<p>Heinrich's Google Drive is now linked. You can close this window.</p>"
            "<p>All Drive features are active. Token refreshes automatically.</p>"
        )
    )
