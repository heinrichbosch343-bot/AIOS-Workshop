"""Regression tests from the 19 Oct 2026 reviews: how the agent behaves when things go wrong, and who it will answer."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from reply_agent import review
from reply_agent.agent import Agent, _iso
from reply_agent.llm import FakeLLM, LLMError
from reply_agent.mailbox import DryRunSender
from reply_agent.models import Decision, Draft
from reply_agent.store import Store
from reply_agent_testkit import (BOX, CFG, GOOD, KNOWN, NOW, FakeSource, auth_headers, classifier_says, make_agent, mail,
                                 raw, routed_llm)

AUTO = CFG.with_overrides(modes={"interested": "auto"})
OK_AUTH = "purelymail.com; dmarc=pass (p=none) header.from=sam@acme.com"


def down(*_):
    raise LLMError("usage limit reached")


def inbox(*ids, body="Yes please, tell me more about it", frm="Sam Lee <sam@acme.com>"):
    return FakeSource([(str(i), raw(body, **{"Message-ID": f"<r{i}@x>", "From": frm, "Authentication-Results": OK_AUTH})) for i in ids])


def queue_approved(agent, mid, *, frm="sam@acme.com", to=BOX, send_after=None, body=GOOD, category="interested"):
    m = mail(mid=mid, frm=frm, to=to)
    decision = Decision(category, 0.9, "test", "model", to)
    return agent.store.record_outcome(m, decision, verified=True, trust="exact", draft=Draft(body, ()),
                                      draft_status="approved", send_after=send_after or _iso(NOW))


# --- a model outage must never bury a reply -------------------------------------------------------
def test_a_model_outage_leaves_the_mail_unrecorded_and_in_the_inbox():
    agent = make_agent(llm=FakeLLM(down))
    with pytest.raises(LLMError):
        agent.handle(mail())
    assert not agent.store.seen("<m1@x>")
    source = inbox(1)
    outcomes = agent.run_once(source)
    assert [o.action for o in outcomes] == ["retry"] and source.done == []


def test_once_the_model_is_back_the_same_mail_is_answered():
    store = Store(":memory:")
    source = inbox(1)
    make_agent(llm=FakeLLM(down), store=store).run_once(source)
    outcomes = make_agent(store=store).run_once(source)
    assert [o.action for o in outcomes] == ["queued"] and source.done == ["1"]
    assert len(store.drafts("pending")) == 1


def test_a_pass_gives_up_after_three_model_failures_in_a_row():
    llm = FakeLLM(down)
    outcomes = make_agent(llm=llm).run_once(inbox(1, 2, 3, 4, 5))
    assert len(llm.calls) == 3  # the model is not asked a fourth time
    assert [o.action for o in outcomes] == ["retry"] * 5  # and the two it was not asked about wait too


def test_a_failure_while_writing_the_draft_loses_nothing():
    calls = {"n": 0}

    def flaky(system, prompt, model):
        if system.startswith("You sort replies"):
            return classifier_says("interested")
        calls["n"] += 1
        if calls["n"] == 1:
            raise LLMError("timed out")
        return GOOD

    store = Store(":memory:")
    source = inbox(1)
    agent = make_agent(llm=FakeLLM(flaky), store=store)
    assert [o.action for o in agent.run_once(source)] == ["retry"]
    assert not store.seen("<r1@x>") and source.done == []
    assert [o.action for o in agent.run_once(source)] == ["queued"]
    assert len(store.drafts("pending")) == 1


def test_a_reply_stuck_for_a_day_is_handed_to_a_person_not_dropped():
    store = Store(":memory:")
    source = inbox(1)
    agent = make_agent(llm=FakeLLM(down), store=store)
    agent.run_once(source)
    agent.clock = lambda: NOW + timedelta(hours=25)
    outcomes = agent.run_once(source)
    assert outcomes[0].action == "logged" and source.done == ["1"]
    kinds = [row["kind"] for row in store.open_attention()]
    assert kinds == ["stuck"]


def test_a_mail_that_keeps_crashing_is_set_aside_after_three_tries(monkeypatch):
    store = Store(":memory:")
    agent = make_agent(store=store)

    def broken(*_a, **_k):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(store, "record_outcome", broken)
    source = inbox(1, 2)
    for _ in range(3):
        agent.run_once(source)
    assert source.quarantined == ["1", "2"]
    assert [row["kind"] for row in store.open_attention()] == ["stuck", "stuck"]


def test_the_mail_row_and_its_draft_are_saved_together_or_not_at_all():
    store = Store(":memory:")
    decision = Decision("interested", 0.9, "t", "model", BOX)
    with pytest.raises(sqlite3.IntegrityError):
        store.record_outcome(mail(), decision, verified=True, trust="exact", draft=Draft(None, ()), draft_status="pending")
    assert not store.seen("<m1@x>")


# --- one reply per person, no double sends --------------------------------------------------------
def test_two_mails_from_one_person_never_both_get_scheduled():
    agent = make_agent(AUTO, sender=DryRunSender())
    assert agent.handle(mail(mid="<a@x>")).action == "scheduled"
    assert agent.handle(mail(mid="<b@x>")).action == "queued"


def test_the_one_reply_a_day_rule_is_checked_again_at_send_time():
    sender = DryRunSender()
    agent = make_agent(AUTO, sender=sender)
    first = queue_approved(agent, "<a@x>")
    second = queue_approved(agent, "<b@x>")
    agent.clock = lambda: NOW + timedelta(minutes=5)
    out = agent.flush(live=True)
    assert len(sender.sent) == 1
    held = agent.store.get_draft(second)
    assert held["status"] == "held" and "24" in (held["note"] or "")
    assert agent.store.get_draft(first)["status"] == "sent"
    assert [o.action for o in out].count("sent") == 1


def test_a_database_error_after_the_send_cannot_cause_a_second_send(monkeypatch):
    sender = DryRunSender()
    agent = make_agent(AUTO, sender=sender)
    did = queue_approved(agent, "<a@x>")
    real_update = agent.store.update_draft

    def flaky_update(draft_id, **fields):
        if fields.get("status") == "sent":
            raise sqlite3.OperationalError("database is locked")
        return real_update(draft_id, **fields)
    monkeypatch.setattr(agent.store, "update_draft", flaky_update)
    agent.clock = lambda: NOW + timedelta(minutes=5)
    first = agent.flush(live=True)
    assert len(sender.sent) == 1 and first[0].action == "sent" and "could not record" in first[0].note
    assert agent.store.get_draft(did)["status"] == "sending"
    agent.flush(live=True)
    assert len(sender.sent) == 1


def test_a_stale_list_of_drafts_cannot_send_the_same_reply_twice(monkeypatch):
    sender = DryRunSender()
    agent = make_agent(AUTO, sender=sender)
    queue_approved(agent, "<a@x>")
    stale = agent.store.drafts("approved")
    monkeypatch.setattr(agent.store, "drafts", lambda status: stale if status == "approved" else [])
    agent.clock = lambda: NOW + timedelta(minutes=5)
    agent.flush(live=True)
    agent.flush(live=True)
    assert len(sender.sent) == 1


def test_a_draft_that_waited_too_long_is_held_for_a_fresh_look():
    sender = DryRunSender()
    agent = make_agent(AUTO, sender=sender)
    did = queue_approved(agent, "<a@x>", send_after=_iso(NOW - timedelta(hours=13)))
    out = agent.flush(live=True)
    assert sender.sent == [] and out[0].action == "held"
    row = agent.store.get_draft(did)
    assert row["status"] == "held" and "waited" in row["note"]


def test_replies_are_spaced_out_one_per_mailbox_per_pass():
    sender = DryRunSender()
    agent = make_agent(AUTO, sender=sender)
    for i, who in enumerate(["sam@acme.com", "lee@other.com", "boss@acme.com"]):
        queue_approved(agent, f"<m{i}@x>", frm=who)
    agent.clock = lambda: NOW + timedelta(minutes=5)
    agent.flush(live=True)
    assert len(sender.sent) == 1 and len(agent.store.drafts("approved")) == 2
    agent.flush(live=True)
    assert len(sender.sent) == 2


def test_a_draft_is_checked_again_before_it_goes_out():
    sender = DryRunSender()
    agent = make_agent(AUTO, sender=sender)
    did = queue_approved(agent, "<a@x>", body=GOOD.replace("free", "free, $99 per month"))
    agent.clock = lambda: NOW + timedelta(minutes=5)
    out = agent.flush(live=True)
    assert sender.sent == [] and out[0].action == "held" and agent.store.get_draft(did)["status"] == "held"


# --- what a person may and may not do -------------------------------------------------------------
def test_approve_refuses_what_could_never_be_sent():
    agent = make_agent(llm=routed_llm("question", reply="ESCALATE: asks for a security report"))
    held = agent.handle(mail()).draft_id
    with pytest.raises(ValueError, match="empty"):
        agent.approve(held, force=True)
    stray = make_agent()
    did = stray.handle(mail(to="nobody@else.com")).draft_id
    with pytest.raises(ValueError, match="mailbox"):
        stray.approve(did, force=True)


def test_a_second_reply_to_the_same_person_inside_a_day_needs_force():
    sender = DryRunSender()
    agent = make_agent(sender=sender)
    first = agent.handle(mail(mid="<a@x>")).draft_id
    agent.approve(first)
    second = agent.handle(mail(mid="<b@x>")).draft_id
    with pytest.raises(ValueError, match="24"):
        agent.approve(second)
    agent.approve(second, force=True)
    agent.clock = lambda: NOW + timedelta(minutes=5)
    agent.flush(live=True)
    agent.flush(live=True)
    assert len(sender.sent) == 2  # one per pass, and the forced one is allowed through


def test_a_failed_send_can_be_retried_by_hand_and_only_a_failed_one():
    class Once:
        def __init__(self):
            self.n, self.sent = 0, []

        def send(self, msg):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("smtp down")
            self.sent.append(msg)
    sender = Once()
    agent = make_agent(sender=sender)
    did = agent.handle(mail()).draft_id
    agent.approve(did)
    assert agent.flush(live=True)[0].action == "failed"
    with pytest.raises(ValueError):
        agent.retry(agent.handle(mail(mid="<other@x>", frm="lee@other.com")).draft_id)
    agent.retry(did)
    assert agent.flush(live=True)[0].action == "sent" and len(sender.sent) == 1


def test_skip_cannot_undo_a_reply_that_already_went():
    sender = DryRunSender()
    agent = make_agent(sender=sender)
    did = agent.handle(mail()).draft_id
    agent.approve(did)
    agent.flush(live=True)
    with pytest.raises(ValueError):
        agent.skip(did)
    with pytest.raises(KeyError):
        agent.skip(9999)


def test_a_missing_lead_file_stops_the_agent_loudly(tmp_path):
    with pytest.raises(FileNotFoundError):
        Agent(CFG.with_overrides(lead_files=(str(tmp_path / "gone.csv"),)), Store(":memory:"), FakeLLM([]))


# --- who the agent will answer by itself ----------------------------------------------------------
def test_mail_whose_sender_cannot_be_verified_is_never_sent_automatically():
    out = make_agent(AUTO).handle(mail(verified=False))
    assert out.action == "queued"


def test_a_colleague_at_a_lead_company_is_reviewed_by_a_person_even_in_auto_mode():
    out = make_agent(AUTO).handle(mail(frm="boss@acme.com", name="Boss Man"))
    assert out.action == "queued"


def test_a_model_that_reports_nan_confidence_gets_no_trust():
    llm = routed_llm()
    base = llm.answers

    def answer(system, prompt, model):
        if system.startswith("You sort replies"):
            return '{"category": "interested", "confidence": NaN, "reason": "x"}'
        return base(system, prompt, model)
    out = make_agent(AUTO, FakeLLM(answer)).handle(mail())
    assert out.action == "queued"


# --- suppression cannot be poisoned ---------------------------------------------------------------
def test_a_forged_unsubscribe_from_a_stranger_suppresses_nobody():
    agent = make_agent()
    out = agent.handle(mail(frm="victim@lead.example", name="Victim", body="please unsubscribe me", verified=False))
    assert out.category == "unsubscribe" and agent.store.suppressed() == frozenset()


def test_a_real_unsubscribe_from_a_known_lead_is_honoured_even_without_a_dmarc_pass():
    agent = make_agent()
    agent.handle(mail(body="please unsubscribe me", verified=False))
    assert "sam@acme.com" in agent.store.suppressed()


def test_a_verified_unsubscribe_from_a_colleague_is_honoured():
    agent = make_agent()
    agent.handle(mail(frm="boss@acme.com", body="please unsubscribe me"))
    assert "boss@acme.com" in agent.store.suppressed()


def test_a_bounce_suppresses_the_address_that_failed_not_the_mail_daemon():
    agent = make_agent()
    bounce = mail(frm="mailer-daemon@mail.acme.com", name="", subject="Undelivered Mail Returned to Sender",
                  failed_recipients=("lee@other.com",), headers=())
    agent.handle(bounce)
    assert agent.store.suppressed() == frozenset({"lee@other.com"})


def test_a_bounce_naming_someone_we_never_wrote_to_changes_nothing():
    agent = make_agent()
    forged = mail(frm="mailer-daemon@evil.example", name="", subject="Undelivered Mail Returned to Sender",
                  failed_recipients=("stranger@random.example",), headers=())
    agent.handle(forged)
    assert agent.store.suppressed() == frozenset()


def test_a_person_can_be_taken_off_the_do_not_write_list():
    agent = make_agent()
    agent.handle(mail(body="please unsubscribe me"))
    agent.store.unsuppress("Sam@Acme.com")
    assert agent.store.suppressed() == frozenset()


def test_someone_on_the_do_not_write_list_who_writes_again_is_shown_to_a_person():
    agent = make_agent()
    agent.store.suppress("sam@acme.com", "unsubscribe")
    out = agent.handle(mail(mid="<again@x>"))
    assert out.category == "ignore"
    assert [row["kind"] for row in agent.store.open_attention()] == ["suppressed_wrote"]


# --- nothing real is silent -----------------------------------------------------------------------
def test_an_unknown_sender_who_replies_to_something_is_shown_to_a_person():
    agent = make_agent()
    out = agent.handle(mail(frm="sam.personal@gmail.com", name="Sam", verified=False))
    assert out.category == "unknown_sender"
    rows = agent.store.open_attention()
    assert [r["kind"] for r in rows] == ["unknown_reply"] and rows[0]["body"]


def test_unknown_marketing_mail_is_logged_without_keeping_its_text():
    agent = make_agent()
    agent.handle(mail(frm="deals@shop.example", name="Shop", subject="Special offer just for you", in_reply_to="",
                      references=(), body="Buy now and save big on everything in the store today"))
    assert agent.store.open_attention() == []
    row = agent.store.get_mail("<m1@x>")
    assert row["body"] == "" and row["category"] == "unknown_sender"


def test_warmup_mail_is_logged_without_keeping_its_text():
    agent = make_agent()
    agent.handle(mail(frm="warm@network.example", body="hello cedar-upstairs how are you today"))
    assert agent.store.open_attention() == [] and agent.store.get_mail("<m1@x>")["body"] == ""


def test_complaints_and_confident_others_are_shown_to_a_person():
    agent = make_agent()
    agent.handle(mail(body="I will report you to my lawyer", mid="<c@x>"))
    agent2 = make_agent(llm=routed_llm("other"))
    agent2.handle(mail(body="thanks", mid="<o@x>"))
    assert [r["kind"] for r in agent.store.open_attention()] == ["complaint"]
    assert [r["kind"] for r in agent2.store.open_attention()] == ["other"]


def test_attention_items_can_be_resolved():
    agent = make_agent()
    agent.handle(mail(body="I will report you to my lawyer"))
    row = agent.store.open_attention()[0]
    agent.store.resolve_attention(row["id"])
    assert agent.store.open_attention() == []


def test_a_flood_of_unknown_replies_cannot_bury_the_review_list():
    agent = make_agent()
    for i in range(60):
        agent.handle(mail(mid=f"<f{i}@x>", frm=f"x{i}@random.example", name="X", verified=False))
    kinds = [r["kind"] for r in agent.store.open_attention()]
    assert len(kinds) <= 41 and kinds.count("flood") == 1  # at most 40 listed, plus one notice saying the rest were not


# --- the model is not a free-for-all --------------------------------------------------------------
def test_one_sender_cannot_use_up_the_model():
    cfg = CFG.with_overrides(max_model_mails_per_sender_per_day=2)
    llm = routed_llm()
    agent = make_agent(cfg, llm)
    outcomes = [agent.handle(mail(mid=f"<s{i}@x>")) for i in range(4)]
    assert [o.category for o in outcomes][2:] == ["ignore", "ignore"]
    assert sum(1 for c in llm.calls if c[0].startswith("You sort replies")) == 2


def test_the_whole_mailbox_has_a_daily_model_budget_too():
    cfg = CFG.with_overrides(max_model_mails_per_day=2)
    llm = routed_llm()
    agent = make_agent(cfg, llm)
    cats = [agent.handle(mail(mid=f"<g{i}@x>", frm=who)).category
            for i, who in enumerate(["sam@acme.com", "lee@other.com", "boss@acme.com"])]
    assert cats[2] == "other"  # not read by the model, and a person is told: a verified colleague is never dropped silently
    assert [r["kind"] for r in agent.store.open_attention()] == ["limit"]


# --- what a person sees ---------------------------------------------------------------------------
def test_review_shows_who_where_and_whether_the_sender_was_verified():
    agent = make_agent()
    agent.handle(mail(subject="Re: quick hello\x1b[2J", name="Sam\x1b]0;pwned\x07 Lee", verified=False))
    text = review.review_text(agent.store, CFG)
    assert "sam@acme.com" in text and BOX in text and "NOT VERIFIED" in text and "Re: quick hello" in text
    assert "\x1b" not in text and "\x07" not in text


def test_review_lists_attention_items_and_stuck_sends():
    agent = make_agent()
    agent.handle(mail(body="I will report you to my lawyer", mid="<c@x>"))
    did = queue_approved(agent, "<s@x>")
    agent.store.update_draft(did, status="sending")
    text = review.review_text(agent.store, CFG)
    assert "complaint" in text and "NEEDS A LOOK" in text


def test_review_says_so_when_there_is_nothing():
    assert "Nothing waiting" in review.review_text(Store(":memory:"), CFG)


def test_the_reviewer_sees_everything_the_model_saw():
    agent = make_agent()
    long_body = "word " * 700
    agent.handle(mail(body=long_body))
    text = review.review_text(agent.store, CFG)
    assert text.count("word") >= 600 or "cut" in text
