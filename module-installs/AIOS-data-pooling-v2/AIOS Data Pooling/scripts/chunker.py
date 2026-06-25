"""
Split a document's text into overlapping passages for the pool.

Char-based (~4 chars per token) so there's no tokenizer dependency: aim for ~800-token
passages with ~100-token overlap, splitting on paragraph then sentence boundaries so a
chunk rarely cuts mid-thought. Each passage is embedded and stored on its own.
"""
import re

_CHARS_PER_TOKEN = 4
DEFAULT_MAX_CHARS = 800 * _CHARS_PER_TOKEN       # ~800 tokens
DEFAULT_OVERLAP_CHARS = 100 * _CHARS_PER_TOKEN   # ~100 tokens


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _split_sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]


def chunk_text(text: str, max_chars: int = DEFAULT_MAX_CHARS,
               overlap_chars: int = DEFAULT_OVERLAP_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []

    # 1. Break into units no larger than max_chars: paragraphs, then sentences, then hard slices.
    units: list[str] = []
    for para in _split_paragraphs(text):
        if len(para) <= max_chars:
            units.append(para)
            continue
        for sent in _split_sentences(para):
            if len(sent) <= max_chars:
                units.append(sent)
            else:
                units.extend(sent[i:i + max_chars] for i in range(0, len(sent), max_chars))

    # 2. Greedily pack units into chunks, carrying a tail-overlap into the next chunk.
    chunks: list[str] = []
    cur = ""
    for u in units:
        if cur and len(cur) + 1 + len(u) > max_chars:
            chunks.append(cur)
            tail = cur[-overlap_chars:] if overlap_chars else ""
            cur = f"{tail}\n{u}".strip() if tail else u
        else:
            cur = f"{cur}\n{u}".strip() if cur else u
    if cur:
        chunks.append(cur)
    return chunks
