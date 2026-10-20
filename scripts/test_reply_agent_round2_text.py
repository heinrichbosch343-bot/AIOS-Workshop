"""Regression tests from the second independent review (19 Oct 2026, after the rebuild): what the rules, the sender check, the
parser and the draft checks still got wrong. Each one was reproduced before it was fixed."""
from __future__ import annotations

import time
from email.message import EmailMessage

import pytest

from reply_agent import mailparse, rules, textnorm, trust, validate
from reply_agent.config import BOOKING_LINK
from reply_agent_testkit import BOX, CFG, GOOD, KNOWN, auth_headers, mail, raw


def _with(claim):
    return GOOD.replace("It's a quick call.", claim)


# --- text folding ---------------------------------------------------------------------------------
@pytest.mark.parametrize("dash", ["\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"])
def test_every_kind_of_dash_is_folded_to_a_hyphen_so_patterns_still_match(dash):
    assert textnorm.normalise(f"opt{dash}out") == "opt-out"
    assert rules.prefilter(mail(body=f"Please opt{dash}out of this"), CFG, KNOWN).category == "unsubscribe"


@pytest.mark.parametrize("hidden", ["\u034f", "\u180e", "\U000e0020", "\ufe0f", "\u3164", "\u115f"])
def test_more_invisible_characters_are_removed(hidden):
    assert textnorm.normalise(f"un{hidden}subscribe") == "unsubscribe"


# --- who is asking us to stop ---------------------------------------------------------------------
MUST_STOP = [
    "Stop.", "STOP", "Please stop these emails.", "Stop the emails", "stop emails", "Stop messages please",
    "Remove from list", "Remove our company from your list", "Please remove our details from your system",
    "Please opt me out", "unsub", "Not interested, never write again.", "Don't reply to this address again.",
    "Haal my asseblief van jou lys af", "Please don't send me any more of these", "Take me off", "Do not email me again",
    "I want to opt out", "Could you please remove me from your list?", "Please stop contacting us.",
    "Stop sending me these", "Don't contact me again", "stop spamming me",
]


@pytest.mark.parametrize("text", MUST_STOP)
def test_every_ordinary_way_of_asking_to_stop_is_caught_by_the_rules(text):
    got = rules.prefilter(mail(body=text), CFG, KNOWN)
    assert got is not None and got.category == "unsubscribe", text


MUST_REACH_THE_MODEL = [
    "We don't send that many bids, maybe two a month, but this sounds interesting. Tell me more.",
    "We never send a bid late, but I'd like to see how this works.",
    "I don't contact vendors directly, please speak to my assistant Jo at jo@acme.com.",
    "Sounds good. We don't call it a proposal, we call it a response. Can you show me?",
    "Not for us, we don't write bids in house.",
    "Our attorney reviews every bid. Send me the details and I will forward them.",
    "Yes please, I'd love to stop writing every bid from scratch.",
    "We need to stop sending bids late. Can you help?",
    "Please don't call me, email is better. Tell me more.",
]


@pytest.mark.parametrize("text", MUST_REACH_THE_MODEL)
def test_a_hot_lead_is_not_mistaken_for_someone_asking_to_stop(text):
    assert rules.prefilter(mail(body=text), CFG, KNOWN) is None, text


def test_a_question_about_opting_out_goes_to_a_person_and_suppresses_nobody():
    got = rules.prefilter(mail(body="Is there a way to opt out after the three free bids?"), CFG, KNOWN)
    assert got.category == "other" and "person" in got.reason


def test_talk_of_data_protection_or_spam_goes_to_a_person_and_suppresses_nobody():
    for text in ("How do you handle data protection for our bid documents?", "Is the data stored in line with POPIA?",
                 "Your email landed in my spam folder but it looks relevant. Can we talk Tuesday?",
                 "I thought this was a scam at first, but your site looks real. Tell me more."):
        got = rules.prefilter(mail(body=text), CFG, KNOWN)
        assert got is not None and got.category == "other", text


def test_a_real_threat_is_still_a_complaint():
    for text in ("I will report you to my lawyer", "My attorneys will be in touch about this",
                 "This is harassment, I will sue you", "I am filing a complaint with the ICO"):
        assert rules.prefilter(mail(body=text), CFG, KNOWN).category == "complaint", text


