"""Tests for the Hormozi library's logic. No PDFs, no network, no API key, no cost.

    uv run --no-project --system-certs --with pytest python -m pytest scripts/test_hormozi_lib.py -q
"""
import sys
from pathlib import Path

import pytest

# scripts/ has an __init__.py, so pytest puts the workspace root on the path, not
# this folder. Without this the file only runs from inside scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import hormozi_lib as hl  # noqa: E402


# ── which book is this ───────────────────────────────────────────────────────

@pytest.mark.parametrize("filename, slug, short", [
    ("$100m money models - Alex Hormozi.pdf", "money-models", "MM"),
    ("100$ Leads.pdf", "leads", "L"),
    ("100M Offers How To Make Offers So Good People Feel Stupid Saying No "
     "(Alex Hormozi) (Z-Library).pdf", "offers", "O"),
    ("100M Series Lost Chapters (Alex Hormozi).pdf", "lost-chapters", "LC"),
])
def test_identify_book_knows_the_series(filename, slug, short):
    book = hl.identify_book(filename)
    assert (book.slug, book.short) == (slug, short)
    assert book.title.startswith("$100M")


SERIES = [hl.Book("leads", "$100M Leads", "L"), hl.Book("lost-chapters", "$100M Lost Chapters", "LC"),
          hl.Book("money-models", "$100M Money Models", "MM"), hl.Book("offers", "$100M Offers", "O")]


def test_resolve_book_takes_an_exact_short_code_before_a_title_match():
    # "o" is inside "Lost Chapters", and lost-chapters sorts before offers.
    assert hl.resolve_book("O", SERIES) == "offers"
    assert hl.resolve_book("lc", SERIES) == "lost-chapters"
    assert hl.resolve_book("money-models", SERIES) == "money-models"


def test_resolve_book_accepts_part_of_a_title():
    assert hl.resolve_book("money", SERIES) == "money-models"
    assert hl.resolve_book("Lost", SERIES) == "lost-chapters"


def test_resolve_book_refuses_a_guess():
    with pytest.raises(ValueError):
        hl.resolve_book("100m", SERIES)      # every book
    with pytest.raises(ValueError):
        hl.resolve_book("ch", SERIES)        # too short to mean anything
    with pytest.raises(ValueError):
        hl.resolve_book("gym", SERIES)       # no book


def test_lost_chapters_is_not_mistaken_for_the_offers_book():
    # Its subtitle names all three books, so order of matching matters.
    assert hl.identify_book("Lost Chapters - Offers, Leads, Money Models.pdf").slug == "lost-chapters"


def test_identify_book_falls_back_to_a_clean_filename():
    book = hl.identify_book("Gym Launch Secrets (Alex Hormozi) (Z-Library).pdf")
    assert book.slug == "gym-launch-secrets"
    assert book.title == "Gym Launch Secrets"
    assert book.short == "GLS"


# ── page cleaning ────────────────────────────────────────────────────────────

def test_clean_page_drops_footer_boilerplate_and_page_numbers():
    raw = ("75\nCopyright © 2025 by BUMBLE IP, LLC NOT FOR DISTRIBUTION\n"
           "Advanced Offer Stacking\nThe body text.\nOceanofPDF.com\nxii\n")
    out = hl.clean_page_text(raw)
    assert "Copyright" not in out
    assert "OceanofPDF" not in out
    assert "75" not in out
    assert "xii" not in out
    assert out == "Advanced Offer Stacking The body text."


def test_clean_page_expands_ligatures():
    assert hl.clean_page_text("a better oﬀer, ﬁrst") == "a better offer, first"


def test_clean_page_joins_words_split_across_lines():
    assert hl.clean_page_text("more cus-\ntomers came") == "more customers came"


def test_clean_page_keeps_real_hyphens():
    assert hl.clean_page_text("a done-for-you offer") == "a done-for-you offer"


def test_clean_page_removes_space_before_punctuation():
    assert hl.clean_page_text("useful . But , why ?") == "useful. But, why?"


def test_boilerplate_page_is_detected():
    assert hl.is_boilerplate_page("All rights reserved. No part of this book may be reproduced")
    assert hl.is_boilerplate_page("9 781963 349559 90000> ISBN 978-1-963349-55-9")
    assert not hl.is_boilerplate_page("Charge what it is worth. " * 20)


# ── which pages get indexed ──────────────────────────────────────────────────
# Snippets are the real first lines of the four books' front matter.

