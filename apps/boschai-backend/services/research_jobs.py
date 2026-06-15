"""
In-memory job manager for deep-research runs.

Deep research takes minutes, so the API starts a background job and the dashboard
polls it. Single-instance (Railway/local) so an in-memory store is fine. Finished
dossiers are also written to outputs/deep-research/{date-slug}/ (best effort).
"""
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services.deep_research import run_deep_research

_JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()
# Repo-root /outputs only exists locally; on hosted deploys (apps/boschai-backend
# is the app root) there's no parents[3], so resolve safely and skip saving there.
_PARENTS = Path(__file__).resolve().parents
_OUT_DIR = (_PARENTS[3] / "outputs" / "deep-research") if len(_PARENTS) > 3 else None
MAX_JOBS = 50  # keep the store bounded


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:50] or "research"


def _set(job_id: str, **fields):
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def _prune():
    if len(_JOBS) > MAX_JOBS:
        oldest = sorted(_JOBS.items(), key=lambda kv: kv[1]["created_at"])[: len(_JOBS) - MAX_JOBS]
        for jid, _ in oldest:
            _JOBS.pop(jid, None)


def _save_dossier(topic: str, result: dict, started: str):
    if not _OUT_DIR:
        return None  # hosted deploy: no repo-root outputs dir, skip local save
    try:
        folder = _OUT_DIR / f"{started[:10]}-{_slug(topic)}"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "synthesis.md").write_text(result.get("dossier", ""), encoding="utf-8")
        (folder / "critic-notes.md").write_text(result.get("critic_notes", ""), encoding="utf-8")
        for r in result.get("reports", []):
            (folder / f"{r['slug']}.md").write_text(r.get("report", ""), encoding="utf-8")
        return str(folder)
    except Exception:
        return None


def _run(job_id: str, topic: str, time_period: str):
    started = _JOBS[job_id]["created_at"]
    _set(job_id, status="running")

    def on_progress(phase, detail, pct):
        _set(job_id, phase=phase, detail=detail, pct=pct)

    try:
        result = run_deep_research(topic, time_period, on_progress=on_progress)
        saved = _save_dossier(topic, result, started)
        _set(job_id, status="done", pct=100, result=result, saved_to=saved)
    except Exception as e:
        _set(job_id, status="error", error=str(e))


def start_job(topic: str, time_period: str = "last 12 months") -> str:
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {
            "id": job_id, "topic": topic, "status": "queued",
            "phase": "queued", "detail": "Starting…", "pct": 0,
            "result": None, "error": None, "saved_to": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        _prune()
    threading.Thread(target=_run, args=(job_id, topic, time_period), daemon=True).start()
    return job_id


def get_job(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None