def test_asking_to_stop_while_citing_the_law_is_a_complaint_not_a_plain_unsubscribe():
    got = rules.prefilter(mail(body="Please remove me from your list, this breaks GDPR and I will report you."), CFG, KNOWN)
    assert got.category == "complaint"


def test_an_automatic_reply_is_never_treated_as_someone_asking_to_stop():
    auto = (("auto-submitted", "auto-replied"),)
    got = rules.prefilter(mail(body="I am away. To unsubscribe from these notices click here.", headers=auto), CFG, KNOWN)
    assert got.category in ("out_of_office", "auto_reply")


def test_localised_outlook_headers_are_cut_so_our_own_footer_is_not_mistaken_for_theirs():
    german = ("Ja bitte, rufen Sie mich an.\n\nVon: Heinrich Bosch <heinrich1@boschly.com>\nGesendet: Freitag, 16. Oktober 2026 17:28\n"
              "An: Sam\nBetreff: quick hello\n\nIf you would like to stop hearing from us, reply unsubscribe.")
    afrikaans = ("Ja asseblief.\n\nVan: Heinrich Bosch\nVerstuur: Vrydag\nAan: Sam\nOnderwerp: hello\n\n"
                 "Reply STOP and we will remove you from our list.")
    for body, keep in ((german, "Ja bitte"), (afrikaans, "Ja asseblief")):
        parsed = mailparse.parse(raw(body), "1")
        assert parsed.body.startswith(keep) and "unsubscribe" not in parsed.body.lower() and "stop" not in parsed.body.lower()


def test_a_reply_that_names_nobody_in_a_header_block_is_not_cut_at_a_label_in_the_middle_of_a_sentence():
    parsed = mailparse.parse(raw("Hello.\nFrom what I can see this is useful.\nVon is my surname.\nCall me."), "1")
    assert "Call me." in parsed.body


@pytest.mark.parametrize("header", [
    "Am Fr., 16. Okt. 2026 um 17:28 schrieb Heinrich Bosch <heinrich1@boschly.com>:",
    "Op vr 16 okt. 2026 om 17:28 het Heinrich Bosch <heinrich1@boschly.com> geskryf:",
    "Le ven. 16 oct. 2026 \u00e0 17:28, Heinrich Bosch <heinrich1@boschly.com> a \u00e9crit :",
    "El vie, 16 oct 2026 a las 17:28, Heinrich Bosch <heinrich1@boschly.com> escribi\u00f3:",
])
def test_other_languages_wrote_headers_are_cut_too(header):
    parsed = mailparse.parse(raw(f"Yes please.\n\n{header}\n> If you would like to stop, reply unsubscribe.\n"), "1")
    assert parsed.body == "Yes please."


def test_a_short_greeting_above_a_quote_does_not_hide_the_answer_written_below_it():
    body = ("Hi Heinrich,\n\nOn Fri, Oct 16, 2026 at 5:28 PM Heinrich <heinrich1@boschly.com> wrote:\n> Want a quick demo?\n\n"
            "Yes please, Tuesday works.\n\nSam")
    parsed = mailparse.parse(raw(body), "1")
    assert "Yes please, Tuesday works." in parsed.body and "Want a quick demo" not in parsed.body


def test_html_quoted_history_is_cut_like_plain_text_history():
    msg = EmailMessage()
    for k, v in {"From": "Sam <sam@acme.com>", "To": BOX, "Subject": "Re: hi", "Message-ID": "<q@x>"}.items():
        msg[k] = v
    msg.set_content("<p>Yes please.</p><div>On Fri, Oct 16, 2026 at 5:28 PM Heinrich wrote:</div>"
                    "<blockquote><p>Reply unsubscribe to stop hearing from us.</p></blockquote>", subtype="html")
    parsed = mailparse.parse(msg.as_bytes(), "1")
    assert parsed.body == "Yes please." and rules.prefilter(parsed, CFG, KNOWN) is None