def test_front_matter_keeps_the_authors_own_writing():
    pages = [
        "What People Have Said About Alex Hormozi “Alex is my husband.” - Leila Hormozi " + "praise " * 50,
        "Guiding Principles Do more.",
        "A Quick Word LEILA: I wrote this dedication seven years ago in my first book " + "words " * 200,
        "Thank Yous To Trevor: Thank you for your true friendship. " + "words " * 80,
    ]
    assert hl.front_matter_reasons(pages) == [None, None, None, None]


def test_front_matter_drops_legal_contents_and_title_pages():
    pages = [
        "",
        "Acquisition.com Volume II $100M Leads How to Get Strangers To Want To Buy Your Stuff Alex Hormozi",
        "A L E X H O R M O Z I LOST TREASURES FROM $100M OFFERS, $100M LEADS, & $100M MONEY MODELS",
        "Alex Hormozi",
        "Copyright © 2023 by Alex Hormozi All rights reserved. No part of this publication may be reproduced",
        "Disclaimer The information provided in this book is for educational and informational purposes " * 20,
        "referred to herein as the “Company”) have not made any guarantees that the strategies " * 20,
        "The Company’s representatives are professionals, and their results are not typical " * 20,
        "Table of Contents Section I: Start Here How I Got Here The Problem This Book Solves",
        "Section VI: Make Your Money Model Ten Years In Ten Minutes Final Thoughts Free Goodies",
    ]
    assert hl.front_matter_reasons(pages) == [
        "blank", "title page", "title page", "title page", "legal", "legal", "legal", "legal",
        "contents", "contents"]


def test_a_page_after_the_contents_with_sentences_is_not_contents():
    assert hl.front_matter_reasons(["Contents Start Here Section I", "Guiding Principles There are no rules."]) \
        == ["contents", None]


def test_front_matter_keeps_a_page_whose_image_carries_the_content():
    figures = ["", "[Figure: Guiding principles: do the boring work, be patient with results, stay the course]"]
    assert hl.front_matter_reasons(["", "Alex Hormozi"], figures) == ["blank", None]


def test_content_page_reasons():
    assert hl.content_page_reason("", "") == "blank"
    assert hl.content_page_reason("Section II: Pricing", "") == "heading only"
    assert hl.content_page_reason("The Ugly Truth", "[Figure: a chart of gym revenue by month over two years]") is None
    assert hl.content_page_reason("Charge what it is worth. " * 5, "") is None


# ── figures ──────────────────────────────────────────────────────────────────

def test_parse_figure_accepts_a_valid_transcript():
    fig = hl.parse_figure({"id": "p054-1", "kind": "diagram", "text": "LTGP = revenue - COGS"}, page=54)
    assert fig == hl.Figure(id="p054-1", page=54, kind="diagram", text="LTGP = revenue - COGS")


@pytest.mark.parametrize("row", [
    {"id": "p054-1", "kind": "cartoon", "text": "x"},        # unknown kind
    {"id": "p054-1", "kind": "diagram", "text": 5},          # text not a string
    {"kind": "diagram", "text": "x"},                        # no id
    "not a dict",
])
def test_parse_figure_rejects_a_malformed_transcript(row):
    assert hl.parse_figure(row, page=54) is None


def test_same_box_allows_rounding_but_not_a_different_image():
    assert hl.same_box([72.0, 100.0, 540.0, 400.0], [72.4, 99.8, 540.0, 400.3])
    assert not hl.same_box([72.0, 100.0, 540.0, 400.0], [72.0, 420.0, 540.0, 700.0])
    assert not hl.same_box([72.0, 100.0, 540.0, 400.0], [72.0, 100.0, 540.0])


def test_figure_text_keeps_content_and_drops_qr_codes_and_logos():
    figures = [
        hl.Figure("p054-1", 54, "diagram", "LTGP: revenue $50 minus COGS $10"),
        hl.Figure("p054-2", 54, "qr", ""),
        hl.Figure("p054-3", 54, "logo", "Acquisition.com"),
        hl.Figure("p054-4", 54, "photo", ""),
        hl.Figure("p054-5", 54, "screenshot", "Ad copy: Lose 20lbs in 6 weeks"),
    ]
    assert hl.figure_text(figures) == \
        "[Figure: LTGP: revenue $50 minus COGS $10] [Figure: Ad copy: Lose 20lbs in 6 weeks]"


# ── outline ──────────────────────────────────────────────────────────────────

def test_clean_outline_drops_junk_bookmarks_and_sorts():
    toc = [
        [1, "_jyeyz5f5pwxw", 9],
        [2, "Your First Avatar", 11],
        [1, "$100M Lost Chapters", 9],
        [1, "", 12],
        [1, "Section A: Attract", 19],
    ]
    out = hl.clean_outline(toc)
    assert [e.title for e in out] == ["$100M Lost Chapters", "Your First Avatar", "Section A: Attract"]


