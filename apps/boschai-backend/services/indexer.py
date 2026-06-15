"""
Build the Knowledge Pool: crawl client Drive folders, slice files into passages, embed them,
and upsert into Supabase `knowledge_chunks`.

Skips system/dev folders and non-report file types (see the exclude lists). Idempotent: a file
whose text is unchanged (same content hash) is left alone, so re-running only does new/changed
work. Embedding is paced + retried so it survives Voyage's free-tier rate limit.

Each top-level company folder = one "company" (the dashboard dropdown value); its subfolders
are crawled automatically and tagged as the "project".
"""
import hashlib
import time

from googleapiclient.discovery import build as gbuild

from config import POOL_CLIENT_ROOTS, EMBED_BATCH_SIZE, EMBED_REQUEST_INTERVAL
from db.client import supabase
from services.drive import get_credentials
from services.drive_extract import extract_text
from services.embeddings import embed_documents
from services.chunker import chunk_text

FOLDER_MIME = "application/vnd.google-apps.folder"

# Folders we never index — system/dev junk + admin/non-report material. Case-insensitive;
# any folder whose name starts with "." is also skipped.
EXCLUDE_FOLDERS = {
    "node_modules", ".git", ".next", ".venv", "__pycache__", "dist", "build", ".cache",
    ".planning", ".claude", ".tmp.driveupload", "templates", "admin", "finance", "billing",
    "invoices", "contracts", "personal", "archive", "old", "designs", "design assets",
}

# Only these file types get indexed (spreadsheets, images, audio, video, etc. are skipped).
INCLUDE_MIMES = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.presentation",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
INCLUDE_EXTS = (".pdf", ".docx", ".txt", ".md")

# File-name signals for admin/non-report or stale material — skipped even if the type is fine.
EXCLUDE_NAME_BITS = (
    "invoice", "receipt", "quote", "proposal", "contract", "nda", "engagement letter",
    "budget", "timesheet", "copy of", "archive", " old", "draft v",
)


def _excluded_folder(name: str) -> bool:
    n = (name or "").strip().lower()
    return n.startswith(".") or n in EXCLUDE_FOLDERS


def _should_index(name: str, mime: str) -> bool:
    n = (name or "").lower()
    if not (mime in INCLUDE_MIMES or n.endswith(INCLUDE_EXTS)):
        return False
    if n.startswith("~$"):
        return False
    return not any(bit in n for bit in EXCLUDE_NAME_BITS)


def _drive():
    return gbuild("drive", "v3", credentials=get_credentials())


def _list_children(svc, folder_id: str) -> list[dict]:
    items, token = [], None
    while True:
        res = svc.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
            pageSize=100, pageToken=token,
        ).execute()
        items.extend(res.get("files", []))
        token = res.get("nextPageToken")
        if not token:
            break
    return items


def _crawl(svc, folder_id: str, company: str, project, out: list[dict]) -> None:
    for f in _list_children(svc, folder_id):
        if f["mimeType"] == FOLDER_MIME:
            if _excluded_folder(f["name"]):
                continue
            _crawl(svc, f["id"], company, project or f["name"], out)
        elif _should_index(f["name"], f["mimeType"]):
            out.append({
                "id": f["id"], "name": f["name"], "mime": f["mimeType"],
                "modified": f.get("modifiedTime"), "company": company, "project": project,
            })


def _company_roots(svc, only: str | None = None) -> list[dict]:
    """Top-level folders to treat as companies (POOL_CLIENT_ROOTS, or all non-excluded)."""
    tops = [f for f in _list_children(svc, "root")
            if f["mimeType"] == FOLDER_MIME and not _excluded_folder(f["name"])]
    if POOL_CLIENT_ROOTS:
        wanted = {w.lower() for w in POOL_CLIENT_ROOTS}
        tops = [f for f in tops if f["name"].lower() in wanted or f["id"] in POOL_CLIENT_ROOTS]
    if only:
        tops = [f for f in tops if f["name"].lower() == only.lower() or f["id"] == only]
    return tops


def discover(only: str | None = None) -> dict:
    """Crawl WITHOUT embedding — returns {company: [file, ...]} for a dry run / preview."""
    svc = _drive()
    plan: dict[str, list[dict]] = {}
    for root in _company_roots(svc, only):
        files: list[dict] = []
        _crawl(svc, root["id"], root["name"], None, files)
        plan[root["name"]] = files
    return plan


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def _existing_hash(source_id: str) -> str | None:
    res = supabase.table("knowledge_chunks").select("content_hash").eq(
        "source_id", source_id).limit(1).execute()
    return res.data[0]["content_hash"] if res.data else None


def _store(file: dict, chunks: list[str], vectors: list[list[float]], h: str) -> None:
    supabase.table("knowledge_chunks").delete().eq("source_id", file["id"]).execute()
    rows = [{
        "content": c,
        "embedding": str(v),
        "source_type": "drive",
        "source_id": file["id"],
        "source_name": file["name"],
        "client": file["company"],
        "project": file.get("project"),
        "source_date": file.get("modified"),
        "chunk_index": i,
        "content_hash": h,
    } for i, (c, v) in enumerate(zip(chunks, vectors))]
    for i in range(0, len(rows), 50):  # modest pages keep request bodies small
        supabase.table("knowledge_chunks").insert(rows[i:i + 50]).execute()


def index_file(file: dict) -> dict:
    """Index one Drive file. Returns a status dict; never raises on a single file."""
    try:
        res = extract_text(file["id"], file["mime"], file["name"], max_chars=None)
        text = (res.get("text") or "").strip()
        # extract_text returns "(Preview not supported...)" / "(Could not extract...)" on failure.
        if not text or text.startswith("("):
            return {"file": file["name"], "status": "skipped (no text)", "chunks": 0}
        h = _hash(text)
        if _existing_hash(file["id"]) == h:
            return {"file": file["name"], "status": "unchanged", "chunks": 0}
        chunks = chunk_text(text)
        vectors: list[list[float]] = []
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            vectors.extend(embed_documents(chunks[i:i + EMBED_BATCH_SIZE]))
            if EMBED_REQUEST_INTERVAL and i + EMBED_BATCH_SIZE < len(chunks):
                time.sleep(EMBED_REQUEST_INTERVAL)
        _store(file, chunks, vectors, h)
        return {"file": file["name"], "status": "indexed", "chunks": len(chunks)}
    except Exception as e:
        return {"file": file["name"], "status": f"error: {e}", "chunks": 0}


def reindex_all(only: str | None = None, log=print) -> dict:
    """Index every selected company folder. `only` limits to one company (name or id)."""
    plan = discover(only)
    totals = {"files": 0, "indexed": 0, "chunks": 0, "skipped": 0, "errors": 0}
    for company, files in plan.items():
        log(f"\n[{company}] {len(files)} candidate files")
        for f in files:
            totals["files"] += 1
            r = index_file(f)
            if r["status"] == "indexed":
                totals["indexed"] += 1
                totals["chunks"] += r["chunks"]
            elif r["status"].startswith("error"):
                totals["errors"] += 1
            else:
                totals["skipped"] += 1
            extra = f" ({r['chunks']} chunks)" if r["chunks"] else ""
            log(f"  - {r['file']}: {r['status']}{extra}")
    return totals