# --- delivery reports -----------------------------------------------------------------------------
def _dsn(action, status="5.1.1"):
    return (b"From: MAILER-DAEMON@mail.acme.com\r\nTo: heinrich1@boschly.com\r\nSubject: Delivery Status Notification\r\n"
            b"Message-ID: <d2@x>\r\nContent-Type: multipart/report; report-type=delivery-status; boundary=\"B\"\r\n\r\n"
            b"--B\r\nContent-Type: text/plain\r\n\r\nNote.\r\n"
            b"--B\r\nContent-Type: message/delivery-status\r\n\r\nReporting-MTA: dns; mail.acme.com\r\n\r\n"
            b"Final-Recipient: rfc822; sam@acme.com\r\nAction: " + action.encode() + b"\r\nStatus: " + status.encode() + b"\r\n\r\n--B--\r\n")


def test_only_a_real_failure_names_an_address_as_failed():
    assert mailparse.parse(_dsn("failed"), "1").failed_recipients == ("sam@acme.com",)
    for action in ("delayed", "delivered", "relayed", "expanded"):
        assert mailparse.parse(_dsn(action, "2.0.0"), "1").failed_recipients == (), action


# --- the sender check -----------------------------------------------------------------------------
def _auth(value, frm="sam@acme.com"):
    return trust.authenticated(mail(frm=frm, headers=(("authentication-results", value),)))


GOOD_AUTH = "purelymail.com; spf=pass smtp.mailfrom=acme.com; dkim=pass header.i=acme.com; dmarc=pass (p=none) header.from=sam@acme.com"


def test_the_real_servers_pass_is_believed():
    assert _auth(GOOD_AUTH) is True
    assert _auth("purelymail.com 1; dmarc=pass header.from=acme.com") is True


@pytest.mark.parametrize("value", [
    # the envelope sender is chosen by the attacker and echoed into the header: 'dmarc=pass' hides inside smtp.mailfrom
    "purelymail.com; spf=fail smtp.mailfrom=x=dmarc=pass@evil.example; dkim=none; dmarc=fail (p=none) header.from=sam@acme.com",
    # text in a comment or a quoted value is not a result
    "purelymail.com; dmarc=fail (reason: dmarc=pass) header.from=sam@acme.com",
    'purelymail.com; dkim=fail header.i="@x dmarc=pass"; dmarc=none header.from=sam@acme.com',
    # a second dmarc result (a continuation line the sender added to our header) makes the whole header untrustworthy
    "purelymail.com; dmarc=fail (p=none) header.from=sam@acme.com ; dmarc=pass header.from=sam@acme.com",
    "purelymail.com; dmarc=pass header.from=sam@acme.com; dmarc=fail header.from=sam@acme.com",
    # the pass must be for exactly the domain in the From line
    "purelymail.com; dmarc=pass header.from=evil.acme.com",
    "purelymail.com; dmarc=pass header.from=mail.acme.com",
    "purelymail.com; dmarc=pass header.from=acme.com.evil.example",
])
def test_a_crafted_authentication_header_does_not_make_a_forged_sender_verified(value):
    assert _auth(value) is False, value


def test_the_sender_cannot_graft_a_second_result_onto_our_servers_header_with_a_leading_space():
    data = (b"Authentication-Results: purelymail.com; spf=none smtp.mailfrom=evil.com; dkim=none; dmarc=fail (p=none) header.from=sam@acme.com\r\n"
            b" dmarc=pass header.from=sam@acme.com\r\n"
            b"From: Sam <sam@acme.com>\r\nTo: heinrich1@boschly.com\r\nSubject: Re: hi\r\nMessage-ID: <g@x>\r\n\r\nhello there friend\r\n")
    assert trust.authenticated(mailparse.parse(data, "1")) is False


# --- addresses ------------------------------------------------------------------------------------
@pytest.mark.parametrize("value,expected", [
    ("Sam@ACME.com", "sam@acme.com"),
    ("sam+tag@acme.com", "sam+tag@acme.com"),
    ("o'brien@acme.com", "o'brien@acme.com"),
    ("sam\x1b[2J@acme.com", ""),
    ("a\x07b@evil.example", ""),
    ("sam\u202e@acme.com", ""),
    ("sam" + chr(0x212A) + "@acme.com", ""),  # the Kelvin sign lowercases to a plain k
    ('"a, victim@thirdparty.com"@acme.com', ""),
    ("acme.com", ""),
    ("sam@acme", ""),
    ("sam@@acme.com", ""),
    ("sam@acme.com.", ""),
    ("", ""),
])
def test_only_a_plain_ascii_address_is_accepted(value, expected):
    assert trust.clean_address(value) == expected


