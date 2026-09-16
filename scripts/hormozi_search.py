"""hormozi_search.py - ask the Hormozi library a question, get cited passages back.

    RUN="uv run --no-project --system-certs --with numpy --with voyageai \
         --with python-dotenv --with truststore python scripts/hormozi_search.py"

    $RUN "how do I build a guarantee" "pricing a service above the market"
    $RUN "attraction offer for a service business" --book money-models --k 8
    $RUN --toc                           every book, section and chapter with pages
    $RUN --chapter "guarantees"          the whole chapter as one piece of prose
    $RUN --page 62 --book LC             that page as a PNG, with its figure transcripts
    $RUN --status                        what is indexed and when it was built

--page needs PyMuPDF, so add --with pymupdf to $RUN when using it.

Each question is searched two ways and the two are merged: keywords (BM25, which
catches Hormozi's own names for things like "Grand Slam Offer" and "Core Four")
and meaning (Voyage embeddings, which catch the question asked in other words).
Voyage's reranker then reorders the best 30. If Voyage is unreachable the search
still runs on keywords alone and says so on the first line, rather than failing.

Search finds the passage; --chapter reads the whole framework around it. A
passage is ~380 words, and most of Hormozi's frameworks run to several pages.
"""
from __future__ import annotations

import argparse
import json
import sys

import hormozi_lib as hl
import hormozi_store as store

CANDIDATES = 30
POOL = 60                   # how deep each ranking goes before fusion
MAX_CHAPTERS_PRINTED = 4    # beyond this, list the matches and ask for a narrower name


def book_filter(value: str | None, chunks: list[hl.Chunk]) -> str | None:
    if not value:
        return None
    books = sorted({hl.Book(c.book, c.title, c.short) for c in chunks}, key=lambda b: b.slug)
    try:
        return hl.resolve_book(value, books)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def failure_note(what: str, exc: Exception) -> str:
    """Why a Voyage step failed, safe to print.

    The catch around each Voyage step is deliberately broad, because search must
    still answer on keywords when anything in that path breaks. So the note names
    the exception type rather than assuming an outage, and strips the key from the
    message in case a transport error ever echoes a request header.
    """
    detail = str(exc)[:120]
    key = store.voyage_key()
    if key:
        detail = detail.replace(key, "***")
    return f"{what} failed ({type(exc).__name__}: {detail})"


def dense_rankings(queries, chunks, vectors, has_vector, allowed):
    """Returns (one ranking per query, None) or (None, reason it is unavailable)."""
    if vectors is None or not has_vector.any():
        return None, "no embeddings in the index (built with --no-embed)"
    try:
        import numpy as np
        client = store.voyage_client()
        result = client.embed(queries, model=store.EMBED_MODEL, input_type="query")
        query_matrix = np.asarray(result.embeddings, dtype=np.float32)
        query_matrix /= np.linalg.norm(query_matrix, axis=1, keepdims=True)
        similarity = query_matrix @ vectors.T
        rankings = []
        for row in similarity:
            order = [i for i in np.argsort(-row) if has_vector[i] and allowed[i]]
            rankings.append([chunks[i].id for i in order[:POOL]])
    except Exception as exc:
        return None, failure_note("meaning search", exc)
    if not any(rankings):
        return None, "no embeddings for the book asked for (built with --no-embed)"
    return rankings, None


def keyword_ranking(bm25, query, chunks, allowed):
    scores = bm25.scores(hl.tokenize(query))
    order = sorted((i for i, s in enumerate(scores) if s > 0 and allowed[i]),
                   key=lambda i: scores[i], reverse=True)
    return [chunks[i].id for i in order[:POOL]]


def rerank(query, candidate_ids, by_id, k):
    """Returns ([(id, score)], None) or (None, reason)."""
    try:
        client = store.voyage_client()
        documents = [hl.embed_text(by_id[i]) for i in candidate_ids]
        result = client.rerank(query, documents, model=store.RERANK_MODEL, top_k=k)
        return [(candidate_ids[r.index], r.relevance_score) for r in result.results], None
    except Exception as exc:
        return None, failure_note("reranking", exc)


