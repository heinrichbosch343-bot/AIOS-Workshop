"""Regression tests from the second independent review (19 Oct 2026, after the rebuild): how the agent behaves under flood,
outage and doubt. Each one was reproduced before it was fixed."""
from __future__ import annotations

import smtplib
from datetime import timedelta

import pytest

from reply_agent import mailparse, review, rules
from reply_agent.agent import _iso
from reply_agent.llm import ClaudeCli, FakeLLM, LLMError
from reply_agent.mailbox import DryRunSender, SendUncertain, SmtpSender, build_reply
from reply_agent.mailparse import OVERSIZE_NOTE
from reply_agent.models import Decision, Draft
from reply_agent.store import Store
from reply_agent_testkit import (BOX, CFG, GOOD, NOW, FakeSource, Msg, auth_headers, classifier_says, connected, make_agent, mail,
                                 raw, routed_llm)

OK_AUTH = "purelymail.com; dmarc=pass (p=none) header.from=sam@acme.com"
MANY = rules.Known(emails=frozenset({"a@acme.com", "b@acme.com", "c@acme.com", "lee@other.com", "sam@acme.com"}),
                   domains=frozenset({"acme.com", "other.com"}))


def down(*_):
    raise LLMError("usage limit reached")


def inbox(*ids, body="Yes please, tell me more about it", frm="Sam Lee <sam@acme.com>"):
    return FakeSource([(str(i), raw(body, **{"Message-ID": f"<r{i}@x>", "From": frm, "Authentication-Results": OK_AUTH})) for i in ids])


def queue_approved(agent, mid, *, frm="sam@acme.com", to=BOX, body=GOOD):
    m = mail(mid=mid, frm=frm, to=to)
    return agent.store.record_outcome(m, Decision("interested", 0.9, "test", "model", to), verified=True, trust="exact",
                                      draft=Draft(body, ()), draft_status="approved", send_after=_iso(NOW))


def notice(address="sam@acme.com", action="failed"):
    return (b"From: MAILER-DAEMON@mail.acme.com\r\nTo: heinrich1@boschly.com\r\nSubject: Delivery Status Notification\r\n"
            b"Message-ID: <d3@x>\r\nContent-Type: multipart/report; report-type=delivery-status; boundary=\"B\"\r\n\r\n"
            b"--B\r\nContent-Type: text/plain\r\n\r\nNote.\r\n"
            b"--B\r\nContent-Type: message/delivery-status\r\n\r\nReporting-MTA: dns; mail.acme.com\r\n\r\n"
            b"Final-Recipient: rfc822; " + address.encode() + b"\r\nAction: " + action.encode() + b"\r\nStatus: 5.1.1\r\n\r\n--B--\r\n")


# --- stopping people, without losing a hot lead ----------------------------------------------------
def test_a_hot_lead_who_says_they_dont_send_that_many_bids_is_answered_not_silenced():
    agent = make_agent()
    out = agent.handle(mail(body="We don't send that many bids, maybe two a month, but this sounds interesting. Tell me more."))
    assert out.category == "interested" and agent.store.suppressed() == frozenset() and len(agent.store.drafts("pending")) == 1


def test_a_possible_unsubscribe_is_shown_to_a_person_and_suppresses_nobody():
    agent = make_agent()
    out = agent.handle(mail(body="Is there a way to opt out after the three free bids?"))
    assert out.category == "other" and agent.store.suppressed() == frozenset()
    assert [r["kind"] for r in agent.store.open_attention()] == ["other"]
    assert "opt out" in review.review_text(agent.store, CFG)


def test_asking_to_stop_while_threatening_is_suppressed_and_a_person_is_told():
    agent = make_agent()
    out = agent.handle(mail(body="Remove me from your list or I will sue you."))
    assert out.category == "complaint" and agent.store.suppressed() == frozenset({"sam@acme.com"})
    assert [r["kind"] for r in agent.store.open_attention()] == ["complaint"]


def test_the_review_lists_who_was_added_to_the_do_not_write_list_and_why():
    agent = make_agent()
    agent.handle(mail(body="please unsubscribe me", verified=False))
    text = review.review_text(agent.store, CFG, now=NOW)
    assert "do-not-write" in text.lower() and "sam@acme.com" in text
    assert "unsubscribe" in text and "not verified" in text.lower()
    assert "sam@acme.com" not in review.review_text(agent.store, CFG, now=NOW + timedelta(days=8))


