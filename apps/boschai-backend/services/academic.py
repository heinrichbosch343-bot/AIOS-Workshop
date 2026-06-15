"""
Academic search via OpenAlex (https://openalex.org) — 250M+ papers, no API key.

Used by the deep-research engine to ground claims in peer-reviewed work and to
profile a company's sector/governance research footprint.
"""
import requests

_BASE = "https://api.openalex.org/works"
# OpenAlex asks for a contact in the UA for the polite pool.
_UA = {"User-Agent": "BoschAI-DeepResearch/1.0 (mailto:heinrichbosch343@gmail.com)"}


def _abstract(inv: dict | None) -> str:
    """Rebuild an abstract from OpenAlex's inverted index."""
    if not inv:
        return ""
    positions = []
    for word, idxs in inv.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)[:1200]


def search(query: str, limit: int = 6, year_from: int = 2021) -> list[dict]:
    """Return top papers by citation count. Never raises — returns [] on error."""
    try:
        resp = requests.get(
            _BASE,
            headers=_UA,
            params={
                "search": query,
                "per_page": min(limit, 25),
                "sort": "cited_by_count:desc",
                "filter": f"from_publication_date:{year_from}-01-01",
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", []) or []
    except Exception:
        return []

    out = []
    for r in results:
        authors = [a.get("author", {}).get("display_name", "") for a in r.get("authorships", [])][:5]
        loc = (r.get("primary_location") or {}).get("source") or {}
        out.append({
            "title": r.get("title", ""),
            "year": r.get("publication_year"),
            "cited_by": r.get("cited_by_count", 0),
            "authors": [a for a in authors if a],
            "venue": loc.get("display_name", ""),
            "doi": r.get("doi", ""),
            "url": r.get("doi") or r.get("id", ""),
            "abstract": _abstract(r.get("abstract_inverted_index")),
        })
    return out
