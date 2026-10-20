"""Turn raw email bytes into an InboundMail. No network, no state.

Anyone can email these mailboxes, so a hostile message must never stop the parser: every step has a size cap, nothing
here is slower than linear in the size of the message, and anything unreadable becomes a flagged placeholder that a
person is shown instead of an exception that blocks the queue.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from email.message import Message
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html import unescape

from .models import InboundMail
from .textnorm import one_line, strip_controls
from .trust import base_address, clean_address

KEPT_HEADERS = (
    "auto-submitted", "x-autoreply", "x-autorespond", "precedence", "x-auto-response-suppress",
    "list-unsubscribe", "x-failed-recipients", "delivered-to", "x-original-to", "return-path",
    "content-type", "reply-to", "authentication-results", "x-pm-original-to",
)
MAX_BODY = 6000
MAX_TEXT = 100_000      # any one text part is cut here before it is scanned
MAX_PAYLOAD = 130_000   # bytes of one text part that are ever decoded (a slow codec on a huge body would stall us)
MAX_HTML = 200_000
MAX_REFS = 20
MAX_HEADER_BYTES = 64_000   # a real header block is a few KB; one this big is an attack on the parser
MAX_BOUNDARIES = 2_000      # a real reply has a handful of MIME parts
UNREADABLE = "[This message could not be read automatically. Open it in the mailbox.]"
# The mailbox reader appends this to the headers of a message it did not download in full.
OVERSIZE_NOTE = "This message is too large to read automatically. Open it in the mailbox."
# Added when all that is left after cutting the quoted history is a greeting (or nothing): the answer may be under the quote.
QUOTED_NOTE = "[The rest of this message looked like quoted history and was left out. Open it in the mailbox if the answer seems to be missing.]"

# Lines that start the quoted history of a reply. "wrote" headers come with '>' quoting, so a bottom-posted answer under
# them can be recovered. "block" headers (Outlook, forwards) carry history with no marker, so nothing below them is trusted.
_WROTE_START = r"(?:on|am|le|el|op|em|den|il|w\s+dniu)"
# "wrote:" and its translations come right before the colon; in German, Dutch and Swedish the verb comes before the name.
_WROTE_TAIL = (r"(?:(?:wrote|geskryf|escreveu|scritto|a\s+\S?crit|escribi\S?|napisa\S?)\s*:"
               r"|(?:schrieb|schreef|skrev)\b[^\n]{0,200}:)")
_WROTE = re.compile(rf"^{_WROTE_START}\b.{{5,300}}?\b{_WROTE_TAIL}\s*$", re.I)
_WROTE_FIRST = re.compile(rf"^{_WROTE_START}\b.{{5,}}", re.I)
_WROTE_LAST = re.compile(rf".*\b{_WROTE_TAIL}\s*$", re.I)
_BLOCK_STARTS = (
    re.compile(r"^-{2,}\s*original message\s*-{2,}", re.I),
    re.compile(r"^-{2,}\s*forwarded message\s*-{2,}", re.I),
    re.compile(r"^from:\s.+", re.I),
    re.compile(r"^_{5,}\s*$"),
)
# Outlook in another language: "Von:", "Van:", "De:" ... followed by at least two more header-style lines ("Gesendet:", "An:", "Betreff:").
_FROM_OTHER = re.compile(r"^(?:von|van|de|da|fr.n|fra|od|absender|afsender|exp.diteur|remitente|lahettaja)\s*:\s*\S", re.I)
_HEADER_LABEL = re.compile(
    r"^(?:sent|date|datum|gesendet|verstuur|verzonden|envoy.+|enviado|fecha|data|skickat|sendt|to|cc|an|aan|a|para|till|til"
    r"|subject|betreff|onderwerp|objet|asunto|assunto|.mne|emne)\s*:", re.I)
_GREETING_ONLY = re.compile(r"^(?:hi|hello|hey|dear|greetings|howdy|good\s+(?:morning|afternoon|evening|day))\b[^.!?\n]{0,40}[,!:.]?\s*$", re.I)
_BLOCK_TAGS = frozenset({"p", "div", "br", "li", "tr", "td", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "table", "ul", "ol", "hr"})
_TAG_NAME = re.compile(r"/?\s*([a-zA-Z][a-zA-Z0-9]*)")
_BLANKS = re.compile(r"[ \t" + chr(0xA0) + r"]+")
# The text encodings real mail uses. A charset outside this list is read as UTF-8: some Python codecs take seconds on a large
# body (punycode), and others are not text encodings at all.
_SAFE_CHARSET = re.compile(
    r"^(?:utf[-_]?8(?:[-_]?sig)?|utf[-_]?16(?:[-_]?[bl]e)?|utf[-_]?32(?:[-_]?[bl]e)?|us[-_]?ascii|ascii|latin[-_]?1|iso[-_]?8859[-_]\d{1,2}"
    r"|l[1-9]|cp125\d|windows[-_]125\d|cp437|cp85\d|cp866|koi8[-_][ru]|mac[-_]?(?:roman|cyrillic)|gb2312|gbk|gb18030|big5(?:hkscs)?"
    r"|shift[-_]?jis|sjis|euc[-_]?(?:jp|kr|tw)|iso[-_]?2022[-_](?:jp|kr))$",
    re.I,
)
_QUOTE_OPEN, _QUOTE_CLOSE = chr(0xE000), chr(0xE001)  # private markers: a <blockquote> opens or closes here


def clean_msgid(value: str) -> str:
    match = re.search(r"<[^>]+>", value or "")
    return match.group(0) if match else (value or "").strip()


def _tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _starts_header_block(lines: list[str], i: int) -> bool:
    stripped = lines[i].strip()
    if any(p.match(stripped) for p in _BLOCK_STARTS):
        return True
    if _FROM_OTHER.match(stripped):
        return sum(1 for later in lines[i + 1:i + 7] if _HEADER_LABEL.match(later.strip())) >= 2
    return False


def strip_quoted(text: str) -> str:
    """Keep what the person just wrote, drop the history and any '>' quote lines."""
    return split_quoted(text)[0]


def split_quoted(text: str) -> tuple[str, bool]:
    """(what the person just wrote, whether some text typed below the quote was left out).

    Normally the new text is above the history. When nothing is above a Gmail-style "On ... wrote:" line, or only a
    greeting, the answer was typed underneath it, so the unquoted lines below it are kept instead, but only when the quote
    itself is marked with '>': a quote nobody marked could be our own earlier email, and merging that into the reply would
    put our own opt-out footer into the person's mouth.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    above: list[str] = []
    below: list[str] = []
    mode = ""  # "", "wrote" or "block"
    marked = False  # saw a '>' quote line under a "wrote" header
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
        stripped = line.strip()
        if not mode:
            if _WROTE.match(stripped):
                mode = "wrote"
                continue
            if _WROTE_FIRST.match(stripped) and i + 1 < len(lines) and _WROTE_LAST.match(lines[i + 1].strip()):
                mode, skip_next = "wrote", True  # the header wrapped onto a second line
                continue
            if _starts_header_block(lines, i):
                mode = "block"
                continue
        if stripped.startswith(">"):
            marked = marked or mode == "wrote"
            continue
        if mode == "block":
            continue
        (below if mode == "wrote" else above).append(line)
    top = _tidy("\n".join(above))
    bottom = _tidy("\n".join(below)) if mode == "wrote" else ""
    if bottom and marked and (not top or _GREETING_ONLY.match(top)):
        return (_tidy(f"{top}\n\n{bottom}") if top else bottom), False
    return top, bool(bottom)


