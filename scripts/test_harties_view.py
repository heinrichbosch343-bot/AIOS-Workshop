"""Tests for the Harties Board page inside Twenty (harties_view.py, harties_status.py, shown by outreach_hub.py?view=harties).

Nothing here reaches Railway or Twenty: the app's numbers feed is replaced with a fake.

    cd scripts
    uv run --no-project --system-certs --with pytest --with streamlit --with pandas --with altair python -m pytest test_harties_view.py -q
"""
import json
from pathlib import Path

import pytest

import harties_status as H
import reply_status as R
import twenty_setup as T
from test_dashboards import text_of, world  # noqa: F401  (world is a fixture)

HUB = str(Path(__file__).resolve().parent / "outreach_hub.py")
KEY = "k3y-with space&odd"


def report(**over):
    """What the Harties Board app's /api/stats answers (the shape was copied from the real route, counts only)."""
    base = {
        "generatedAt": "2026-11-04T08:00:00.000Z",
        "stats": {
            "firstDay": "2026-11-02",
            "active": {"today": 3, "week": 21, "month": 23, "all": 23},
            "returning": 7,
            "installed": {"today": 0, "week": 8, "month": 8, "all": 8},
            "appUsers": {"today": 2, "week": 5, "month": 6, "all": 6},
            "opened": {"list": 3, "post": 5},
            "funnel": {"visited": 23, "tapped": 11, "accepted": 5, "installed": 8, "saidAdded": 0},
            "platforms": {"ios": 11, "android": 11, "desktop": 1},
            "months": [{"key": "2026-11", "opens": 40, "people": 23, "appPeople": 6, "added": 8},
                       {"key": "2026-10", "opens": 0, "people": 0, "appPeople": 0, "added": 0}],
            "weeks": [{"key": "2026-11-02", "opens": 40, "people": 23, "appPeople": 6, "added": 8},
                      {"key": "2026-10-26", "opens": 0, "people": 0, "appPeople": 0, "added": 0}],
        },
        "listing": {
            "listings": {"sent": 5, "approved": 2, "waiting": 2, "rejected": 1, "when": {"today": 1, "week": 5, "month": 5, "all": 5}},
            "promos": {"sent": 3, "approved": 1, "waiting": 2, "rejected": 0, "when": {"today": 0, "week": 3, "month": 3, "all": 3}},
            "months": [{"key": "2026-11", "listings": 5, "promos": 3}, {"key": "2026-10", "listings": 0, "promos": 0}],
            "weeks": [{"key": "2026-11-02", "listings": 5, "promos": 3}, {"key": "2026-10-26", "listings": 0, "promos": 0}],
        },
        "board": {"businesses": 100, "listedThemselves": 2, "promos": 34},
        "waiting": 4,
        "feedbackNew": 1,
    }
    base.update(over)
    return base


# ---------------------------------------------------------------- harties_status: the plain logic

def test_target_reads_the_saved_file_then_the_env(tmp_path):
    f = tmp_path / "feed.json"
    assert H.target(f, env={}) == ("", "")
    assert H.target(f, env={"HARTIES_STATS_URL": "https://hb.app/", "HARTIES_STATS_KEY": "k"}) == ("https://hb.app", "k")
    f.write_text('{"url": "https://hartisboard.up.railway.app/", "key": "abc"}', encoding="utf-8")
    assert H.target(f, env={"HARTIES_STATS_URL": "https://other", "HARTIES_STATS_KEY": "z"}) == ("https://hartisboard.up.railway.app", "abc")
    f.write_text("{broken", encoding="utf-8")
    assert H.target(f, env={}) == ("", "")


def test_report_asks_the_feed_with_the_key_in_the_address_and_checks_the_answer(monkeypatch):
    asked = []
    monkeypatch.setattr(R, "get_json", lambda url, timeout=10: asked.append(url) or report())
    assert H.report(("https://hb.app", KEY))["board"]["businesses"] == 100
    assert asked == ["https://hb.app/api/stats?key=k3y-with%20space%26odd"]


def test_report_says_so_when_this_pc_was_never_told_where_the_app_is():
    with pytest.raises(R.Unreachable, match="does not know where"):
        H.report(("", ""))


def test_report_refuses_an_answer_that_is_not_the_numbers(monkeypatch):
    monkeypatch.setattr(R, "get_json", lambda url, timeout=10: {"hello": "world"})
    with pytest.raises(R.Unreachable, match="not the numbers"):
        H.report(("https://hb.app", "k"))


def test_an_old_build_without_the_feed_is_explained_in_words_a_person_can_act_on(monkeypatch):
    def old(url, timeout=10):
        raise R.Unreachable("that page is not there (an older build?)")
    monkeypatch.setattr(R, "get_json", old)
    with pytest.raises(R.Unreachable, match="not been updated"):
        H.report(("https://hb.app", "k"))


