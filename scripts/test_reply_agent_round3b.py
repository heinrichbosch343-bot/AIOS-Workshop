"""Regression tests from the third review round (19 Oct 2026, the code reviewer reading the fixed code). Each one was
reproduced by a probe before it was fixed. The file is plain ASCII: special characters are written as numbers."""
from __future__ import annotations

import os
import smtplib
import subprocess
import sys
from datetime import timedelta

import pytest

from reply_agent import mailparse, review, rules, trust, validate
from reply_agent.agent import _iso
from reply_agent.llm import FakeLLM, LLMError
from reply_agent.mailbox import DryRunSender, SmtpSender, build_reply
from reply_agent.models import Decision, Draft
from reply_agent.store import Store
from reply_agent_testkit import (BOX, CFG, GOOD, KNOWN, NOW, FakeSource, auth_headers, classifier_says, make_agent, mail, raw,
                                 routed_llm)

OK_AUTH = "purelymail.com; dmarc=pass (p=none) header.from=sam@acme.com"


def category(body="", subject="Re: quick hello", **kw):
    decision = rules.prefilter(mail(body=body, subject=subject, **kw), CFG, KNOWN)
    return decision.category if decision else "model"


# --- 1. a footer, a signature or our own subject is not the person's request --------------------------------------
FOOTERS = [
    "Yes please.\n\nSam\n\nIf you are not the intended recipient, please delete this email from your system.",
    "Yes please.\n\nSam\n\nPlease delete this message from your system if received in error.",
    "Yes please.\n\nSam\n\nIf you no longer wish to receive emails from our firm, please let us know.",
    "Yes please.\n\nSam\n\nUnsubscribe from our newsletter: https://acme.example/unsub",
    "Yes please. Tuesday?\n\n-- \nSam Lee | Acme\nTo stop receiving these emails, click unsubscribe.",
    "Yes please. Tuesday?\n\nSent from my iPhone\nunsubscribe",
    "Yes please. Tuesday?\n\nCONFIDENTIALITY NOTICE: if you wish to opt out of our notices, tell us.",
]


@pytest.mark.parametrize("body", FOOTERS)
def test_a_footer_or_signature_that_mentions_unsubscribing_does_not_silence_a_yes(body):
    assert category(body) not in ("unsubscribe", "complaint"), body


def test_the_subject_of_our_own_email_is_not_read_as_the_persons_request():
    assert category("Yes, interested. Tuesday?", subject="Re: Stop the follow-ups on every bid") == "model"


def test_a_stop_request_that_is_only_in_the_subject_is_still_caught():
    assert category("", subject="unsubscribe") == "unsubscribe"
    assert category("thanks", subject="Re: unsubscribe") == "unsubscribe"


# --- 2. everyday wording is not a request to stop, and a real request still is ----------------------------------------
EVERYDAY = [
    "Please send any further emails to my colleague Jo, she handles bids.",
    "We dont need to get approval for this, so tell me more.",
    "Dont write us off, we are just busy until January. Try me then.",
    "Never contact me by phone, email is better. Tell me more.",
    "Any more emails like this one would be welcome.",
    "I will have my lawyer look at it. Can you send the details?",
    "I reported this to our bid manager, she will reach out.",
    "Please take me off the thread and put Jo on it instead. We are interested.",
]


@pytest.mark.parametrize("text", EVERYDAY)
def test_everyday_wording_from_a_lead_is_not_a_stop_or_a_threat(text):
    assert category(text) not in ("unsubscribe", "complaint"), text


@pytest.mark.parametrize("text", [
    "Please don't send any further emails.", "Do not contact me by email again.", "I have reported you to the FTC.",
    "I am reporting this as spam to your provider and my lawyer.", "No more emails to me, thanks.",
    "Please remove me from your list, how did you get my address?", "Please unsubscribe me\nWhere did you get my email?",
    "I would like to be removed from your list", "I want to be taken off your list", "Would you mind removing me from your mailing list?",
    "Remove.", "Please cease all contact.", "Deregister me please", "Why are you still emailing me? Stop it.",
])
def test_a_real_request_to_stop_is_still_caught(text):
    assert category(text) in ("unsubscribe", "complaint"), text


def test_a_question_about_how_to_unsubscribe_is_still_for_a_person():
    assert category("How do I unsubscribe?") == "other"
    assert category("Is there a way to opt out after the three free bids?") == "other"


# --- 3. a stop request nobody could confirm is never invisible ------------------------------------------------------------
@pytest.mark.parametrize("frm", ["jsmith@acme.com", "sam.lee@smallfirm.example"])
def test_a_stop_request_nobody_could_confirm_is_listed_for_a_person(frm):
    agent = make_agent()
    agent.handle(mail(frm=frm, name="J", verified=False, body="Please remove me from your list.", mid="<f3@x>"))
    assert [r["kind"] for r in agent.store.open_attention()] == ["stop_unconfirmed"]
    assert agent.store.suppressed() == frozenset()
    assert "remove me" in review.review_text(agent.store, CFG) and "suppress" in review.review_text(agent.store, CFG)