def _html_to_text(markup: str) -> str:
    """Plain text from HTML in one pass. Hand-rolled because the usual regex and parser routes go quadratic on hostile input.

    Quoted history (<blockquote>) comes out with '>' in front of each line, like the plain-text version of the same reply.
    """
    markup = markup[:MAX_HTML]
    low = markup.lower()
    out: list[str] = []
    i, n = 0, len(markup)
    while i < n:
        lt = markup.find("<", i)
        if lt == -1:
            out.append(markup[i:])
            break
        out.append(markup[i:lt])
        gt = markup.find(">", lt + 1)
        if gt == -1:  # a '<' that never closes: nothing after it is a tag, and none of it is worth scanning again
            break
        inner = markup[lt + 1:gt]
        name_match = _TAG_NAME.match(inner[:40])
        name = name_match.group(1).lower() if name_match else ""
        if inner.startswith("!--"):
            end = low.find("-->", lt + 4)
            if end == -1:
                break
            i = end + 3
            continue
        if name in ("script", "style") and not inner.startswith("/"):
            end = low.find(f"</{name}", gt)
            if end == -1:
                break
            close = markup.find(">", end)
            i = n if close == -1 else close + 1
            continue
        if name == "blockquote":
            out.append(f"\n{_QUOTE_CLOSE if inner.startswith('/') else _QUOTE_OPEN}\n")
        elif name in _BLOCK_TAGS:
            out.append("\n")
        i = gt + 1
    text = unescape("".join(out))
    depth, pieces = 0, []
    for part in re.split(f"([{_QUOTE_OPEN}{_QUOTE_CLOSE}])", text):
        if part == _QUOTE_OPEN:
            depth += 1
        elif part == _QUOTE_CLOSE:
            depth = max(0, depth - 1)
        else:
            pieces.append("\n".join(f"> {line}" if depth and line.strip() else line for line in part.split("\n")))
    return _BLANKS.sub(" ", "".join(pieces)).strip()


