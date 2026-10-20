"""The only code that touches the network for mail. Thin on purpose, everything else is tested without it."""
from __future__ import annotations

import imaplib
import re
import smtplib
import time
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from .config import Config
from .mailparse import OVERSIZE_NOTE
from .textnorm import plain_subject
from .tls import verifying_context
from .validate import subject_is_safe

DONE_FLAG = "ReplyAgentDone"      # set on a message once its outcome is safely saved
FAILED_FLAG = "ReplyAgentFailed"  # set (with DONE_FLAG) on a message we gave up on
SYNTHETIC_ID = re.compile(r"^<noid-[0-9a-f]+@reply-agent>$")
MAX_REFERENCES = 20


class Sender(Protocol):
    def send(self, msg: EmailMessage) -> None: ...


class SendUncertain(Exception):
    """The connection broke while a message was going out, so it may or may not have been delivered."""


# Errors that mean the server said no (or never got as far as our message): the mail certainly did not go.
_DEFINITE_FAILURES = (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError,
                      smtplib.SMTPHeloError, smtplib.SMTPNotSupportedError)


def build_reply(*, mailbox: str, to_addr: str, to_name: str, subject: str, their_id: str,
                their_refs: tuple[str, ...], body: str, cfg: Config) -> EmailMessage:
    """A threaded plain-text reply, sent as the campaign mailbox the person wrote to.

    The subject is washed (no links, numbers or addresses from the sender), a made-up Message-ID is never used as a
    thread reference, and an enormous References chain is cut down.
    """
    if mailbox.lower() not in {m.lower() for m in cfg.campaign_mailboxes}:
        raise ValueError(f"{mailbox!r} is not one of our campaign mailboxes, refusing to send as it")
    msg = EmailMessage()
    msg["From"] = f"{cfg.full_name} <{mailbox}>"
    msg["To"] = f"{to_name} <{to_addr}>" if to_name and re.fullmatch(r"[\w .'-]{1,60}", to_name) else to_addr
    # The subject is the sender's own words. Echo it only when it is plainly harmless; otherwise a neutral one.
    msg["Subject"] = f"Re: {plain_subject(subject if subject_is_safe(subject) else '')}"
    if their_id and not SYNTHETIC_ID.match(their_id):
        refs = [r for r in their_refs if not SYNTHETIC_ID.match(r)][-(MAX_REFERENCES - 1):]
        msg["In-Reply-To"] = their_id
        msg["References"] = " ".join((*refs, their_id))
    msg["Message-ID"] = make_msgid(domain=mailbox.split("@")[-1])
    msg["Date"] = formatdate(localtime=False)
    msg.set_content(body)
    return msg


class DryRunSender:
    """Records what would have been sent. Used for demos, tests and any run without --live."""

    def __init__(self):
        self.sent: list[EmailMessage] = []

    def send(self, msg: EmailMessage) -> None:
        self.sent.append(msg)


