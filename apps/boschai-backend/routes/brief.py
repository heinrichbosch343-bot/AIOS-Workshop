from fastapi import APIRouter, Header, HTTPException

from config import API_SECRET_KEY
from services import daily_brief

router = APIRouter(tags=["brief"])


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/daily-brief")
def preview_brief(x_api_key: str = Header(...)):
    """Build the brief and return it WITHOUT sending to Telegram (preview)."""
    verify_key(x_api_key)
    return {"brief": daily_brief.build_brief()}


@router.post("/daily-brief")
def send_brief(x_api_key: str = Header(...)):
    """Build the brief and send it to Heinrich's Telegram."""
    verify_key(x_api_key)
    return daily_brief.send_daily_brief()
