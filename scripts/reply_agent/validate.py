"""Checks every draft must pass before a person sees it as clean. Code, not the model, has the last word.

The draft is attacker-influenced (the model read a stranger's email to write it), so these checks never trust its shape:
an over-long text is refused before any pattern runs, hidden or look-alike characters fail it outright, and every number in
it has to come from somewhere approved.
"""
from __future__ import annotations

import re

from . import textnorm
from .config import Config

MAX_DRAFT_CHARS = 1600  # a reply of the allowed length is well under this; longer is never worth scanning
EM_DASH, EN_DASH = chr(0x2014), chr(0x2013)

_NUMBER_WORD = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty|sixty|seventy"
                r"|eighty|ninety|hundred|thousand|million|grand|dozen)")
_CURRENCY_WORD = r"(?:usd|eur|gbp|zar|cad|aud|rand|dollars?|euros?|pounds?|bucks|cents?)"
_PRICE_WORD = r"(?:fees?|prices?|pricing|costs?|charges?|rates?|retainer|subscription|invoice|licen[cs]e)"
_CURRENCY_SYMBOL = "[$" + chr(0x20AC) + chr(0xA3) + "]"
_PRICE = re.compile(
    rf"{_CURRENCY_SYMBOL}\s?\d"                                      # $99
    r"|(?-i:\bR)\s?\d"                                                # R7,500 (rand, capital R only)
    r"|\b(?:usd|eur|gbp|zar|cad|aud)\s?\d"                            # USD 500
    rf"|\b\d[\d,.]*\s?[km]?\s?{_CURRENCY_WORD}\b"                    # 500 dollars, 99 bucks
    rf"|\b{_NUMBER_WORD}\b.{{0,15}}?\b{_CURRENCY_WORD}\b"            # fifty dollars, five bucks, two hundred rand
    rf"|\b{_PRICE_WORD}\b[^.\n]{{0,25}}(?:\d|\b{_NUMBER_WORD}\b)"    # a flat fee of 99, we charge by the bid, ninety nine
    rf"|(?:\d|\b{_NUMBER_WORD}\b)[^.\n]{{0,25}}\b{_PRICE_WORD}\b"    # 1 500 for the setup fee
    r"|\b(?:starts?|starting)\s+(?:at|from)\s+\d[\d ,]{2,}"           # it starts at 1 500
    r"|\b(?:hundred|thousand|million|grand)\s+(?:a|per)\s+(?:month|year|week|bid|seat|user)\b"   # five hundred a month, two grand a year
    r"|\b\d[\d,]{2,}\s+(?:a|per)\s+(?:month|year|week)\b"             # 500 a month, 1,500 per year
    r"|\bpricing is\b|/\s?month\b",
    re.I,
)
# A figure or a promise nothing approves. The facts allow "next three bids" and one unnamed 24 hours to 10 hours result, nothing more.
_CLAIM = re.compile(
    r"\d+(?:\.\d+)?[\s-]?(?:%|per[\s-]?cent)|\b\d+[\s-]?x\b|\b(?:" + _NUMBER_WORD + r")[\s-]*per[\s-]?cent"
    r"|\b(?:promis\w*|guarantee\w*|assure\w*|certain\s+to|confident\s+(?:you|that|it)|no[\s-]risk|risk[\s-]free|money[\s-]back|refund\w*"
    r"|free\s+forever|forever\s+free|lifetime|discount\w*|we\s+(?:will\s+)?ensure|will\s+(?:definitely|certainly|surely|absolutely))\b"
    r"|\bwill\s+(?:double|triple|halve|win|save|cut|reduce|go\s+from)\b|\b(?:double|triple|quadruple|halve|halves|halved)\s+(?:your|the|their|bid|it|that)\b"
    r"|\byou(?:'ll|\s+will)\s+(?:save|win|get|go\s+from|cut|see|double|triple|halve|reduce|gain|close|land)\b"
    r"|\b(?:in|by)\s+half\b|\b(?:a|one)\s+third\b(?!\s+(?:party|parties|person|bid|time|option|one))|\btwo\s+thirds\b"
    r"|\b(?:twice|thrice)\s+as\b|\b\w+\s+times\s+(?:faster|more|less|quicker|better|as)\b"
    r"|\b(?:cuts?|reduces?|slashes|shortens?)\s+(?:your|the|bid)\b"
    r"|\b(?:firms|companies|clients|customers|teams|businesses)\s+(?:we\s+(?:work|have\s+worked)\s+with|like\s+(?:yours|you))\s+(?:have|are|get|see|save|win|cut)\b",
    re.I,
)
_SENSITIVE = re.compile(
    r"\b(?:pass[\s-]?word|pass[\s-]?code|pin\s+code|log\s?-?in\b|sign\s?-?in\b|credentials?|bank\s+(?:details|account)|account\s+(?:number|details)|"
    r"credit\s+card|card\s+(?:number|details)|iban|swift\s+code|routing\s+number|social\s+security|ssn|verify\s+your|"
    r"confirm\s+your\s+(?:identity|account|details|bank|password)|gift\s+card|bitcoin|crypto|wire\s+transfer|one[- ]time\s+code)\b",
    re.I,
)
_OBFUSCATED_EMAIL = re.compile(
    r"\b[\w.+-]+\s*[(\[{]\s*at\s*[)\]}]\s*[\w-]+(?:\s*[(\[{]?\s*dot\s*[)\]}]?\s*[\w-]+)+|\b[\w.+-]+\s+at\s+[\w-]+\s+dot\s+\w+",
    re.I,
)