def _part_text(part: Message) -> str:
    """The text of one part, decoded from at most MAX_PAYLOAD bytes. Only ordinary text encodings are used; anything else
    (some codecs are slow on a large body, others are not text at all) is read as UTF-8."""
    payload = (part.get_payload(decode=True) or b"")[:MAX_PAYLOAD]
    charset = part.get_content_charset() or "utf-8"
    if not _SAFE_CHARSET.match(charset):
        charset = "utf-8"
    try:
        text = payload.decode(charset, "replace")
    except (LookupError, ValueError):
        text = payload.decode("utf-8", "replace")
    return text[:MAX_TEXT]


def _body_text(msg: Message) -> str:
    plain = msg.get_body(preferencelist=("plain",))
    if plain is not None:
        return _part_text(plain)
    html_part = msg.get_body(preferencelist=("html",))
    return _html_to_text(_part_text(html_part)) if html_part is not None else ""


def _received(msg: Message) -> str:
    now = datetime.now(timezone.utc)
    try:
        when = parsedate_to_datetime(str(msg.get("Date", "")))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when = when.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return now.isoformat(timespec="seconds")
    return min(when, now + timedelta(days=1)).isoformat(timespec="seconds")


def _failed_recipients(msg: Message) -> tuple[str, ...]:
    """The addresses a delivery failure notice says did not get our mail. A delay or a delivery notice names nobody."""
    from_header = [a for _, a in getaddresses([str(msg.get("X-Failed-Recipients", ""))]) if a]
    found: list[str] = []
    has_report = False  # when the notice carries its own status report, that report decides; the header is only a fallback
    try:
        for part in msg.walk():
            if part.get_content_type() != "message/delivery-status":
                continue
            has_report = True
            blocks = part.get_payload()
            for block in blocks if isinstance(blocks, list) else []:
                action = str(block.get("Action", "")).strip().lower()
                if action and action != "failed":
                    continue
                value = str(block.get("Final-Recipient", "") or block.get("Original-Recipient", ""))
                found.append(value.split(";", 1)[-1].strip())
    except Exception:  # noqa: BLE001  a malformed report must not cost us the rest of the message
        pass
    named = found if has_report else from_header
    return tuple(dict.fromkeys(base_address(clean_address(a)) for a in named if clean_address(a)))


def _synthetic_id(raw: bytes) -> str:
    # A message with no Message-ID still needs a stable key, or it would be handled again on every pass.
    return f"<noid-{hashlib.sha1(raw).hexdigest()[:20]}@reply-agent>"


def _addresses(*values: str) -> tuple[str, ...]:
    try:
        return tuple(dict.fromkeys(a for a in (clean_address(addr) for _, addr in getaddresses(list(values))) if a))
    except Exception:  # noqa: BLE001  deeply nested comments and the like: no usable addresses
        return ()


def _safe_parseaddr(value: str) -> tuple[str, str]:
    try:
        return parseaddr(value)
    except Exception:  # noqa: BLE001  a From line built to defeat the address parser: no usable sender
        return "", ""


def _raw_header_values(msg: Message, name: str) -> list[str]:
    """Every value of a header exactly as it arrived: encoded words are NOT decoded, folded lines are joined.

    Used for the server's verdict. Mail software decodes encoded words into whatever characters they stand for, which would
    let text a sender chose change the structure of a header our own server wrote.
    """
    wanted = name.lower()
    return [re.sub(r"\r?\n[ \t]+", " ", str(value)).strip() for key, value in msg.raw_items() if key.lower() == wanted][:20]


