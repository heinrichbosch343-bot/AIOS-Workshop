"""hormozi_figures.py - pull every image out of the Hormozi books so it can be read.

A PDF's text layer holds none of the words inside its images, and these books
put real content there: whiteboard formulas (LTGP, CAC), handwritten worked
examples, typed author notes saved as pictures, ad screenshots. Local OCR was
tested on them and turned the handwriting into noise, so each image is cut out
here and transcribed by Claude reading the picture. hormozi_index.py then adds
the transcript to the page it came from.

    uv run --no-project --system-certs --with pymupdf python scripts/hormozi_figures.py
    ... --batches 6     split untranscribed figures into 6 work lists for transcribers
    ... --status        counts only

Layout, per book, all inside the gitignored Hormozi/ folder:

    Hormozi/figures/<slug>/_figures.json     every figure: id, page, position
    Hormozi/figures/<slug>/p054-1.png        the image as it appears on the page
    Hormozi/figures/<slug>/p054-1.json       its transcript: {"id", "kind", "text"}
    Hormozi/figures/_batches/batch-1.tsv     png path, transcript path, book, page

Transcripts are the expensive part and live apart from Hormozi/.index/, so a
rebuild of the index never touches them. A figure is only ever re-extracted if
its PNG is missing, and a transcript is never overwritten here.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import hormozi_lib as hl
import hormozi_store as store

FIGURES_DIR = store.LIBRARY_DIR / "figures"
BATCH_DIR = FIGURES_DIR / "_batches"
MIN_FIGURE_AREA = 0.03      # below 3% of the page it is an icon, a bullet or a rule
MAX_SIDE_PX = 1400          # enough to read handwriting, small enough to read cheaply
MAX_DPI = 220


def book_dir(slug: str) -> Path:
    return FIGURES_DIR / slug


def retire(slug: str, fid: str, why: str, reread: bool = True) -> None:
    """Set a figure's PNG and transcript aside so it is cut and read again.

    The transcript is renamed, never deleted: it is the expensive part, and a
    human may want to see what was there.
    """
    out = book_dir(slug)
    (out / f"{fid}.png").unlink(missing_ok=True)
    transcript = out / f"{fid}.json"
    if transcript.is_file():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        transcript.rename(out / f"{fid}.stale-{stamp}.json")
        then = " and it needs reading again" if reread else ""
        print(f"  {slug} {fid}: {why}; its transcript was set aside{then}")


def extract_book(pdf: Path, book: hl.Book) -> list[dict]:
    import pymupdf

    out = book_dir(book.slug)
    out.mkdir(parents=True, exist_ok=True)
    # Ids come from an image's order on its page. If the PDF is replaced and a
    # different picture now sits behind an old id, the old transcript must not
    # be trusted for it.
    previous = {row["id"]: row["bbox"] for row in load_figure_list(book.slug)}
    rows = []
    with pymupdf.open(pdf) as doc:
        for page in doc:
            page_area = page.rect.width * page.rect.height
            rects, seen = [], set()
            for info in page.get_image_info():
                rect = pymupdf.Rect(info["bbox"]) & page.rect
                key = tuple(round(v) for v in rect)
                if rect.is_empty or key in seen or rect.width * rect.height / page_area < MIN_FIGURE_AREA:
                    continue
                seen.add(key)
                rects.append(rect)
            rects.sort(key=lambda r: (round(r.y0), round(r.x0)))
            for n, rect in enumerate(rects, start=1):
                number = page.number + 1
                fid = f"p{number:03d}-{n}"
                bbox = [round(v, 1) for v in rect]
                if fid in previous and not hl.same_box(previous[fid], bbox):
                    retire(book.slug, fid, "a different image now sits at this position")
                png = out / f"{fid}.png"
                if not png.is_file():
                    longest_inches = max(rect.width, rect.height) / 72
                    dpi = max(72, min(MAX_DPI, int(MAX_SIDE_PX / longest_inches)))
                    page.get_pixmap(clip=rect, dpi=dpi).save(png)
                rows.append({"id": fid, "page": number, "bbox": bbox})
    for fid in sorted(set(previous) - {row["id"] for row in rows}):
        retire(book.slug, fid, "this image is no longer in the PDF", reread=False)
    (out / "_figures.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return rows


def load_figure_list(slug: str) -> list[dict]:
    path = book_dir(slug) / "_figures.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def transcript_state(slug: str, row: dict) -> tuple[str, hl.Figure | None]:
    """('missing' | 'invalid' | 'done', figure)."""
    path = book_dir(slug) / f"{row['id']}.json"
    if not path.is_file():
        return "missing", None
    try:
        figure = hl.parse_figure(json.loads(path.read_text(encoding="utf-8")), page=row["page"])
    except (json.JSONDecodeError, OSError):
        figure = None
    return ("done", figure) if figure else ("invalid", None)


def status(books: list[hl.Book]) -> list[tuple[hl.Book, dict]]:
    pending = []
    total = Counter()
    for book in books:
        kinds, states = Counter(), Counter()
        for row in load_figure_list(book.slug):
            state, figure = transcript_state(book.slug, row)
            states[state] += 1
            if figure:
                kinds[figure.kind] += 1
            else:
                pending.append((book, row))
        total.update(states)
        print(f"{book.title:<22} figures {sum(states.values()):>4}  transcribed {states['done']:>4}  "
              f"missing {states['missing']:>4}  invalid {states['invalid']:>3}  {dict(kinds)}")
    print(f"{'All books':<22} figures {sum(total.values()):>4}  transcribed {total['done']:>4}  "
          f"missing {total['missing']:>4}  invalid {total['invalid']:>3}")
    return pending


def write_batches(pending: list[tuple[hl.Book, dict]], count: int) -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    for old in BATCH_DIR.glob("batch-*.tsv"):
        old.unlink()
    if not pending:
        print("Nothing left to transcribe.")
        return
    count = max(1, min(count, len(pending)))
    size = -(-len(pending) // count)
    for index in range(count):
        part = pending[index * size:(index + 1) * size]
        if not part:
            continue
        lines = [f"{book_dir(b.slug) / (r['id'] + '.png')}\t{book_dir(b.slug) / (r['id'] + '.json')}"
                 f"\t{b.title}\t{r['page']}" for b, r in part]
        path = BATCH_DIR / f"batch-{index + 1}.tsv"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{path}  ({len(part)} figures)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batches", type=int, default=0)
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    pdfs = sorted(store.LIBRARY_DIR.glob("*.pdf"))
    books = [hl.identify_book(p.name) for p in pdfs]
    if not args.status:
        for pdf, book in zip(pdfs, books):
            print(f"extracted {len(extract_book(pdf, book)):>4} figures from {book.title}")
    pending = status(books)
    if args.batches:
        write_batches(pending, args.batches)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
