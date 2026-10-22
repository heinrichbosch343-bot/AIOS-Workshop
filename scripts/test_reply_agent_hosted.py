"""The hosted (Railway) layer: scripts/reply_agent/hosted.py and web.py. No network, no real model."""
from __future__ import annotations

import imaplib
import json
import smtplib

import pytest

from reply_agent import hosted as hosted_mod
from reply_agent.config import BOOKING_LINK
from reply_agent.hosted import Hosted, data_folder
from reply_agent.llm import FakeLLM
from reply_agent_testkit import FakeImap, Msg, raw

GOOD_SHARED = {"sender_name": "Heinrich", "booking_link": BOOKING_LINK, "facts": ["We build AI systems for bids."],
              "modes": {"interested": "review"}}
GOOD_LOCAL = {"tracking_mailbox": "inbox@boschly.com", "campaign_mailboxes": ["bosch@boschly.com"],
              "warmup_tags": ("cedar-upstairs",)}
GOOD_PAYLOAD = {"shared": GOOD_SHARED, "local": GOOD_LOCAL, "leads": ["sam@acme.com"], "password": "app-password-123",
                "suppressed": []}

GOOD_REPLY = ("Hi Sam,\n\nThanks for getting back to me. Five bids a month is a lot. Happy to show you on a quick call.\n"
              + BOOKING_LINK + "\n\nHeinrich")


def routed_llm(category="interested", reply=GOOD_REPLY):
    def answer(system, prompt, model):
        return json.dumps({"category": category, "confidence": 0.9, "reason": "test"}) if system.startswith("You sort replies") else reply
    return FakeLLM(answer)


class FakeSmtp:
    def __init__(self, host, port, **kw):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, *a):
        pass

    def send_message(self, msg):
        FakeSmtp.sent.append(msg)


def _preloaded_imap(messages):
    """A FakeImap class that already holds `messages` the instant it's constructed, for code that builds its own
    ImapSource internally (hosted.run_pass) rather than taking one as a parameter."""
    class Preloaded(FakeImap):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.messages = dict(messages)
    return Preloaded


def _wire_mail(monkeypatch, messages):
    FakeSmtp.sent = []
    monkeypatch.setattr(imaplib, "IMAP4_SSL", _preloaded_imap(messages))
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)


AUTH_SAM = ("purelymail.com; spf=pass (domain of acme.com designates 1.2.3.4 as permitted sender) smtp.mailfrom=acme.com; "
           "dkim=pass header.i=acme.com; dmarc=pass (p=none) header.from=sam@acme.com")


def sam_mail(body="Sure, tell me more, we send about 5 bids a month."):
    return raw(body, **{"From": "Sam Lee <sam@acme.com>", "To": "bosch@boschly.com", "Authentication-Results": AUTH_SAM})


# --- data_folder --------------------------------------------------------------------------------------------------

def test_data_folder_prefers_the_explicit_env_var():
    assert data_folder({"REPLY_AGENT_DIR": "/explicit", "RAILWAY_VOLUME_MOUNT_PATH": "/volume"}) == __import__("pathlib").Path("/explicit")


def test_data_folder_falls_back_to_the_railway_volume():
    assert str(data_folder({"RAILWAY_VOLUME_MOUNT_PATH": "/volume"})).replace("\\", "/") == "/volume/reply-agent"


def test_data_folder_is_none_with_neither():
    assert data_folder({}) is None


# --- blockers -------------------------------------------------------------------------------------------------------

def test_blockers_with_no_folder_at_all():
    assert "volume" in Hosted(None).blockers()[0]


def test_blockers_before_setup(tmp_path):
    assert "railway-setup" in Hosted(tmp_path / "ra").blockers()[0]


def test_blockers_with_damaged_json(tmp_path):
    folder = tmp_path / "ra"
    folder.mkdir()
    for name in ("shared.json", "local.json", "leads.csv", "secret.json"):
        (folder / name).write_text("{}" if name != "leads.csv" else "email\n", encoding="utf-8")
    (folder / "shared.json").write_text("not json", encoding="utf-8")
    assert "cannot be used" in Hosted(folder).blockers()[0]


def test_blockers_clear_after_a_good_setup(tmp_path):
    hosted = Hosted(tmp_path / "ra")
    hosted.apply_setup(GOOD_PAYLOAD)
    assert hosted.blockers() == []


# --- apply_setup ------------------------------------------------------------------------------------------------------

def test_apply_setup_refuses_without_a_folder():
    with pytest.raises(ValueError, match="volume"):
        Hosted(None).apply_setup(GOOD_PAYLOAD)