def _who_wrote(values: list[str]) -> str:
    """The server name at the start of each Authentication-Results header, in order. More than one that claims to be ours
    means someone else wrote one of them."""
    found = []
    for value in values:
        first = value.split(";", 1)[0].split()
        found.append(first[0].lower() if first else "")
    return " ".join(found)


def _build(raw: bytes, uid: str, msg: Message) -> InboundMail:
    name, addr = parseaddr(str(msg.get("From", "")))
    raw_verdicts = _raw_header_values(msg, "authentication-results")
    headers = tuple((h, raw_verdicts[0] if h == "authentication-results" and raw_verdicts else str(msg[h]).strip())
                    for h in KEPT_HEADERS if msg[h] is not None)
    senders = _who_wrote(raw_verdicts)
    if senders.strip():
        headers += (("authentication-results-ids", senders),)
    full = _body_text(msg)
    text, dropped = split_quoted(full)
    if dropped or (len(full.strip()) > len(text) + 40 and (not text or _GREETING_ONLY.match(text))):
        text = f"{text}\n\n{QUOTED_NOTE}" if text else QUOTED_NOTE  # the answer may sit under a quote we could not tell apart
    return InboundMail(
        uid=str(uid),
        message_id=clean_msgid(str(msg.get("Message-ID", ""))) or _synthetic_id(raw),
        in_reply_to=clean_msgid(str(msg.get("In-Reply-To", ""))),
        references=tuple(re.findall(r"<[^>]+>", str(msg.get("References", ""))))[-MAX_REFS:],
        from_addr=clean_address(addr),
        from_name=one_line(name)[:120],
        to_addrs=_addresses(*(str(msg.get(h, "")) for h in ("To", "Cc"))),
        subject=one_line(str(msg.get("Subject", "")))[:300],
        body=strip_controls(text)[:MAX_BODY],
        headers=tuple((k, strip_controls(v)[:2000]) for k, v in headers),
        received_at=_received(msg),
        flags=("oversized",) if OVERSIZE_NOTE in text else (),
        failed_recipients=_failed_recipients(msg),
    )


def _salvage(raw: bytes, uid: str) -> InboundMail:
    """What the headers alone say, for a message the parser could not handle. A person is shown it instead of it blocking the queue."""
    head = re.split(r"\r?\n\r?\n", raw[:20000].decode("utf-8", "replace"), maxsplit=1)[0]
    head = re.sub(r"\r?\n[ \t]+", " ", head)

    def field(name: str) -> str:
        found = re.search(rf"(?im)^{name}:[ \t]*(.*)$", head)
        return found.group(1).strip() if found else ""

    try:
        subject = str(make_header(decode_header(field("Subject"))))
    except Exception:  # noqa: BLE001
        subject = field("Subject")
    name, addr = _safe_parseaddr(field("From"))
    return InboundMail(
        uid=str(uid),
        message_id=clean_msgid(field("Message-ID")) or _synthetic_id(raw),
        in_reply_to=clean_msgid(field("In-Reply-To")),
        references=tuple(re.findall(r"<[^>]+>", field("References")))[-MAX_REFS:],
        from_addr=clean_address(addr),
        from_name=one_line(name)[:120],
        to_addrs=_addresses(field("To"), field("Cc")),
        subject=one_line(subject)[:300],
        body=UNREADABLE,
        headers=(),
        received_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        flags=("unreadable",),
    )


def _too_heavy(raw: bytes) -> bool:
    """A header block or a part count no ordinary reply has. Refused before the slow, structured parser ever sees it."""
    ends = [i for i in (raw.find(b"\r\n\r\n"), raw.find(b"\n\n")) if i != -1]
    return (min(ends) if ends else len(raw)) > MAX_HEADER_BYTES or raw.count(b"\n--") > MAX_BOUNDARIES


def parse(raw: bytes, uid: str = "") -> InboundMail:
    if _too_heavy(raw):
        return _salvage(raw, uid)
    try:
        return _build(raw, uid, message_from_bytes(raw, policy=policy.default))
    except Exception:  # noqa: BLE001  RecursionError, LookupError and friends: keep the headers, flag the rest
        return _salvage(raw, uid)
