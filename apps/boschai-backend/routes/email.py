from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import API_SECRET_KEY
from services import email as email_service
from services import autodraft

router = APIRouter(prefix="/email", tags=["email"])


class ReplyRequest(BaseModel):
    body: str


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _guard_drive_errors(fn, *args, **kwargs):
    """Translate 'Google not connected' RuntimeErrors into a clean 503."""
    try:
        return fn(*args, **kwargs)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/messages")
def list_messages(unread: bool = False, people: bool = False, today: bool = False,
                  unreplied: bool = False, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    q = "in:inbox category:primary"
    if unread:
        q += " is:unread"
    if today:
        q += " newer_than:2d"  # generous pre-filter; today_only does the strict calendar-day cut
    return {"messages": _guard_drive_errors(
        email_service.list_inbox, q=q, people_only=people, today_only=today,
        exclude_replied=unreplied)}


@router.post("/auto-draft")
async def auto_draft(x_api_key: str = Header(...)):
    """Scan recent real emails and save reply drafts to Gmail for the routine ones."""
    verify_key(x_api_key)
    try:
        return await autodraft.auto_draft_replies()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/messages/{msg_id}")
def read_message(msg_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return _guard_drive_errors(email_service.get_message, msg_id)


@router.post("/messages/{msg_id}/reply")
def reply_message(msg_id: str, request: ReplyRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    if not request.body.strip():
        raise HTTPException(status_code=400, detail="Reply body cannot be empty")
    return _guard_drive_errors(email_service.send_reply, msg_id, request.body)