def test_period_rows_have_readable_labels_and_the_listings_joined_by_period_not_by_position():
    data = report()
    # Listings are given in the opposite order, so a join by position would swap the rows.
    data["listing"]["months"] = list(reversed(data["listing"]["months"]))
    rows = H.period_rows(data, "months")
    assert rows == [["Nov 2026", "40", "23", "6", "8", "5"], ["Oct 2026", "0", "0", "0", "0", "0"]]
    assert H.period_rows(data, "weeks")[0] == ["Mon 2 Nov", "40", "23", "6", "8", "5"]


def test_numbers_that_are_missing_or_not_numbers_read_as_zero_rather_than_breaking_the_page():
    data = report()
    data["stats"]["months"][0]["opens"] = "<script>"
    del data["stats"]["months"][0]["people"]
    assert H.period_rows(data, "months")[0][:3] == ["Nov 2026", "0", "0"]


def test_cards_answer_who_is_using_it_who_has_it_installed_and_who_listed():
    cards = dict((label, big) for big, label in H.cards(report()))
    assert cards["Using it today"] == "3"
    assert cards["Using it this week"] == "21"
    assert cards["Have it on their phone"] == "8"
    assert cards["Opened it from the icon, 30 days"] == "6"
    assert cards["Businesses that listed themselves"] == "2"
    assert cards["Waiting for you to check"] == "4"


# ---------------------------------------------------------------- the page, rendered