def test_a_section_sorts_before_a_chapter_on_the_same_page():
    toc = [[2, "1. How We Got Here", 12], [1, "Section I: How We Got Here", 12]]
    out = hl.clean_outline(toc)
    assert out[0].is_section and not out[1].is_section


def test_content_starts_after_front_matter():
    toc = [[1, "Title Page", 1], [1, "Copyright", 4], [1, "What Others Have Said", 5],
           [1, "Contents", 8], [1, "Start Here", 9]]
    assert hl.content_start_page(hl.clean_outline(toc)) == 9


def test_content_start_defaults_to_page_one_without_an_outline():
    assert hl.content_start_page([]) == 1


def test_page_labels_reset_chapter_at_a_new_section():
    toc = [[1, "Section I: Money", 2], [2, "Pricing", 3], [1, "Section II: Value", 5]]
    labels = hl.page_labels(hl.clean_outline(toc), page_count=6)
    assert labels[1] == ("", "")
    assert labels[2] == ("Section I: Money", "")
    assert labels[4] == ("Section I: Money", "Pricing")
    assert labels[5] == ("Section II: Value", "")


def test_page_labels_use_the_title_not_the_bookmark_depth():
    # $100M Leads nests its sections one level deeper than its chapters.
    toc = [[1, "Leads Alone Aren't Enough", 40], [2, "Section III: Get Leads", 73],
           [1, "#1 Warm Outreach", 78]]
    labels = hl.page_labels(hl.clean_outline(toc), page_count=80)
    assert labels[75] == ("Section III: Get Leads", "")
    assert labels[79] == ("Section III: Get Leads", "#1 Warm Outreach")


# ── chunking ─────────────────────────────────────────────────────────────────

def _page(no, words, section="S", chapter="C"):
    return hl.Page(number=no, text=" ".join(words), section=section, chapter=chapter)


def _words(prefix, n):
    return [f"{prefix}{i}" for i in range(n)]


def test_chunks_never_cross_a_chapter_boundary():
    pages = [_page(1, _words("a", 50), chapter="One"), _page(2, _words("b", 50), chapter="Two")]
    chunks = hl.chunk_pages(pages, book=hl.identify_book("100$ Leads.pdf"), target=400, overlap=40)
    assert [c.chapter for c in chunks] == ["One", "Two"]
    assert "b0" not in chunks[0].text


def test_chunks_overlap_and_track_their_pages():
    pages = [_page(1, _words("p", 300)), _page(2, _words("q", 300))]
    chunks = hl.chunk_pages(pages, book=hl.identify_book("100$ Leads.pdf"), target=400, overlap=50,
                            min_tail=10)
    assert len(chunks) == 2
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)
    assert chunks[1].page_end == 2
    first, second = chunks[0].text.split(), chunks[1].text.split()
    assert first[-50:] == second[:50]


def test_a_tiny_tail_is_folded_into_the_last_chunk():
    pages = [_page(1, _words("w", 420))]
    chunks = hl.chunk_pages(pages, book=hl.identify_book("100$ Leads.pdf"), target=400, overlap=50,
                            min_tail=60)
    assert len(chunks) == 1
    assert len(chunks[0].text.split()) == 420


def test_chunk_end_snaps_back_to_a_sentence():
    words = _words("x", 390) + ["end."] + _words("y", 200)
    chunks = hl.chunk_pages([_page(1, words)], book=hl.identify_book("100$ Leads.pdf"),
                            target=400, overlap=20, snap=30)
    assert chunks[0].text.endswith("end.")


def test_chunk_ids_are_stable_and_prefixed_by_book():
    pages = [_page(1, _words("w", 900))]
    chunks = hl.chunk_pages(pages, book=hl.identify_book("100M Offers.pdf"), target=400, overlap=50)
    assert [c.id for c in chunks] == [f"O-{i:04d}" for i in range(len(chunks))]


def test_chunking_refuses_an_overlap_that_would_never_advance():
    with pytest.raises(ValueError):
        hl.chunk_pages([_page(1, _words("w", 10))], book=hl.identify_book("x.pdf"), target=50, overlap=50)


def test_embed_text_carries_book_and_chapter_context():
    chunk = hl.Chunk(id="O-0001", book="offers", title="$100M Offers", short="O", section="Section IV",
                     chapter="Guarantees", page_start=139, page_end=140, text="Body.")
    assert hl.embed_text(chunk).startswith("$100M Offers | Section IV > Guarantees")