# --- floods and budgets ---------------------------------------------------------------------------
def test_spoofed_mail_from_a_leads_company_cannot_use_up_the_model_budget():
    llm = routed_llm("interested")
    agent = make_agent(llm=llm)
    for i in range(60):
        agent.handle(mail(mid=f"<spoof{i}@x>", frm=f"u{i}@acme.com", name="U", verified=False, body="hello there friend"))
    assert llm.calls == []  # nobody unverified at a lead's company reaches the model
    kinds = [r["kind"] for r in agent.store.open_attention()]
    assert kinds.count("unverified") == 40 and kinds.count("flood") == 1
    real = agent.handle(mail(mid="<real@x>", frm="lee@other.com", name="Lee Chen", headers=auth_headers("lee@other.com")))
    assert real.category == "interested" and len(agent.store.drafts("pending")) == 1


def test_a_verified_lead_is_shown_to_a_person_when_the_days_model_budget_is_gone():
    cfg = CFG.with_overrides(max_model_mails_per_day=3)
    agent = make_agent(cfg, known=MANY)
    for who in ("a@acme.com", "b@acme.com", "c@acme.com"):
        assert agent.handle(mail(mid=f"<{who}>", frm=who, name="X", headers=auth_headers(who))).category == "interested"
    out = agent.handle(mail(mid="<real@x>", frm="lee@other.com", name="Lee Chen", headers=auth_headers("lee@other.com"),
                            body="Yes please, tell me more about it. Tuesday?"))
    assert out.action == "logged"
    assert [r["kind"] for r in agent.store.open_attention()] == ["limit"]
    assert "Yes please, tell me more" in review.review_text(agent.store, cfg)


def test_unverified_mail_can_use_only_half_of_the_days_model_budget():
    cfg = CFG.with_overrides(max_model_mails_per_day=4)
    llm = routed_llm("interested")
    agent = make_agent(cfg, llm=llm, known=MANY)
    for who in ("a@acme.com", "b@acme.com", "c@acme.com"):
        agent.handle(mail(mid=f"<{who}>", frm=who, name="X", verified=False))
    assert len([c for c in llm.calls if c[0].startswith("You sort replies")]) == 2
    real = agent.handle(mail(mid="<real@x>", frm="lee@other.com", name="Lee Chen", headers=auth_headers("lee@other.com")))
    assert real.category == "interested"


def test_when_strangers_flood_the_review_list_a_person_is_told_once():
    agent = make_agent()
    for i in range(45):
        agent.handle(mail(mid=f"<f{i}@x>", frm=f"x{i}@random.example", name="X", verified=False))
    kinds = [r["kind"] for r in agent.store.open_attention()]
    assert kinds.count("unknown_reply") == 40 and kinds.count("flood") == 1
    assert "inbox" in review.review_text(agent.store, CFG).lower()


def test_an_oversized_bounce_or_auto_reply_is_not_listed_as_too_large():
    agent = make_agent()
    agent.handle(mail(frm="mailer-daemon@mail.acme.com", subject="Undelivered Mail Returned to Sender", flags=("oversized",),
                      body=OVERSIZE_NOTE, mid="<big1@x>"))
    agent.handle(mail(mid="<big2@x>", flags=("oversized",), body=OVERSIZE_NOTE, headers=(("auto-submitted", "auto-replied"),)))
    assert agent.store.open_attention() == []


# --- bounces --------------------------------------------------------------------------------------
def test_a_bounce_of_a_reply_we_sent_is_shown_to_a_person():
    agent = make_agent(sender=DryRunSender())
    agent.approve(agent.handle(mail(mid="<m1@x>")).draft_id)
    assert agent.flush(live=True)[0].action == "sent"
    agent.handle(mailparse.parse(notice("sam@acme.com", "failed"), "9"))
    assert [r["kind"] for r in agent.store.open_attention()] == ["bounced_reply"]


def test_a_delay_notice_does_not_stop_us_writing_to_anyone():
    agent = make_agent()
    out = agent.handle(mailparse.parse(notice("sam@acme.com", "delayed"), "9"))
    assert out.category == "bounce" and agent.store.suppressed() == frozenset()


def test_a_real_failure_notice_stops_us_writing_to_the_address_that_failed():
    agent = make_agent()
    agent.handle(mailparse.parse(notice("sam@acme.com", "failed"), "9"))
    assert agent.store.suppressed() == frozenset({"sam@acme.com"})


