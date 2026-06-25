"""
Text embeddings via Voyage AI — the "meaning fingerprints" behind the pool.

Every document passage and every search question is turned into a vector here, so that
semantically similar text lands close together regardless of exact wording. This is the
ONE place that talks to the embeddings provider — swap models/providers here and nothing
else changes (just re-run the SQL with the new dimension and re-index).

Voyage tunes the two sides of a match differently, so indexing uses input_type="document"
and a live search uses input_type="query".
"""
import time

import voyageai
from voyageai.error import RateLimitError

import pool_config

# Voyage caps a single request at 1000 texts; we batch to stay under it.
_MAX_BATCH = 1000

_client = None


def _get_client() -> "voyageai.Client":
    global _client
    if _client is None:
        pool_config.require("VOYAGE_API_KEY")
        _client = voyageai.Client(api_key=pool_config.VOYAGE_API_KEY)
    return _client


def _embed_batch(client, batch: list[str], input_type: str) -> list[list[float]]:
    """One request, with backoff so the free-tier rate limit (3 RPM) just waits it out."""
    for attempt in range(6):
        try:
            return client.embed(
                batch, model=pool_config.EMBEDDING_MODEL, input_type=input_type
            ).embeddings
        except RateLimitError:
            if attempt == 5:
                raise
            time.sleep(min(60, 15 * (attempt + 1)))


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    if not texts:
        return []
    client = _get_client()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), _MAX_BATCH):
        vectors.extend(_embed_batch(client, texts[i:i + _MAX_BATCH], input_type))
    return vectors


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed passages for storage in the pool. Batched; returns one vector per text."""
    return _embed(texts, input_type="document")


def embed_query(text: str) -> list[float]:
    """Embed a single search question. Returns one vector."""
    return _embed([text], input_type="query")[0]