def search(queries, k, book, keyword_only, no_rerank):
    chunks, vectors, has_vector = store.load_index()
    if not chunks:
        raise SystemExit("The library is not indexed yet. Run scripts/hormozi_index.py first.")
    slug = book_filter(book, chunks)
    allowed = [slug is None or c.book == slug for c in chunks]
    by_id = {c.id: c for c in chunks}
    bm25 = hl.BM25([hl.tokenize(hl.embed_text(c)) for c in chunks])

    notes = []
    dense = None
    if keyword_only:
        notes.append("keyword only (asked for)")
    else:
        dense, reason = dense_rankings(queries, chunks, vectors, has_vector, allowed)
        if reason:
            notes.append(f"keyword only: {reason}")

    results = []
    for index, query in enumerate(queries):
        rankings = [keyword_ranking(bm25, query, chunks, allowed)]
        if dense:
            rankings.append(dense[index])
        fused = hl.rrf([r for r in rankings if r])
        candidates = [item for item, _ in fused[:CANDIDATES]]

        hits = [(item, score) for item, score in fused[:k]]
        if dense and not no_rerank and candidates:
            reranked, reason = rerank(query, candidates, by_id, k)
            if reranked:
                hits = reranked
            elif reason not in notes:
                notes.append(reason)
        results.append({"query": query, "hits": [(by_id[i], s) for i, s in hits]})

    mode = "meaning + keyword" if dense else "keyword"
    if dense and not no_rerank and not any(n.startswith("reranking") for n in notes):
        mode += ", reranked"
    return chunks, results, mode, notes


def print_search(chunks, results, mode, notes, as_json):
    if as_json:
        print(json.dumps({
            "mode": mode, "notes": notes,
            "queries": [{"query": r["query"], "hits": [
                {"id": c.id, "cite": hl.cite(c), "book": c.title, "section": c.section,
                 "chapter": c.chapter, "page_start": c.page_start, "page_end": c.page_end,
                 "score": round(float(s), 4), "text": c.text} for c, s in r["hits"]]}
                for r in results]}, ensure_ascii=False, indent=2))
        return

    books = len({c.book for c in chunks})
    print(f"# Hormozi library: {books} books, {len(chunks)} passages | search: {mode}")
    for note in notes:
        print(f"! {note}")
    shown: set[str] = set()
    for number, result in enumerate(results, start=1):
        print(f"\n## Q{number}: {result['query']}")
        if not result["hits"]:
            print("(nothing matched)")
        for rank, (chunk, score) in enumerate(result["hits"], start=1):
            print(f"\n[{rank}] {chunk.id} | {hl.cite(chunk)} | score {float(score):.3f}")
            if chunk.id in shown:
                print("(same passage as above)")
                continue
            shown.add(chunk.id)
            print(chunk.text)


def print_toc(chunks):
    current = None
    for row in hl.table_of_contents(chunks):
        if row.title != current:
            current = row.title
            print(f"\n# {row.title}  (--book {row.book})")
        name = " > ".join(p for p in (row.section, row.chapter) if p) or "(untitled)"
        print(f"  pp. {row.page_start}-{row.page_end}  {name}  [{row.chunks}]")


def print_chapter(chunks, query, book):
    slug = book_filter(book, chunks)
    matches = hl.find_chapter(chunks, query, slug)
    if not matches:
        raise SystemExit(f"No chapter or section title contains '{query}'. Try --toc.")

    groups: dict[tuple, list[hl.Chunk]] = {}
    for c in matches:
        groups.setdefault((c.book, c.section, c.chapter), []).append(c)
    if len(groups) > MAX_CHAPTERS_PRINTED:
        print(f"'{query}' matches {len(groups)} chapters. Name one more precisely:")
        for (_, section, chapter), members in groups.items():
            print(f"  {members[0].title} | {' > '.join(p for p in (section, chapter) if p)}")
        return

    for (_, section, chapter), members in groups.items():
        first, last = members[0], members[-1]
        where = " > ".join(p for p in (section, chapter) if p)
        print(f"\n# {first.title} | {where} | pp. {first.page_start}-{last.page_end}\n")
        print(hl.merge_overlap([m.text for m in members]))