def test_a_sender_address_with_control_characters_never_reaches_the_lists_or_the_screen():
    parsed = mailparse.parse(b"From: a\x1bb@evil.example\r\nTo: heinrich1@boschly.com\r\nSubject: Re: hi\r\nMessage-ID: <e@x>\r\n\r\nstop\r\n", "1")
    assert parsed.from_addr == ""


def test_recipients_are_cleaned_the_same_way():
    parsed = mailparse.parse(raw("hello there friend", To=f"{BOX}, bad\x1b@evil.example"), "1")
    assert parsed.to_addrs == (BOX,)


# --- hostile mail ---------------------------------------------------------------------------------
def test_an_enormous_header_block_is_refused_quickly_not_parsed():
    addresses = ", ".join(f"u{i}@example.com" for i in range(30000))
    data = f"From: a@b.com\r\nTo: {addresses}\r\nSubject: hi\r\nMessage-ID: <h@x>\r\n\r\nbody\r\n".encode()
    started = time.perf_counter()
    parsed = mailparse.parse(data, "1")
    assert time.perf_counter() - started < 1.5 and "unreadable" in parsed.flags


def test_a_message_made_of_tens_of_thousands_of_tiny_parts_is_refused_quickly():
    parts = "".join(f"--B\r\nContent-Type: text/plain\r\n\r\nx\r\n" for _ in range(30000))
    data = ("From: a@b.com\r\nTo: heinrich1@boschly.com\r\nSubject: hi\r\nMessage-ID: <t@x>\r\n"
            "Content-Type: multipart/mixed; boundary=B\r\n\r\n" + parts + "--B--\r\n").encode()
    started = time.perf_counter()
    parsed = mailparse.parse(data, "1")
    assert time.perf_counter() - started < 2 and "unreadable" in parsed.flags


def test_a_slow_charset_on_a_huge_body_cannot_stall_the_parser():
    body = b"a" * 900_000
    data = (b"From: a@b.com\r\nTo: heinrich1@boschly.com\r\nSubject: hi\r\nMessage-ID: <p@x>\r\n"
            b"Content-Type: text/plain; charset=punycode\r\nContent-Transfer-Encoding: 8bit\r\n\r\n" + body + b"\r\n")
    started = time.perf_counter()
    mailparse.parse(data, "1")
    assert time.perf_counter() - started < 2


# --- the draft checks -----------------------------------------------------------------------------
WRITES_FOR_THEM = [
    "We'll be writing your next three bids.", "We're writing your bids for you.", "We take care of writing your proposals.",
    "We handle the writing of every bid.", "We write the first draft of your bids.", "We write, edit and submit your bids.",
    "Your bids get written by our team.", "We'll have each proposal written for you.", "We produce your proposals end to end.",
    "We create complete bids for you.", "Our team does the bid writing for you.", "We do all the writing.",
    "We generate your responses.", "We take it from there and write the whole thing.",
]


@pytest.mark.parametrize("claim", WRITES_FOR_THEM)
def test_every_way_of_saying_we_write_their_bids_is_blocked(claim):
    assert any("they still write" in p for p in validate.check(_with(claim), "interested", CFG)), claim


@pytest.mark.parametrize("claim", [
    "We don't write your bids, you still do.",
    "You still write every bid. Our system finds the answers you wrote in earlier bids.",
    "We build a searchable library from your past bids.",
    "We can show you how it works on your next three bids.",
    "We set it up on your next three bids, free.",
    "It finds the answers you already wrote in your old bids and pulls them back out.",
    "I'll write back with a few times that work for your next three bids.",
    "We can prepare a short walkthrough for your next three bids.",
])
def test_describing_what_we_really_do_is_not_blocked(claim):
    assert not any("they still write" in p for p in validate.check(_with(claim), "interested", CFG)), claim


@pytest.mark.parametrize("claim", [
    "It costs R7,500 for the audit.", "It is R500 per month.", "USD 500 a month.", "EUR 300 per bid.", "A flat fee of 99 a month.",
    "It starts at 1 500 for the setup.", "It's about the price of a coffee, five bucks.", "We charge by the bid, ninety nine each.",
    "It is fifty dollars a month.", "The fee is under five hundred.",
])
def test_every_way_of_naming_a_price_is_blocked(claim):
    assert any("price" in p for p in validate.check(_with(claim), "interested", CFG)), claim