@pytest.fixture
def pages(world, monkeypatch):
    for name in ("OUTREACH_CRM_SYNC", "OUTREACH_OPENER", "OUTREACH_LINKEDIN_PULL"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def open_page(view="harties"):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(HUB, default_timeout=60)
    at.query_params["view"] = view
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_the_page_shows_the_cards_the_monthly_and_weekly_tables_and_who_is_listing(pages):
    pages.setattr(H, "report", lambda target=None: report())
    at = open_page()
    text = text_of(at)
    assert [t.value for t in at.title] == ["Harties Board"] and not at.tabs
    for label in ("Using it today", "Have it on their phone", "Businesses that listed themselves", "Waiting for you to check"):
        assert label in text
    assert "Every month" in text and "Nov 2026" in text and "Every week" in text and "Mon 2 Nov" in text
    for head in ("Opens", "People", "Icon", "Added", "Listed"):
        assert f">{head}<" in text
    assert "Who is listing" in text and ">Businesses<" in text and ">Promos<" in text and "Sent in, ever" in text
    assert "Counting started" in text and "2 Nov" in text


def test_the_page_never_shows_the_key_or_the_address_of_the_feed(pages):
    pages.setattr(H, "target", lambda path=None, env=None: ("https://hb.app", KEY))
    pages.setattr(R, "get_json", lambda url, timeout=10: report())
    text = text_of(open_page())
    assert "k3y-with" not in text and "hb.app" not in text and "/api/stats" not in text


def test_the_page_goes_red_and_says_why_when_the_app_cannot_be_reached(pages):
    def down(target=None):
        raise R.Unreachable("it did not answer (timed out)")
    pages.setattr(H, "report", down)
    text = text_of(open_page())
    assert 'class="dot red"' in text and "timed out" in text
    assert "Every month" not in text


def test_nothing_in_the_feed_can_put_html_on_the_page(pages):
    data = report()
    data["stats"]["firstDay"] = "<script>alert(1)</script>"
    data["stats"]["months"][0]["key"] = "<img src=x onerror=alert(2)>"
    pages.setattr(H, "report", lambda target=None: data)
    text = text_of(open_page())
    assert "<script>" not in text and "<img src=x" not in text


# ---------------------------------------------------------------- the visitor dashboard

def traffic(**over):
    """The shape of the app's `traffic` block (lib/traffic.ts), with one 28-day range filled in and 7 and 90 copied."""
    block = {
        "days": 28, "from": "2026-10-09", "to": "2026-11-05",
        "current": {"visitors": 1234, "visits": 1800, "pageviews": 5400, "viewsPerVisit": 3.0, "bounceRate": 40,
                    "visitSeconds": 442, "added": 9},
        "previous": {"visitors": 1000, "visits": 2000, "pageviews": 5400, "viewsPerVisit": 2.7, "bounceRate": 50,
                     "visitSeconds": 0, "added": 0},
        "series": [{"day": "2026-11-04", "visitors": 20, "visits": 25, "pageviews": 70},
                   {"day": "2026-11-05", "visitors": 30, "visits": 41, "pageviews": 99}],
        "channels": [{"name": "Direct", "visitors": 800}, {"name": "Social", "visitors": 200}],
        "sources": [{"name": "Direct / None", "visitors": 800}, {"name": "WhatsApp", "visitors": 150}],
        "pages": [{"name": "/", "visitors": 900}, {"name": "/b/masala-express", "visitors": 300}],
        "entries": [{"name": "/", "visitors": 700}],
        "exits": [{"name": "/c/houses", "visitors": 400}],
        "devices": [{"name": "iPhone", "visitors": 600}, {"name": "Android", "visitors": 500}],
    }
    block.update(over)
    return {"liveNow": 3, "ranges": {"7": {**block, "days": 7}, "28": block, "90": {**block, "days": 90}}}


def test_a_change_says_up_or_down_and_whether_that_is_good_news():
    assert H.change(1234, 1000) == ("23%", "good-up")
    assert H.change(1800, 2000) == ("10%", "bad-down")
    assert H.change(40, 50, rise_is_good=False) == ("20%", "good-down"), "a falling bounce rate is good news"
    assert H.change(9, 0) == ("new", "flat"), "nothing before is new, never a division by zero"
    assert H.change(0, 0) == ("0%", "flat")
    assert H.change("x", None) == ("0%", "flat")


def test_numbers_are_written_the_way_the_dashboard_writes_them():
    assert [H.compact(x) for x in (7, 999, 1000, 1234, 22700, 299000, 1800000)] == ["7", "999", "1k", "1.2k", "23k", "299k", "1.8M"]
    assert [H.duration(x) for x in (0, 59, 442, 3725, -5, "x")] == ["0s", "59s", "7m 22s", "1h 2m", "0s", "0s"]


def test_tiles_carry_the_seven_dashboard_numbers_with_their_change():
    tiles = {t["label"]: t for t in H.tiles(traffic()["ranges"]["28"])}
    assert list(tiles) == ["Unique visitors", "Total visits", "Page views", "Views per visit", "Bounce rate", "Visit length",
                           "Added to phone"]
    assert tiles["Unique visitors"]["value"] == "1.2k" and tiles["Unique visitors"]["mood"] == "good-up"
    assert tiles["Bounce rate"]["value"] == "40%" and tiles["Bounce rate"]["mood"] == "good-down"
    assert tiles["Visit length"]["value"] == "7m 22s" and tiles["Views per visit"]["value"] == "3.0"


def test_list_rows_give_a_page_its_name_and_keep_the_address_under_it():
    rows = H.list_rows(traffic()["ranges"]["28"], "pages", {"/": "Today", "/b/masala-express": "Masala Express"})
    assert rows[0] == {"name": "Today", "sub": "/", "count": "900", "width": 100}
    assert rows[1]["name"] == "Masala Express" and rows[1]["width"] == 33
    assert H.list_rows({}, "pages") == []
    assert H.traffic_range(report(), 28) is None, "an app without the dashboard numbers says so"


def test_the_page_shows_the_dashboard_when_the_app_sends_it(pages):
    pages.setattr(H, "report", lambda target=None: report(traffic=traffic(), pageNames={"/b/masala-express": "Masala Express"}))
    at = open_page()
    text = text_of(at)
    for label in ("Unique visitors", "Total visits", "Bounce rate", "Visit length", "Added to phone", "3 on the app now"):
        assert label in text
    assert "1.2k" in text and "7m 22s" in text
    tab_labels = [t.label for t in at.tabs]
    for name in ("Channels", "Sources", "Devices", "Top pages", "Entry pages", "Exit pages"):
        assert name in tab_labels
    assert "Masala Express" in text and "WhatsApp" in text and "Direct / None" in text
    assert "Every month" in text, "the older tables stay under the dashboard"


def test_the_page_says_the_dashboard_is_coming_when_the_app_is_older(pages):
    pages.setattr(H, "report", lambda target=None: report())
    text = text_of(open_page())
    assert "full visitor dashboard appears once" in text and "Every month" in text


def test_nothing_in_the_dashboard_numbers_can_put_html_on_the_page(pages):
    t = traffic(sources=[{"name": "<img src=x onerror=alert(1)>", "visitors": 5}],
                pages=[{"name": "/b/<script>", "visitors": 3}])
    pages.setattr(H, "report", lambda target=None: report(traffic=t, pageNames={"/b/<script>": "<script>alert(2)</script>"}))
    text = text_of(open_page())
    assert "<img src=x" not in text and "<script>" not in text


# ---------------------------------------------------------------- the sidebar

def test_twenty_gets_a_harties_board_page_under_linkedin():
    names = [p["name"] for p in T.PAGES]
    assert "Harties Board" in names and names.index("Harties Board") == names.index("LinkedIn") + 1
    spec = next(p for p in T.PAGES if p["name"] == "Harties Board")
    assert spec["url"] == T.HUB_URL + "&view=harties"