# --- a send that may or may not have gone ---------------------------------------------------------
class Doubtful:
    def send(self, msg):
        raise SendUncertain("timed out while sending")


def test_a_send_that_may_have_gone_out_is_left_as_sending_and_needs_a_person():
    agent = make_agent(sender=Doubtful())
    did = queue_approved(agent, "<u@x>")
    out = agent.flush(live=True)
    assert out[0].action == "uncertain" and agent.store.get_draft(did)["status"] == "sending"
    text = review.review_text(agent.store, CFG)
    assert "NEEDS A LOOK" in text and f"settle {did}" in text
    with pytest.raises(ValueError):
        agent.retry(did)
    with pytest.raises(ValueError):
        agent.skip(did)
    assert agent.flush(live=True) == []  # and it is never picked up for another go


def test_settling_a_doubtful_send_by_hand():
    agent = make_agent(sender=Doubtful())
    first, second = queue_approved(agent, "<u1@x>"), queue_approved(agent, "<u2@x>", frm="lee@other.com", to="hello@boschly.com")
    agent.flush(live=True)
    agent.settle(first, delivered=True)
    agent.settle(second, delivered=False)
    assert agent.store.get_draft(first)["status"] == "sent" and agent.store.get_draft(second)["status"] == "failed"
    agent.retry(second)  # now it is known not to have gone, so trying again is safe
    with pytest.raises(ValueError):
        agent.settle(first, delivered=True)  # only a doubtful one can be settled


def test_a_plain_refusal_is_still_a_failure_that_can_be_retried():
    class Refuses:
        def send(self, msg):
            raise smtplib.SMTPRecipientsRefused({"x": (550, b"no such user")})
    agent = make_agent(sender=Refuses())
    did = queue_approved(agent, "<r@x>")
    assert agent.flush(live=True)[0].action == "failed" and agent.store.get_draft(did)["status"] == "failed"