@pytest.mark.parametrize("claim", [
    "It cuts your bid time in half.", "It cuts your bid time by a third.", "You will go from 24 hours to 10 hours per bid.",
    "It makes bids ten times faster.", "You'll win more bids.", "You'll save 14 hours on every bid.", "That is a 40-percent saving.",
    "It is twice as fast.", "I'm confident you'll win more work.", "We ensure every bid is compliant.",
    "It will definitely save you time.", "It's free forever.", "You get a discount on the next ones.",
])
def test_every_way_of_promising_a_result_is_blocked(claim):
    assert any("claim" in p for p in validate.check(_with(claim), "interested", CFG)), claim


@pytest.mark.parametrize("claim", [
    "One firm went from 24 hours per bid to 10 hours.",
    "We could start the week of 2026-11-02.",
    "Tuesday 20 October at 14:00 works.",
    "The call takes about 20 minutes.",
    "We can start with your next three bids, free.",
    "It's a third party tool, so nothing to install.",
])
def test_ordinary_things_are_not_blocked_as_claims_or_prices(claim):
    assert not any(("claim" in p or "price" in p or "number" in p) for p in validate.check(_with(claim), "interested", CFG)), claim


def test_a_number_nothing_approved_is_flagged_but_the_prospects_own_numbers_may_be_repeated():
    invented = validate.check(_with("We've helped 12 firms like yours."), "interested", CFG)
    assert any("number" in p for p in invented)
    echoed = validate.check(_with("Five bids a month is a good fit, and 8 firms like that are common."), "interested", CFG,
                            context="We send about 8 bids a month")
    assert not any("number" in p for p in echoed)


@pytest.mark.parametrize("claim", [
    "See evil-bids.club/offer.", "Details at attacker.gov/pay.", "Visit bidlab.sh/start.", "Open cal(dot)com/evil.",
    "Visit evil.zip.", "Visit example.one/now.", "Look at bad.tk.", "Look at bad.icu.", "Look at bad.es.",
    "Visit evil dot com for details.", "See bit ly slash abc.", "Go to evil . com now.",
])
def test_a_web_address_is_caught_whatever_its_ending(claim):
    assert any(("link" in p or "email" in p) for p in validate.check(_with(claim), "interested", CFG)), claim


def test_the_booking_link_must_be_exactly_the_booking_link():
    for twisted in (BOOKING_LINK + "/evil", BOOKING_LINK + "0", BOOKING_LINK + "&next=evil.com", BOOKING_LINK + ".evil.example/x"):
        assert any("link" in p for p in validate.check(GOOD.replace(BOOKING_LINK, twisted), "interested", CFG)), twisted
    for fine in (BOOKING_LINK + ".", BOOKING_LINK + "!", BOOKING_LINK + ")"):
        assert validate.check(GOOD.replace(BOOKING_LINK, fine), "interested", CFG) == (), fine


@pytest.mark.parametrize("claim", [
    "Call 555/010/0123.", "Call five five five zero one zero zero one two three.", "My cell is 555\u2011010\u20110123.", "Ring 555.010.0123.",
])
def test_phone_numbers_are_caught_in_more_shapes(claim):
    assert any("phone" in p for p in validate.check(_with(claim), "interested", CFG)), claim


def test_a_date_written_with_slashes_is_not_a_phone_number():
    assert not any("phone" in p for p in validate.check(_with("We could talk on 16/10/2026."), "interested", CFG))


@pytest.mark.parametrize("claim", ["Send your pass-word.", "Please log in to your account.", "What is your pass word?"])
def test_asking_for_credentials_is_caught_however_it_is_spelled(claim):
    assert any("personal details" in p for p in validate.check(_with(claim), "interested", CFG)), claim


@pytest.mark.parametrize("hidden", ["\u034f", "\u180e", "\U000e0020", "\ufe0f", "\u3164", "\u0430"])
def test_hidden_or_look_alike_characters_make_a_draft_fail(hidden):
    sneaky = GOOD.replace("It's a quick call.", f"Visit evil{hidden}.com now.")
    assert any("characters" in p for p in validate.check(sneaky, "interested", CFG)), repr(hidden)