# "We write your bids" is the one claim that must never go out. Each pattern below is one way of saying it; a match that
# contains a negation ("we don't write your bids") is the right answer and is let through.
_THEY = r"(?:we|our\s+(?:team|system|ai|tool|software)|the\s+(?:system|team|tool))"
_US = rf"(?:{_THEY}|us|i|heinrich)"
_GAP = r"[^\w.!?;\n]+"  # what sits between two words of one sentence
_PREP = r"(?:from|of|in|on|with|for|using|about|at|into|around|across|than|by|to|over|under|inside|within)"
_TOKEN = rf"(?:(?:each|all|any|every|some|most|both|many)\s+of|(?!{_PREP}\b)\w+)"
_BIDS = r"(?:bids?|proposals?|rfps?|rfqs?|responses?|submissions?|tenders?)"
_DO = (r"(?:writ(?:e|es|ing)|wrote|draft(?:s|ed|ing)?|prepar(?:e|es|ed|ing)|produc(?:e|es|ing)|creat(?:e|es|ing)|generat(?:e|es|ing)"
       r"|compil(?:e|es|ing)|complet(?:e|es|ing)|finish(?:es|ing)?|submit(?:s|ting)?|deliver(?:s|ing)?|assembl(?:e|es|ing)"
       r"|put(?:s|ting)?\s+together|tak(?:e|es|ing)\s+care\s+of)")
_WRITES_FOR_THEM = tuple(re.compile(p, re.I) for p in (
    rf"\b{_US}\b(?:{_GAP}\w+){{0,4}}?{_GAP}{_DO}\b(?:{_GAP}{_TOKEN}){{0,5}}?{_GAP}{_BIDS}\b",
    rf"\b{_US}\b(?:{_GAP}\w+){{0,3}}?{_GAP}(?:handl\w+|tak(?:e|es|ing)\s+care\s+of|run(?:s|ning)?)\s+(?:all\s+(?:of\s+)?)?(?:the\s+)?(?:bid\s+|proposal\s+)?writ(?:ing|e)\b",
    rf"\b{_US}\b(?:{_GAP}\w+){{0,3}}?{_GAP}do(?:es|ing)?\s+(?:all\s+(?:of\s+)?(?:the\s+)?|the\s+)(?:bid\s+|proposal\s+)?writ(?:ing|e)\b",
    rf"\b{_US}\b(?:{_GAP}\w+){{0,6}}?{_GAP}writ\w+\s+(?:the\s+)?(?:whole|entire)\b",
    rf"\b{_US}\b(?:{_GAP}\w+){{0,3}}?{_GAP}(?:writ\w+|wrote|draft\w*|prepar\w+|produc\w+|creat\w+)\s+(?:the\s+|a\s+|your\s+|each\s+|every\s+)?(?:first\s+|initial\s+|full\s+|complete\s+|whole\s+)?(?:draft|drafts|version|copy)\s+of\b",
    rf"\b{_THEY}\b(?:{_GAP}\w+){{0,2}}?{_GAP}(?:writ(?:e|es|ing)|wrote|draft(?:s|ed|ing)?|prepar(?:e|es|ed|ing))\s+(?:them|it|these|those)\b(?:\s+all)?(?:\s+for\s+you)?",
    rf"\b{_BIDS}\b[^.!?;\n]{{0,30}}?\b(?:written|drafted|prepared|produced|created|generated|handled|completed|finished|done)\b[^.!?;\n]{{0,25}}?\b(?:for\s+you|by\s+(?:us|our|the\s+(?:team|system|ai)|heinrich))\b",
))
_NEGATION = re.compile(r"n't|\b(?:not|never|no)\b", re.I)
_TOKEN_MARK = re.compile(r"\{[^}]*\}|\[[^\]]*\]|<[^>]*>|\bTODO\b|\bXXX\b")

