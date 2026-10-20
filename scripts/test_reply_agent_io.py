"""Regression tests from the 19 Oct 2026 reviews: the mailbox connection, the outgoing message, the model process, the config."""
from __future__ import annotations

import imaplib
import json
import re
import smtplib
import ssl
import subprocess

import pytest

from reply_agent import tls
from reply_agent.config import CONFIG_PATH, LOCAL_PATH, Config, from_dict, load, load_shared
from reply_agent.llm import ClaudeCli, LLMError
from reply_agent.mailbox import ImapSource, SmtpSender, build_reply
from reply_agent_testkit import BOX, CFG, FakeImap, Msg, connected, make_agent, raw

OK_AUTH = "purelymail.com; dmarc=pass (p=none) header.from=sam@acme.com"


# --- the connection -------------------------------------------------------------------------------
def test_the_verifying_context_really_verifies():
    ctx = tls.verifying_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


def test_imap_connects_with_certificate_checks_and_a_timeout(monkeypatch):
    _, conn = connected(monkeypatch, {})
    assert conn.args["ssl_context"].verify_mode == ssl.CERT_REQUIRED and conn.args["ssl_context"].check_hostname
    assert conn.args["timeout"] and conn.args["port"] == 993


def test_smtp_connects_with_certificate_checks_and_a_timeout(monkeypatch):
    seen = {}

    class FakeSmtp:
        def __init__(self, host, port, **kw):
            seen.update(host=host, port=port, **kw)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def send_message(self, msg):
            seen["sent"] = msg
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    SmtpSender("smtp.example", "u", "p").send(build_reply(
        mailbox=BOX, to_addr="sam@acme.com", to_name="Sam", subject="hi", their_id="<a@x>", their_refs=(), body="Hi", cfg=CFG))
    assert seen["context"].verify_mode == ssl.CERT_REQUIRED and seen["timeout"]


# --- reading the inbox ----------------------------------------------------------------------------
def test_only_unhandled_mail_is_fetched_and_nothing_is_moved_or_deleted(monkeypatch):
    source, conn = connected(monkeypatch, {
        "1": Msg(raw("old", **{"Message-ID": "<1@x>"}), flags={"ReplyAgentDone"}),
        "2": Msg(raw("new one", **{"Message-ID": "<2@x>"})),
        "3": Msg(raw("flagged for deletion by a person", **{"Message-ID": "<3@x>"}), flags={"\\Deleted"}),
        "4": Msg(raw("another", **{"Message-ID": "<4@x>"})),
    })
    got = source.fetch_new()
    assert [uid for uid, _ in got] == ["2", "4"]
    source.mark_done("2")
    assert "ReplyAgentDone" in conn.messages["2"].flags
    assert conn.messages["3"].flags == {"\\Deleted"}  # a person's own flag is left alone, never expunged


def test_a_flagged_message_is_not_fetched_again(monkeypatch):
    source, conn = connected(monkeypatch, {"1": Msg(raw("x", **{"Message-ID": "<1@x>"}))})
    assert len(source.fetch_new()) == 1
    source.mark_done("1")
    assert source.fetch_new() == []


def test_the_oldest_stuck_mail_cannot_hide_newer_mail(monkeypatch):
    messages = {str(i): Msg(raw("m", **{"Message-ID": f"<{i}@x>"})) for i in range(1, 8)}
    source, conn = connected(monkeypatch, messages)
    conn.store_status = "NO"
    first = [uid for uid, _ in source.fetch_new(limit=3)]
    assert first == ["1", "2", "3"]
    for uid in first:
        with pytest.raises(RuntimeError):
            source.mark_done(uid)
    assert [uid for uid, _ in source.fetch_new(limit=3)] == ["4", "5", "6"]


def test_a_huge_message_is_replaced_by_its_headers_and_a_note(monkeypatch):
    big = raw("x" * 5000, **{"Message-ID": "<big@x>"})
    source, conn = connected(monkeypatch, {"1": Msg(big)})
    source.max_size = 1000
    (uid, data), = source.fetch_new()
    assert len(data) < 1500 and b"big@x" in data and b"too large" in data.lower()


def test_marking_done_fails_loudly_when_the_server_says_no(monkeypatch):
    source, conn = connected(monkeypatch, {"1": Msg(raw("x"))})
    conn.store_status = "NO"
    with pytest.raises(RuntimeError):
        source.mark_done("1")


