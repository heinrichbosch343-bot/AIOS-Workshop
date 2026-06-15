from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import API_SECRET_KEY
from services.design_brief import generate_brief
from services.projects import update_project
from services.scaffolder import scaffold_report

router = APIRouter()


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


class ProjectRef(BaseModel):
    project_id: str


@router.post("/report/scaffold")
async def generate_scaffold(body: ProjectRef, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    try:
        return scaffold_report(project_id=body.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scaffolding failed: {e}")


@router.post("/report/brief")
async def create_design_brief(body: ProjectRef, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    try:
        return generate_brief(project_id=body.project_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Brief generation failed: {e}")


@router.post("/report/mark-sent")
async def mark_brief_sent(body: ProjectRef, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return update_project(
        body.project_id,
        {"brief_sent_at": datetime.now(timezone.utc).isoformat()},
    )
