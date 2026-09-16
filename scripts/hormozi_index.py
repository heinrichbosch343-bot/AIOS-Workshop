"""hormozi_index.py - read the Hormozi books, cut them into passages, embed them.

    uv run --no-project --system-certs --with pymupdf --with numpy --with voyageai \
      --with python-dotenv --with truststore python scripts/hormozi_index.py

    ... --audit      every page of every book: indexed, or skipped and why. Writes nothing
    ... --dry        show books, passages and cost, write nothing
    ... --force      rebuild every book, not only new or changed ones
    ... --no-embed   passages only; keyword search works, meaning search does not

What goes in: every page with text on it, plus the transcribed words from the
book's images (scripts/hormozi_figures.py), plus front-matter pages written by
the author. What stays out, and --audit lists each one: blank pages, legal
pages, title pages, contents pages, and section-heading pages whose heading is
already carried by every passage in that section.

Drop another PDF into Hormozi/ and run it again: books whose file, figure
transcripts and settings are unchanged are skipped, so the second run costs
nothing. Removing a PDF removes it from the index on the next run.

Cost: the four books are ~210k words, about 280k tokens. voyage-3-large lists at
$0.18 per million, so a full build is roughly five US cents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import hormozi_figures as figs
import hormozi_lib as hl
import hormozi_store as store

TOKENS_PER_WORD = 1.35
PRICE_PER_MILLION_TOKENS = 0.18
MAX_ATTEMPTS = 6


def book_figures(slug: str) -> tuple[dict[int, list[hl.Figure]], int, str]:
    """-> (transcribed figures by page, how many are not transcribed yet, fingerprint)."""
    by_page: dict[int, list[hl.Figure]] = defaultdict(list)
    pending = 0
    digest = hashlib.sha256()
    for row in figs.load_figure_list(slug):
        _state, figure = figs.transcript_state(slug, row)
        if figure:
            by_page[row["page"]].append(figure)
            digest.update(json.dumps([figure.id, figure.kind, figure.text]).encode("utf-8"))
        else:
            pending += 1
            digest.update(f"pending:{row['id']}".encode("utf-8"))
    return dict(by_page), pending, digest.hexdigest()[:16]


def read_book(pdf: Path, figures: dict[int, list[hl.Figure]]):
    """-> (pages to index, [(page number, reason skipped)], PDF page count)."""
    import pymupdf

    with pymupdf.open(pdf) as doc:
        outline = hl.clean_outline(doc.get_toc())
        start = hl.content_start_page(outline)
        labels = hl.page_labels(outline, doc.page_count)
        texts = {n: hl.clean_page_text(doc[n - 1].get_text()) for n in range(1, doc.page_count + 1)}
        count = doc.page_count

    extras = {n: hl.figure_text(figures.get(n, [])) for n in range(1, count + 1)}
    front = [n for n in range(1, min(start, count + 1))]
    front_reasons = dict(zip(front, hl.front_matter_reasons([texts[n] for n in front],
                                                            [extras[n] for n in front])))

    pages, skipped = [], []
    for number in range(1, count + 1):
        extra = extras[number]
        if number < start:
            reason = front_reasons[number]
        else:
            reason = hl.content_page_reason(texts[number], extra)
        if reason:
            skipped.append((number, reason))
            continue
        section, chapter = labels[number]
        if number < start:
            section = "Front matter"
        pages.append(hl.Page(number, f"{texts[number]} {extra}".strip(), section, chapter))
    return pages, skipped, count


def embed_chunks(client, chunks: list[hl.Chunk], label: str) -> list[list[float]]:
    from voyageai.error import AuthenticationError, InvalidRequestError, MalformedRequestError

    texts = [hl.embed_text(c) for c in chunks]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), store.EMBED_BATCH):
        batch = texts[start:start + store.EMBED_BATCH]
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                result = client.embed(batch, model=store.EMBED_MODEL, input_type="document",
                                      truncation=True)
                break
            except (AuthenticationError, InvalidRequestError, MalformedRequestError) as exc:
                # Waiting three minutes will not fix a bad key or a bad request.
                raise RuntimeError(f"Voyage rejected {label}: {type(exc).__name__}") from exc
            except Exception as exc:  # outages, rate limits, timeouts: worth another go
                if attempt == MAX_ATTEMPTS:
                    raise RuntimeError(f"Voyage refused {label} after {attempt} tries: {exc}") from exc
                wait = min(60, 5 * 2 ** (attempt - 1))
                print(f"    Voyage said no ({type(exc).__name__}); waiting {wait}s and trying again")
                time.sleep(wait)
        vectors.extend(result.embeddings)
        print(f"    embedded {min(start + len(batch), len(texts))}/{len(texts)}")
    return vectors


def stale_reasons(entry: dict | None, sha: str, figures_sha: str, params: dict, embed: bool) -> list[str]:
    """Why a book's saved index no longer matches its sources. Empty means current."""
    if not entry:
        return ["never built"]
    reasons = []
    if entry.get("sha256") != sha:
        reasons.append("the PDF changed")
    if entry.get("params") != params:
        reasons.append("the indexing code or settings changed")
    if entry.get("figures") != figures_sha:
        reasons.append("figure transcripts changed")
    if not store.chunk_path(entry["slug"]).is_file():
        reasons.append("the passage file is missing")
    if embed and not entry.get("embedded"):
        reasons.append("it was built without embeddings")
    return reasons


def needs_build(entry: dict | None, sha: str, figures_sha: str, params: dict, embed: bool) -> bool:
    return bool(stale_reasons(entry, sha, figures_sha, params, embed))