# --- 4. the server's verdict: one dmarc word and one header.from word, counted before anything is stripped ------------------
def _verdict_after(server_line, continuation):
    data = ("Received: by purelymail (fake)\r\nX-Pm-Original-To: heinrich1@boschly.com\r\n" + server_line + "\r\n" + continuation + "\r\n"
            "From: Sam Lee <sam@acme.com>\r\nTo: heinrich1@boschly.com\r\nSubject: Re: hello\r\nMessage-ID: <cont@x>\r\n"
            "Date: Fri, 16 Oct 2026 10:00:00 +0200\r\n\r\nhi\r\n").encode()
    return trust.authenticated(mailparse.parse(data, "1"))


def test_a_sender_chosen_bracket_or_quote_cannot_swallow_the_servers_real_result():
    paren = "Authentication-Results: purelymail.com; spf=fail smtp.mailfrom=a(b@evil.example; dkim=none; dmarc=fail (p=none) header.from=sam@acme.com"
    quote = 'Authentication-Results: purelymail.com; spf=fail smtp.mailfrom=a"b@evil.example; dkim=none; dmarc=fail (p=none) header.from=sam@acme.com'
    assert _verdict_after(paren, " ) ; dmarc=pass header.from=sam@acme.com") is False
    assert _verdict_after(quote, ' " ; dmarc=pass header.from=sam@acme.com') is False


# --- 5. strangers cannot use up what real leads are allowed ---------------------------------------------------------------
def test_strangers_cannot_use_up_the_allowance_of_real_leads():
    agent = make_agent()
    for i in range(60):
        agent.handle(mail(mid=f"<s{i}@x>", frm=f"x{i}@random.example", name="X", verified=False, body="Is the data stored in line with POPIA?"))
    out = agent.handle(mail(mid="<real@x>", body="How do you handle data protection for our bid documents?", headers=auth_headers("sam@acme.com")))
    assert out.category == "other" and "shown in review: other" in out.note
    assert agent.store.get_mail("<real@x>")["body"]


def test_120_mails_from_one_listed_address_do_not_fill_the_review():
    agent = make_agent()
    for i in range(120):
        agent.handle(mail(mid=f"<l{i}@x>", frm="sam@acme.com", name="Sam", verified=False, body=f"hello there friend {i}"))
    kinds = [r["kind"] for r in agent.store.open_attention()]
    assert 1 <= len(kinds) <= 10  # one address gets a few items a day, however many ways it finds to be listed


def test_a_verified_colleague_at_the_per_sender_limit_is_listed_not_ignored():
    cfg = CFG.with_overrides(max_model_mails_per_sender_per_day=2)
    agent = make_agent(cfg)
    for i in range(4):
        agent.handle(mail(mid=f"<b{i}@x>", frm="boss@acme.com", name="Boss", headers=auth_headers("boss@acme.com"), body=f"Following up {i}. Call me."))
    assert "limit" in [r["kind"] for r in agent.store.open_attention()]


# --- 6. weak machine signs never silence a trusted sender ----------------------------------------------------------------
def test_a_verified_colleague_replying_from_outlook_is_read_as_a_reply():
    headers = (("x-auto-response-suppress", "DR, NDR, RN, NRN, OOF, AutoReply"), *auth_headers("boss@acme.com"))
    assert rules.prefilter(mail(frm="boss@acme.com", body="Yes please, call me Tuesday.", headers=headers), CFG, KNOWN) is None


def test_a_listed_lead_whose_mail_carries_a_list_unsubscribe_header_is_read_as_a_reply():
    headers = (("list-unsubscribe", "<mailto:x@acme.com>"), *auth_headers("sam@acme.com"))
    assert rules.prefilter(mail(body="Yes please, call me Tuesday.", headers=headers), CFG, KNOWN) is None


def test_bulk_mail_from_a_stranger_is_still_quiet():
    got = rules.prefilter(mail(frm="news@newsletter.example", name="News", in_reply_to="", references=(), body="Weekly digest",
                               headers=(("list-unsubscribe", "<mailto:x@y.com>"),)), CFG, KNOWN)
    assert got is not None and got.category == "auto_reply"


def test_a_real_auto_reply_is_automatic_for_everyone():
    got = rules.prefilter(mail(body="I am out of the office until Monday.", headers=(("auto-submitted", "auto-replied"),)), CFG, KNOWN)
    assert got is not None and got.category == "out_of_office"


