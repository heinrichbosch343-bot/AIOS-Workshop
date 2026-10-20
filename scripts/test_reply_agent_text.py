"""Regression tests from the 19 Oct 2026 code and security reviews: text handling, sender checks, parsing, rules, draft checks."""
from __future__ import annotations

import time
from email.message import EmailMessage

import pytest

from reply_agent import draft as drafting
from reply_agent import mailparse, rules, textnorm, trust, validate
from reply_agent.config import BOOKING_LINK
from reply_agent_testkit import BOX, CFG, GOOD, KNOWN, auth_headers, mail, raw


# --- textnorm ------------------------------------------------------------------------------------
def test_normalise_folds_typography_markup_and_invisible_characters():
    assert textnorm.normalise("Please don\u2019t email me") == "Please don't email me"
    assert textnorm.normalise("stop\u00a0emailing") == "stop emailing"
    assert textnorm.normalise("stop&nbsp;emailing &amp; more") == "stop emailing & more"
    assert textnorm.normalise("un\u200bsub\u00adscribe") == "unsubscribe"
    assert textnorm.normalise("a \n\n b\t\tc") == "a b c"


def test_strip_controls_removes_terminal_and_bidi_tricks_but_keeps_line_breaks():
    dirty = "hi\x1b[2J\x1bc there\x07\u202e\u2066 ok\nnext\tline\x9b"
    clean = textnorm.strip_controls(dirty)
    assert "\x1b" not in clean and "\x07" not in clean and "\u202e" not in clean and "\x9b" not in clean
    assert "\n" in clean and "\t" in clean and "next" in clean


@pytest.mark.parametrize("subject,expected", [
    ("Re: Re: hello there", "hello there"),
    ("RE: hello", "hello"),
    ("Your account is locked, verify at bit.ly/xk29 or call +1 555 0100", "Your account is locked, verify at or call"),
    ("Quote for sam@acme.com", "Quote for"),
    ("see https://evil.example/pay now", "see now"),
    ("", "your message"),
    ("Re: ", "your message"),
])
def test_plain_subject_never_echoes_links_numbers_or_addresses(subject, expected):
    assert textnorm.plain_subject(subject) == expected


def test_plain_subject_is_short_and_free_of_control_characters():
    out = textnorm.plain_subject("word " * 80 + "\x1b[2J")
    assert len(out) <= 70 and "\x1b" not in out and not out.endswith(" ")


# --- trust ---------------------------------------------------------------------------------------
def test_base_address_ignores_plus_tags_and_case():
    assert trust.base_address("John+promo@Lead.COM") == "john@lead.com"
    assert trust.base_address("plain@x.com") == "plain@x.com"
    assert trust.base_address("not-an-address") == "not-an-address"


def test_authenticated_needs_our_own_servers_dmarc_pass_for_the_same_domain():
    assert trust.authenticated(mail()) is True
    assert trust.authenticated(mail(verified=False)) is False
    assert trust.authenticated(mail(headers=auth_headers("sam@acme.com", result="fail"))) is False
    other_server = (("authentication-results", "mx.evil.example; dmarc=pass header.from=sam@acme.com"),)
    assert trust.authenticated(mail(headers=other_server)) is False
    wrong_domain = (("authentication-results", "purelymail.com; dmarc=pass (p=none) header.from=someone@evil.example"),)
    assert trust.authenticated(mail(headers=wrong_domain)) is False
    no_dmarc = (("authentication-results", "purelymail.com; spf=pass smtp.mailfrom=acme.com; dkim=pass header.i=acme.com"),)
    assert trust.authenticated(mail(headers=no_dmarc)) is False


def test_authenticated_needs_the_exact_from_domain_and_only_the_topmost_header_counts():
    sub = (("authentication-results", "purelymail.com; dmarc=pass (p=none) header.from=mail.acme.com"),)
    assert trust.authenticated(mail(headers=sub)) is False  # a pass for another domain, even a related one, proves nothing
    forged_lower = (("authentication-results", "purelymail.com; dmarc=fail header.from=sam@acme.com"),
                    ("authentication-results", "purelymail.com; dmarc=pass header.from=sam@acme.com"))
    assert trust.authenticated(mail(headers=forged_lower)) is False


