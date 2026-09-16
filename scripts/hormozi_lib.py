"""hormozi_lib.py - the logic behind the Hormozi library, with no I/O in it.

Book identification, page cleaning, chapter labels from the PDF bookmarks,
chunking, keyword scoring (BM25), rank fusion and citations. Everything that can
be wrong without a PDF, a network or an API key lives here, so it is tested by
scripts/test_hormozi_lib.py for free. hormozi_index.py and hormozi_search.py do
the reading, embedding and printing around it.

Three decisions that are easy to undo by accident:

  Chapters come from the bookmark TITLE, never its depth. $100M Leads nests its
  sections one level below its chapters, so depth reads the book upside down.

  A chunk never crosses a chapter. A citation that spans two chapters points at
  neither, and "open the PDF on page 139" is the whole point of citing.

  Keyword scoring sits next to the embeddings on purpose. Hormozi names his
  frameworks ("Grand Slam Offer", "Value Equation", "Core Four"), and an exact
  name is what BM25 is best at and what a vector blurs.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

# ── defaults ─────────────────────────────────────────────────────────────────

CHUNK_TARGET_WORDS = 380      # ~500 tokens: one idea with its example attached
CHUNK_OVERLAP_WORDS = 60      # a framework that starts at a boundary survives in both
CHUNK_MIN_TAIL_WORDS = 80     # anything shorter is folded into the chunk before it
CHUNK_SNAP_WORDS = 60         # how far back to look for a sentence end
MIN_PAGE_WORDS = 8            # title pages, barcodes and blank pages carry nothing
RRF_K = 60                    # the standard constant from Cormack et al. 2009


# ── books ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Book:
    slug: str
    title: str
    short: str


# Checked in order. Lost Chapters comes first because its subtitle names the
# other three books, so any looser match would claim it.
KNOWN_BOOKS = (
    ("lost chapters", Book("lost-chapters", "$100M Lost Chapters", "LC")),
    ("money models", Book("money-models", "$100M Money Models", "MM")),
    ("leads", Book("leads", "$100M Leads", "L")),
    ("offers", Book("offers", "$100M Offers", "O")),
)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def identify_book(filename: str) -> Book:
    stem = Path(filename).stem
    lowered = stem.lower()
    for needle, book in KNOWN_BOOKS:
        if needle in lowered:
            return book

    title = re.sub(r"\([^)]*\)", "", stem)
    title = re.sub(r"\s+-\s+alex hormozi\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip() or stem
    short = "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", title)).upper() or "B"
    return Book(slugify(title) or "book", title, short)


def resolve_book(value: str, books: list[Book]) -> str:
    """A --book argument -> one book's slug, or ValueError rather than a guess.

    Exact slug or short code wins outright. Only then is part of a title
    accepted, and only if it is 3+ characters and names exactly one book: a
    loose match first is how "O" once resolved to Lost Chapters.
    """
    wanted = value.lower().strip()
    for book in books:
        if wanted in (book.slug, book.short.lower()):
            return book.slug
    loose = sorted({b.slug for b in books if len(wanted) >= 3 and wanted in b.title.lower()})
    if len(loose) == 1:
        return loose[0]
    names = ", ".join(f"{b.slug} ({b.short})" for b in books)
    problem = f"matches {len(loose)} books" if loose else "matches no book"
    raise ValueError(f"'{value}' {problem}. Books: {names}")


# ── page cleaning ────────────────────────────────────────────────────────────

_BOILERPLATE_LINES = (
    re.compile(r"^copyright ©.*not for distribution$", re.IGNORECASE),
    re.compile(r"^oceanofpdf\.com$", re.IGNORECASE),
    re.compile(r"^\d{1,4}$"),
    # Roman page numbers from the front matter. The lookahead leaves out m and d
    # so an ordinary word on its own line ("mid", "mix") is not mistaken for one.
    re.compile(r"^(?=[ivxlc]+$)(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.IGNORECASE),
)

_BOILERPLATE_PAGE_MARKERS = (
    "all rights reserved",
    "no part of this book may be reproduced",
    "reproduction or translation of any part",
    "library of congress",
    "isbn",
)

# Only ever applied to pages BEFORE the book's first chapter. "guarantees" and
# "not typical" are ordinary words inside the chapters, so these must never be
# run over content pages.
_FRONT_MATTER_LEGAL = _BOILERPLATE_PAGE_MARKERS + (
    "disclaimer",
    "for educational and informational purposes",
    "not made any guarantees",
    "results are not typical",
)


def clean_page_text(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = re.sub(r"(\w)-\n(?=[a-z])", r"\1", text)          # cus-\ntomers -> customers
    lines = [line.strip() for line in text.splitlines()]
    kept = [line for line in lines
            if line and not any(p.match(line) for p in _BOILERPLATE_LINES)]
    text = " ".join(kept)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,;:!?])", r"\1", text)             # "useful . But" -> "useful. But"
    return text.strip()


def is_boilerplate_page(text: str) -> bool:
    lowered = text.lower()
    return len(text.split()) < 250 and any(m in lowered for m in _BOILERPLATE_PAGE_MARKERS)


def front_matter_reasons(texts: list[str], figures: list[str] | None = None) -> list[str | None]:
    """For each page before the first chapter: None to index it, else why not.

    Kept: the author's own words (guiding principles, dedications, a quick word,
    thank-yous, testimonials). Dropped: blank, legal, title and contents pages.
    A contents page is dropped for a reason beyond tidiness: it names every
    chapter, so it would match every chapter-name search and crowd out the
    chapter itself.

    `figures` is each page's transcribed image text. A page that looks blank or
    like a title page is kept when its image carries real content.
    """
    figures = figures or [""] * len(texts)
    reasons: list[str | None] = []
    for text, figure in zip(texts, figures):
        lowered = text.lower()
        words = len(text.split())
        previous = reasons[-1] if reasons else None
        if words == 0:
            reason = "blank"
        elif lowered.startswith(("contents", "table of contents")):
            reason = "contents"
        elif previous == "contents" and not re.search(r"[.!?]", text):
            reason = "contents"          # the second page of a two-page contents list
        elif any(marker in lowered for marker in _FRONT_MATTER_LEGAL):
            reason = "legal"
        elif words < 3 or (words < 40 and "$100m" in lowered):
            reason = "title page"
        else:
            reason = None
        if reason in ("blank", "title page") and len(figure.split()) >= MIN_PAGE_WORDS:
            reason = None
        reasons.append(reason)
    return reasons


def content_page_reason(text: str, figures: str) -> str | None:
    """For a page inside the book: None to index it, else why not.

    `figures` is the transcribed text of the page's images, so a page that is
    one diagram and a three-word caption is indexed rather than skipped.
    """
    words = len(text.split()) + len(figures.split())
    if words == 0:
        return "blank"
    if is_boilerplate_page(text):
        return "legal"
    if words < MIN_PAGE_WORDS:
        return "heading only"
    return None


# ── figures ──────────────────────────────────────────────────────────────────

FIGURE_KINDS = frozenset({
    "text",          # typed text set as an image (author notes, callout boxes)
    "diagram",       # drawn or whiteboard diagrams, charts, formulas with labels
    "table",
    "handwritten",   # handwritten notes and lists
    "screenshot",    # ads, posts, emails, web pages
    "photo",
    "qr",
    "logo",
    "decorative",
})
_NON_CONTENT_KINDS = frozenset({"qr", "logo", "decorative"})


@dataclass(frozen=True)
class Figure:
    id: str
    page: int
    kind: str
    text: str


def parse_figure(row, page: int) -> Figure | None:
    """A transcript as written by a transcriber -> Figure, or None if malformed."""
    if not isinstance(row, dict):
        return None
    fid, kind, text = row.get("id"), row.get("kind"), row.get("text")
    if not isinstance(fid, str) or not fid or kind not in FIGURE_KINDS or not isinstance(text, str):
        return None
    return Figure(id=fid, page=page, kind=kind, text=text.strip())


def same_box(a: list[float], b: list[float], tolerance: float = 1.0) -> bool:
    """Whether two figure positions (x0, y0, x1, y1 in points) are the same image.

    Figure ids come from an image's order on its page, so a replaced PDF can put a
    different picture behind an old id. Comparing positions catches that.
    """
    return len(a) == len(b) == 4 and all(abs(x - y) <= tolerance for x, y in zip(a, b))


def figure_text(figures: list[Figure]) -> str:
    """One page's figures -> text appended to that page. QR codes and logos add nothing."""
    return " ".join(f"[Figure: {f.text}]" for f in figures
                    if f.kind not in _NON_CONTENT_KINDS and f.text)