@pytest.mark.parametrize("break_it", [
    lambda p: p.pop("shared"),
    lambda p: p.__setitem__("shared", "not a dict"),
    lambda p: p.pop("local"),
    lambda p: p.__setitem__("leads", []),
    lambda p: p.__setitem__("leads", ["not-an-email"]),
    lambda p: p.__setitem__("leads", list(range(hosted_mod.MAX_LEADS + 1))),
    lambda p: p.pop("password"),
    lambda p: p.__setitem__("password", ""),
    lambda p: p.__setitem__("suppressed", [{"addr": "bad@x.com"}].__add__([{} for _ in range(1)])),
    lambda p: p.__setitem__("local", {}),
])
def test_apply_setup_rejects_a_bad_payload(tmp_path, break_it):
    payload = json.loads(json.dumps(GOOD_PAYLOAD))
    break_it(payload)
    with pytest.raises(ValueError):
        Hosted(tmp_path / "ra").apply_setup(payload)


def test_apply_setup_writes_leads_sorted_and_deduplicated(tmp_path):
    folder = tmp_path / "ra"
    payload = json.loads(json.dumps(GOOD_PAYLOAD))
    payload["leads"] = ["Sam@Acme.com", "lee@other.com", "sam@acme.com"]
    result = Hosted(folder).apply_setup(payload)
    assert result["leads"] == 2
    assert (folder / "leads.csv").read_text(encoding="utf-8") == "email\nlee@other.com\nsam@acme.com\n"


def test_apply_setup_merges_suppressed_without_duplicating(tmp_path):
    folder = tmp_path / "ra"
    hosted = Hosted(folder)
    p1 = json.loads(json.dumps(GOOD_PAYLOAD))
    p1["suppressed"] = [{"addr": "bad@x.com", "reason": "first", "at": "2026-10-01T00:00:00+00:00"}]
    assert hosted.apply_setup(p1)["suppressed_added"] == 1
    p2 = json.loads(json.dumps(GOOD_PAYLOAD))
    p2["suppressed"] = [{"addr": "bad@x.com", "reason": "again", "at": "2026-10-02T00:00:00+00:00"},
                       {"addr": "new@x.com", "reason": "new one", "at": "2026-10-02T00:00:00+00:00"}]
    assert hosted.apply_setup(p2)["suppressed_added"] == 1
    store = hosted.store()
    try:
        assert store.suppressed() == frozenset({"bad@x.com", "new@x.com"})
    finally:
        store.close()


def test_apply_setup_password_file_is_owner_only(tmp_path):
    import os
    folder = tmp_path / "ra"
    Hosted(folder).apply_setup(GOOD_PAYLOAD)
    mode = oct((folder / "secret.json").stat().st_mode)[-3:]
    if os.name != "nt":  # Windows chmod does not narrow permissions the same way; the real host is Linux
        assert mode == "600"


def test_rerunning_setup_never_leaves_a_half_written_folder(tmp_path):
    """A refused second setup must not corrupt the good one already on disk."""
    folder = tmp_path / "ra"
    hosted = Hosted(folder)
    hosted.apply_setup(GOOD_PAYLOAD)
    bad = json.loads(json.dumps(GOOD_PAYLOAD))
    bad["leads"] = []
    with pytest.raises(ValueError):
        hosted.apply_setup(bad)
    assert hosted.blockers() == []
    assert "sam@acme.com" in (folder / "leads.csv").read_text(encoding="utf-8")


# --- run_pass ------------------------------------------------------------------------------------------------------

def test_run_pass_reads_classifies_drafts_and_saves_status(tmp_path, monkeypatch):
    folder = tmp_path / "ra"
    hosted = Hosted(folder)
    hosted.apply_setup(GOOD_PAYLOAD)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    result = hosted.run_pass(routed_llm(), send=False)
    assert result["ok"] is True and result["counts"] == {"queued": 1} and result["waiting"]["drafts"] == 1
    assert hosted.status()["last_pass_at"] == result["last_pass_at"]
    assert FakeSmtp.sent == []  # send=False: nothing goes out even though a draft was written


def test_run_pass_live_actually_sends_an_approved_draft(tmp_path, monkeypatch):
    folder = tmp_path / "ra"
    hosted = Hosted(folder)
    hosted.apply_setup(GOOD_PAYLOAD)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    hosted.run_pass(routed_llm(), send=False)
    store = hosted.store()
    try:
        draft_id = store.drafts("pending")[0]["id"]
        from reply_agent.agent import Agent
        from reply_agent.rules import Known
        from reply_agent.llm import FakeLLM as _F
        Agent(hosted.config(), store, _F([]), known=Known()).approve(draft_id, None)
    finally:
        store.close()
    _wire_mail(monkeypatch, {})  # nothing new to read this pass; only the approved send should happen
    result = hosted.run_pass(routed_llm(), send=True)
    assert result["counts"].get("sent") == 1
    assert len(FakeSmtp.sent) == 1


