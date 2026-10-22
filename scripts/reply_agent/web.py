"""The hosted side: a tiny FastAPI app for Railway. Deployed as its own service (root directory `scripts`, start
command `uvicorn reply_agent.web:app --host 0.0.0.0 --port $PORT`), separate from the main BoschAI backend, so a
mail problem here can never touch invoicing or the quote bot.

Everything that reads or changes anything (setup, the review page, approving a reply) needs `?key=...` to match
REPLY_AGENT_KEY, checked with a constant-time compare. /health and /ready are the only open endpoints, and /ready
gives no personal data, the same convention as /invoices/ready and /quotebot/ready in the other service.

Env vars: REPLY_AGENT_KEY (required for anything guarded), ANTHROPIC_API_KEY (the model), REPLY_AGENT_ENABLED=1
(turns on the background pass; a bare deploy does nothing), REPLY_AGENT_LIVE=1 (actually send; belt and suspenders
on top of the config's own `live` flag), REPLY_AGENT_INTERVAL_MINUTES (default 1), REPLY_AGENT_DIR or Railway's
own RAILWAY_VOLUME_MOUNT_PATH (where the private folder lives), PUBLIC_BASE_URL or RAILWAY_PUBLIC_DOMAIN (for the
link in the "replies are waiting" email).
"""
from __future__ import annotations

import asyncio
import hmac
import html
import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .agent import Agent
from .hosted import Hosted, data_folder
from .llm import LLM, AnthropicApi, LLMError
from .rules import Known
from .store import Store
from .textnorm import strip_controls

BUILD = "reply-agent-web-2 (2026-10-20, /summary for the Replies page in Twenty)"


def _clean_env(name: str) -> str:
    return (os.environ.get(name) or "").strip().strip('"').strip("'").strip()


def public_base_url() -> str:
    explicit = _clean_env("PUBLIC_BASE_URL").rstrip("/")
    if explicit:
        return explicit
    railway = _clean_env("RAILWAY_PUBLIC_DOMAIN")
    return f"https://{railway}" if railway else "http://localhost:8000"


def _key() -> str:
    return _clean_env("REPLY_AGENT_KEY")


def _authorised(request: Request) -> bool:
    given = request.query_params.get("key", "")
    wanted = _key()
    return bool(wanted) and hmac.compare_digest(given, wanted)


def _denied() -> JSONResponse:
    return JSONResponse({"error": "missing or wrong ?key="}, status_code=403)


def _hosted() -> Hosted:
    return Hosted(data_folder())


def _esc(value) -> str:
    """HTML-escaped and control-character-free: nothing a sender wrote can break the page or hide another entry."""
    return html.escape(strip_controls(str(value or "")))


class NullLLM:
    """For actions (approve, skip, retry, settle) that never draft or classify: calling this is a bug, not a quiet no-op."""

    def complete(self, system: str, prompt: str, *, model: str) -> str:
        raise LLMError("this action should never need the model")


def _llm() -> LLM:
    return AnthropicApi(os.environ["ANTHROPIC_API_KEY"])


DEFAULT_INTERVAL_MINUTES = 1     # a reply is read and drafted within about a minute; one inbox check is a single cheap IMAP login


def _interval_minutes() -> int:
    try:
        return max(1, int(_clean_env("REPLY_AGENT_INTERVAL_MINUTES") or str(DEFAULT_INTERVAL_MINUTES)))
    except ValueError:
        return DEFAULT_INTERVAL_MINUTES


async def _background_loop() -> None:
    enabled = _clean_env("REPLY_AGENT_ENABLED") == "1"
    print(f"[reply-agent] background pass {'enabled' if enabled else 'disabled (set REPLY_AGENT_ENABLED=1)'}", flush=True)
    if not enabled:
        return
    minutes = _interval_minutes()
    live = _clean_env("REPLY_AGENT_LIVE") == "1"
    key = _key()
    link = f"{public_base_url()}/replies?key={key}" if key else ""
    while True:
        try:
            hosted = _hosted()
            blockers = hosted.blockers()
            if blockers:
                print(f"[reply-agent] not set up yet: {blockers[0]}", flush=True)
            else:
                result = await asyncio.to_thread(hosted.run_pass, _llm(), live, link)
                print(f"[reply-agent] pass done: {result['counts']}, live={live}", flush=True)
        except Exception as exc:  # noqa: BLE001  one bad pass must not end the loop
            print(f"[reply-agent] pass failed: {type(exc).__name__}: {str(exc)[:300]}", flush=True)
        await asyncio.sleep(minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_background_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    hosted = _hosted()
    blockers = hosted.blockers()
    status = hosted.status()
    return {
        "build": BUILD,
        "ready": not blockers,
        "blockers": blockers or ["none"],
        "key_set": bool(_key()),
        "background_enabled": _clean_env("REPLY_AGENT_ENABLED") == "1",
        "live": _clean_env("REPLY_AGENT_LIVE") == "1",
        "last_pass": {k: status[k] for k in ("last_pass_at", "last_ok_at", "ok", "error") if k in status} or None,
    }


@app.get("/summary")
def summary(request: Request):
    """Counts, the newest replies and whether the agent is alive, for the Replies page inside Twenty. Guarded: it carries
    what people wrote."""
    if not _authorised(request):
        return _denied()
    data = _hosted().summary(enabled=_clean_env("REPLY_AGENT_ENABLED") == "1", live=_clean_env("REPLY_AGENT_LIVE") == "1",
                             interval_minutes=_interval_minutes())
    return {"build": BUILD, **data}


@app.post("/setup")
async def setup(request: Request):
    if not _authorised(request):
        return _denied()
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "body must be JSON"}, status_code=400)
    try:
        result = _hosted().apply_setup(payload)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    return result