# ── outline ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OutlineEntry:
    title: str
    page: int
    is_section: bool


_FRONT_MATTER = {
    "title page", "copyright", "what others have said", "dedication", "thank you",
    "contents", "table of contents", "acknowledgments", "acknowledgements", "praise",
}


def clean_outline(toc: list) -> list[OutlineEntry]:
    """PyMuPDF get_toc() rows [level, title, page] -> clean, page-ordered entries.

    Drops the auto-generated bookmarks some exports carry ("_jyeyz5f5pwxw") and
    sorts a section ahead of a chapter that starts on the same page.
    """
    entries = []
    for index, row in enumerate(toc):
        _level, title, page = row[0], str(row[1]).strip(), int(row[2])
        if not title or title.startswith("_") or page < 1:
            continue
        is_section = bool(re.match(r"^section\b", title, re.IGNORECASE))
        entries.append((page, 0 if is_section else 1, index, OutlineEntry(title, page, is_section)))
    return [entry for *_, entry in sorted(entries)]


def content_start_page(outline: list[OutlineEntry]) -> int:
    for entry in outline:
        if entry.title.lower() not in _FRONT_MATTER:
            return entry.page
    return 1


def page_labels(outline: list[OutlineEntry], page_count: int) -> dict[int, tuple[str, str]]:
    """Page number -> (section, chapter) that page belongs to."""
    labels = {}
    section, chapter = "", ""
    remaining = list(outline)
    for page in range(1, page_count + 1):
        while remaining and remaining[0].page <= page:
            entry = remaining.pop(0)
            if entry.is_section:
                section, chapter = entry.title, ""
            else:
                chapter = entry.title
        labels[page] = (section, chapter)
    return labels