def test_run_pass_records_a_failure_without_losing_the_last_good_status(tmp_path, monkeypatch):
    folder = tmp_path / "ra"
    hosted = Hosted(folder)
    hosted.apply_setup(GOOD_PAYLOAD)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    good = hosted.run_pass(routed_llm(), send=False)

    def boom(*a, **kw):
        raise RuntimeError("the server is down")
    monkeypatch.setattr(imaplib, "IMAP4_SSL", boom)
    with pytest.raises(RuntimeError):
        hosted.run_pass(routed_llm(), send=False)
    status = hosted.status()
    assert status["ok"] is False and status["last_ok_at"] == good["last_pass_at"]


def test_run_pass_emails_heinrich_once_then_waits(tmp_path, monkeypatch):
    folder = tmp_path / "ra"
    payload = json.loads(json.dumps(GOOD_PAYLOAD))
    payload["local"]["notify_to"] = "heinrich@boschly.com"
    hosted = Hosted(folder)
    hosted.apply_setup(payload)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    r1 = hosted.run_pass(routed_llm(), send=False, notify_link="http://host/replies?key=x")
    assert r1["notified"] is True and len(FakeSmtp.sent) == 1
    monkeypatch.setattr(imaplib, "IMAP4_SSL", _preloaded_imap({}))  # nothing new to read; keep FakeSmtp.sent as is
    r2 = hosted.run_pass(routed_llm(), send=False, notify_link="http://host/replies?key=x")
    assert r2["notified"] is False and len(FakeSmtp.sent) == 1  # same unresolved item: told once, not again


def test_a_new_item_too_soon_after_the_last_notice_is_held_back(tmp_path, monkeypatch):
    """Two independent guards protect this. This checks the time throttle on its own: a second, DIFFERENT item
    arrives well inside the 30-minute window, so it must still wait, even though the dedup-by-item check alone
    would have let it through."""
    folder = tmp_path / "ra"
    payload = json.loads(json.dumps(GOOD_PAYLOAD))
    payload["local"]["notify_to"] = "heinrich@boschly.com"
    payload["leads"] = ["sam@acme.com", "lee@other.com"]
    hosted = Hosted(folder)
    hosted.apply_setup(payload)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    r1 = hosted.run_pass(routed_llm(), send=False, notify_link="http://host/replies?key=x")
    assert r1["notified"] is True and len(FakeSmtp.sent) == 1
    other = raw("Interested, we send bids too", **{"From": "Lee <lee@other.com>", "To": "bosch@boschly.com", "Message-ID": "<other1@x>",
                "Authentication-Results": AUTH_SAM.replace("acme.com", "other.com").replace("sam@acme.com", "lee@other.com")})
    monkeypatch.setattr(imaplib, "IMAP4_SSL", _preloaded_imap({"1": Msg(other)}))
    r2 = hosted.run_pass(routed_llm(), send=False, notify_link="http://host/replies?key=x")
    assert r2["notified"] is False and len(FakeSmtp.sent) == 1


def test_the_same_unresolved_item_never_notifies_twice_even_once_the_throttle_window_has_passed(tmp_path, monkeypatch):
    """Checks the dedup-by-item guard on its own: plenty of time has passed (the throttle alone would allow a new
    notice), but nothing actually changed, so there is still nothing new to tell him."""
    from datetime import timedelta
    folder = tmp_path / "ra"
    payload = json.loads(json.dumps(GOOD_PAYLOAD))
    payload["local"]["notify_to"] = "heinrich@boschly.com"
    clock_at = [hosted_mod._now()]
    hosted = Hosted(folder, clock=lambda: clock_at[0])
    hosted.apply_setup(payload)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    r1 = hosted.run_pass(routed_llm(), send=False, notify_link="http://host/replies?key=x")
    assert r1["notified"] is True and len(FakeSmtp.sent) == 1
    clock_at[0] += timedelta(hours=2)
    monkeypatch.setattr(imaplib, "IMAP4_SSL", _preloaded_imap({}))
    r2 = hosted.run_pass(routed_llm(), send=False, notify_link="http://host/replies?key=x")
    assert r2["notified"] is False and len(FakeSmtp.sent) == 1


# --- summary (what the Replies page inside Twenty reads) ------------------------------------------------------------

