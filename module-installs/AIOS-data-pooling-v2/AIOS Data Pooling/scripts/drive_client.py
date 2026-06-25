"""
Google Drive access for the pool — auth, download, and text extraction in one place.

Auth is the standard desktop OAuth flow: a `credentials.json` (downloaded once from Google
Cloud Console) plus a `token.json` this module creates on first run and refreshes after
that. Run `python drive_client.py` directly to do the one-time connect.

Extraction handles the formats reports actually live in: Google Docs/Slides/Sheets
(exported), PDF (pypdf), Word .docx (python-docx), and plain text.
"""
import io

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

import pool_config

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Google-native types must be EXPORTED, not downloaded directly.
_GOOGLE_EXPORT = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}
_PDF = "application/pdf"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

_creds = None


def get_credentials() -> Credentials:
    """Load token.json, refresh if expired, or run the one-time browser consent flow."""
    global _creds
    if _creds and _creds.valid:
        return _creds

    import os
    creds = None
    if os.path.exists(pool_config.GOOGLE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(pool_config.GOOGLE_TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        if not os.path.exists(pool_config.GOOGLE_CREDENTIALS_FILE):
            raise RuntimeError(
                f"Google credentials not found at {pool_config.GOOGLE_CREDENTIALS_FILE}. "
                "Download an OAuth client (Desktop app) JSON from Google Cloud Console "
                "and save it there — see INSTALL.md step 2."
            )
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(
            pool_config.GOOGLE_CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

    with open(pool_config.GOOGLE_TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    _creds = creds
    return creds


def drive_service():
    return build("drive", "v3", credentials=get_credentials())


def download_file(file_id: str) -> bytes:
    request = drive_service().files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def _export_google(file_id: str, export_mime: str) -> str:
    data = drive_service().files().export_media(
        fileId=file_id, mimeType=export_mime).execute()
    return data.decode("utf-8", "ignore") if isinstance(data, bytes) else str(data)


def _pdf_to_text(raw: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _docx_to_text(raw: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(raw))
    return "\n".join(p.text for p in doc.paragraphs if p.text)


def extract_text(file_id: str, mime_type: str = "", name: str = "") -> str:
    """Full plain text of one Drive file. Empty string when the type is unsupported
    or extraction fails (the indexer records those as 'skipped')."""
    try:
        if mime_type in _GOOGLE_EXPORT:
            return (_export_google(file_id, _GOOGLE_EXPORT[mime_type]) or "").strip()
        if mime_type == _PDF or name.lower().endswith(".pdf"):
            return _pdf_to_text(download_file(file_id)).strip()
        if mime_type == _DOCX or name.lower().endswith(".docx"):
            return _docx_to_text(download_file(file_id)).strip()
        if mime_type.startswith("text/") or name.lower().endswith((".txt", ".md", ".csv")):
            return download_file(file_id).decode("utf-8", "ignore").strip()
    except Exception:
        return ""
    return ""


if __name__ == "__main__":
    get_credentials()
    about = drive_service().about().get(fields="user").execute()
    print(f"Connected to Google Drive as {about['user']['emailAddress']}.")
