from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import API_SECRET_KEY
from services.signoff import create_signoff, get_open_signoffs, resolve_signoff
from services.signoff_watcher import check_signoffs

router = APIRouter(prefix="/signoffs", tags=["signoffs"])


class SignoffCreate(BaseModel):
    waiting_on: str
    item: str
    project_id: Optional[str] = None
    due_at: Optional[str] = None
    contact_email: Optional[str] = None


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("")
def create(body: SignoffCreate, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    signoff = create_signoff(body.waiting_on, body.item, body.project_id, body.due_at, body.contact_email)
    # Immediate first check — catch a reply that already arrived.
    try:
        check_signoffs()
    except Exception:
        pass
    return signoff


@router.post("/check")
def check(x_api_key: str = Header(...)):
    """Run the watcher now: scan Gmail for replies to open sign-offs and notify."""
    verify_key(x_api_key)
    return check_signoffs()


@router.get("")
def list_open(x_api_key: str = Header(...)):
    verify_key(x_api_key)
    return get_open_signoffs()


@router.patch("/{signoff_id}/resolve")
def resolve(signoff_id: str, x_api_key: str = Header(...)):
    verify_key(x_api_key)
    try:
        return resolve_signoff(signoff_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Signoff not found")
