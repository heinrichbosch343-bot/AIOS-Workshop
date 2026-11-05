"""Tests for harties_geo.py. No network, no real data."""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import harties_geo as G  # noqa: E402

COLS = ["title", "latitude", "longitude", "phone", "website"]


def places(tmp_path, rows):
    path = tmp_path / "places.csv"
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    return G.Places(path)


def biz(slug, name, area="pecanwood", **kw):
    return {"slug": slug, "name": name, "area": area, **kw}


def test_phone_website_and_name_matching_normalise_the_text(tmp_path):
    p = places(tmp_path, [
        {"title": "Aviators Harties", "latitude": "-25.78304", "longitude": "27.789088", "phone": "+27 12 345 0001", "website": "https://www.aviators.co.za/x"},
        {"title": "Pecan Deli", "latitude": "-25.764", "longitude": "27.858", "phone": "", "website": ""},
    ])
    seed = {"businesses": [
        biz("a", "Something else", area="r512", phone="012 345 0001"),
        biz("b", "Another", area="r512", website="http://aviators.co.za"),
        biz("c", "The Pecan Deli (Pty) Ltd"),
    ], "promos": []}
    r = G.fill(seed, p)
    assert r["by"] == {"phone": 1, "website": 1, "name": 1}
    assert seed["businesses"][0]["lat"] == -25.78304
    assert seed["businesses"][2]["lng"] == 27.858


def test_a_namesake_far_from_the_area_is_refused_and_the_nearest_branch_wins(tmp_path):
    p = places(tmp_path, [
        {"title": "Spar", "latitude": "-25.7770", "longitude": "27.8580", "phone": "", "website": ""},
        {"title": "Spar", "latitude": "-25.7440", "longitude": "27.9000", "phone": "", "website": ""},
        {"title": "Faraway Cafe", "latitude": "-26.4", "longitude": "27.5", "phone": "", "website": ""},
    ])
    seed = {"businesses": [biz("s", "Spar", area="r512"), biz("f", "Faraway Cafe", area="pecanwood")], "promos": []}
    r = G.fill(seed, p)
    assert seed["businesses"][0]["lat"] == -25.777, "the branch in the business's own area"
    assert "lat" not in seed["businesses"][1], "a match 70 km from its area is a namesake"
    assert r["no_match"] == 1


def test_homes_never_get_a_point_and_an_existing_point_is_kept(tmp_path):
    p = places(tmp_path, [{"title": "Pecan Deli", "latitude": "-25.764", "longitude": "27.858", "phone": "", "website": ""}])
    seed = {"businesses": [
        biz("h", "Pecan Deli", home={"deal": "sale"}, lat=-25.7, lng=27.8),
        biz("k", "Pecan Deli", lat=-25.77, lng=27.85),
    ], "promos": []}
    G.fill(seed, p)
    assert "lat" not in seed["businesses"][0]
    assert seed["businesses"][1]["lat"] == -25.77
    G.fill(seed, p, force=True)
    assert seed["businesses"][1]["lat"] == -25.764


def test_an_event_takes_its_venues_point_even_when_another_business_runs_it(tmp_path):
    p = places(tmp_path, [{"title": "Aviators Harties", "latitude": "-25.78304", "longitude": "27.789088", "phone": "", "website": ""}])
    seed = {"businesses": [biz("tau", "TAU Entertainment", area="r512")], "promos": [
        {"id": "e1", "businessSlug": "tau", "venue": "Aviators Harties, R512, Portion 34, De Rust"},
        {"id": "e2", "businessSlug": "tau", "venue": "Nowhere Hall"},
        {"id": "e3", "businessSlug": "tau"},
    ]}
    r = G.fill(seed, p)
    assert seed["promos"][0]["lat"] == -25.78304
    assert "lat" not in seed["promos"][1] and "lat" not in seed["promos"][2]
    assert r["promo_no_venue"] == ["e2: Nowhere Hall"]


def test_points_outside_the_box_are_not_read(tmp_path):
    p = places(tmp_path, [{"title": "London Pub", "latitude": "51.5", "longitude": "-0.12", "phone": "", "website": ""}])
    assert p.rows == []