class SmtpSender:
    def __init__(self, host: str, user: str, password: str, port: int = 465):
        self.host, self.user, self.password, self.port = host, user, password, port

    def send(self, msg: EmailMessage) -> None:
        accepted = False
        try:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=60, context=verifying_context()) as smtp:
                smtp.login(self.user, self.password)  # a failure up to here means nothing was sent
                try:
                    smtp.send_message(msg)
                except _DEFINITE_FAILURES:
                    raise
                except (OSError, smtplib.SMTPException) as exc:  # a timeout or a dropped connection: the server may have taken it
                    raise SendUncertain(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
                accepted = True
        except SendUncertain:
            raise
        except Exception:
            if not accepted:
                raise
            # The server took the message. An error while saying goodbye (a QUIT it did not answer with 221) changes nothing,
            # and must not make a delivered reply look unsent: a retry would send it twice.


class FilingSender:
    """Sends over SMTP, then files a copy in the tracking mailbox's Sent folder. A filing failure never undoes a send."""

    def __init__(self, smtp: Sender, imap: "ImapSource"):
        self.smtp, self.imap = smtp, imap

    def send(self, msg: EmailMessage) -> None:
        self.smtp.send(msg)
        try:
            self.imap.append_sent(msg.as_bytes())
        except Exception:  # noqa: BLE001
            pass


class ImapSource:
    """Reads the tracking mailbox.

    Mail is never moved or deleted: once handled it gets a flag and stays in the Inbox, so it can still be read there like
    any mailbox. A message a person has flagged for deletion is left alone, and nothing here ever calls EXPUNGE.
    """

    max_size = 1_000_000  # bytes; anything bigger is read by its headers only

    def __init__(self, host: str, user: str, password: str, folder: str = "INBOX"):
        self.host, self.user, self.password, self.folder = host, user, password, folder
        self._conn: imaplib.IMAP4_SSL | None = None
        self._stuck: set[str] = set()  # handled, but the flag could not be set: skip so they cannot hide newer mail

    def connect(self) -> None:
        conn = imaplib.IMAP4_SSL(self.host, 993, ssl_context=verifying_context(), timeout=60)
        conn.login(self.user, self.password)
        self._conn = conn

    def _need(self) -> imaplib.IMAP4_SSL:
        if self._conn is None:
            self.connect()
        assert self._conn is not None
        return self._conn

    def _size(self, conn, uid: str) -> int:
        status, data = conn.uid("fetch", uid, "(RFC822.SIZE)")
        found = re.search(rb"RFC822\.SIZE (\d+)", b" ".join(x for x in (data or []) if isinstance(x, bytes)))
        return int(found.group(1)) if status == "OK" and found else 0

    def _body(self, conn, uid: str, what: str) -> bytes | None:
        status, msg = conn.uid("fetch", uid, f"(BODY.PEEK[{what}])")
        if status == "OK" and msg and isinstance(msg[0], tuple):
            return msg[0][1]
        return None

    def fetch_new(self, limit: int = 50, exclude=frozenset()) -> list[tuple[str, bytes]]:
        """The oldest unhandled messages, up to `limit`. Messages in `exclude` (already seen in this pass) are passed over."""
        conn = self._need()
        conn.select(f'"{self.folder}"')
        status, data = conn.uid("search", None, "UNKEYWORD", DONE_FLAG, "UNDELETED")
        uids = [u.decode() for u in (data[0].split() if status == "OK" and data and data[0] else [])]
        out: list[tuple[str, bytes]] = []
        for uid in uids:
            if uid in self._stuck or uid in exclude:
                continue
            if len(out) >= limit:
                break
            if self._size(conn, uid) > self.max_size:
                head = self._body(conn, uid, "HEADER")
                if head is not None:
                    out.append((uid, head.rstrip(b"\r\n") + b"\r\n\r\n" + OVERSIZE_NOTE.encode() + b"\r\n"))
                continue
            data_bytes = self._body(conn, uid, "")
            if data_bytes is not None:
                out.append((uid, data_bytes))
        return out

    def _flag(self, uid: str, *flags: str) -> None:
        conn = self._need()
        status, detail = conn.uid("store", uid, "+FLAGS", "(" + " ".join(flags) + ")")
        if status != "OK":
            self._stuck.add(uid)
            raise RuntimeError(f"could not mark message {uid} as handled: {status} {detail}")

    def mark_done(self, uid: str) -> None:
        self._flag(uid, DONE_FLAG)

    def quarantine(self, uid: str) -> None:
        """Give up on a message that keeps failing: flag it so it is never fetched again. A person can still read it."""
        self._flag(uid, DONE_FLAG, FAILED_FLAG)

    def append_sent(self, raw: bytes) -> None:
        conn = self._need()
        conn.append("Sent", "(\\Seen)", imaplib.Time2Internaldate(time.time()), raw)

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.logout()
            finally:
                self._conn = None