def print_page(number: int, book: str | None, chunks: list[hl.Chunk]):
    """Render one PDF page to PNG so a diagram can be looked at, not just read about."""
    slug = book_filter(book, chunks)
    if not slug:
        raise SystemExit("--page needs --book, e.g. --page 62 --book lost-chapters")
    entry = store.read_manifest()["books"][slug]
    try:
        import pymupdf
    except ImportError as exc:
        raise SystemExit("--page needs PyMuPDF: add --with pymupdf to the uv command") from exc

    out = store.LIBRARY_DIR / ".pages" / f"{slug}-p{number:03d}.png"
    with pymupdf.open(store.LIBRARY_DIR / entry["file"]) as doc:
        if not 1 <= number <= doc.page_count:
            raise SystemExit(f"{entry['title']} has pages 1-{doc.page_count}")
        out.parent.mkdir(parents=True, exist_ok=True)
        doc[number - 1].get_pixmap(dpi=110).save(out)
    print(f"# {entry['title']}, page {number}\nimage: {out}")

    import hormozi_figures as figs
    for row in figs.load_figure_list(slug):
        if row["page"] != number:
            continue
        _state, figure = figs.transcript_state(slug, row)
        described = f"{figure.kind}: {figure.text or '(no text)'}" if figure else "not transcribed yet"
        print(f"figure {row['id']} ({figs.book_dir(slug) / (row['id'] + '.png')})\n  {described}")
    # A passage's page range can span a skipped page in the same chapter, so ask
    # the indexer's own rules whether THIS page went in, rather than the range.
    import hormozi_index
    by_page, _, _ = hormozi_index.book_figures(slug)
    _, skipped, _ = hormozi_index.read_book(store.LIBRARY_DIR / entry["file"], by_page)
    reason = dict(skipped).get(number)
    if reason:
        print(f"not indexed: {reason} page")
        return
    for c in chunks:
        if c.book == slug and c.page_start <= number <= c.page_end:
            print(f"passage {c.id} | {hl.cite(c)}")


def print_status():
    manifest = store.read_manifest()
    books = manifest.get("books", {})
    if not books:
        print(f"Nothing indexed. PDFs go in {store.LIBRARY_DIR}, then run hormozi_index.py.")
        return
    print(f"Library: {store.LIBRARY_DIR}")
    for entry in books.values():
        embedded = "embedded" if entry.get("embedded") else "keyword only"
        pages = (f"{entry['pages']}/{entry['pdf_pages']} pages" if "pdf_pages" in entry
                 else f"{entry['pages']} pages")
        pending = entry.get("figures_pending", 0)
        figures = f"  {pending} figures untranscribed" if pending else ""
        print(f"  {entry['title']:<24} {pages:>13}  {entry['chunks']:>4} passages  {entry['words']:>7,} words  "
              f"{embedded}{figures}  built {entry['built_at']}  <- {entry['file']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queries", nargs="*")
    ap.add_argument("--k", type=int, default=6, help="passages per question (default 6)")
    ap.add_argument("--book", help="offers | leads | money-models | lost-chapters (or O, L, MM, LC)")
    ap.add_argument("--toc", action="store_true")
    ap.add_argument("--chapter")
    ap.add_argument("--page", type=int, help="render a PDF page to PNG, with its figures (needs --book)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--keyword-only", action="store_true")
    ap.add_argument("--no-rerank", action="store_true")
    args = ap.parse_args()

    if args.status:
        print_status()
        return 0
    if args.toc or args.chapter or args.page:
        chunks, _, _ = store.load_index()
        if not chunks:
            raise SystemExit("The library is not indexed yet. Run scripts/hormozi_index.py first.")
        if args.toc:
            print_toc([c for c in chunks if c.book == (book_filter(args.book, chunks) or c.book)])
        elif args.chapter:
            print_chapter(chunks, args.chapter, args.book)
        else:
            print_page(args.page, args.book, chunks)
        return 0
    if not args.queries:
        ap.error("give at least one question, or --toc / --chapter / --status")
    if not 1 <= args.k <= 25:
        ap.error("--k must be between 1 and 25")

    chunks, results, mode, notes = search(args.queries, args.k, args.book,
                                          args.keyword_only, args.no_rerank)
    print_search(chunks, results, mode, notes, args.json)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
