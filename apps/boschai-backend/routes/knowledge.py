from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from pydantic import BaseModel

from config import API_SECRET_KEY
from services.knowledge import ask
from services import indexer

# Reindex logs per file; silence that in the request path (totals are returned/logged instead).
def _quiet(*_args, **_kwargs):
    pass

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def verify_key(x_api_key: str):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


class AskRequest(BaseModel):
    question: str
    client: str | None = None       # company/top-level folder name
    project: str | None = None      # subfolder within the client
    source_id: str | None = None    # one specific Drive file
    k: int = 15


@router.post("/ask")
def ask_knowledge(req: AskRequest, x_api_key: str = Header(...)):
    """
    Answer a question from the Knowledge Pool — semantic search across every indexed Drive
    document and meeting transcript at once, matched by meaning. Scope narrows with each
    filter: `client` → one company, `project` → one subfolder, `source_id` → one file
    (all enforced at the DB layer). Returns { answer, citations, chunks_used }.
    """
    verify_key(x_api_key)
    try:
        return ask(req.question, client=req.client, project=req.project,
                   source_id=req.source_id, k=req.k)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:  # Voyage/Supabase not configured
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class ReindexRequest(BaseModel):
    client: str | None = None      # one company/folder name; omit to refresh the whole pool
    background: bool = False        # true → return immediately and index in the background


@router.post("/reindex")
def reindex_knowledge(
    req: ReindexRequest, background_tasks: BackgroundTasks, x_api_key: str = Header(...)
):
    """
    Refresh the Knowledge Pool from Drive. Incremental + idempotent: only new or changed files
    are re-embedded (unchanged files are skipped via their content hash). `client` limits the
    run to one company; omit to refresh everything.

    Default runs synchronously and returns the counts { files, indexed, chunks, skipped, errors }.
    Set `background: true` to return { status: "started" } immediately and index in the
    background — use that for a large first backfill so the request doesn't time out.
    """
    verify_key(x_api_key)
    try:
        if req.background:
            background_tasks.add_task(indexer.reindex_all, only=req.client, log=_quiet)
            return {"status": "started", "client": req.client}
        return indexer.reindex_all(only=req.client, log=_quiet)
    except RuntimeError as e:  # Google/Voyage/Supabase not configured
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