# Numbers: dates, times, call lengths and small counts of the things we really talk about need no approval; any other
# number has to appear in the approved facts, in the examples, or in the very message being answered.
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
_DATE_OR_TIME = re.compile(
    rf"\b\d{{4}}-\d{{2}}-\d{{2}}\b|\b\d{{1,2}}[:.]\d{{2}}\s?(?:[ap]\.?m\.?)?|\b\d{{1,2}}\s?[ap]\.?m\b"
    rf"|\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\b(?:\s+\d{{4}})?|\b{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?\b"
    r"|\b\d{1,4}/\d{1,2}/\d{1,4}\b|\b20\d\d\b|\b\d+(?:st|nd|rd|th)\b",
    re.I,
)
_CALL_LENGTH = re.compile(r"\b(?:5|10|15|20|25|30|45|60)\s*(?:minutes?|mins?)\b", re.I)
_SMALL_COUNT = re.compile(r"\b(?:[1-9]|10)\s+(?:bids?|proposals?|rfps?|responses?|calls?|days?|weeks?|steps?|questions?|things?|options?)\b", re.I)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and not word.endswith(("le", "ee")) and count > 1:
        count -= 1
    return max(1, count)


def reading_grade(text: str) -> float:
    """Flesch-Kincaid grade, good enough to tell grade 5 from grade 12. Links are left out, they are not prose."""
    text = textnorm.LINK.sub("", text)
    sentences = [s for s in re.split(r"[.!?]+\s|\n+", text) if re.search(r"[A-Za-z]", s)]
    words = re.findall(r"[A-Za-z']+", text)
    if not sentences or not words:
        return 0.0
    syl = sum(_syllables(w) for w in words)
    return 0.39 * (len(words) / len(sentences)) + 11.8 * (syl / len(words)) - 15.59


def _says_we_write_their_bids(flat: str) -> bool:
    return any(not _NEGATION.search(found.group(0)) for pattern in _WRITES_FOR_THEM for found in pattern.finditer(flat))


def _unapproved_numbers(text: str, cfg: Config, context: str) -> list[str]:
    approved = " ".join([*cfg.facts, *(f"{e['in']} {e['out']}" for e in cfg.examples), context])
    known = set(_NUMBER.findall(approved))
    plain = _SMALL_COUNT.sub(" ", _CALL_LENGTH.sub(" ", _DATE_OR_TIME.sub(" ", text)))
    return [n for n in _NUMBER.findall(plain) if n not in known]


