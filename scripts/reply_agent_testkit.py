"""Helpers shared by the reply agent tests. No network, no real model, no real mailbox."""
from __future__ import annotations

import imaplib
import json
import random
import re
from datetime import datetime, timezone
from email.message import EmailMessage

from reply_agent import rules
from reply_agent.agent import Agent
from reply_agent.config import BOOKING_LINK, Config
from reply_agent.llm import FakeLLM
from reply_agent.models import InboundMail
from reply_agent.store import Store

BOX = "heinrich1@boschly.com"
CFG = Config(
    tracking_mailbox="track@boschly.com",
    campaign_mailboxes=(BOX, "hello@boschly.com"),
    warmup_tags=("cedar-upstairs",),
    facts=("We build AI operating systems for bids.",
           "One result we can state: a consulting firm we work with cut about 14 hours off each bid, from 24 hours down to 10."),
)
KNOWN = rules.Known(emails=frozenset({"sam@acme.com", "lee@other.com"}), domains=frozenset({"acme.com", "other.com"}))
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=timezone.utc)

GOOD = (
    "Hi Sam,\n\nThanks for getting back to me. We'd love to show you how it works on your next three bids, free. "
    "It's a quick call.\n\nHere's a link to pick a time:\n" + BOOKING_LINK + "\n\n"
    "You can also just reply with a day that suits you.\n\nHeinrich"
)
SOFT = "Hi Sam,\n\nNo problem at all, and thanks for letting us know. The door's open whenever it suits you, so just say the word.\n\nHeinrich"


def auth_headers(frm: str, result: str = "pass") -> tuple:
    """The header our own mail server (Purelymail) adds to every inbound message."""
    domain = frm.split("@")[-1]
    value = (f"purelymail.com; spf={result} (domain of {domain} designates 1.2.3.4 as permitted sender) smtp.mailfrom={domain}; "
             f"dkim={result} header.i={domain}; dmarc={result} (p=none) header.from={frm}")
    return (("authentication-results", value),)


def mail(body="Sure, tell me more", frm="sam@acme.com", name="Sam Lee", to=BOX, subject="Re: quick hello", mid="<m1@x>",
         verified=True, **kw):
    """A reply from a verified sender unless told otherwise (verified=False drops the authentication header)."""
    headers = kw.pop("headers", None)
    if headers is None:
        headers = auth_headers(frm) if verified else ()
    base = dict(uid="1", message_id=mid, in_reply_to="<ours@x>", references=("<ours@x>",), from_addr=frm, from_name=name,
                to_addrs=(to,), subject=subject, body=body, headers=headers, received_at="2026-10-17T08:00:00+00:00")
    base.update(kw)
    return InboundMail(**base)


def classifier_says(category, confidence=0.9):
    return json.dumps({"category": category, "confidence": confidence, "reason": "test"})


def routed_llm(category="interested", confidence=0.9, reply=GOOD):
    """Answers classification calls with JSON and drafting calls with `reply`."""
    def answer(system, prompt, model):
        return classifier_says(category, confidence) if system.startswith("You sort replies") else reply
    return FakeLLM(answer)


def make_agent(cfg=CFG, llm=None, sender=None, store=None, known=KNOWN):
    return Agent(cfg, store or Store(":memory:"), llm or routed_llm(), sender=sender, clock=lambda: NOW,
                 rng=random.Random(1), known=known)


def raw(body, **headers):
    msg = EmailMessage()
    base = {"From": "Sam Lee <Sam@Acme.com>", "To": BOX, "Subject": "Re: hello", "Message-ID": "<a1@x>",
            "Date": "Fri, 16 Oct 2026 10:00:00 +0200"}
    for k, v in {**base, **headers}.items():
        if v is not None:
            msg[k] = v
    msg.set_content(body)
    return msg.as_bytes()


class FakeSource:
    """Stands in for ImapSource: hands out (uid, raw) pairs and remembers what was marked done or quarantined."""

    def __init__(self, items):
        self.items = list(items)
        self.done: list[str] = []
        self.quarantined: list[str] = []

    def fetch_new(self, limit: int = 50, exclude=frozenset()):
        return [(u, r) for u, r in self.items if u not in self.done and u not in self.quarantined and u not in exclude][:limit]

    def mark_done(self, uid):
        self.done.append(uid)

    def quarantine(self, uid):
        self.quarantined.append(uid)


# --- a stand-in for the mail server ---------------------------------------------------------------
class Msg:
    def __init__(self, data: bytes, flags=()):
        self.raw, self.flags = data, set(flags)


class FakeImap:
    """Just enough of imaplib.IMAP4_SSL for the code under test. Anything that could lose mail raises."""
    last = None

    def __init__(self, host="", port=993, *, ssl_context=None, timeout=None):
        self.args = {"host": host, "port": port, "ssl_context": ssl_context, "timeout": timeout}
        self.messages: dict[str, Msg] = {}
        self.store_status = "OK"
        self.keeps_flags = True  # False imitates a server that says OK to a flag and then forgets it
        self.appended = []
        FakeImap.last = self

    def login(self, user, password):
        return "OK", [b"logged in"]

    def select(self, mailbox, readonly=False):
        return "OK", [b"1"]

    def uid(self, command, *args):
        command = command.lower()
        if command == "search":
            wanted_out = {a for a in args if a not in (None, "UNKEYWORD", "UNDELETED")}
            ids = [u for u, m in sorted(self.messages.items(), key=lambda kv: int(kv[0]))
                   if not (wanted_out & m.flags) and "\\Deleted" not in m.flags]
            return "OK", [" ".join(ids).encode()]
        if command == "fetch":
            uid, spec = args
            uid = uid.decode() if isinstance(uid, bytes) else uid
            msg = self.messages[uid]
            if "RFC822.SIZE" in spec:
                return "OK", [f"{uid} (UID {uid} RFC822.SIZE {len(msg.raw)})".encode()]
            if "HEADER" in spec:
                head = re.split(rb"\r?\n\r?\n", msg.raw, maxsplit=1)[0] + b"\r\n\r\n"
                return "OK", [(f"{uid} (UID {uid} BODY[HEADER] {{{len(head)}}}".encode(), head), b")"]
            return "OK", [(f"{uid} (UID {uid} BODY[] {{{len(msg.raw)}}}".encode(), msg.raw), b")"]
        if command == "store":
            uid, mode, flags = args
            uid = uid.decode() if isinstance(uid, bytes) else uid
            if self.store_status != "OK":
                return self.store_status, [b"denied"]
            if self.keeps_flags:
                self.messages[uid].flags |= set(flags.strip("()").split())
            return "OK", [b"done"]
        raise AssertionError(f"the agent must never call uid {command}")

    def expunge(self):
        raise AssertionError("the agent must never expunge")

    def copy(self, *a):
        raise AssertionError("the agent must never copy mail away")

    def append(self, *args):
        self.appended.append(args)
        return "OK", [b"appended"]

    def logout(self):
        return "BYE", [b""]


def connected(monkeypatch, messages):
    """An ImapSource wired to a FakeImap holding `messages`."""
    from reply_agent.mailbox import ImapSource
    monkeypatch.setattr(imaplib, "IMAP4_SSL", FakeImap)
    source = ImapSource("imap.example", "inbox@boschly.com", "pw")
    source.connect()
    FakeImap.last.messages = messages
    return source, FakeImap.last