# --- the review page ---------------------------------------------------------------------------------------

def _qk(key: str) -> str:
    return quote(key, safe="")


def _page(body: str, message: str = "") -> HTMLResponse:
    banner = f'<p style="color:#9c2b00">{_esc(message)}</p>' if message else ""
    html_doc = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Reply agent</title>"
        "<style>body{font-family:sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;line-height:1.5}"
        "textarea{width:100%;min-height:8rem;font-family:inherit}"
        ".item{border:1px solid #ccc;border-radius:6px;padding:1rem;margin-bottom:1rem}"
        ".them{white-space:pre-wrap;background:#f6f6f6;padding:.5rem;border-radius:4px}"
        "button{margin-right:.5rem}</style></head><body>"
        f"<h2>Reply agent</h2>{banner}{body}</body></html>"
    )
    return HTMLResponse(html_doc)


def _draft_item(key: str, row, label: str) -> str:
    verified_note = "" if row["verified"] else "<p><b>Not verified:</b> our mail server could not confirm who sent this.</p>"
    return (
        f"<div class='item'><p><b>{_esc(label)}</b> &middot; {_esc(row['category'])} &middot; "
        f"{_esc(row['from_name'] or row['from_addr'])} &lt;{_esc(row['from_addr'])}&gt;</p>"
        f"<p>Subject: {_esc(row['subject'])} &middot; answering from: {_esc(row['mailbox'] or '(none)')}</p>"
        f"<p>They wrote:</p><div class='them'>{_esc(row['their_body'])}</div>"
        f"<form method='post' action='/drafts/{row['id']}/approve?key={_qk(key)}'>"
        f"<textarea name='body'>{_esc(row['body'])}</textarea>"
        f"<p><label><input type='checkbox' name='force' value='1'> send even if the checks object or we already "
        f"replied today</label></p>{verified_note}"
        f"<button type='submit'>Approve</button></form>"
        f"<form method='post' action='/drafts/{row['id']}/skip?key={_qk(key)}' style='display:inline'>"
        f"<button type='submit'>Skip</button></form></div>"
    )


def _doubtful_item(key: str, row) -> str:
    return (
        f"<div class='item'><p><b>NEEDS A LOOK</b> &middot; this was going out when the connection broke. "
        f"Find out whether it arrived, then say which:</p>"
        f"<p>{_esc(row['from_name'] or row['from_addr'])} &lt;{_esc(row['from_addr'])}&gt; &middot; {_esc(row['subject'])}</p>"
        f"<div class='them'>{_esc(row['body'])}</div>"
        f"<form method='post' action='/drafts/{row['id']}/settle?key={_qk(key)}&sent=1' style='display:inline'>"
        f"<button type='submit'>It arrived</button></form> "
        f"<form method='post' action='/drafts/{row['id']}/settle?key={_qk(key)}&sent=0' style='display:inline'>"
        f"<button type='submit'>It did not arrive</button></form></div>"
    )


def _failed_item(key: str, row) -> str:
    return (
        f"<div class='item'><p><b>FAILED to send</b> (it did not go out) &middot; "
        f"{_esc(row['from_name'] or row['from_addr'])} &lt;{_esc(row['from_addr'])}&gt; &middot; {_esc(row['subject'])}</p>"
        f"<div class='them'>{_esc(row['note'])}</div>"
        f"<form method='post' action='/drafts/{row['id']}/retry?key={_qk(key)}'><button type='submit'>Retry</button></form></div>"
    )


def _attention_item(key: str, row) -> str:
    who = f"{_esc(row['from_name'] or row['from_addr'])} &lt;{_esc(row['from_addr'])}&gt;" if row["from_addr"] else ""
    body = f"<div class='them'>{_esc(row['body'])}</div>" if row["body"] else ""
    return (
        f"<div class='item'><p><b>{_esc(row['kind'])}</b> {who}</p>"
        f"<p>Subject: {_esc(row['subject'] or '')}</p><p>{_esc(row['note'] or '')}</p>{body}"
        f"<form method='post' action='/attention/{row['id']}/resolve?key={_qk(key)}'>"
        f"<button type='submit'>Mark reviewed</button></form></div>"
    )


