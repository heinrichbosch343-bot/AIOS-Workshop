from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import API_SECRET_KEY
from services.research import research_company
from services import research_jobs

router = APIRouter(prefix="/research", tags=["research"])


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


class ResearchRequest(BaseModel):
    query: str


@router.post("")
def research(req: ResearchRequest, x_api_key: str = Header(...)):
    """Quick research a client/company. Returns { query, brief, sources, error? }."""
    verify_key(x_api_key)
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty query")
    return research_company(q)


class DeepRequest(BaseModel):
    query: str
    time_period: str = "last 12 months"


@router.post("/deep")
def start_deep(req: DeepRequest, x_api_key: str = Header(...)):
    """Start a deep multi-agent research run. Returns { job_id }."""
    verify_key(x_api_key)
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Empty query")
    return {"job_id": research_jobs.start_job(q, req.time_period)}


@router.get("/deep/{job_id}")
def poll_deep(job_id: str, x_api_key: str = Header(...)):
    """Poll a deep research job. Returns status, phase, pct, and result when done."""
    verify_key(x_api_key)
    job = research_jobs.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