# --- 7. a model's doubtful no does not silence a lead -------------------------------------------------------------------
def test_a_doubtful_no_from_the_model_is_listed_not_acted_on():
    agent = make_agent(llm=routed_llm("not_interested", confidence=0.2))
    agent.handle(mail(body="We are covered for now, maybe check back in the new year."))
    assert agent.store.suppressed() == frozenset()
    assert [r["kind"] for r in agent.store.open_attention()] == ["unsure_no"]
    assert agent.store.get_mail("<m1@x>")["body"]


def test_a_confident_no_from_the_model_still_ends_the_conversation():
    agent = make_agent(llm=routed_llm("not_interested", confidence=0.95))
    agent.handle(mail(body="No thanks, we are not interested."))
    assert agent.store.suppressed() == frozenset({"sam@acme.com"})


# --- 8. quoted history ---------------------------------------------------------------------------------------------------
HEADER = "On Fri, Oct 16, 2026 at 5:28 PM Heinrich Bosch <heinrich1@boschly.com> wrote:"


def test_something_typed_under_a_quote_after_an_ordinary_opener_is_flagged_not_silently_dropped():
    parsed = mailparse.parse(raw(f"Thanks.\n\n{HEADER}\n> Would you like a demo?\n> reply unsubscribe to stop.\n\nPlease remove me from your list.\n\nSam"), "1")
    assert "Thanks." in parsed.body and "quoted history" in parsed.body and "unsubscribe" not in parsed.body.lower()


def test_an_unmarked_quote_is_never_merged_into_the_reply():
    body = f"Hi Heinrich, yes please send details\n\n{HEADER}\n\nHi Sam,\nIf you would rather not hear from me, reply unsubscribe.\nHeinrich"
    parsed = mailparse.parse(raw(body), "1")
    assert "unsubscribe" not in parsed.body.lower() and "quoted history" in parsed.body
    assert rules.prefilter(parsed, CFG, KNOWN) is None


def test_an_answer_under_a_marked_quote_with_a_greeting_above_is_still_recovered():
    parsed = mailparse.parse(raw(f"Hi Heinrich,\n\n{HEADER}\n> Want a quick demo?\n\nYes please, Tuesday works.\n\nSam"), "1")
    assert "Yes please, Tuesday works." in parsed.body


# --- 9. a forwarded introduction from a stranger is listed ------------------------------------------------------------------
def test_a_forwarded_introduction_from_a_stranger_is_listed_with_its_text():
    agent = make_agent()
    agent.handle(mail(frm="bidmanager@elsewhere.example", name="Pat", subject="Fwd: Quick question", in_reply_to="", references=(),
                      body="Hi Heinrich, John forwarded me your email. I run bids here and would like to see how it works.", mid="<f10@x>",
                      headers=auth_headers("bidmanager@elsewhere.example")))
    assert [r["kind"] for r in agent.store.open_attention()] == ["unknown_reply"]
    assert agent.store.get_mail("<f10@x>")["body"]


# --- 10. the review prints whatever is in it, on any console --------------------------------------------------------------
def test_the_review_command_survives_a_console_that_cannot_print_an_emoji(tmp_path):
    here = os.path.dirname(os.path.abspath(__file__))
    child = f"""
import sys
sys.path.insert(0, r"{here}")
from reply_agent import __main__ as cli
from reply_agent.models import Decision
from reply_agent.store import Store
from reply_agent_testkit import CFG, mail
db = r"{tmp_path / 'r.db'}"
cfg = CFG.with_overrides(db_path=db)
Store(db).record_outcome(mail(subject="Re: hello " + chr(0x1F600), body="Yes " + chr(0x1F44D), mid="<enc@x>"),
                         Decision("other", 0.5, "x", "model", "heinrich1@boschly.com"), verified=True, trust="exact",
                         attention=("other", "needs a person"))
cli.config_mod.load = lambda: cfg
cli._setup_environment = lambda: None
cli.main(["review"])
"""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    done = subprocess.run([sys.executable, "-c", child], capture_output=True, env=env)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")[-400:]
    assert "needs a person" in done.stdout.decode("utf-8", "replace")


# --- 11. a refused goodbye after the server accepted the message is not a failed send ---------------------------------------
def test_a_refused_goodbye_after_the_message_was_accepted_is_not_a_failed_send(monkeypatch):
    delivered = []

    class Smtp:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            raise smtplib.SMTPResponseException(421, b"closing")

        def login(self, *a):
            pass

        def send_message(self, msg):
            delivered.append(msg)
    monkeypatch.setattr(smtplib, "SMTP_SSL", Smtp)
    msg = build_reply(mailbox=BOX, to_addr="sam@acme.com", to_name="Sam", subject="hi", their_id="<a@x>", their_refs=(), body="Hi", cfg=CFG)
    SmtpSender("smtp.example", "u", "p").send(msg)
    assert len(delivered) == 1