@app.get("/replies")
def replies_page(request: Request, msg: str = ""):
    if not _authorised(request):
        return _denied()
    key = request.query_params.get("key", "")
    hosted = _hosted()
    blockers = hosted.blockers()
    if blockers:
        return _page(f"<p>{_esc(blockers[0])}</p>", msg)
    store = Store(hosted.config().db_path)
    try:
        parts = []
        for status, label in (("pending", "PENDING, needs your approval"), ("held", "HELD, a person answers this one")):
            parts += [_draft_item(key, row, label) for row in store.drafts(status)]
        parts += [_doubtful_item(key, row) for row in store.drafts("sending")]
        parts += [_failed_item(key, row) for row in store.drafts("failed")]
        parts += [_attention_item(key, row) for row in store.open_attention()]
        approved = len(store.drafts("approved"))
        if approved:
            parts.append(f"<p>{approved} approved repl{'y' if approved == 1 else 'ies'} lined up to send.</p>")
        body = "".join(parts) or "<p>Nothing waiting.</p>"
    finally:
        store.close()
    return _page(body, msg)


def _action_agent(hosted: Hosted) -> Agent:
    return Agent(hosted.config(), hosted.store(), NullLLM(), known=Known())


def _back(key: str, msg: str) -> HTMLResponse:
    return HTMLResponse(status_code=303, headers={"Location": f"/replies?key={quote(key, safe='')}&msg={quote(msg, safe='')}"})


ACTIONS = ("approve", "skip", "retry", "settle", "resolve")


def _do(action: str, item_id: int, body: str = "", force: bool = False, sent: bool = True) -> tuple[bool, str]:
    """The one place a person's decision is carried out, for the review page and for the JSON route that the Replies page
    inside Twenty uses. It never raises for a refusal: the reason comes back as the message."""
    hosted = _hosted()
    if action == "resolve":
        store = hosted.store()
        try:
            done = store.resolve_attention(item_id)
        finally:
            store.close()
        return done, "Marked reviewed." if done else "No open item with that number."
    agent = _action_agent(hosted)
    try:
        if action == "approve":
            agent.approve(item_id, body or None, force=force)
            return True, f"Draft {item_id} approved."
        if action == "skip":
            agent.skip(item_id)
            return True, f"Draft {item_id} skipped."
        if action == "retry":
            agent.retry(item_id)
            return True, f"Draft {item_id} queued again."
        if action == "settle":
            agent.settle(item_id, delivered=sent)
            return True, f"Draft {item_id} closed."
    except (KeyError, ValueError) as exc:
        return False, (f"Could not approve draft {item_id}: {exc}" if action == "approve" else str(exc))
    finally:
        agent.store.close()
    return False, f"Unknown action {action}."


@app.post("/api/act")
async def act(request: Request):
    """approve (with the edited words), skip, retry, settle or resolve, as JSON, for the Replies page inside Twenty.
    A refused action answers 200 with ok false and the reason; only a malformed request is a 400."""
    if not _authorised(request):
        return _denied()
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "body must be JSON"}, status_code=400)
    item_id = payload.get("id") if isinstance(payload, dict) else None
    body = payload.get("body", "") if isinstance(payload, dict) else ""
    if (not isinstance(payload, dict) or payload.get("action") not in ACTIONS or isinstance(item_id, bool)
            or not isinstance(item_id, int) or item_id < 1 or not isinstance(body, str) or len(body) > 20000):
        return JSONResponse({"error": "send {action: approve|skip|retry|settle|resolve, id: a number, body: text}"}, status_code=400)
    ok, message = await asyncio.to_thread(_do, payload["action"], item_id, body, payload.get("force") is True,
                                          payload.get("sent") is not False)
    return {"ok": ok, "message": message}


@app.post("/drafts/{draft_id}/approve")
def approve(draft_id: int, request: Request, body: str = Form(""), force: str = Form("")):
    if not _authorised(request):
        return _denied()
    return _back(request.query_params.get("key", ""), _do("approve", draft_id, body, bool(force))[1])


@app.post("/drafts/{draft_id}/skip")
def skip(draft_id: int, request: Request):
    if not _authorised(request):
        return _denied()
    return _back(request.query_params.get("key", ""), _do("skip", draft_id)[1])


@app.post("/drafts/{draft_id}/retry")
def retry(draft_id: int, request: Request):
    if not _authorised(request):
        return _denied()
    return _back(request.query_params.get("key", ""), _do("retry", draft_id)[1])


@app.post("/drafts/{draft_id}/settle")
def settle(draft_id: int, request: Request, sent: str = "1"):
    if not _authorised(request):
        return _denied()
    return _back(request.query_params.get("key", ""), _do("settle", draft_id, sent=sent == "1")[1])


@app.post("/attention/{attention_id}/resolve")
def resolve(attention_id: int, request: Request):
    if not _authorised(request):
        return _denied()
    return _back(request.query_params.get("key", ""), _do("resolve", attention_id)[1])
