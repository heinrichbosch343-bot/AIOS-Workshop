"""
Deep Research — research a prospective or existing client company.

Given a company name or website, this searches the web and scrapes the company's
site via Firecrawl, then asks Claude to synthesise a client-research brief aimed at
BoschAI (a custom AIOS agency): what the company does, who leads it, how it runs its
operations, recent news, and how BoschAI might engage them.
"""
import re

import anthropic
import requests

from config import ANTHROPIC_API_KEY, FIRECRAWL_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-6"

FIRECRAWL_BASE = "https://api.firecrawl.dev/v1"
_URL_RE = re.compile(r"^(https?://|www\.)|\.[a-z]{2,}(/|$)", re.I)
SOURCE_CHAR_CAP = 4000   # per-source content fed to the model
MAX_SOURCES = 6


def _is_url(text: str) -> bool:
    return bool(_URL_RE.search(text.strip()))


def _headers() -> dict:
    return {"Authorization": f"Bearer {FIRECRAWL_API_KEY}", "Content-Type": "application/json"}


def _search(query: str, limit: int = MAX_SOURCES) -> list[dict]:
    """Firecrawl web search with page content as markdown."""
    resp = requests.post(
        f"{FIRECRAWL_BASE}/search",
        headers=_headers(),
        json={"query": query, "limit": limit, "scrapeOptions": {"formats": ["markdown"]}},
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json().get("data", []) or []
    out = []
    for d in data:
        out.append({
            "title": d.get("title") or d.get("metadata", {}).get("title") or d.get("url", ""),
            "url": d.get("url", ""),
            "content": (d.get("markdown") or d.get("description") or "")[:SOURCE_CHAR_CAP],
        })
    return out


def _scrape(url: str) -> dict | None:
    """Scrape a single URL to markdown."""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        resp = requests.post(
            f"{FIRECRAWL_BASE}/scrape",
            headers=_headers(),
            json={"url": url, "formats": ["markdown"]},
            timeout=90,
        )
        resp.raise_for_status()
        d = resp.json().get("data", {}) or {}
        return {
            "title": d.get("metadata", {}).get("title") or url,
            "url": url,
            "content": (d.get("markdown") or "")[:SOURCE_CHAR_CAP],
        }
    except Exception:
        return None


def _gather_sources(query: str) -> list[dict]:
    sources: list[dict] = []
    if _is_url(query):
        primary = _scrape(query)
        if primary:
            sources.append(primary)
        # Plus broader search on the domain name for news/context.
        name = re.sub(r"^https?://(www\.)?", "", query).split("/")[0]
        sources += _search(f"{name} company governance leadership news", limit=MAX_SOURCES - 1)
    else:
        sources += _search(f"{query} company overview governance leadership board", limit=MAX_SOURCES)
    # De-dupe by url, keep ones with content.
    seen, deduped = set(), []
    for s in sources:
        u = s.get("url", "")
        if u and u not in seen and s.get("content"):
            seen.add(u)
            deduped.append(s)
    return deduped[:MAX_SOURCES]


_BRIEF_PROMPT = """You are a research analyst at BoschAI, a solo AI agency that builds custom AI \
Operating Systems (AIOS) for medium-to-large companies. Heinrich (the founder) is researching the \
company below as a potential or existing client. Using ONLY the sources provided, write a tight \
research brief.

Company / query: {query}

SOURCES:
{sources}

Write the brief in this structure, using plain markdown headings. Be concrete and specific. If a \
section has no evidence in the sources, write "Not found in sources" rather than guessing.

## Snapshot
One or two sentences: what the company is and does.

## What they do
The business, sector, size, and footprint.

## Leadership & team
Named founders, executives, or key team members if present.

## Operational signals
Anything relevant to how they run the business: team size, manual workload, tooling/tech stack, data \
sources, recurring processes, and where bandwidth or admin overhead likely bites.

## Recent news
Notable recent developments.

## Angle for BoschAI
2-4 sentences on how a custom AIOS build from BoschAI could help them (recovering bandwidth by \
automating recurring work, wiring up a daily brief, unifying their context and data), and a sensible \
way to open the conversation.

Do not use em dashes. Use contractions. No filler."""


def research_company(query: str) -> dict:
    """Return { query, brief, sources:[{title,url}], error? }."""
    if not FIRECRAWL_API_KEY:
        return {"query": query, "brief": "", "sources": [],
                "error": "FIRECRAWL_API_KEY is not set on the server."}

    try:
        sources = _gather_sources(query)
    except requests.HTTPError as e:
        return {"query": query, "brief": "", "sources": [], "error": f"Search failed: {e}"}
    except Exception as e:
        return {"query": query, "brief": "", "sources": [], "error": f"Search error: {e}"}

    if not sources:
        return {"query": query, "brief": "", "sources": [],
                "error": "No usable sources found. Try a more specific company name or a website URL."}

    source_block = "\n\n".join(
        f"[{i+1}] {s['title']} — {s['url']}\n{s['content']}" for i, s in enumerate(sources)
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            messages=[{"role": "user",
                       "content": _BRIEF_PROMPT.format(query=query, sources=source_block)}],
        )
        brief = "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        return {"query": query, "brief": "", "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
                "error": f"Synthesis failed: {e}"}

    return {
        "query": query,
        "brief": brief,
        "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
    }
