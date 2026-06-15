from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import API_SECRET_KEY
from db.client import supabase
from services.projects import (
    create_project,
    list_projects,
    get_project,
    update_project,
)

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    drive_folder_id: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    client_id: Optional[str] = None
    drive_folder_id: Optional[str] = None
    status: Optional[str] = None
    transcription_done_at: Optional[str] = None
    compilation_done_at: Optional[str] = None
    scaffold_done_at: Optional[str] = None
    brief_sent_at: Optional[str] = None


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("")
def create(body: ProjectCreate, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return create_project(body.name, body.client_id, body.drive_folder_id, body.client_name)


@router.get("")
def list_all(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return list_projects()


@router.get("/{project_id}")
def get_one(project_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.patch("/{project_id}")
def update(project_id: str, body: ProjectUpdate, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    return update_project(project_id, updates)


class StageApproval(BaseModel):
    document_id: str
    stage: str  # "compilation" | "scaffold"


_STAGE_FIELD = {
    "compilation": "compilation_done_at",
    "scaffold": "scaffold_done_at",
}


@router.post("/{project_id}/approve-stage")
def approve_stage(project_id: str, body: StageApproval, x_api_key: str = Header(...)):
    """Approve a pipeline document and advance the project stage timestamp."""
    verify_key(x_api_key)
    if body.stage not in _STAGE_FIELD:
        raise HTTPException(status_code=400, detail=f"Unknown stage: {body.stage}")
    supabase.table("documents").update({"status": "approved"}).eq("id", body.document_id).execute()
    field = _STAGE_FIELD[body.stage]
    return update_project(project_id, {field: datetime.now(timezone.utc).isoformat()})


@router.get("/{project_id}/documents/{document_id}")
def get_document(project_id: str, document_id: str, x_api_key: str = Header(...)):
    """Fetch full document content (for inline viewer)."""
    verify_key(x_api_key)
    result = (
        supabase.table("documents")
        .select("*")
        .eq("id", document_id)
        .eq("project_id", project_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Document not found")
    return result.data