# ── chunking ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Page:
    number: int
    text: str
    section: str
    chapter: str


@dataclass(frozen=True)
class Chunk:
    id: str
    book: str
    title: str
    short: str
    section: str
    chapter: str
    page_start: int
    page_end: int
    text: str


def _ends_sentence(word: str) -> bool:
    return word.rstrip("\"'”’)]").endswith((".", "!", "?"))


def _snap_end(words: list[str], start: int, end: int, target: int, snap: int) -> int:
    floor = max(start + target // 2, end - snap)
    for i in range(end - 1, floor - 1, -1):
        if _ends_sentence(words[i]):
            return i + 1
    return end


def _groups(pages: list[Page]) -> list[list[Page]]:
    groups: list[list[Page]] = []
    for page in pages:
        if groups and (groups[-1][0].section, groups[-1][0].chapter) == (page.section, page.chapter):
            groups[-1] = [*groups[-1], page]
        else:
            groups.append([page])
    return groups


def chunk_pages(pages: list[Page], book: Book, target: int = CHUNK_TARGET_WORDS,
                overlap: int = CHUNK_OVERLAP_WORDS, min_tail: int = CHUNK_MIN_TAIL_WORDS,
                snap: int = CHUNK_SNAP_WORDS) -> list[Chunk]:
    if overlap >= target:
        raise ValueError(f"overlap ({overlap}) must be smaller than target ({target})")

    chunks: list[Chunk] = []
    for group in _groups(pages):
        words: list[str] = []
        owners: list[int] = []
        for page in group:
            page_words = page.text.split()
            words.extend(page_words)
            owners.extend([page.number] * len(page_words))

        n, start = len(words), 0
        while start < n:
            end = min(start + target, n)
            if n - end < min_tail:
                end = n
            else:
                end = _snap_end(words, start, end, target, snap)
            chunks.append(Chunk(
                id=f"{book.short}-{len(chunks):04d}", book=book.slug, title=book.title,
                short=book.short, section=group[0].section, chapter=group[0].chapter,
                page_start=owners[start], page_end=owners[end - 1], text=" ".join(words[start:end]),
            ))
            if end >= n:
                break
            start = max(end - overlap, start + 1)
    return chunks


def location(chunk: Chunk) -> str:
    return " > ".join(part for part in (chunk.section, chunk.chapter) if part)


def embed_text(chunk: Chunk) -> str:
    where = location(chunk)
    header = f"{chunk.title} | {where}" if where else chunk.title
    return f"{header}\n\n{chunk.text}"


# ── keyword search ───────────────────────────────────────────────────────────

_STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further
had has have having he her here hers him his how i if in into is it its itself just me more
most my no nor not now of off on once only or other our ours out over own same she should so
some such than that the their theirs them then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you
your yours yourself
""".split())


def _fold(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    text = re.sub(r"['’]s\b", "", text.lower())
    return [_fold(t) for t in re.findall(r"[a-z0-9]+", text) if len(t) > 1 and t not in _STOPWORDS]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [self._counts(doc) for doc in docs]
        self.lengths = [len(doc) for doc in docs]
        self.avg_length = (sum(self.lengths) / len(docs)) if docs else 0.0
        frequency: dict[str, int] = {}
        for counts in self.docs:
            for term in counts:
                frequency[term] = frequency.get(term, 0) + 1
        n = len(docs)
        self.idf = {t: math.log((n - df + 0.5) / (df + 0.5) + 1) for t, df in frequency.items()}

    @staticmethod
    def _counts(doc: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for term in doc:
            counts[term] = counts.get(term, 0) + 1
        return counts

    def scores(self, query: list[str]) -> list[float]:
        terms = [t for t in dict.fromkeys(query) if t in self.idf]
        results = []
        for counts, length in zip(self.docs, self.lengths):
            score = 0.0
            for term in terms:
                tf = counts.get(term, 0)
                if tf:
                    norm = self.k1 * (1 - self.b + self.b * length / (self.avg_length or 1))
                    score += self.idf[term] * tf * (self.k1 + 1) / (tf + norm)
            results.append(score)
        return results


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: merge rankings by position, ignoring raw scores."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda pair: pair[1], reverse=True)


# ── lookups and citations ────────────────────────────────────────────────────

def cite(chunk: Chunk) -> str:
    pages = (f"p. {chunk.page_start}" if chunk.page_start == chunk.page_end
             else f"pp. {chunk.page_start}-{chunk.page_end}")
    where = chunk.chapter or chunk.section
    return f"{chunk.title}, {pages}" + (f" ({where})" if where else "")


def _title_tail(title: str) -> list[str]:
    """The part of a chapter title after its numbering and prefix, as tokens."""
    return tokenize(re.split(r"[:.]\s+", title)[-1])


def find_chapter(chunks: list[Chunk], query: str, book: str | None = None) -> list[Chunk]:
    """Chunks whose chapter or section title contains the query.

    A chapter NAMED the query beats one that merely mentions it, so "guarantees"
    returns the Guarantees chapter and not the overview listing five topics.
    """
    needle = query.lower().strip()
    in_book = [c for c in chunks if book is None or c.book == book]
    exact = [c for c in in_book if c.chapter and _title_tail(c.chapter) == tokenize(needle)]
    if exact:
        return exact
    return [c for c in in_book if needle in c.chapter.lower() or needle in c.section.lower()]


def merge_overlap(texts: list[str], max_overlap: int = CHUNK_OVERLAP_WORDS * 2) -> str:
    """Join consecutive chunks back into prose without repeating the overlap."""
    merged: list[str] = []
    for text in texts:
        words = text.split()
        limit = min(max_overlap, len(merged), len(words))
        shared = next((k for k in range(limit, 0, -1) if merged[-k:] == words[:k]), 0)
        merged = [*merged, *words[shared:]]
    return " ".join(merged)


@dataclass(frozen=True)
class TocRow:
    book: str
    title: str
    section: str
    chapter: str
    page_start: int
    page_end: int
    chunks: int


def table_of_contents(chunks: list[Chunk]) -> list[TocRow]:
    rows: list[TocRow] = []
    for c in chunks:
        last = rows[-1] if rows else None
        if last and (last.book, last.section, last.chapter) == (c.book, c.section, c.chapter):
            rows[-1] = TocRow(last.book, last.title, last.section, last.chapter, last.page_start,
                              max(last.page_end, c.page_end), last.chunks + 1)
        else:
            rows.append(TocRow(c.book, c.title, c.section, c.chapter, c.page_start, c.page_end, 1))
    return rows