# --- parsing -------------------------------------------------------------------------------------
BOGUS_CHARSET = (b"From: Sam <sam@acme.com>\r\nTo: heinrich1@boschly.com\r\nSubject: Re: hi\r\nMessage-ID: <b@x>\r\n"
                 b"Date: Fri, 16 Oct 2026 10:00:00 +0200\r\nContent-Type: text/plain; charset=bogus\r\n"
                 b"Content-Transfer-Encoding: 8bit\r\n\r\nYes please, Tuesday works.\r\n")


def test_unknown_charset_is_read_not_fatal():
    parsed = mailparse.parse(BOGUS_CHARSET, "1")
    assert "Yes please" in parsed.body and parsed.from_addr == "sam@acme.com"


def test_absurd_date_does_not_stop_the_parser():
    parsed = mailparse.parse(raw("Hello there friend", Date="Mon, 31 Dec 9999 23:59:59 -0500"), "1")
    assert parsed.received_at.startswith("20")  # fell back to now, not an exception


def test_unparseable_message_becomes_a_flagged_placeholder_with_its_headers(monkeypatch):
    def boom(*_a, **_k):
        raise RecursionError("too deep")
    monkeypatch.setattr(mailparse, "message_from_bytes", boom)
    parsed = mailparse.parse(raw("whatever"), "9")
    assert "unreadable" in parsed.flags
    assert parsed.from_addr == "sam@acme.com" and parsed.subject == "Re: hello" and parsed.message_id == "<a1@x>"


def test_hostile_html_is_read_in_linear_time():
    msg = EmailMessage()
    for k, v in {"From": "x@y.com", "To": BOX, "Subject": "s", "Message-ID": "<h@x>"}.items():
        msg[k] = v
    msg.set_content("<script " * 12000, subtype="html")
    started = time.perf_counter()
    parsed = mailparse.parse(msg.as_bytes(), "1")
    assert time.perf_counter() - started < 1.5 and parsed.from_addr == "x@y.com"


def test_control_characters_never_reach_names_subjects_or_bodies():
    data = (b"From: \"Sam\x1b[2J Lee\" <sam@acme.com>\r\nTo: heinrich1@boschly.com\r\nSubject: =?utf-8?q?hi=07there?=\r\n"
            b"Message-ID: <c@x>\r\n\r\nbody \x1b]0;pwned\x07 text\r\n")
    parsed = mailparse.parse(data, "1")
    for text in (parsed.from_name, parsed.subject, parsed.body):
        assert "\x1b" not in text and "\x07" not in text


def test_a_bottom_posted_answer_is_kept():
    body = "On Fri, Oct 16, 2026 at 5:28 PM Heinrich <heinrich1@boschly.com> wrote:\n> Do you want a quick demo?\n\nYes please, Tuesday works."
    assert mailparse.parse(raw(body), "1").body == "Yes please, Tuesday works."


def test_a_top_posted_answer_still_drops_the_history():
    body = "Yes please.\n\nOn Fri, Oct 16, 2026 at 5:28 PM Heinrich <heinrich1@boschly.com> wrote:\n> Do you want a demo?\n\nold tail text"
    parsed = mailparse.parse(raw(body), "1").body
    assert parsed.startswith("Yes please.") and "old tail text" not in parsed  # and the reader is told something was left out


DSN = (b"From: MAILER-DAEMON@mail.acme.com\r\nTo: heinrich1@boschly.com\r\nSubject: Undelivered Mail Returned to Sender\r\n"
       b"Message-ID: <d1@x>\r\nContent-Type: multipart/report; report-type=delivery-status; boundary=\"B\"\r\n\r\n"
       b"--B\r\nContent-Type: text/plain\r\n\r\nYour message could not be delivered.\r\n"
       b"--B\r\nContent-Type: message/delivery-status\r\n\r\nReporting-MTA: dns; mail.acme.com\r\n\r\n"
       b"Final-Recipient: rfc822; gone@acme.com\r\nAction: failed\r\nStatus: 5.1.1\r\n\r\n--B--\r\n")


