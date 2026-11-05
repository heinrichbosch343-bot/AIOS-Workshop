"""Tests for harties_promo_text.py and the promo part of harties_dedupe.py (no files, no network)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harties_dedupe import dedupe_promos  # noqa: E402
from harties_promo_text import apply_text  # noqa: E402


def promo(pid, **extra):
    return {"id": pid, "businessSlug": "b", "kind": "event", "title": pid, **extra}


def test_description_price_and_note_are_applied_but_an_existing_price_is_kept():
    seed = {"businesses": [], "promos": [promo("a", priceText="R10"), promo("b"), promo("c")]}
    text = {"a": {"details": "New words.", "priceText": "R99"}, "b": {"details": "More words.", "priceText": "From R50", "dateNote": "Check the date with the organiser"}}
    out, count = apply_text(seed, text)
    by = {p["id"]: p for p in out["promos"]}
    assert by["a"]["details"] == "New words." and by["a"]["priceText"] == "R10"
    assert by["b"]["priceText"] == "From R50" and by["b"]["dateNote"].startswith("Check")
    assert "details" not in by["c"] and count == 2


def test_too_long_text_is_ignored_and_a_photo_is_only_set_when_the_file_exists():
    seed = {"businesses": [], "promos": [promo("a"), promo("b")]}
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder) / "here.jpg").write_bytes(b"x")
        text = {"a": {"details": "x" * 401, "image": "/media/here.jpg"}, "b": {"image": "/media/gone.jpg"}}
        out, _ = apply_text(seed, text, Path(folder))
    by = {p["id"]: p for p in out["promos"]}
    assert "details" not in by["a"] and by["a"]["image"] == "/media/here.jpg"
    assert "image" not in by["b"]


def test_a_promo_that_already_has_its_own_picture_keeps_it():
    seed = {"businesses": [], "promos": [promo("a", image="/media/own.jpg")]}
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder) / "here.jpg").write_bytes(b"x")
        out, _ = apply_text(seed, {"a": {"image": "/media/here.jpg"}}, Path(folder))
    assert out["promos"][0]["image"] == "/media/own.jpg"


def test_only_event_organisers_are_renamed_and_the_names_entry_is_not_a_promo():
    seed = {"businesses": [{"slug": "x", "name": "Old (organiser not named)", "origin": "events"}, {"slug": "y", "name": "Keep me", "origin": "directory"}], "promos": [promo("a")]}
    out, _ = apply_text(seed, {"_businesses": {"x": "New", "y": "Changed"}})
    assert [b["name"] for b in out["businesses"]] == ["New", "Keep me"]


def test_promo_duplicates_keep_one_and_a_missing_keeper_removes_nothing():
    seed = {"businesses": [], "promos": [promo("keep"), promo("dup"), promo("other")]}
    out, log = dedupe_promos(seed, [{"keep": "keep", "remove": ["dup"], "why": "same"}, {"keep": "not-there", "remove": ["other"]}])
    assert [p["id"] for p in out["promos"]] == ["keep", "other"] and len(log) == 1