WARMUP_MAIL = raw("hello there cedar-upstairs", **{"From": "Warm <warm@else.com>", "To": "bosch@boschly.com",
                                                    "Message-ID": "<warm1@x>", "Subject": "Quick catch-up cedar-upstairs"})
AUTO_MAIL = raw("I am out of the office until Monday.", **{"From": "Sam Lee <sam@acme.com>", "To": "bosch@boschly.com",
                                                          "Message-ID": "<ooo1@x>", "Auto-Submitted": "auto-replied",
                                                          "Subject": "Automatic reply: quick hello"})


def test_summary_counts_a_real_reply_and_shows_what_we_drafted(tmp_path, monkeypatch):
    hosted = Hosted(tmp_path / "ra")
    hosted.apply_setup(GOOD_PAYLOAD)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    hosted.run_pass(routed_llm(), send=False)
    s = hosted.summary(enabled=True, live=False)
    assert s["replies"] == {"day": 1, "week": 1, "month": 1, "all": 1}
    assert s["drafts"]["waiting"] == 1 and s["drafts"]["sent"] == 0
    row = s["recent"][0]
    assert row["from_name"] == "Sam Lee" and row["from_addr"] == "sam@acme.com" and row["category"] == "interested"
    assert row["draft_status"] == "pending" and row["draft"].startswith("Hi Sam")
    assert "5 bids a month" in row["their_words"]


def test_summary_leaves_warmup_and_auto_replies_out_of_the_reply_count(tmp_path, monkeypatch):
    hosted = Hosted(tmp_path / "ra")
    hosted.apply_setup(GOOD_PAYLOAD)
    _wire_mail(monkeypatch, {"1": Msg(WARMUP_MAIL), "2": Msg(AUTO_MAIL)})
    hosted.run_pass(routed_llm(), send=False)
    s = hosted.summary(enabled=True, live=False)
    assert s["replies"]["all"] == 0 and s["recent"] == []
    assert s["filed_away_month"] == 2


def test_summary_is_online_only_after_a_recent_good_pass_with_the_loop_on(tmp_path, monkeypatch):
    from datetime import timedelta
    clock_at = [hosted_mod._now()]
    hosted = Hosted(tmp_path / "ra", clock=lambda: clock_at[0])
    hosted.apply_setup(GOOD_PAYLOAD)
    before = hosted.summary(enabled=True, live=False)
    assert before["online"] is False and "not finished" in before["why_not"]

    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    hosted.run_pass(routed_llm(), send=False)
    assert hosted.summary(enabled=True, live=False)["online"] is True
    off = hosted.summary(enabled=False, live=False)
    assert off["online"] is False and "switched off" in off["why_not"]

    clock_at[0] += timedelta(hours=1)
    stale = hosted.summary(enabled=True, live=False, interval_minutes=5)
    assert stale["online"] is False and "minutes ago" in stale["why_not"]


def test_summary_goes_red_when_the_last_pass_failed(tmp_path, monkeypatch):
    hosted = Hosted(tmp_path / "ra")
    hosted.apply_setup(GOOD_PAYLOAD)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    hosted.run_pass(routed_llm(), send=False)

    def boom(*a, **kw):
        raise RuntimeError("the server is down")
    monkeypatch.setattr(imaplib, "IMAP4_SSL", boom)
    with pytest.raises(RuntimeError):
        hosted.run_pass(routed_llm(), send=False)
    s = hosted.summary(enabled=True, live=False)
    assert s["online"] is False and "the server is down" in s["why_not"]


def test_summary_before_setup_says_why_and_counts_nothing(tmp_path):
    s = Hosted(tmp_path / "ra").summary(enabled=True, live=False)
    assert s["online"] is False and "railway-setup" in s["why_not"]
    assert s["replies"]["all"] == 0 and s["recent"] == []


# --- web.py ----------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    fastapi = pytest.importorskip("fastapi")
    pytest.importorskip("multipart")
    monkeypatch.setenv("REPLY_AGENT_KEY", "testkey123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-x")
    monkeypatch.setenv("REPLY_AGENT_DIR", str(tmp_path / "ra"))
    monkeypatch.delenv("REPLY_AGENT_ENABLED", raising=False)
    from fastapi.testclient import TestClient
    from reply_agent import web
    return TestClient(web.app)


def test_health_and_ready_need_no_key(client):
    assert client.get("/health").json() == {"status": "ok"}
    body = client.get("/ready").json()
    assert body["ready"] is False and "railway-setup" in body["blockers"][0]


