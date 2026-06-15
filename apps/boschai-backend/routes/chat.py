import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from config import API_SECRET_KEY
from db.client import supabase
from services.agent import build_agent_prompt, run_agent_loop

router = APIRouter()


def _encode_content(content):
    """Serialise a message's content for storage: plain text stays text, block lists
    (tool_use / tool_result) are stored as JSON so the whole turn can be replayed."""
    if isinstance(content, str):
        return content
    return json.dumps(content, default=str)


def _decode_content(raw):
    """Inverse of _encode_content. A stored JSON list of content blocks is parsed back
    into a list; everything else (ordinary text, including older rows) stays a string."""
    if isinstance(raw, str) and raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, TypeError):
            pass
    return raw


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    client_id: Optional[str] = None


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def ensure_session(session_id: Optional[str], client_id: Optional[str], first_message: str) -> str:
    if session_id:
        return session_id
    row = {"session_type": "chat", "title": (first_message or "New chat").strip()[:60]}
    if client_id:
        row["client_id"] = client_id
    created = supabase.table("sessions").insert(row).execute()
    return created.data[0]["id"]


@router.post("/chat")
async def chat(request: ChatRequest, x_api_key: str = Header(...)):
    verify_key(x_api_key)

    session_id = ensure_session(request.session_id, request.client_id, request.message)
    system_prompt = await build_agent_prompt(request.client_id)

    history = (
        supabase.table("messages")
        .select("role, content")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    # Rebuild full context, including past tool calls/results, so the model remembers
    # exactly what it fetched (e.g. the numbered email list) instead of re-listing.
    messages = [{"role": m["role"], "content": _decode_content(m["content"])} for m in history.data]
    turn_start = len(messages)
    messages.append({"role": "user", "content": request.message})

    reply = run_agent_loop(system_prompt, messages, source="dashboard")

    # Persist the entire turn (user message, every tool call/result, final reply) so the
    # next turn has full context and never has to re-fetch and re-number the same data.
    rows = [
        {"session_id": session_id, "role": m["role"], "content": _encode_content(m["content"])}
        for m in messages[turn_start:]
    ]
    if rows:
        supabase.table("messages").insert(rows).execute()

    return {"response": reply, "session_id": session_id}
