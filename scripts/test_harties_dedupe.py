"""Tests for harties_dedupe.py (no files, no network): python -m pytest scripts/test_harties_dedupe.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harties_dedupe import dedupe  # noqa: E402


def biz(slug, **extra):
    return {"slug": slug, "name": slug, "category": "food", "subcategory": "restaurants", "backedBy": 0, **extra}


def test_keeps_the_one_with_a_picture_and_fills_in_what_it_lacks():
    seed = {"businesses": [biz("maps", origin="directory", phone="012 1", hours="Mon", image="/media/m.jpg", imageFrom="m.co.za"),
                           biz("group", whatsapp="082 1", backedBy=2, tags=["a"])],
            "promos": [{"id": "p", "businessSlug": "group"}]}
    out, log = dedupe(seed, [{"same": ["group", "maps"], "why": "x"}])
    assert [b["slug"] for b in out["businesses"]] == ["maps"]
    kept = out["businesses"][0]
    assert kept["whatsapp"] == "082 1" and kept["phone"] == "012 1" and kept["backedBy"] == 2 and kept["tags"] == ["a"]
    assert kept["imageFrom"] == "m.co.za"
    assert out["promos"][0]["businessSlug"] == "maps"
    assert len(log) == 1


def test_without_pictures_the_group_row_beats_a_help_number_beats_maps_beats_events():
    seed = {"businesses": [biz("ev", origin="events"), biz("maps", origin="directory"), biz("num", origin="numbers")], "promos": []}
    out, _ = dedupe(seed, [{"same": ["ev", "maps", "num"]}])
    assert [b["slug"] for b in out["businesses"]] == ["num"]
    seed["businesses"].append(biz("grp"))
    out, _ = dedupe(seed, [{"same": ["ev", "maps", "num", "grp"]}])
    assert [b["slug"] for b in out["businesses"]] == ["grp"]


def test_never_takes_another_rows_pictures_and_skips_missing_slugs_and_running_twice_changes_nothing():
    seed = {"businesses": [biz("a", origin="directory", phone="1"), biz("b", origin="events", image="/media/b.jpg", gallery=["/media/b2.jpg"]), biz("c")],
            "promos": []}
    groups = [{"same": ["a", "b"]}, {"same": ["c", "not-there"]}]
    out, _ = dedupe(seed, groups)
    assert [b["slug"] for b in out["businesses"]] == ["b", "c"]
    again, log = dedupe(out, groups)
    assert again == out and log == []
    out2, _ = dedupe({"businesses": [biz("x", origin="directory", phone="1"), biz("y", origin="events")], "promos": []}, [{"same": ["x", "y"]}])
    assert "image" not in out2["businesses"][0]