def test_a_bounce_names_the_address_that_failed():
    assert mailparse.parse(DSN, "1").failed_recipients == ("gone@acme.com",)


def test_the_servers_authentication_header_is_kept_first_occurrence_only():
    data = raw("hello there friend",
               **{"Authentication-Results": "purelymail.com; dmarc=pass header.from=sam@acme.com"})
    assert mailparse.parse(data, "1").header("authentication-results").startswith("purelymail.com; dmarc=pass")


# --- rules ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Please don\u2019t email me again",
    "Don\u2019t contact us",
    "stop\u00a0emailing me",
    "stop&nbsp;emailing me",
    "Remove my email from your list",
    "please take my name off your list",
    "Remove this address from your mailing list",
    "I no longer wish to receive these",
    "Unsubscribed",
    "no more emails please",
    "Please DELETE my details",
])
def test_unsubscribe_wording_is_caught_however_it_is_typed(text):
    got = rules.prefilter(mail(body=text), CFG, KNOWN)
    assert got is not None and got.category == "unsubscribe", text


@pytest.mark.parametrize("text", [
    "Could you remove the blank page from your sample?",
    "Sounds good, tell me more about how it works",
])
def test_ordinary_words_are_not_mistaken_for_an_unsubscribe(text):
    assert rules.prefilter(mail(body=text), CFG, KNOWN) is None


def test_bounce_detection_uses_the_report_type_not_the_word_report():
    dsn = (("content-type", 'multipart/report; report-type=delivery-status; boundary="B"'),)
    assert rules.prefilter(mail(headers=dsn), CFG, KNOWN).category == "bounce"
    receipt = (("content-type", 'multipart/report; report-type=disposition-notification; boundary="B"'),)
    assert rules.prefilter(mail(headers=receipt), CFG, KNOWN).category == "auto_reply"
    attachment = (("content-type", "text/plain; name=report.txt"),)
    assert rules.prefilter(mail(headers=attachment), CFG, KNOWN) is None


def test_a_reply_to_our_message_only_counts_from_the_person_we_wrote_to():
    known = rules.Known(sent={"<sent1@x>": "sam@acme.com"})
    stranger = mail(frm="stranger@random.org", in_reply_to="<sent1@x>")
    assert rules.prefilter(stranger, CFG, known).category == "unknown_sender"
    assert rules.prefilter(mail(frm="sam@acme.com", in_reply_to="<sent1@x>"), CFG, known) is None


def test_plus_tags_cannot_dodge_the_lists():
    assert rules.prefilter(mail(frm="sam+promo@acme.com"), CFG, KNOWN) is None
    known = rules.Known(emails=KNOWN.emails, suppressed=frozenset({"sam@acme.com"}))
    assert rules.prefilter(mail(frm="sam+x@acme.com"), CFG, known).category == "ignore"


def test_the_servers_own_original_recipient_header_beats_a_forged_to_line():
    forged = mail(to="hello@boschly.com", headers=(("x-pm-original-to", BOX),))
    assert rules.our_mailbox(forged, CFG) == BOX
    direct_to_the_tracking_box = mail(to="hello@boschly.com", headers=(("x-pm-original-to", "track@boschly.com"),))
    assert rules.our_mailbox(direct_to_the_tracking_box, CFG) == ""


def test_the_original_recipient_header_is_kept_when_parsing():
    parsed = mailparse.parse(raw("hello there friend", **{"X-Pm-Original-To": BOX}), "1")
    assert parsed.header("x-pm-original-to") == BOX


def test_trust_levels():
    assert rules.trust_level(mail(frm="sam@acme.com"), KNOWN) == "exact"
    assert rules.trust_level(mail(frm="boss@acme.com"), KNOWN) == "domain"
    assert rules.trust_level(mail(frm="x@random.org"), KNOWN) == "none"
    assert rules.trust_level(mail(frm="SAM+q@acme.com"), KNOWN) == "exact"
    assert rules.trust_level(mail(frm="x@random.org", in_reply_to="<s@x>"), rules.Known(sent={"<s@x>": "x@random.org"})) == "exact"