def test_a_set_aside_message_is_flagged_so_it_is_never_fetched_again(monkeypatch):
    source, conn = connected(monkeypatch, {"1": Msg(raw("x"))})
    source.quarantine("1")
    assert {"ReplyAgentDone", "ReplyAgentFailed"} <= conn.messages["1"].flags and source.fetch_new() == []


def test_a_full_pass_over_a_fake_mailbox(monkeypatch):
    source, conn = connected(monkeypatch, {
        "1": Msg(raw("Yes please, tell me more about it", **{"Message-ID": "<1@x>", "Authentication-Results": OK_AUTH})),
        "2": Msg(raw("Please unsubscribe me", **{"Message-ID": "<2@x>", "Authentication-Results": OK_AUTH})),
    })
    outcomes = make_agent().run_once(source)
    assert sorted(o.action for o in outcomes) == ["logged", "queued"]
    assert all("ReplyAgentDone" in m.flags for m in conn.messages.values())


# --- the outgoing message -------------------------------------------------------------------------
def test_the_outgoing_subject_never_carries_the_senders_links_or_numbers():
    msg = build_reply(mailbox=BOX, to_addr="sam@acme.com", to_name="Sam", their_id="<a@x>", their_refs=(), body="Hi", cfg=CFG,
                      subject="Your account is locked, verify at bit.ly/xk29 or call +1 555 0100")
    assert msg["Subject"] == "Re: your message"  # a subject with a link or a number in it is not echoed at all
    plain = build_reply(mailbox=BOX, to_addr="sam@acme.com", to_name="Sam", their_id="<a@x>", their_refs=(), body="Hi", cfg=CFG,
                        subject="Re: quick hello about our bids")
    assert plain["Subject"] == "Re: quick hello about our bids"


def test_a_message_without_an_id_of_its_own_is_not_threaded_to_a_made_up_one():
    msg = build_reply(mailbox=BOX, to_addr="sam@acme.com", to_name="Sam", subject="hi", their_id="<noid-abc123@reply-agent>",
                      their_refs=(), body="Hi", cfg=CFG)
    assert msg["In-Reply-To"] is None and msg["References"] is None


def test_a_huge_references_chain_is_cut_down():
    refs = tuple(f"<r{i}@x>" for i in range(60))
    msg = build_reply(mailbox=BOX, to_addr="sam@acme.com", to_name="Sam", subject="hi", their_id="<a@x>", their_refs=refs,
                      body="Hi", cfg=CFG)
    assert len(msg["References"].split()) <= 20 and msg["References"].split()[-1] == "<a@x>"


# --- the model process ----------------------------------------------------------------------------
def test_a_hung_or_missing_model_process_is_a_model_error_not_a_crash(monkeypatch):
    monkeypatch.setattr("reply_agent.llm._claude_exe", lambda: "claude")

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("claude", 240)

    def missing(*a, **k):
        raise FileNotFoundError("claude")
    with pytest.raises(LLMError):
        ClaudeCli(runner=slow).complete("s", "p", model="haiku")
    with pytest.raises(LLMError):
        ClaudeCli(runner=missing).complete("s", "p", model="haiku")


def test_the_model_process_gets_the_environment_it_is_given_minus_the_api_key(monkeypatch):
    seen = {}

    class Done:
        returncode, stderr, stdout = 0, "", '{"result": "ok", "is_error": false}'

    def runner(cmd, **kw):
        seen.update(kw)
        return Done()
    monkeypatch.setattr("reply_agent.llm._claude_exe", lambda: "claude")
    base = {"PATH": "p", "ANTHROPIC_API_KEY": "stale", "HOME": "h"}
    ClaudeCli(runner=runner, base_env=base).complete("s", "p", model="haiku")
    assert seen["env"] == {"PATH": "p", "HOME": "h"}


# --- the command line -----------------------------------------------------------------------------
def test_sending_needs_the_flag_and_a_real_true_in_the_config():
    from reply_agent.__main__ import resolve_live
    on = CFG.with_overrides(live=True)
    assert resolve_live(True, on) is True
    assert resolve_live(True, CFG) is False
    assert resolve_live(False, on) is False
    assert resolve_live("yes", on) is False
    assert resolve_live(True, CFG.with_overrides(live="false")) is False  # a string must never open the gate, even if it got past validation


