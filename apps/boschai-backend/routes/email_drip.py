"""
Email drip queue API — the bridge between Heinrich's local CRM, his Gmail
drafts, and the Supabase queues the scheduler drains (services/email_drip.py).

POST /email/drip/queue          — enqueue CSV-drafted emails (deduped on local_id)
GET  /email/drip/status         — counts + per-row status for both queues,
                                   so the local dashboard mirrors cloud sends
GET  /email/drip/drafts         — the Gmail drafts the backend can see + queue state
POST /email/drip/drafts/import  — stage current Gmail drafts into the drip
GET  /email/drip/updates        — unsynced draft sends + handled replies (for
                                   crm_cloud_sync.py to mirror down)
POST /email/drip/updates/ack    — mark those rows synced after local apply
"""
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

import config
from config import API_SECRET_KEY, EMAIL_DRIP_ENABLED, EMAIL_DRIP_DAILY_CAP
from db.client import supabase
from services import draft_drip, drip_responder

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

    from services import email_drip
    return {
        "enabled": EMAIL_DRIP_ENABLED,
        "daily_cap": EMAIL_DRIP_DAILY_CAP,
        "sent_today": email_drip.sent_today(),
        "counts": counts,
        "rows": rows,
        "draft_counts": draft_drip.queue_counts(),
        "autoreply": drip_responder.get_status(),
    }


class ImportRequest(BaseModel):
    query: str = ""   # optional Gmail search filter, e.g. "label:drip"


@router.get("/drafts")
def list_drafts(x_api_key: str = Header(...)):
    """What the backend's Gmail connection sees in Drafts, next to what's staged."""
    verify_key(x_api_key)
    from services import email as email_service
    try:
        drafts = email_service.list_drafts()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    staged = (supabase.table("draft_queue")
              .select("draft_id,to_email,subject,status,sent_at,error")
              .order("queued_at", desc=True)
              .limit(500)
              .execute()).data
    return {"gmail_drafts": [
        {"draft_id": d["draft_id"], "to": d["to"], "subject": d["subject"]}
        for d in drafts
    ], "queue": staged}


@router.post("/drafts/import")
def import_drafts(req: ImportRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    try:
        return draft_drip.import_drafts(query=req.query)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


class AutoReplySwitch(BaseModel):
    kill: bool


@router.post("/autoreply/kill")
def autoreply_kill(req: AutoReplySwitch, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    drip_responder.set_kill_switch(req.kill)
    return drip_responder.get_status()


# ---------------------------------------------------------------------------
# Sync-down feed for scripts/crm_cloud_sync.py
# ---------------------------------------------------------------------------

@router.get("/updates")
def updates(x_api_key: str = Header(...)):
    """Everything the cloud did that the local CSVs don't know about yet."""
    verify_key(x_api_key)
    draft_sends = (supabase.table("draft_queue")
                   .select("id,to_email,subject,status,sent_at,error")
                   .eq("synced", False)
                   .in_("status", ["sent", "failed", "gone"])
                   .order("queued_at")
                   .limit(500)
                   .execute()).data
    replies = (supabase.table("drip_replies")
               .select("id,source,prospect_email,prospect_name,subject,"
                       "category,action,reply_body,inbound_preview,created_at")
               .eq("synced", False)
               .order("created_at")
               .limit(500)
               .execute()).data
    return {"draft_sends": draft_sends, "replies": replies}


class AckRequest(BaseModel):
    draft_ids: list[int] = []
    reply_ids: list[int] = []


@router.post("/updates/ack")
def ack_updates(req: AckRequest, x_api_key: str = Header(...)):
    """Called after the local apply succeeded, so nothing is mirrored twice."""
    verify_key(x_api_key)
    if req.draft_ids:
        supabase.table("draft_queue").update({"synced": True}) \
            .in_("id", req.draft_ids).execute()
    if req.reply_ids:
        supabase.table("drip_replies").update({"synced": True}) \
            .in_("id", req.reply_ids).execute()
    return {"acked_drafts": len(req.draft_ids), "acked_replies": len(req.reply_ids)}
