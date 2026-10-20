"""Plain data types. Frozen: nothing is changed after it is made, a new copy is made instead."""
from __future__ import annotations

from dataclasses import dataclass

# What the model may choose between. Everything else comes from the code-side rules.
MODEL_CATEGORIES = ("interested", "question", "referral", "soft_no", "not_interested", "other")

# Decided by rules before any model is called.
RULE_CATEGORIES = ("unsubscribe", "complaint", "out_of_office", "auto_reply", "bounce", "ignore", "unknown_sender")

ALL_CATEGORIES = MODEL_CATEGORIES + RULE_CATEGORIES

# The only categories that get a written answer. All other mail is logged and left alone.
DRAFT_CATEGORIES = frozenset({"interested", "question", "referral", "soft_no"})

# People who must never be written to again once we see one of these.
SUPPRESS_CATEGORIES = frozenset({"unsubscribe", "not_interested", "bounce", "complaint"})

MODES = ("off", "review", "auto")


@dataclass(frozen=True)
class InboundMail:
    uid: str
    message_id: str
    in_reply_to: str
    references: tuple[str, ...]
    from_addr: str
    from_name: str
    to_addrs: tuple[str, ...]
    subject: str
    body: str  # the new text only, quoted history cut off
    headers: tuple[tuple[str, str], ...]  # selected headers, lower-case names, first occurrence of each
    received_at: str  # ISO 8601
    flags: tuple[str, ...] = ()  # "unreadable" when the message could not be parsed, "oversized" when only its headers were read
    failed_recipients: tuple[str, ...] = ()  # on a delivery failure notice: the addresses that did not get our mail

    def header(self, name: str) -> str:
        wanted = name.lower()
        return next((v for k, v in self.headers if k == wanted), "")


@dataclass(frozen=True)
class Decision:
    category: str
    confidence: float
    reason: str
    source: str  # "rule" or "model"
    mailbox: str  # which of our campaign mailboxes the person wrote to ("" if unknown)


@dataclass(frozen=True)
class Draft:
    body: str
    problems: tuple[str, ...]  # what the checks still object to; empty means clean

    @property
    def clean(self) -> bool:
        return bool(self.body) and not self.problems