def test_a_login_failure_is_still_an_error(monkeypatch):
    class Smtp:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            raise smtplib.SMTPAuthenticationError(535, b"bad login")
    monkeypatch.setattr(smtplib, "SMTP_SSL", Smtp)
    msg = build_reply(mailbox=BOX, to_addr="sam@acme.com", to_name="Sam", subject="hi", their_id="<a@x>", their_refs=(), body="Hi", cfg=CFG)
    with pytest.raises(smtplib.SMTPAuthenticationError):
        SmtpSender("smtp.example", "u", "p").send(msg)


# --- 12. failure notices ---------------------------------------------------------------------------------------------------------
def _notice(action, header=b""):
    return (b"From: MAILER-DAEMON@evil.example\r\nTo: heinrich1@boschly.com\r\nSubject: Delivery Status Notification (Failure)\r\n" + header +
            b"Message-ID: <d3@x>\r\nContent-Type: multipart/report; report-type=delivery-status; boundary=\"B\"\r\n\r\n"
            b"--B\r\nContent-Type: text/plain\r\n\r\nNote.\r\n--B\r\nContent-Type: message/delivery-status\r\n\r\n"
            b"Reporting-MTA: dns; evil.example\r\n\r\nFinal-Recipient: rfc822; sam@acme.com\r\nAction: " + action + b"\r\nStatus: 4.4.7\r\n\r\n--B--\r\n")


def test_a_delay_notice_that_also_carries_a_failed_recipients_header_names_nobody():
    assert mailparse.parse(_notice(b"delayed", b"X-Failed-Recipients: sam@acme.com\r\n"), "1").failed_recipients == ()


def test_a_failed_recipients_header_alone_still_names_the_address():
    data = (b"From: MAILER-DAEMON@mx.acme.com\r\nTo: heinrich1@boschly.com\r\nSubject: Undelivered Mail Returned to Sender\r\n"
            b"X-Failed-Recipients: sam@acme.com\r\nMessage-ID: <h1@x>\r\n\r\nMailbox full.\r\n")
    assert mailparse.parse(data, "1").failed_recipients == ("sam@acme.com",)


# --- 13. subjects and prices ---------------------------------------------------------------------------------------------------
def _outgoing_subject(subject):
    agent = make_agent(sender=DryRunSender())
    agent.store.record_outcome(mail(mid="<sub@x>", subject=subject), Decision("interested", 0.9, "t", "model", BOX), verified=True,
                               trust="exact", draft=Draft(GOOD, ()), draft_status="approved", send_after=_iso(NOW))
    agent.flush(live=True)
    return agent.sender.sent[0]["Subject"]


@pytest.mark.parametrize("subject", ["Re: Account management contract", "Re: Knowledge transfer plan", "Re: Tax credit program",
                                     "Re: Urgent: RFP due Friday"])
def test_an_ordinary_subject_keeps_its_thread(subject):
    assert _outgoing_subject(subject) == subject


@pytest.mark.parametrize("claim", ["It is about five hundred a month.", "It is two grand a year.", "It is 500 a month.", "It is 1,500 per year."])
def test_spelled_out_and_plain_prices_per_period_are_blocked(claim):
    assert any("price" in p for p in validate.check(GOOD.replace("It's a quick call.", claim), "interested", CFG)), claim


def test_bids_per_month_are_not_a_price():
    assert not any("price" in p for p in validate.check(GOOD.replace("It's a quick call.", "Five bids a month is a good fit."), "interested", CFG))


# --- 14. the model being down must not hold up what the rules can settle -----------------------------------------------------------
def down(*_):
    raise LLMError("usage limit reached")


def _inbox(items):
    return FakeSource([(str(i), raw(body, **{"Message-ID": f"<q{i}@x>", "From": frm, "Authentication-Results": auth_value}))
                       for i, (frm, auth_value, body) in enumerate(items, 1)])


def test_a_stop_request_is_handled_even_while_the_model_is_down():
    llm = FakeLLM(down)
    agent = make_agent(llm=llm)
    items = [("Sam Lee <sam@acme.com>", OK_AUTH, "Yes please, tell me more about it")] * 3
    items.append(("Sam Lee <sam@acme.com>", OK_AUTH, "Please unsubscribe me"))
    source = _inbox(items)
    outcomes = agent.run_once(source)
    assert len(llm.calls) == 3  # the model is not hammered
    assert "4" in source.done and agent.store.seen("<q4@x>") and agent.store.suppressed() == frozenset({"sam@acme.com"})
    assert "1" not in source.done
    assert [o.action for o in outcomes if o.action == "retry"] == ["retry"] * 3
