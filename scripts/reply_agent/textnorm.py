"""Make text safe to match and safe to print. Pure functions, no state.

Mail is typed by phones, word processors and attackers. A pattern written for plain ASCII has to see what a person sees,
and nothing that came from outside may reach a terminal or an outgoing subject line unwashed.

Every special character below is written as a number, so this file holds only plain ASCII and nothing invisible can hide in it.
"""
from __future__ import annotations

import html
import re
import unicodedata


def _char_class(ranges) -> str:
    """A regex character class from (first, last) code point pairs."""
    return "[" + "".join(re.escape(chr(a)) + (("-" + re.escape(chr(b))) if b != a else "") for a, b in ranges) + "]"


# Curly and prime-like quotes become straight ones.
_QUOTES = {**{cp: "'" for cp in (0x2018, 0x2019, 0x201A, 0x201B, 0x02BC, 0x2032, 0x00B4, 0x0060)},
           **{cp: '"' for cp in (0x201C, 0x201D, 0x201E, 0x2033)}}
# Every kind of dash and minus becomes a plain hyphen, so "opt<non-breaking hyphen>out" still reads as "opt-out".
_DASHES = {cp: "-" for cp in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212, 0xFE58, 0xFE63, 0xFF0D)}
# Characters that draw nothing: soft hyphen, joiners, zero-width and bidirectional marks, fillers, variation selectors, tag characters.
_INVISIBLE = re.compile(_char_class((
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180E), (0x200B, 0x200F),
    (0x202A, 0x202E), (0x2060, 0x206F), (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0),
    (0xE0000, 0xE0FFF),
)))
# C0 controls except tab and newline, DEL, C1 controls, and the bidirectional overrides that can reorder printed text.
_CONTROLS = re.compile(_char_class((
    (0x00, 0x08), (0x0B, 0x1F), (0x7F, 0x9F), (0x200E, 0x200F), (0x202A, 0x202E), (0x2066, 0x2069),
)))
# Plain punctuation a typist or a phone may produce: curly quotes, ellipsis, no-break space. Dashes have a message of their own.
_PLAIN_PUNCTUATION = frozenset(chr(cp) for cp in (0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x00A0, 0x2014, 0x2013))

SCHEME = re.compile(r"\b(?:[a-z][a-z0-9+.-]{1,15}://|(?:mailto|tel|sms|javascript|data|file):)", re.I)
# Any "word.word" with a letters-only ending counts as a web address: a list of known endings is always out of date.
LINK = re.compile(
    r"(?:https?://|ftp://|www\.)\S+|\b(?:[a-z0-9][a-z0-9-]*\.)+[a-z]{2,24}\b(?:/\S*)?|\b\d{1,3}(?:\.\d{1,3}){3}\b",
    re.I,
)
# A domain spelled out to dodge the pattern above: "evil dot com", "evil (dot) com", "evil . com", "bit ly slash abc".
SPELLED_LINK = re.compile(
    r"\b[a-z0-9-]{2,}\s*(?:[(\[{]\s*dot\s*[)\]}]|\bdot\b)\s*[a-z]{2,24}\b|\b[a-z0-9-]{2,}\s+\.\s+[a-z]{2,24}\b"
    r"|\b[a-z0-9-]{2,}\s+(?:dot|slash)\s+[a-z0-9-]{2,}\b|\b[a-z0-9-]{2,}\s+\.[a-z]{2,24}\b",
    re.I,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONEISH = re.compile(r"\+?\d[\d\s().\-/]{5,}\d")
_DATEISH = re.compile(r"^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$")
_DIGIT_WORD = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine)"
_SPOKEN_PHONE = re.compile(rf"\b(?:{_DIGIT_WORD}[\s,.\-]+){{6,}}{_DIGIT_WORD}\b", re.I)
_REPLY_PREFIX = re.compile(r"^\s*(?:(?:re|fw|fwd|aw|sv)\s*:\s*)+", re.I)


def normalise(text: str) -> str:
    """Fold typography, markup and invisible characters, and collapse whitespace, so patterns see what a reader sees."""
    text = html.unescape(text or "")
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).translate(_DASHES)
    text = _INVISIBLE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_controls(text: str) -> str:
    """Remove terminal escape characters and text-direction tricks. Line breaks and tabs stay."""
    return _CONTROLS.sub("", text or "")


def one_line(text: str) -> str:
    """Control characters out and every run of whitespace, line breaks included, turned into one space.

    For a field that is printed on one line (a subject, a name): a line break in it could otherwise start a fake entry.
    """
    return " ".join(strip_controls(text).split())


# Letters that do not come apart into a base letter and an accent, and the plain letters they stand in for.
_FOLD_LETTERS = {
    0x00DF: "ss", 0x00E6: "ae", 0x00C6: "AE", 0x0153: "oe", 0x0152: "OE", 0x00F8: "o", 0x00D8: "O", 0x0111: "d", 0x0110: "D",
    0x00F0: "d", 0x00D0: "D", 0x00FE: "th", 0x00DE: "Th", 0x0142: "l", 0x0141: "L", 0x0127: "h", 0x0126: "H", 0x0131: "i",
    0x0167: "t", 0x0166: "T", 0x014B: "n", 0x014A: "N", 0x0138: "k", 0x0192: "f",
}


def ascii_fold(text: str) -> str:
    """Accented and look-alike Latin letters as the plain letters they imitate, so "guarant<e acute>e" is read as "guarantee".

    The draft checks are written for plain letters. A name may keep its accent in the draft itself; only the copy the
    patterns look at is folded.
    """
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).translate(_FOLD_LETTERS)


def has_odd_characters(text: str) -> bool:
    """True when text holds anything but plain letters, digits and punctuation: hidden characters, other alphabets, emoji.

    Accented Latin letters are fine (a name can have one). A draft written in Heinrich's voice has no reason for the rest,
    and the rest is how a web address is hidden from a pattern or a long text is padded past the length check.
    """
    for ch in unicodedata.normalize("NFC", text or ""):
        if ch.isascii():
            if ch.isprintable() or ch in "\n\t\r":
                continue
            return True
        if ch in _PLAIN_PUNCTUATION or (0x00C0 <= ord(ch) <= 0x024F and ch.isalpha()):
            continue
        return True
    return False


def has_phone(text: str) -> bool:
    """Seven or more digits with only phone-style punctuation between them, or seven digits spoken as words. Dates do not count."""
    for match in _PHONEISH.finditer(text):
        found = match.group(0).strip()
        if sum(ch.isdigit() for ch in found) >= 7 and not _DATEISH.match(found):
            return True
    return bool(_SPOKEN_PHONE.search(text))


def plain_subject(subject: str, limit: int = 70) -> str:
    """A subject safe to send back: no links, addresses, numbers or control characters, and short."""
    text = normalise(strip_controls(subject))
    text = _REPLY_PREFIX.sub("", text)
    text = EMAIL.sub(" ", text)
    text = LINK.sub(" ", text)
    text = _PHONEISH.sub(lambda m: " " if has_phone(m.group(0)) else m.group(0), text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")
    if len(text) > limit:
        cut = text[:limit]
        text = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return text.strip(" ,;:-") or "your message"
