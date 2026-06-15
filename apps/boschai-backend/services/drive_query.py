"""
Answer a natural-language question using ONLY the text of files in a Drive folder.

Reuses the Drive OAuth token + extract_text. Never invents — cites every claim by
file name, or says the answer isn't in the documents. (Pull & Write — query side.)
"""
import re

from anthropic import Anthropic

from config import ANTHROPIC_API_KEY
from services.drive import list_folder
from services.drive_extract import extract_text

MODEL = "claude-sonnet-4-6"
MAX_FILES = 15  # cap how many files we read per question (keeps cost + context sane)
FOLDER_MIME = "application/vnd.google-apps.folder"
NOT_FOUND = "This was not found in any of the provided documents."

_SYSTEM = (
    "You are a research assistant for Heinrich at BoschAI. "
    "Answer the question using ONLY the source documents provided by the user.\n"
    "Rules (violating them makes the answer unusable and is professionally dangerous):\n"
    "1. Do not invent, infer, or add anything not present in the documents.\n"
    "2. Cite the source for every claim in brackets with the file name, "
    "e.g. [BCX_Session2_Transcript].\n"
    f'3. If the answer is not found in any document, reply with exactly: "{NOT_FOUND}"\n'
    "4. Be concise and structured. Use bullet points for multi-part answers."
)


def _rank_files(files: list[dict], question: str) -> list[dict]:
    """Order files by filename keyword overlap with the question (best match first)."""
    words = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if len(w) > 2}
    return sorted(
        files,
        key=lambda f: sum(1 for w in words if w in (f.get("name") or "").lower()),
        reverse=True,
    )


def query_folder(folder_id: str, question: str, file_ids: list[str] | None = None) -> dict:
    """
    Read the chosen files in a Drive folder and answer the question from them.

    If file_ids is given, only those files are read; otherwise every (non-folder)
    file in the folder is considered, ranked by filename relevance, capped at
    MAX_FILES. Returns {answer, files_searched, files_total, truncated}.
    """
    if not question or not question.strip():
        raise ValueError("Question cannot be empty")

    files = [f for f in list_folder(folder_id) if f.get("mimeType") != FOLDER_MIME]
    if file_ids:
        wanted = set(file_ids)
        files = [f for f in files if f.get("id") in wanted]
    else:
        files = _rank_files(files, question)

    truncated = len(files) > MAX_FILES
    files = files[:MAX_FILES]

    blocks, searched = [], []
    for f in files:
        res = extract_text(f["id"], f.get("mimeType", ""), f.get("name", ""))
        text = (res.get("text") or "").strip()
        if text:
            blocks.append(f"[{f['name']}]\n{text}")
            searched.append(f["name"])

    if not blocks:
        return {"answer": NOT_FOUND, "files_searched": [], "files_total": 0, "truncated": truncated}

    user_content = (
        f"Question: {question}\n\nSource documents:\n\n" + "\n\n---\n\n".join(blocks)
    )
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    answer = "".join(b.text for b in resp.content if b.type == "text").strip()
    return {
        "answer": answer or NOT_FOUND,
        "files_searched": searched,
        "files_total": len(searched),
        "truncated": truncated,
    }
