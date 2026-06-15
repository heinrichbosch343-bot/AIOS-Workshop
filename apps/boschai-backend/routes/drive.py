from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import API_SECRET_KEY
from services.drive import get_credentials, list_folder
from services.drive_extract import extract_text
from services.drive_query import query_folder
from googleapiclient.discovery import build

router = APIRouter(prefix="/drive", tags=["drive"])


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/folders")
def list_drive_folders(x_api_key: str = Header(...)):
    """
    Returns all top-level Google Drive folders for Heinrich's account.
    Used to populate the folder picker in the New Project form.
    Returns list of { id, name }.
    """
    verify_key(x_api_key)

    try:
        creds = get_credentials()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    service = build("drive", "v3", credentials=creds)

    result = service.files().list(
        q="'root' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id, name)",
        orderBy="name",
        pageSize=100,
    ).execute()

    return {"folders": result.get("files", [])}


@router.get("/files")
def list_drive_files(folder_id: str, x_api_key: str = Header(...)):
    """List non-trashed files in a Drive folder. Returns { files: [{id, name, mimeType}] }."""
    verify_key(x_api_key)
    try:
        return {"files": list_folder(folder_id)}
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class ExtractRequest(BaseModel):
    file_id: str
    mime_type: str = ""
    name: str = ""


@router.post("/extract")
def extract_drive_file(req: ExtractRequest, x_api_key: str = Header(...)):
    """Pull a file's readable text. Returns { text, chars, truncated, mime }."""
    verify_key(x_api_key)
    return extract_text(req.file_id, req.mime_type, req.name)


class QueryRequest(BaseModel):
    folder_id: str
    question: str
    file_ids: list[str] = []


@router.post("/query")
def query_drive(req: QueryRequest, x_api_key: str = Header(...)):
    """
    Answer a question using ONLY the text of files in a Drive folder, with citations.
    If file_ids is empty, the whole folder is searched. Returns
    { answer, files_searched, files_total, truncated }.
    """
    verify_key(x_api_key)
    try:
        return query_folder(req.folder_id, req.question, req.file_ids or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:  # Google not connected
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
