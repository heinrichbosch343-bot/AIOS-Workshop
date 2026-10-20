"""Who really sent this? The From line is typed by the sender, so it proves nothing on its own.

Our own mail server (Purelymail) checks every inbound message and records the result in an Authentication-Results header it
adds at the top. We believe only that header: the topmost one, from our own server, with exactly one DMARC result, a pass,
for exactly the domain in the From line. Everything else in that header is text a sender may have influenced (the envelope
sender is echoed into it, and a first line starting with a space is read as a continuation of it), so comments and quoted
values are thrown away first and anything that is not unambiguous counts as "not verified".
"""
from __future__ import annotations

import re

from .models import InboundMail

DEFAULT_AUTH_HOST = "purelymail.com"
MAX_HEADER_TEXT = 4000

# A plain address: ASCII only, one @, a dotted domain. Anything fancier (quoted names, comments, look-alike letters, control
# characters) is not worth trusting with a list or a screen, so it counts as no address at all.
_ADDRESS = re.compile(r"^[a-z0-9][a-z0-9._%+'=-]{0,63}@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,23}$")


def clean_address(raw: str) -> str:
    """The address in lower case, or "" when it is not a plain ASCII address. Checked before lower-casing, because lower()
    turns some look-alike letters (the Kelvin sign, for one) into ordinary ones."""
    value = (raw or "").strip()
    if not value.isascii():
        return ""
    value = value.lower()
    return value if len(value) <= 254 and _ADDRESS.match(value) else ""


def base_address(addr: str) -> str:
    """alice+promo@Example.com -> alice@example.com, so a plus tag cannot dodge a list."""
    local, at, domain = (addr or "").strip().lower().partition("@")
    return f"{local.split('+', 1)[0]}@{domain}" if at else (addr or "").strip().lower()


def _domain(addr_or_domain: str) -> str:
    return addr_or_domain.strip("<>\" ").lower().rsplit("@", 1)[-1]


def _without_comments_and_quotes(value: str) -> str | None:
    """Drop (comments) and "quoted values". Text inside them is not a result, whatever it says.

    None when the header is not well formed: a comment or quote that never closes, a stray ")", or a quote inside a comment.
    A server never writes any of those, so they mean somebody else's text got into the header.
    """
    out: list[str] = []
    depth, quoted, skip = 0, False, False
    for ch in value:
        if skip:
            skip = False
            continue
        if ch == "\\" and (quoted or depth):
            skip = True
            continue
        if quoted:
            quoted = ch != '"'
            continue
        if depth:
            if ch == '"':
                return None
            depth += (ch == "(") - (ch == ")")
            continue
        if ch == '"':
            quoted = True
            out.append('""')
        elif ch == "(":
            depth = 1
        elif ch == ")":
            return None
        else:
            out.append(ch)
    return None if (quoted or depth or skip) else "".join(out)


def authenticated(mail: InboundMail, auth_host: str = DEFAULT_AUTH_HOST) -> bool:
    """True only when our own server reports exactly one DMARC result, a pass, for the domain in the From line."""
    value = mail.header("authentication-results")[:MAX_HEADER_TEXT]
    if not value:
        return False
    if "=?" in value:
        return False  # an encoded word is decoded by mail software into whatever the sender chose; the server never writes one here
    lowered = value.lower()
    if lowered.count("dmarc=") != 1 or lowered.count("header.from=") != 1:
        return False  # counted in the raw text, comments and quotes included: a result hidden in a comment still counts against it
    senders = mail.header("authentication-results-ids").split()  # who wrote each such header in the message, set by the parser
    if senders and senders.count(auth_host.lower()) != 1:
        return False  # a second header claiming to be ours means one of them is not
    plain = _without_comments_and_quotes(value)
    if plain is None:
        return False
    head, _, results = plain.partition(";")
    ident = head.split()[0].lower() if head.split() else ""
    if ident != auth_host.lower():
        return False
    tokens = [t.lower() for t in re.split(r"[;\s]+", results) if t]
    dmarc = [t for t in tokens if t.startswith("dmarc=")]
    claimed = [t for t in tokens if t.startswith("header.from=")]
    if dmarc != ["dmarc=pass"] or len(claimed) != 1:
        return False
    ours = _domain(mail.from_addr)
    return bool(ours) and _domain(claimed[0].split("=", 1)[1]) == ours
