import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from bot.command_os import start_bot, stop_bot
from services.scheduler import start_scheduler, stop_scheduler
from routes.auth import router as auth_router
from routes.drive import router as drive_router
from routes.chat import router as chat_router
from routes.report import router as report_router
from routes.extract import router as extract_router
from routes.signoff import router as signoff_router
from routes.projects import router as projects_router
from routes.email import router as email_router
from routes.brief import router as brief_router
from routes.research import router as research_router
from routes.knowledge import router as knowledge_router


# Set DISABLE_TELEGRAM_BOT=1 to run the API without the Telegram bot poller.
# Used for local testing so it doesn't conflict with the live Railway bot.
BOT_ENABLED = os.getenv("DISABLE_TELEGRAM_BOT") != "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if BOT_ENABLED:
        await start_bot()
        start_scheduler()  # daily brief + sign-off watcher (hosted only)
    yield
    if BOT_ENABLED:
        await stop_bot()
        stop_scheduler()


app = FastAPI(lifespan=lifespan)

# ── Basic per-IP rate limiting (abuse / brute-force protection) ──
_RATE_WINDOW = 60     # seconds
_RATE_MAX = 120       # max requests per window per client IP
_hits: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")
    now = time.time()
    dq = _hits[ip]
    while dq and dq[0] < now - _RATE_WINDOW:
        dq.popleft()
    if len(dq) >= _RATE_MAX:
        return JSONResponse({"error": "Rate limit exceeded. Please slow down."}, status_code=429)
    dq.append(now)
    if len(_hits) > 5000:  # drop idle IPs so the map can't grow unbounded
        for k in [k for k, v in list(_hits.items()) if not v]:
            _hits.pop(k, None)
    return await call_next(request)


app.include_router(auth_router)
app.include_router(drive_router)
app.include_router(chat_router)
app.include_router(report_router)
app.include_router(extract_router)
app.include_router(signoff_router)
app.include_router(projects_router)
app.include_router(email_router)
app.include_router(brief_router)
app.include_router(research_router)
app.include_router(knowledge_router)


@app.get("/health")
def health():
    return {"status": "ok"}