def test_padding_with_text_the_checks_cannot_read_does_not_get_a_draft_through():
    padded = GOOD + "\n\n" + " ".join(["\u043f\u0440\u0438\u0432\u0435\u0442"] * 3000)
    problems = validate.check(padded, "interested", CFG)
    assert problems and any(("long" in p or "characters" in p) for p in problems)


def test_a_hostile_draft_cannot_stall_the_checks():
    started = time.perf_counter()
    validate.check(_with("a." * 8000 + "com"), "interested", CFG)
    validate.check(_with("a" * 20000), "interested", CFG)
    assert time.perf_counter() - started < 2


def test_accented_names_are_fine_in_a_draft():
    assert validate.check(GOOD.replace("Hi Sam,", "Hi Jos\u00e9,"), "interested", CFG) == ()


def test_curly_quotes_in_a_draft_are_fine():
    assert validate.check(GOOD.replace("We'd", "We\u2019d").replace("It's", "It\u2019s"), "interested", CFG) == ()


def test_the_shipped_examples_still_pass_every_check():
    from reply_agent.config import load_shared
    cfg = load_shared()
    for example, category in zip(cfg.examples, ("interested", "question", "soft_no")):
        assert validate.check(example["out"], category, cfg, context=example["in"]) == (), category


# --- found by running the second reviewers' own probe scripts against the fixed code ---------------
def test_a_from_line_that_defeats_the_parser_is_a_flagged_placeholder_not_an_exception():
    data = ("From: a@b.com " + "(" * 4000 + ")" * 4000 + "\r\nTo: heinrich1@boschly.com\r\nSubject: hi\r\nMessage-ID: <n@x>\r\n\r\nbody\r\n").encode()
    parsed = mailparse.parse(data, "1")
    assert "unreadable" in parsed.flags and parsed.message_id == "<n@x>"


def test_words_that_only_start_like_unsubscribe_are_not_a_request_to_stop():
    for text in ("Those claims are unsubstantiated, can you show me?", "We are optimistic about this", "An optout button would help us"):
        got = rules.prefilter(mail(body=text), CFG, KNOWN)
        assert got is None or got.category != "unsubscribe", text


def test_two_headers_claiming_to_be_our_server_make_neither_believable():
    one = raw("hello there friend", **{"Authentication-Results": GOOD_AUTH})
    assert trust.authenticated(mailparse.parse(one, "1")) is True
    two = one.replace(b"Authentication-Results:", b"Authentication-Results: purelymail.com; dmarc=pass header.from=sam@acme.com\r\nAuthentication-Results:", 1)
    assert trust.authenticated(mailparse.parse(two, "1")) is False
    other_hop = one.replace(b"Authentication-Results:", b"Authentication-Results: mx.google.com; dmarc=pass header.from=sam@acme.com\r\nAuthentication-Results:", 1)
    assert trust.authenticated(mailparse.parse(other_hop, "1")) is False  # first header is another server's; only OUR topmost one counts


def test_when_only_a_greeting_survives_the_reader_is_told_the_rest_was_cut():
    body = "Hi Heinrich,\n\nFrom: Heinrich Bosch <heinrich1@boschly.com>\nSent: Friday\nTo: Sam\nSubject: hello\n\nDo you want a quick demo of what we do for bids?"
    parsed = mailparse.parse(raw(body), "1")
    assert parsed.body.startswith("Hi Heinrich,") and "quoted history" in parsed.body and "mailbox" in parsed.body


def test_a_normal_short_reply_does_not_get_the_cut_note():
    assert "quoted history" not in mailparse.parse(raw("Yes please.\n\nOn Fri, Oct 16, 2026 at 5:28 PM Heinrich <heinrich1@boschly.com> wrote:\n> Want a demo?"), "1").body


@pytest.mark.parametrize("claim", ["Details at evil .com/claim.", "Please sign in to the portal with your credentials.", "Use your credentials to get in."])
def test_more_ways_of_hiding_a_link_or_asking_for_a_login_are_caught(claim):
    assert any(("link" in p or "personal details" in p) for p in validate.check(_with(claim), "interested", CFG)), claim
