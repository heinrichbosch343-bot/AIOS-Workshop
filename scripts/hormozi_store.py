"""hormozi_store.py - where the Hormozi index lives, and how to reach Voyage.

Shared by hormozi_index.py (writes) and hormozi_search.py (reads). The index sits
beside the books in Hormozi/.index/, one pair of files per book, so a new book is
one more pair and a changed book rebuilds only its own pair:

    manifest.json               what was built, from which file, with which model
    <slug>.chunks.json          the passages with book, section, chapter and pages
    <slug>.vectors.npy          one Voyage embedding per passage, same order

The whole Hormozi/ folder is gitignored. The chunk files ARE the books' text, and
this repo pushes to GitHub.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path

import hormozi_lib as hl

WORKSPACE = Path(__file__).resolve().parents[1]
LIBRARY_DIR = Path(os.environ.get("HORMOZI_DIR") or WORKSPACE / "Hormozi")
INDEX_DIR = LIBRARY_DIR / ".index"
MANIFEST = INDEX_DIR / "manifest.json"

# Bump to force a rebuild for a reason the fingerprint cannot see (a change here
# or in hormozi_index.py). Edits to hormozi_lib.py are caught automatically.
INDEX_VERSION = 1

EMBED_MODEL = "voyage-3-large"
EMBED_DIM = 1024
RERANK_MODEL = "rerank-2.5"
EMBED_BATCH = 48              # ~24k tokens a request, well inside Voyage's 120k cap


def prepare_network() -> None:
    """Norton breaks Python TLS here two ways; undo both before importing voyageai.

    It points SSLKEYLOGFILE at a device path (OpenSSL aborts with "no
    OPENSSL_Applink") and re-signs HTTPS with a root only the Windows store knows.
    """
    os.environ.pop("SSLKEYLOGFILE", None)
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass


def voyage_key() -> str:
    # The workspace .env wins over the shell, same rule as the Anthropic key:
    # Claude Code exports variables of its own that are not this workspace's.
    try:
        import logging
        from dotenv import dotenv_values
        # A line elsewhere in .env that dotenv cannot parse warns on every run;
        # it has nothing to do with this key and only buries the real output.
        logging.getLogger("dotenv.main").setLevel(logging.ERROR)
        value = dotenv_values(WORKSPACE / ".env").get("VOYAGE_API_KEY") or ""
    except ImportError:
        value = ""
    return value or os.environ.get("VOYAGE_API_KEY", "")


@functools.lru_cache(maxsize=1)
def voyage_client():
    key = voyage_key()
    if not key:
        raise RuntimeError("VOYAGE_API_KEY is not set in .env")
    prepare_network()
    import voyageai
    return voyageai.Client(api_key=key, max_retries=2, timeout=30)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_params() -> dict:
    """The fingerprint a built book is compared against.

    Includes a hash of hormozi_lib.py itself: cleaning regexes, outline handling
    and chunk sizes all live there, and a rebuild that depends on someone
    remembering to bump a number is a stale index waiting to happen. A comment
    edit triggers a rebuild too, which costs about five cents.
    """
    lib_source = Path(hl.__file__).read_bytes()
    return {"version": INDEX_VERSION, "model": EMBED_MODEL, "dim": EMBED_DIM,
            "lib": hashlib.sha256(lib_source).hexdigest()[:16]}


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_manifest() -> dict:
    if not MANIFEST.is_file():
        return {"books": {}}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"The index manifest is unreadable ({exc}). Rebuild with --force.") from exc


def write_manifest(manifest: dict) -> None:
    _atomic_write_bytes(MANIFEST, json.dumps(manifest, indent=2).encode("utf-8"))


def chunk_path(slug: str) -> Path:
    return INDEX_DIR / f"{slug}.chunks.json"


def vector_path(slug: str) -> Path:
    return INDEX_DIR / f"{slug}.vectors.npy"


def save_book(slug: str, chunks: list[hl.Chunk], vectors) -> None:
    import io
    import numpy as np

    matrix = None
    if vectors is not None:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape != (len(chunks), EMBED_DIM):
            raise ValueError(f"{slug}: {len(chunks)} passages but vectors shaped {matrix.shape}")

    payload = json.dumps([asdict(c) for c in chunks], ensure_ascii=False)
    _atomic_write_bytes(chunk_path(slug), payload.encode("utf-8"))
    if matrix is None:
        vector_path(slug).unlink(missing_ok=True)
        return
    buffer = io.BytesIO()
    np.save(buffer, matrix)
    _atomic_write_bytes(vector_path(slug), buffer.getvalue())


def remove_book(slug: str) -> None:
    chunk_path(slug).unlink(missing_ok=True)
    vector_path(slug).unlink(missing_ok=True)


def load_index():
    """Every book in the manifest -> (chunks, vectors, has_vector).

    vectors is one unit-length row per chunk (zeros where a book was built with
    --no-embed) and has_vector says which rows are real, so a half-embedded index
    still answers keyword searches over everything.
    """
    import numpy as np

    manifest = read_manifest()
    chunks: list[hl.Chunk] = []
    rows, mask = [], []
    for slug in sorted(manifest.get("books", {})):
        path = chunk_path(slug)
        if not path.is_file():
            continue
        book_chunks = [hl.Chunk(**row) for row in json.loads(path.read_text(encoding="utf-8"))]
        matrix = None
        if vector_path(slug).is_file():
            matrix = np.load(vector_path(slug))
            if matrix.shape != (len(book_chunks), EMBED_DIM):
                matrix = None          # stale or malformed pair: trust the text, not the vectors
        chunks.extend(book_chunks)
        if matrix is None:
            rows.append(np.zeros((len(book_chunks), EMBED_DIM), dtype=np.float32))
            mask.extend([False] * len(book_chunks))
        else:
            rows.append(matrix.astype(np.float32))
            mask.extend([True] * len(book_chunks))

    if not chunks:
        return [], None, np.zeros(0, dtype=bool)
    vectors = np.vstack(rows)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.where(norms == 0, 1, norms)
    return chunks, vectors, np.asarray(mask, dtype=bool)