def test_the_review_suppress_and_resolve_commands_work_end_to_end(tmp_path, monkeypatch, capsys):
    from reply_agent import __main__ as cli
    from reply_agent.store import Store
    cfg = CFG.with_overrides(db_path=str(tmp_path / "replies.db"))
    monkeypatch.setattr(cli.config_mod, "load", lambda: cfg)
    monkeypatch.setattr(cli, "_setup_environment", lambda: None)
    cli.main(["review"])
    assert "Nothing waiting" in capsys.readouterr().out
    cli.main(["suppress", "Sam+x@Acme.com", "--reason", "asked"])
    cli.main(["suppressed"])
    out = capsys.readouterr().out
    assert "sam@acme.com" in out and "PlusVibe" in out
    cli.main(["unsuppress", "sam@acme.com"])
    assert "Removed" in capsys.readouterr().out
    Store(cfg.db_path).add_attention("<x@y>", "complaint", "test")
    cli.main(["resolve", "1"])
    assert "Cleared" in capsys.readouterr().out
    cli.main(["review"])
    assert "Nothing waiting" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["skip", "999"])


def test_a_bad_config_stops_the_command_with_a_plain_message(tmp_path, monkeypatch):
    from reply_agent import __main__ as cli

    def broken():
        raise ValueError("live must be true or false")
    monkeypatch.setattr(cli.config_mod, "load", broken)
    monkeypatch.setattr(cli, "_setup_environment", lambda: None)
    with pytest.raises(SystemExit) as stopped:
        cli.main(["review"])
    assert "live must be true or false" in str(stopped.value)


# --- the config -----------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [
    {"live": "false"}, {"live": 1}, {"live": None},
    {"delay_minutes": [5]}, {"delay_minutes": [10, 5]}, {"delay_minutes": ["a", "b"]},
    {"max_per_day": "ten"}, {"max_per_day": -1}, {"max_per_day": True},
    {"max_grade": "x"}, {"max_words": 0},
    {"campaign_mailboxes": ["not-an-email"]}, {"campaign_mailboxes": [5]},
    {"stale_after_hours": 0}, {"max_model_mails_per_day": -3},
])
def test_wrongly_typed_settings_are_refused_rather_than_trusted(bad):
    with pytest.raises(ValueError):
        from_dict(bad)


def test_good_settings_are_accepted_and_normalised():
    cfg = from_dict({"live": True, "delay_minutes": [4, 22], "campaign_mailboxes": ["Hello@Boschly.com"], "max_per_day": 5})
    assert cfg.live is True and cfg.delay_minutes == (4, 22) and cfg.campaign_mailboxes == ("hello@boschly.com",)


def test_new_safety_settings_have_cautious_defaults():
    cfg = Config()
    assert cfg.auth_host == "purelymail.com" and cfg.require_verified_for_auto is True
    assert cfg.stale_after_hours == 12 and cfg.park_after_hours == 24
    assert cfg.max_model_mails_per_sender_per_day == 6 and cfg.max_model_mails_per_day == 200


def test_the_private_settings_know_every_warmup_tag_and_every_campaign_mailbox():
    if not LOCAL_PATH.exists():
        pytest.skip("no reply-agent.local.json on this machine")
    cfg = load()
    assert len(set(cfg.warmup_tags)) >= 7, "each of the 7 mailboxes has its own PlusVibe warmup tag"
    assert "heinrich@boschly.com" in cfg.campaign_mailboxes and len(cfg.campaign_mailboxes) == 7
    assert cfg.tracking_mailbox == "inbox@boschly.com" and cfg.live is False


def test_the_shareable_config_carries_nothing_private():
    shared = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    assert not {"tracking_mailbox", "campaign_mailboxes", "warmup_tags", "lead_files"} & set(shared)
    assert shared["live"] is False


def test_the_private_file_is_laid_over_the_shareable_one(tmp_path):
    (tmp_path / "agent.json").write_text(json.dumps({"max_per_day": 5, "live": False, "sender_name": "Heinrich"}), encoding="utf-8")
    (tmp_path / "agent.local.json").write_text(json.dumps({"tracking_mailbox": "Box@x.com", "max_per_day": 7}), encoding="utf-8")
    cfg = load(tmp_path / "agent.json")
    assert cfg.tracking_mailbox == "box@x.com" and cfg.max_per_day == 7 and cfg.live is False
    assert load_shared(tmp_path / "agent.json").tracking_mailbox == ""


def test_a_config_file_that_is_not_an_object_is_refused(tmp_path):
    (tmp_path / "agent.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError):
        load(tmp_path / "agent.json")


def test_git_ignores_the_private_settings_and_the_database():
    gitignore = (CONFIG_PATH.parents[2] / ".gitignore").read_text(encoding="utf-8")
    assert "outputs/outreach/reply-agent.local.json" in gitignore and "outputs/outreach/replies/" in gitignore
