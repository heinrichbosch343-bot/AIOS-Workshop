"""
Email drip queue API — the bridge between Heinrich's local CRM and the
Supabase queue the scheduler drains (services/email_drip.py).

POST /email/drip/queue   — enqueue drafted emails (deduped on local_id)
GET  /email/drip/status  — counts + per-row status, so the local dashboard
                            can mirror what the cloud has sent
"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import API_SECRET_KEY, EMAIL_DRIP_ENABLED, EMAIL_DRIP_DAILY_CAP
from db.client import supabase

router = APIRouter(prefix="/email/drip", tags=["email-drip"])


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


class QueueItem(BaseModel):
    local_id: str
    to: str
    name: str = ""
    firm: str = ""
    subject: str
    body: str


class QueueRequest(BaseModel):
    items: list[QueueItem]


@router.post("/queue")
def enqueue(req: QueueRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    if not req.items:
        return {"queued": 0, "duplicates": 0}
    incoming_ids = [i.local_id for i in req.items]
    existing = (supabase.table("email_queue")
                .select("local_id")
                .in_("local_id", incoming_ids)
                .execute()).data
    known = {r["local_id"] for r in existing}
    fresh = [i for i in req.items if i.local_id not in known]
    if fresh:
        supabase.table("email_queue").insert([{
            "local_id": i.local_id,
            "to_email": i.to.strip(),
            "name": i.name,
            "firm": i.firm,
            "subject": i.subject,
            "body": i.body,
        } for i in fresh]).execute()
    return {"queued": len(fresh), "duplicates": len(known)}


@router.get("/status")
def status(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    rows = (supabase.table("email_queue")
            .select("local_id,to_email,firm,name,subject,status,sent_at,error")
            .order("queued_at", desc=True)
            .limit(500)
            .execute()).data
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"enabled": EMAIL_DRIP_ENABLED, "daily_cap": EMAIL_DRIP_DAILY_CAP,
            "counts": counts, "rows": rows}