def _page_list(numbers: list[int]) -> str:
    return " ".join(f"p{n}" for n in numbers)


def audit(pdfs: list[Path]) -> int:
    """Every page accounted for, and a check that the saved index matches."""
    books = store.read_manifest().get("books", {})
    params = store.build_params()
    stale = 0
    for pdf in pdfs:
        book = hl.identify_book(pdf.name)
        figures, pending, figures_sha = book_figures(book.slug)
        pages, skipped, count = read_book(pdf, figures)
        transcribed = sum(len(v) for v in figures.values())
        print(f"\n# {book.title}: {count} PDF pages, {len(pages)} indexed, {len(skipped)} skipped, "
              f"{transcribed + pending} figures ({transcribed} transcribed, {pending} not yet)")

        by_reason: dict[str, list[int]] = defaultdict(list)
        for number, reason in skipped:
            by_reason[reason].append(number)
        for reason, numbers in sorted(by_reason.items()):
            print(f"  skipped, {reason} ({len(numbers)}): {_page_list(numbers)}")

        with_figures = sorted(n for n in figures if any(p.number == n for p in pages))
        print(f"  pages carrying transcribed figure text: {len(with_figures)}")

        wanted = {p.number for p in pages}
        indexed: set[int] = set()
        path = store.chunk_path(book.slug)
        if book.slug in books and path.is_file():
            for row in json.loads(path.read_text(encoding="utf-8")):
                indexed.update(range(row["page_start"], row["page_end"] + 1))
        missing = sorted(wanted - indexed)
        # Page coverage alone can look fine while the passages hold old text (a
        # corrected transcript, a changed cleaning rule), so check the sources too.
        reasons = stale_reasons(books.get(book.slug), store.file_sha256(pdf), figures_sha, params, embed=True)
        if missing:
            reasons.append(f"{len(missing)} indexable pages are not in it "
                           f"({_page_list(missing[:15])}{' ...' if len(missing) > 15 else ''})")
        if reasons:
            stale += 1
            print(f"  INDEX IS OUT OF DATE: {'; '.join(reasons)}. Run the indexer.")
        else:
            print("  index up to date: sources unchanged since the build, and every indexable page is in a passage")
    return 1 if stale else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-embed", action="store_true")
    args = ap.parse_args()
    embed = not args.no_embed

    if not store.LIBRARY_DIR.is_dir():
        print(f"No library folder at {store.LIBRARY_DIR}. Put the PDFs there first.")
        return 1
    pdfs = sorted(store.LIBRARY_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {store.LIBRARY_DIR}.")
        return 1
    if args.audit:
        return audit(pdfs)

    manifest = store.read_manifest()
    books = dict(manifest.get("books", {}))
    params = store.build_params()
    client = None
    seen: set[str] = set()
    total_words = 0

    for pdf in pdfs:
        book = hl.identify_book(pdf.name)
        if book.slug in seen:
            print(f"SKIP  {pdf.name}: another file already maps to '{book.slug}'")
            continue
        seen.add(book.slug)

        sha = store.file_sha256(pdf)
        figures, pending, figures_sha = book_figures(book.slug)
        if not args.force and not needs_build(books.get(book.slug), sha, figures_sha, params, embed):
            print(f"OK    {book.title}: unchanged, {books[book.slug]['chunks']} passages")
            continue

        pages, skipped, count = read_book(pdf, figures)
        if not pages:
            # A scanned PDF has no text layer. Writing an empty book would leave a
            # manifest entry that looks built and answers nothing, so drop it.
            print(f"SKIP  {book.title}: no readable text in {pdf.name} (a scanned PDF needs OCR first)")
            if book.slug in books and not args.dry:
                store.remove_book(book.slug)
                books = {k: v for k, v in books.items() if k != book.slug}
                store.write_manifest({**manifest, "books": books})
            continue
        chunks = hl.chunk_pages(pages, book)
        words = sum(len(p.text.split()) for p in pages)
        total_words += words
        chapters = len({(c.section, c.chapter) for c in chunks})
        print(f"BUILD {book.title}: {len(pages)} of {count} pages, {words:,} words, "
              f"{chapters} chapters, {len(chunks)} passages")
        if pending:
            print(f"    note: {pending} figures are not transcribed yet (scripts/hormozi_figures.py --status)")
        if not embed and books.get(book.slug, {}).get("embedded"):
            print("    note: --no-embed replaces this book's embeddings with keyword-only passages. "
                  "Run again without it to restore meaning search.")
        if args.dry:
            continue

        vectors = None
        if embed:
            client = client or store.voyage_client()
            vectors = embed_chunks(client, chunks, book.title)
        store.save_book(book.slug, chunks, vectors)
        books[book.slug] = {
            "slug": book.slug, "title": book.title, "file": pdf.name, "sha256": sha,
            "params": params, "figures": figures_sha, "figures_pending": pending,
            "pdf_pages": count, "pages": len(pages), "skipped": len(skipped),
            "words": words, "chunks": len(chunks), "embedded": vectors is not None,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        store.write_manifest({**manifest, "books": books})

    for slug in sorted(set(books) - seen):
        print(f"DROP  {books[slug]['title']}: its PDF is gone")
        if not args.dry:
            store.remove_book(slug)
            books = {k: v for k, v in books.items() if k != slug}
            store.write_manifest({**manifest, "books": books})

    if total_words and embed:
        tokens = total_words * TOKENS_PER_WORD
        cost = tokens / 1e6 * PRICE_PER_MILLION_TOKENS
        verb = "Would embed" if args.dry else "Embedded"
        print(f"\n{verb} ~{tokens:,.0f} tokens with {store.EMBED_MODEL}, about ${cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