def test_summary_route_needs_the_key_and_reports_the_loop_switch(client, monkeypatch):
    assert client.get("/summary").status_code == 403
    assert client.get("/summary?key=wrong").status_code == 403
    client.post("/setup?key=testkey123", json=GOOD_PAYLOAD)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    from reply_agent.hosted import Hosted as H
    H(__import__("os").environ["REPLY_AGENT_DIR"]).run_pass(routed_llm(), send=False)
    body = client.get("/summary?key=testkey123").json()
    assert body["replies"]["all"] == 1 and body["recent"][0]["from_addr"] == "sam@acme.com"
    assert body["enabled"] is False and body["online"] is False  # the fixture leaves REPLY_AGENT_ENABLED unset
    monkeypatch.setenv("REPLY_AGENT_ENABLED", "1")
    assert client.get("/summary?key=testkey123").json()["online"] is True


def test_the_inbox_is_checked_every_minute_unless_the_switch_says_otherwise(client, monkeypatch):
    from reply_agent import web
    monkeypatch.delenv("REPLY_AGENT_INTERVAL_MINUTES", raising=False)
    assert web._interval_minutes() == 1
    monkeypatch.setenv("REPLY_AGENT_INTERVAL_MINUTES", "3")
    assert web._interval_minutes() == 3
    monkeypatch.setenv("REPLY_AGENT_INTERVAL_MINUTES", "0")
    assert web._interval_minutes() == 1                                      # never a tight loop
    monkeypatch.setenv("REPLY_AGENT_INTERVAL_MINUTES", "soon")
    assert web._interval_minutes() == 1                                      # nonsense falls back to the default, not to 5


@pytest.mark.parametrize("path", ["/replies", "/setup"])
def test_guarded_routes_refuse_without_the_right_key(client, path):
    method = client.post if path == "/setup" else client.get
    assert method(path).status_code == 403
    assert method(f"{path}?key=wrong").status_code == 403


def test_setup_over_http_then_the_page_shows_the_real_draft(client, monkeypatch):
    assert client.post("/setup?key=testkey123", json=GOOD_PAYLOAD).status_code == 200
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    from reply_agent.hosted import Hosted as H
    H(__import__("os").environ["REPLY_AGENT_DIR"]).run_pass(routed_llm(), send=False)
    page = client.get("/replies?key=testkey123")
    assert page.status_code == 200 and "Sam Lee" in page.text and "sam@acme.com" in page.text


def test_the_page_html_escapes_a_hostile_senders_own_text(client, monkeypatch):
    client.post("/setup?key=testkey123", json=GOOD_PAYLOAD)
    hostile = sam_mail('</textarea><script>alert(1)</script> we send about 5 bids a month, tell me more')
    _wire_mail(monkeypatch, {"1": Msg(hostile)})
    from reply_agent.hosted import Hosted as H
    H(__import__("os").environ["REPLY_AGENT_DIR"]).run_pass(routed_llm(), send=False)
    page = client.get("/replies?key=testkey123")
    assert "<script>" not in page.text and "&lt;script&gt;" in page.text


def test_approve_through_http_rejects_a_bad_edit_and_accepts_a_good_one(client, monkeypatch):
    client.post("/setup?key=testkey123", json=GOOD_PAYLOAD)
    _wire_mail(monkeypatch, {"1": Msg(sam_mail())})
    from reply_agent.hosted import Hosted as H
    import os
    H(os.environ["REPLY_AGENT_DIR"]).run_pass(routed_llm(), send=False)
    page = client.get("/replies?key=testkey123")
    import re
    draft_id = re.search(r"/drafts/(\d+)/approve", page.text).group(1)

    r = client.post(f"/drafts/{draft_id}/approve?key=testkey123", data={"body": "too short"}, follow_redirects=False)
    assert r.status_code == 303 and "Could%20not%20approve" in r.headers["location"]

    r = client.post(f"/drafts/{draft_id}/approve?key=testkey123", data={"body": GOOD_REPLY}, follow_redirects=False)
    assert r.status_code == 303 and "approved" in r.headers["location"].lower()


def test_actions_refuse_without_the_right_key(client):
    for path in ("/drafts/1/approve", "/drafts/1/skip", "/drafts/1/retry", "/drafts/1/settle", "/attention/1/resolve"):
        assert client.post(path).status_code == 403
        assert client.post(f"{path}?key=wrong").status_code == 403


def test_resolve_on_an_unknown_attention_id_says_so_rather_than_erroring(client):
    client.post("/setup?key=testkey123", json=GOOD_PAYLOAD)
    r = client.post("/attention/999/resolve?key=testkey123", follow_redirects=False)
    assert r.status_code == 303 and "No%20open%20item" in r.headers["location"]
