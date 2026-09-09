import base64
import binascii
import re

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


class DraftRequest(BaseModel):
    """One outbound email, saved to Drafts and never sent.

    `attachment_base64` is the file exactly as the operator uploaded it. It travels
    base64 because this is JSON, which costs a third in size and buys the caller not
    having to build a multipart request from a browser.
    """
    to: str
    subject: str
    body: str
    attachment_filename: str | None = None
    attachment_base64: str | None = None
    mime_type: str = ("application/vnd.openxmlformats-officedocument"
                      ".spreadsheetml.sheet")


# Gmail refuses a message over 25MB and answers with a 400 that says nothing useful.
# Refusing it here means the caller is told which attachment was too big.
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

_ADDRESS = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


@router.post("/drafts")
def save_draft(request: DraftRequest, x_api_key: str = Header(...)):
    """Save one email to Gmail Drafts. Nothing is ever sent from here.

    Deliberately drafts-only, and not a flag away from sending. The caller is a
    browser tab driving a list of merchants, so a bug or a double-click on a send
    path would be an outbound campaign nobody approved — whereas the worst a bug
    can do here is put drafts in a mailbox a human still has to open.
    """
    verify_key(x_api_key)

    to = request.to.strip()
    if not _ADDRESS.match(to):
        raise HTTPException(status_code=400, detail=f"Not a single valid address: {to!r}")
    if not request.subject.strip():
        raise HTTPException(status_code=400, detail="Subject cannot be empty")

    if not request.attachment_base64:
        return _guard_drive_errors(email_service.create_draft, to,
                                   request.subject, request.body)

    try:
        blob = base64.b64decode(request.attachment_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Attachment is not valid base64: {exc}")
    if not blob:
        raise HTTPException(status_code=400, detail="Attachment decoded to zero bytes")
    if len(blob) > _MAX_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Attachment is {len(blob) // 1024}KB; the limit here is "
                   f"{_MAX_ATTACHMENT_BYTES // 1024}KB")

    return _guard_drive_errors(
        email_service.create_draft_with_attachment, to, request.subject,
        request.body, blob, request.attachment_filename or "offer.xlsx",
        request.mime_type)