def test_looks_like_reply():
    assert rules.looks_like_reply(mail(in_reply_to="<a@x>", references=(), subject="hello"))
    assert rules.looks_like_reply(mail(in_reply_to="", references=("<a@x>",), subject="hello"))
    assert rules.looks_like_reply(mail(in_reply_to="", references=(), subject="RE: hello"))
    assert not rules.looks_like_reply(mail(in_reply_to="", references=(), subject="Special offer"))


def test_a_missing_lead_file_is_an_error_not_silence(tmp_path):
    with pytest.raises(FileNotFoundError):
        rules.load_known(CFG.with_overrides(lead_files=(str(tmp_path / "gone.csv"),)))


def test_lead_files_are_read_with_plus_tags_removed(tmp_path):
    path = tmp_path / "leads.csv"
    path.write_text("Name,Email\nSam,Sam+x@Acme.com\n", encoding="utf-8")
    known = rules.load_known(CFG.with_overrides(lead_files=(str(path),)))
    assert known.emails == frozenset({"sam@acme.com"})


# --- greeting ------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,expected", [
    ("Sam Lee", "Sam"), ("SAM LEE", "Sam"), ("Lee, Sam", ""), ("Dr. Sam Lee", "Sam"), ("Mr Sam Lee", "Sam"),
    ("Dr Lee", ""), ("Jean-Luc Picard", "Jean-Luc"), ("Sales Team", ""), ("", ""), ("S", ""),
])
def test_a_first_name_is_used_only_when_we_are_sure(name, expected):
    assert drafting.first_name(mail(name=name)) == expected


# --- the draft checks ----------------------------------------------------------------------------
def _with(claim):
    return GOOD.replace("It's a quick call.", claim)


@pytest.mark.parametrize("claim", [
    "We\u2019ll write your bids.",
    "We'll write your next three bids.",
    "We write them all for you.",
    "Our team will prepare your proposals.",
    "We draft each of your responses.",
])
def test_every_wording_of_we_write_your_bids_is_blocked(claim):
    assert any("they still write" in p for p in validate.check(_with(claim), "interested", CFG)), claim


@pytest.mark.parametrize("claim", [
    "We don\u2019t write your bids, you still do.",
    "We do not write your bids.",
    "We won't draft your proposals for you.",
])
def test_saying_we_do_not_write_them_stays_allowed(claim):
    assert validate.check(_with(claim), "interested", CFG) == (), claim


@pytest.mark.parametrize("claim", [
    "Details at bit.ly/3xYz9Q.",
    "Details at evil-bids.example/claim-your-offer.",
    "See evil.com/pay for details.",
    "Get the pack from ftp://evil.example/pack.zip.",
    "Details at mailto:attacker@evil.example.",
])
def test_links_without_http_are_still_links(claim):
    assert any("link" in p or "email" in p for p in validate.check(_with(claim), "interested", CFG)), claim


@pytest.mark.parametrize("claim,fragment", [
    ("Call me on +1 555 0100.", "phone number"),
    ("Call 5550100123 any time.", "phone number"),
    ("Write to attacker (at) evil dot example.", "email address"),
    ("Confirm your bank details first.", "personal details"),
    ("Send your password and login.", "personal details"),
    ("It cuts bid time by 70 percent.", "claim"),
    ("It saves 40% of the work.", "claim"),
    ("We promise you will win more.", "claim"),
    ("It costs two hundred dollars a month.", "price"),
    ("It is only $99.", "price"),
    ("Pricing is simple, 500 rand.", "price"),
])
def test_claims_prices_phone_numbers_and_credential_phrases_are_blocked(claim, fragment):
    assert any(fragment in p for p in validate.check(_with(claim), "interested", CFG)), claim


def test_things_the_facts_allow_are_not_blocked():
    assert validate.check(_with("One firm went from 24 hours per bid to 10 hours."), "interested", CFG) == ()
    assert validate.check(GOOD.replace(BOOKING_LINK, BOOKING_LINK + "!"), "interested", CFG) == ()