def check(body: str, category: str, cfg: Config, context: str = "") -> tuple[str, ...]:
    """Everything wrong with a draft, as short plain sentences. Empty means it passes.

    `context` is the message being answered: a number the prospect wrote may be repeated back to them.
    """
    problems: list[str] = []
    wanted = (body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    text = textnorm.strip_controls(wanted)
    if not text:
        return ("the draft is empty",)
    if text != wanted:  # what is checked must be what is sent, so hidden characters are a failure, not something to wash away
        problems.append("contains hidden control or text-direction characters")
    words = re.findall(r"[A-Za-z0-9']+", text)
    if len(words) > cfg.max_words or len(text) > MAX_DRAFT_CHARS:
        problems.append(f"too long ({len(words)} words, the limit is {cfg.max_words})")
        if len(text) > MAX_DRAFT_CHARS:
            return tuple(problems)  # not worth running every pattern over a text this long
    flat = textnorm.ascii_fold(textnorm.normalise(text))  # one line, plain quotes and plain letters: what the patterns are written against
    lower = flat.lower()

    if len(words) < 15:
        problems.append("too short to be a real reply")
    if EM_DASH in text or EN_DASH in text or " -- " in text:
        problems.append("contains a dash used as punctuation, use a comma or a full stop")
    if textnorm.has_odd_characters(text):
        problems.append("contains characters that are hidden or look like other letters, so the checks cannot be sure what it says")
    for word in cfg.banned_words:
        if re.search(rf"\b{re.escape(word)}\b", lower):
            problems.append(f"uses the banned word '{word}'")
    for phrase in cfg.banned_phrases:
        if phrase in lower:
            problems.append(f"uses the banned phrase '{phrase}'")
    if _says_we_write_their_bids(flat):
        problems.append("says we write their bids, they still write every bid")
    if _PRICE.search(flat):
        problems.append("mentions a price, none has been set")
    if _CLAIM.search(flat):
        problems.append("makes a claim or promise (a percentage, a guarantee) that nothing approves")
    if _SENSITIVE.search(flat):
        problems.append("asks for personal details or money, which we never do")
    if _TOKEN_MARK.search(text):
        problems.append("has an unfilled placeholder")
    if text.count("!") > 1:
        problems.append("too many exclamation marks")

    # The booking link counts only when nothing is stuck on its end: ".../meets?duration=30/evil" or "...30&next=evil.com" is a different link.
    link_here = re.compile(rf"{re.escape(cfg.booking_link)}(?=$|[\s.,;:!?)\]\"'>])")
    outside_booking_link = link_here.sub(" ", flat)
    if textnorm.SCHEME.search(outside_booking_link) or textnorm.LINK.search(outside_booking_link) \
            or textnorm.SPELLED_LINK.search(outside_booking_link):
        problems.append("contains a link that is not the booking link")
    if textnorm.has_phone(outside_booking_link):
        problems.append("contains a phone number")
    mine = {m.lower() for m in cfg.campaign_mailboxes} | {cfg.tracking_mailbox.lower()}
    if any(e.group(0).lower() not in mine for e in textnorm.EMAIL.finditer(outside_booking_link)) or _OBFUSCATED_EMAIL.search(flat):
        problems.append("contains an email address we did not supply")
    odd_numbers = _unapproved_numbers(outside_booking_link, cfg, textnorm.normalise(context))
    if odd_numbers:
        problems.append(f"uses a number that nothing approves ({', '.join(dict.fromkeys(odd_numbers))})")

    if category == "interested" and not link_here.search(flat):
        problems.append("an interested reply must include the booking link")
    if category in ("soft_no", "referral") and cfg.booking_link in text:
        problems.append("a soft no or a referral must not push the booking link")

    if not re.match(r"^(hi|hey|hello)\b", lower):
        problems.append("does not start with a greeting")
    if not text.rstrip().endswith(cfg.sender_name):
        problems.append(f"does not end with the sign-off '{cfg.sender_name}'")
    if reading_grade(text) > cfg.max_grade:
        problems.append(f"reads above grade {cfg.max_grade:g}, use shorter words and sentences")
    return tuple(problems)


# Fraud wording in a subject. Narrow on purpose: "Account management contract", "Knowledge transfer plan" and "Urgent: RFP due Friday"
# are real subjects, and a reply with a different subject lands in a separate conversation in the recipient's mail program.
_SUBJECT_RISK = re.compile(
    r"\b(?:pay(?:ment)?\s+(?:the|this|your|an?|our)?\s*invoice|invoice\s+(?:payment|overdue)|(?:new|updated?|changed?)\s+(?:bank\s+)?account"
    r"(?:\s+(?:details|number))?|(?:update[d]?|change[d]?)\s+(?:bank|payment)\s+(?:details|account))\b",
    re.I,
)


def subject_is_safe(subject: str) -> bool:
    """May this subject be echoed back after "Re:"? A reply goes to the sender (or to the real person a forged From names),
    so a subject that makes a promise, names a price, asks for money or a login, hides a link or uses look-alike letters is
    replaced by a plain one instead."""
    if not subject or textnorm.has_odd_characters(subject) or textnorm.strip_controls(subject) != subject:
        return False
    folded = textnorm.ascii_fold(textnorm.normalise(subject))
    if (textnorm.SCHEME.search(folded) or textnorm.LINK.search(folded) or textnorm.SPELLED_LINK.search(folded)
            or textnorm.EMAIL.search(folded) or textnorm.has_phone(folded)):
        return False
    return not (_CLAIM.search(folded) or _PRICE.search(folded) or _SENSITIVE.search(folded) or _SUBJECT_RISK.search(folded))