# ── keyword search ───────────────────────────────────────────────────────────

def test_tokenize_drops_stopwords_and_folds_plurals():
    assert hl.tokenize("The guarantees are what make offers work") == ["guarantee", "make", "offer", "work"]


def test_tokenize_keeps_short_words_that_end_in_s_intact():
    assert hl.tokenize("business bonus gas") == ["business", "bonus", "gas"]


def test_bm25_prefers_the_document_with_the_rare_term():
    docs = [hl.tokenize("price value offer"), hl.tokenize("guarantee offer offer"),
            hl.tokenize("value offer")]
    scores = hl.BM25(docs).scores(hl.tokenize("guarantee"))
    assert max(range(3), key=scores.__getitem__) == 1
    assert scores[0] == 0 and scores[2] == 0


def test_bm25_empty_query_scores_nothing():
    assert hl.BM25([["a"], ["b"]]).scores([]) == [0.0, 0.0]


def test_rrf_rewards_agreement_between_rankings():
    fused = hl.rrf([["a", "b", "c"], ["b", "a", "d"]])
    ids = [i for i, _ in fused]
    assert set(ids[:2]) == {"a", "b"}
    assert set(ids[2:]) == {"c", "d"}


def test_rrf_scores_an_item_found_by_only_one_ranking():
    fused = dict(hl.rrf([["a"], ["b"]]))
    assert fused["a"] == fused["b"] > 0


# ── lookups and citations ────────────────────────────────────────────────────

def _chunk(id_, book, chapter, pages=(1, 1), section="Section"):
    return hl.Chunk(id=id_, book=book, title=f"$100M {book.title()}", short=id_.split("-")[0],
                    section=section, chapter=chapter, page_start=pages[0], page_end=pages[1],
                    text=f"text of {id_}")


def test_cite_single_page_and_range():
    assert hl.cite(_chunk("O-0001", "offers", "Guarantees", (139, 139))) == \
        "$100M Offers, p. 139 (Guarantees)"
    assert hl.cite(_chunk("O-0002", "offers", "Guarantees", (139, 141))) == \
        "$100M Offers, pp. 139-141 (Guarantees)"


def test_cite_falls_back_to_the_section_when_there_is_no_chapter():
    assert hl.cite(_chunk("L-0001", "leads", "", (75, 75), section="Section III: Get Leads")) == \
        "$100M Leads, p. 75 (Section III: Get Leads)"


def test_find_chapter_matches_title_and_respects_book_filter():
    chunks = [_chunk("O-0001", "offers", "15. Guarantees"), _chunk("O-0002", "offers", "15. Guarantees"),
              _chunk("MM-0001", "money-models", "Win Your Money Back")]
    found = hl.find_chapter(chunks, "guarantee")
    assert [c.id for c in found] == ["O-0001", "O-0002"]
    assert hl.find_chapter(chunks, "guarantee", book="money-models") == []


def test_find_chapter_prefers_the_chapter_named_exactly():
    # "Scarcity, Urgency, Bonuses, Guarantees, and Naming" mentions guarantees;
    # "Enhancing The Offer: Guarantees" IS the guarantees chapter.
    chunks = [_chunk("O-0001", "offers", "11. Enhancing The Offer: Scarcity, Urgency, Bonuses, Guarantees"),
              _chunk("O-0002", "offers", "15. Enhancing The Offer: Guarantees")]
    assert [c.id for c in hl.find_chapter(chunks, "guarantees")] == ["O-0002"]
    assert [c.id for c in hl.find_chapter(chunks, "Guarantee")] == ["O-0002"]
    assert [c.id for c in hl.find_chapter(chunks, "urgency")] == ["O-0001"]


def test_merge_overlap_removes_the_repeated_words_at_each_join():
    assert hl.merge_overlap(["a b c d e", "d e f g", "f g h"]) == "a b c d e f g h"


def test_merge_overlap_keeps_text_that_does_not_overlap():
    assert hl.merge_overlap(["one two", "three four"]) == "one two three four"
    assert hl.merge_overlap([]) == ""


def test_table_of_contents_rolls_up_pages_per_chapter():
    chunks = [_chunk("O-0001", "offers", "Guarantees", (139, 141)),
              _chunk("O-0002", "offers", "Guarantees", (141, 150)),
              _chunk("O-0003", "offers", "Naming", (154, 160))]
    rows = hl.table_of_contents(chunks)
    assert [(r.chapter, r.page_start, r.page_end, r.chunks) for r in rows] == [
        ("Guarantees", 139, 150, 2), ("Naming", 154, 160, 1)]
