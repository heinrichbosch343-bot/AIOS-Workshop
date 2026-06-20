import io
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaInMemoryUpload

from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from db.client import supabase

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]


def _require_google_config():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError(
            "Google Drive is not configured. "
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in Railway environment variables, "
            "then complete the one-time OAuth flow at /auth/google."
        )


def get_credentials() -> Credentials:
    """
    Reads Heinrich's Google token from Supabase.
    Refreshes automatically if expired. Saves updated token back.
    Raises RuntimeError if no token exists (OAuth not yet completed).
    """
    _require_google_config()

    result = supabase.table("google_tokens").select("*").limit(1).execute()
    if not result.data:
        raise RuntimeError(
            "No Google token found. "
            "Complete the one-time auth at /auth/google to connect Google Drive."
        )

    row = result.data[0]
    creds = Credentials(
        token=row["access_token"],
        refresh_token=row["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        scopes=SCOPES,
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        supabase.table("google_tokens").update({
            "access_token": creds.token,
            "expires_at": creds.expiry.isoformat() if creds.expiry else None,
        }).eq("id", row["id"]).execute()

    return creds


def download_file(file_id: str) -> bytes:
    """
    Downloads a Google Drive file by ID.
    Returns raw bytes. Caller is responsible for handling the content.
    """
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    return buffer.getvalue()


def upload_file(
    folder_id: str,
    filename: str,
    content: bytes,
    mime_type: str = "text/markdown",
) -> str:
    """
    Uploads content to the specified Drive folder.
    Returns the new file's Drive ID.
    """
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    metadata = {"name": filename, "parents": [folder_id]}
    media = MediaInMemoryUpload(content, mimetype=mime_type)

    file = service.files().create(
        body=metadata,
        media_body=media,
        fields="id",
    ).execute()

    return file["id"]


def list_folder(folder_id: str) -> list[dict]:
    """
    Lists non-trashed files in a Drive folder.
    Returns list of dicts with keys: id, name, mimeType.
    """
    creds = get_credentials()
    service = build("drive", "v3", credentials=creds)

    result = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="files(id, name, mimeType)",
        pageSize=100,
    ).execute()

    return result.get("files", [])
