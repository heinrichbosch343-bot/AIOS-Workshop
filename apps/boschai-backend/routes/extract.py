from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import API_SECRET_KEY
from services.compiler import compile_sources

router = APIRouter()


class ExtractRequest(BaseModel):
    project_id: str
    source_text: Optional[str] = None  # paste raw text if no Drive docs uploaded yet


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/extract")
async def extract_data(request: ExtractRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    try:
        result = compile_sources(
            project_id=request.project_id,
            raw_text=request.source_text,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Compilation failed: {e}")