def test_smtp_errors_after_the_message_started_going_are_doubtful_and_earlier_ones_are_not(monkeypatch):
    class Smtp:
        mode = ""

        def __init__(self, host, port, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            if Smtp.mode == "auth":
                raise smtplib.SMTPAuthenticationError(535, b"bad login")

        def send_message(self, msg):
            if Smtp.mode == "timeout":
                raise TimeoutError("timed out")
            if Smtp.mode == "disconnect":
                raise smtplib.SMTPServerDisconnected("connection unexpectedly closed")
            if Smtp.mode == "refused":
                raise smtplib.SMTPRecipientsRefused({"x": (550, b"no")})
            if Smtp.mode == "data":
                raise smtplib.SMTPDataError(554, b"rejected")
    monkeypatch.setattr(smtplib, "SMTP_SSL", Smtp)
    msg = build_reply(mailbox=BOX, to_addr="sam@acme.com", to_name="Sam", subject="hi", their_id="<a@x>", their_refs=(), body="Hi", cfg=CFG)
    for mode, expected in (("timeout", SendUncertain), ("disconnect", SendUncertain), ("auth", smtplib.SMTPAuthenticationError),
                           ("refused", smtplib.SMTPRecipientsRefused), ("data", smtplib.SMTPDataError)):
        Smtp.mode = mode
        with pytest.raises(expected) as info:
            SmtpSender("smtp.example", "u", "p").send(msg)
        assert isinstance(info.value, SendUncertain) == (mode in ("timeout", "disconnect")), mode


def test_an_old_approved_draft_with_no_due_time_is_not_sent_without_a_fresh_look():
    agent = make_agent(sender=DryRunSender())
    old = mail(mid="<old@x>")
    did = agent.store.record_outcome(old, Decision("interested", 0.9, "t", "model", BOX), verified=True, trust="exact",
                                     draft=Draft(GOOD, ()), draft_status="approved", send_after=None,
                                     at=_iso(NOW - timedelta(days=30)))
    agent.store.update_draft(did, approved_at=None)
    assert agent.flush(live=True)[0].action == "held" and agent.sender.sent == []


# --- the model is down, or choking on one mail ----------------------------------------------------
def test_mail_the_model_keeps_failing_on_cannot_block_the_mail_behind_it():
    def answer(system, prompt, model):
        if "POISON" in prompt:
            raise LLMError("cannot read this one")
        return classifier_says("interested") if system.startswith("You sort replies") else GOOD
    store = Store(":memory:")
    items = [(str(i), raw("POISON please", **{"Message-ID": f"<p{i}@x>", "From": "Sam Lee <sam@acme.com>", "Authentication-Results": OK_AUTH}))
             for i in (1, 2, 3)]
    items.append(("4", raw("Yes please, tell me more", **{"Message-ID": "<good@x>", "From": "Lee Chen <lee@other.com>",
                                                          "Authentication-Results": "purelymail.com; dmarc=pass header.from=lee@other.com"})))
    source = FakeSource(items)
    agent = make_agent(llm=FakeLLM(answer), store=store)
    agent.run_once(source)
    agent.run_once(source)
    assert store.seen("<good@x>") and not store.seen("<p1@x>")


def test_after_a_long_outage_one_pass_hands_every_waiting_mail_to_a_person():
    store = Store(":memory:")
    source = inbox(*range(1, 9))
    agent = make_agent(llm=FakeLLM(down), store=store)
    agent.run_once(source)
    assert len(store.waiting_retries()) == 8  # the ones the model never got to are counted as waiting too
    assert "8 message(s)" in review.review_text(store, CFG)
    agent.clock = lambda: NOW + timedelta(hours=25)
    llm = FakeLLM(down)
    agent.classify_llm = agent.draft_llm = llm
    agent.run_once(source)
    assert [r["kind"] for r in store.open_attention()] == ["stuck"] * 8
    assert sorted(source.done) == [str(i) for i in range(1, 9)] and llm.calls == []


@pytest.mark.parametrize("stdout", ["null", "[]", '"usage limit reached"', "42"])
def test_model_output_that_is_valid_json_but_not_an_object_is_a_model_error(monkeypatch, stdout):
    monkeypatch.setattr("reply_agent.llm._claude_exe", lambda: "claude")

    class Done:
        returncode, stderr = 0, ""

    Done.stdout = stdout
    with pytest.raises(LLMError):
        ClaudeCli(runner=lambda *a, **k: Done()).complete("s", "p", model="haiku")


# --- reading the inbox ----------------------------------------------------------------------------
def test_a_pass_works_past_mail_that_cannot_be_flagged(monkeypatch):
    messages = {str(i): Msg(raw("Yes please", **{"Message-ID": f"<s{i}@x>", "Authentication-Results": OK_AUTH})) for i in range(1, 61)}
    source, conn = connected(monkeypatch, messages)
    conn.store_status = "NO"
    agent = make_agent()
    agent.run_once(source)
    assert all(agent.store.seen(f"<s{i}@x>") for i in range(1, 61))


def test_a_server_that_forgets_flags_cannot_make_a_pass_loop_or_miss_mail(monkeypatch):
    messages = {str(i): Msg(raw("Yes please", **{"Message-ID": f"<k{i}@x>", "Authentication-Results": OK_AUTH})) for i in range(1, 56)}
    source, conn = connected(monkeypatch, messages)
    conn.keeps_flags = False
    agent = make_agent()
    agent.run_once(source)
    assert all(agent.store.seen(f"<k{i}@x>") for i in range(1, 56))


# --- the command line -----------------------------------------------------------------------------
def test_the_suppressed_command_never_prints_terminal_escapes(tmp_path, monkeypatch, capsys):
    from reply_agent import __main__ as cli
    cfg = CFG.with_overrides(db_path=str(tmp_path / "replies.db"))
    Store(cfg.db_path).suppress("a\x1bcpwned@evil.example", "x\x07y")
    monkeypatch.setattr(cli.config_mod, "load", lambda: cfg)
    monkeypatch.setattr(cli, "_setup_environment", lambda: None)
    cli.main(["suppressed"])
    out = capsys.readouterr().out
    assert "\x1b" not in out and "\x07" not in out and "evil.example" in out


def test_the_settle_command_closes_a_doubtful_send(tmp_path, monkeypatch, capsys):
    from reply_agent import __main__ as cli
    cfg = CFG.with_overrides(db_path=str(tmp_path / "replies.db"))
    store = Store(cfg.db_path)
    agent = make_agent(cfg, sender=Doubtful(), store=store)
    did = queue_approved(agent, "<u@x>")
    agent.flush(live=True)
    monkeypatch.setattr(cli.config_mod, "load", lambda: cfg)
    monkeypatch.setattr(cli, "_setup_environment", lambda: None)
    cli.main(["settle", str(did), "--not-sent"])
    assert "not sent" in capsys.readouterr().out.lower()
    assert Store(cfg.db_path).get_draft(did)["status"] == "failed"
