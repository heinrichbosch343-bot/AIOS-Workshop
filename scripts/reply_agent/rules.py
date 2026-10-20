"""Decisions made by code, before any model is called.

The cheapest and safest place for a rule is here: no cost, no surprises, easy to test.

Two mistakes are not equally bad. Writing to someone who asked us to stop is a legal and reputational problem; silencing a
real lead because a sentence happened to contain "don't send" loses a booking without anyone knowing. So a clear request to
stop wins over everything (including interest), a wording that could go either way is shown to a person and suppresses
nobody, and a plain mention of data or spam is shown to a person too. Only what the person typed is read for any of this:
not their signature, not a legal disclaimer, and not the subject line (which is usually our own) unless they wrote next to nothing.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .models import Decision, InboundMail
from .textnorm import normalise, strip_controls
from .trust import authenticated, base_address

# Consumer mail providers and ISPs: a lead on one of these says nothing about the company, so the whole domain must never count
# as "someone at a lead's company".
FREE_MAIL = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "icloud.com",
    "aol.com", "proton.me", "protonmail.com", "protonmail.ch", "pm.me", "msn.com", "me.com", "mac.com", "ymail.com", "rocketmail.com",
    "yahoo.co.uk", "yahoo.ca", "yahoo.com.au", "yahoo.co.za", "yahoo.fr", "yahoo.de", "yahoo.es", "yahoo.it", "yahoo.co.in",
    "hotmail.co.uk", "hotmail.co.za", "hotmail.fr", "hotmail.de", "hotmail.it", "hotmail.es", "outlook.co.za", "outlook.com.au",
    "live.co.uk", "live.co.za", "live.com.au", "live.ca", "comcast.net", "att.net", "sbcglobal.net", "verizon.net", "cox.net",
    "charter.net", "bellsouth.net", "earthlink.net", "juno.com", "optonline.net", "frontier.com", "windstream.net", "mail.com",
    "gmx.com", "gmx.net", "gmx.de", "web.de", "zoho.com", "hey.com", "fastmail.com", "fastmail.fm", "tutanota.com", "tuta.io",
    "yandex.com", "yandex.ru", "mail.ru", "qq.com", "163.com", "126.com", "naver.com", "btinternet.com", "sky.com", "talktalk.net",
    "virginmedia.com", "ntlworld.com", "bigpond.com", "optusnet.com.au", "shaw.ca", "rogers.com", "telus.net", "sympatico.ca",
    "mweb.co.za", "telkomsa.net", "vodamail.co.za", "webmail.co.za", "iafrica.com", "absamail.co.za", "polka.co.za",
})

_MAIL_OBJECT = r"(?:e-?mails?|messages?|mails?|follow-?ups?|contact|spam|messaging|solicitations?|marketing|outreach)"
# What "opt out of ..." may be followed by and still be a request to stop hearing from us.
_ABOUT_US = (r"(?:your|our|the|these|those|this|that|all|any|further|future|more|everything|it|them|e-?mails?|mailing|marketing|"
             r"communications?|newsletters?|messages?|receiving|updates?|contact|outreach|follow-?ups?)")
# Things a person is taken off that are not our mailing list.
_THREAD_WORDS = r"(?:cc|bcc|thread|chain|loop|invite|calendar|meeting|call|agenda)"
_NOT_THREAD_OFF = rf"(?!\s+(?:of\s+)?(?:the\s+|this\s+|that\s+|your\s+|our\s+)?{_THREAD_WORDS}\b)"
_NOT_THREAD_FROM = rf"(?!\s+(?:from|off)\s+(?:the\s+|this\s+|that\s+|your\s+|our\s+)?{_THREAD_WORDS}\b)"
_CHANNEL = r"(?:phone|telephone|calls?|cell|mobile|texts?|sms|whatsapp)"
_LIST_TARGET = (r"(?:from|off)\s+(?:(?:your|the|this|that|our|my)\s+)?"
                r"(?:(?:mailing|e-?mail|contact|distribution|marketing|sending|outreach|prospect|subscriber)\s+)?(?:lists?|database|system|records?|file)\b")
# "remove the old address from your records" names an address, not a person: only me, us, my, our, "this address" and the like count.
_ME_OBJECT = r"(?:me|us|my\s+\w+|our\s+\w+|(?:this|that|these)\s+(?:e-?mail\s+address|address|number|contact|name|details)|them)"
_TAKE_VERB = r"(?:remov(?:e|ed|es|ing)|delet(?:e|ed|es|ing)|tak(?:e|es|en|ing)|drop(?:s|ped|ping)?|eras(?:e|ed|es|ing))"
# Matched against normalise()d text, so curly apostrophes, non-breaking spaces, odd hyphens and HTML entities are already plain.
# "don't send" or "never write" alone is NOT here: "we don't send that many bids" is a customer, not a request. The words that
# make it a request are the ones that aim it at us ("me", "us", "again", "any more").
_STOP = re.compile(
    r"\b(?:"
    r"unsubscrib\w*|un-subscrib\w*|unsub\b"
    # "opt out of low value bids" is about something else; "opt out", "opt out of your emails" and "opt out of everything" are not
    rf"|opt(?:ed|ing)?[ -]?out\b(?!\s+of\s+(?!{_ABOUT_US}\b))|opt\s+(?:me|us)\s+out"
    rf"|remove\s+(?:me|us)\b{_NOT_THREAD_FROM}"
    r"|remove\s+(?:my|our)\s+(?:e-?mail(?:\s+address)?|name|address|details|number|contact|company|firm|business|info\w*)"
    r"|remove\s+(?:this|that)\s+(?:e-?mail\s+address|address|number|contact|name|details)"
    rf"|{_TAKE_VERB}\s+(?:{_ME_OBJECT}\s+)?{_LIST_TARGET}"
    rf"|(?:be|get|been)\s+(?:removed|deleted|taken|dropped)\s+{_LIST_TARGET}"
    # "take me off the cc line" is not an unsubscribe
    rf"|take\s+(?:me|us|my|our|this)\b[^.\n]{{0,25}}\boff\b{_NOT_THREAD_OFF}"
    rf"|(?:be|get|been)\s+taken\s+off\b{_NOT_THREAD_OFF}"
    r"|cease\s+(?:all\s+)?(?:contact|e-?mail\w*|communicat\w*)"
    r"|de-?regist\w+\s+(?:me|us)|delist\s+(?:me|us)"
    r"|stop\s+(?:e-?mailing|contacting|messaging|mailing|bothering|spamming|texting|pestering|harassing)\b"
    r"|stop\s+(?:sending|writing)\s+(?:me|us|to\s+(?:me|us)|these|those|this|that|any|more|further|them|e-?mails?|messages?)\b"
    rf"|stop\s+(?:the|these|those|your|all|any|further|more|this|that)\s+{_MAIL_OBJECT}\b"
    r"|stop\s+(?:e-?mails?|messages?|mails?)\b"
    r"|please\s+stop(?=[ \t]*(?:[.!,\n]|$))"
    # "never contact me by phone, email is better" and "don't write us off" are not requests to stop
    rf"|(?:do\s+not|don'?t|dont|never)\s+(?:e-?mail|contact|message|write(?:\s+to)?|text|reach(?:\s+out\s+to)?)\s+(?:me|us|this)\b"
    rf"(?!\s+(?:off|down|up|out|in|back)\b)(?!\s+(?:by|via|on|through|at)\s+{_CHANNEL}\b)"
    r"|(?:do\s+not|don'?t|dont|never)\s+(?:e-?mail|contact|message|write|reply|respond|send)\b[^.\n]{0,25}\b(?:again|anymore|any\s+more|any\s+further)\b"
    r"|(?:do\s+not|don'?t|dont|never)\s+send\s+(?:me|us)\b"
    # "no more emails to the old address" tells us which inbox to use; "any more emails like this would be welcome" is not a request
    r"|no\s+(?:more|further)\s+(?:e-?mails?|messages?|contact|mail|follow-?ups?)"
    r"(?!\s+(?:to|at|on)\s+(?:the|my|our|that)\s+(?:old|previous|former|other|wrong|first|second|work|personal)\b)"
    r"|(?:do\s+not|don'?t|dont|never|stop|without)\b[^.\n]{0,25}\bany\s+(?:more|further)\s+(?:e-?mails?|messages?|contact|mail|follow-?ups?)"
    r"|leave\s+(?:me|us)\s+alone"
    r"|(?:delete|erase|remove)\s+(?:my|our)\s+(?:data|details|information|info|e-?mail|name|address|record)s?"
    r"|(?:no\s+longer|do\s+not|don'?t)\s+(?:wish|want|need)\s+to\s+"
    r"(?:receive|hear\s+from|be\s+contacted|get\s+(?:any\s+)?(?:more\s+)?(?:e-?mails?|messages?|mail|contact))"
    r"|never\s+(?:e-?mail|contact|write|message)\b[^.\n]{0,15}\bagain"
    # a few common ways to say it in Afrikaans, German, French, Spanish and Dutch
    r"|haal\s+(?:my|ons)\b[^.\n]{0,30}\b(?:af|van)\b|verwyder\s+(?:my|ons)\b|skrap\s+my\b"
    r"|moenie\s+(?:my|ons)?\s*(?:meer\s+)?(?:e-?pos|kontak|skryf|stuur)"
    r"|abmelden|austragen|keine\s+(?:e-?mails|werbung)\s+mehr"
    r"|d.sabonn\w+|d.sinscri\w+|ne\s+plus\s+recevoir|darme\s+de\s+baja|no\s+me\s+(?:escriba|env.e|envie)|uitschrijven|afmelden"
    r")\b",
    re.I,
)
_OPT_OUT_NOUN = re.compile(r"^opt(?:ed|ing)?[ -]?out$", re.I)
_DETERMINER_BEFORE = re.compile(r"\b(?:a|an|the|your|our|their|this|that|any|no|one|easy|simple|clear|visible)\s+$", re.I)
# "Could you please remove me from your list?" is a request even though it is phrased as a question.
_POLITE_REQUEST = re.compile(
    r"\b(?:(?:could|can|would|will|won'?t)\s+you\s+(?:please\s+|kindly\s+)?(?:stop|remove|take|unsubscribe|opt|delete|leave)"
    r"|would\s+you\s+mind\s+(?:removing|taking|stopping|deleting|unsubscribing))\b", re.I)
_INTERROGATIVE_START = re.compile(
    r"^(?:is|are|was|were|can|could|do|does|did|how|what|why|will|would|should|may|might|which|where|when|who|whom|whose|shall|any"
    r"|isn't|aren't|can't|won't)\b", re.I)
# A whole sentence that is only the request: "Stop.", "Remove.", "Unsubscribe me", "Stop it".
_BARE_STOP = re.compile(
    r"^(?:(?:ok|okay|hi|hello|hey|please|kindly|just)[ ,]*)*"
    r"(?:stop|remove(?:\s+(?:me|us))?|unsubscribe(?:\s+(?:me|us))?|opt\s*out|cancel|delete\s+(?:me|us)|deregister(?:\s+(?:me|us))?)"
    r"(?:\s+(?:it|now|this|that|please|thanks|thank\s+you))?\W*$", re.I)
# "If you no longer wish to receive emails from us ..." and "If you would like to unsubscribe ..." are footers, not requests.
_CONDITIONAL_BEFORE = re.compile(
    r"\b(?:if|when|should|whenever)\s+(?:you|they|anyone|someone)\s+"
    r"(?:(?:would\s+(?:like|prefer|rather)|want|wish|need|choose|decide|prefer)\s+(?:to\s+)?)?$", re.I)
# Words that mark a line as a newsletter footer or a link, not something the person typed to us.
_FOOTER_LINK = re.compile(
    r"\bour\s+(?:newsletter|mailing\s+list|e-?mails?)\b|\bprivacy\s+policy\b|\bview\s+(?:this\s+)?(?:e-?mail\s+)?in\s+(?:your\s+)?browser\b"
    r"|\bmanage\s+(?:your\s+)?(?:preferences|subscriptions?)\b|https?://|\bwww\.|\bclick\s+(?:here|(?:on\s+)?(?:the\s+)?(?:link|unsubscribe))\b",
    re.I)
# Where a signature or a legal disclaimer starts.
_FOOTER_START = re.compile(
    r"^(?:-{2,}|_{3,}|={3,})\s*$"
    r"|^(?:sent\s+from\s+my\b|get\s+outlook\s+for\b|sent\s+via\b|sent\s+using\b)"
    r"|^(?:confidentiality\s+notice|confidential\b|disclaimer\b|legal\s+notice|privacy\s+notice"
    r"|this\s+(?:e-?mail|message|communication)\s+(?:and\s+any|is\s+(?:intended|confidential|for)|may\s+contain|contains)"
    r"|if\s+you\s+(?:are\s+not\s+the\s+intended|have\s+received\s+this|received\s+this)"
    r"|please\s+(?:consider\s+the\s+environment|delete\s+this)|think\s+before\s+you\s+print)", re.I)
# What counts as an authority when someone says they reported us to it.
_AUTHORITY = (r"(?:ftc|fcc|ico|police|authorit\w+|regulator\w*|attorney\s+general|information\s+regulator|"
              r"(?:my|our)\s+(?:lawyers?|attorneys?|solicitors?|legal\w*)|your\s+(?:provider|host|isp|registrar)|spamhaus|google|microsoft|abuse)")
# A real threat: it suppresses the sender and a person is told.
# Only wording aimed at us: "our lawyers will need to review the terms", "FCC licensed", "I reported this to our bid manager" and
# "harassment prevention training" are what customers write, so a bare lawyer, regulator, report or harassment is not a threat.
_THREAT = re.compile(
    r"\b(?:sue\s+(?:you|your|the\s+company)|legal\s+action|cease\s+and\s+desist"
    r"|(?:this\s+is|you\s+are|you're|it\s+is|it's)\s+(?:harassment|harassing)|harass(?:ing|ed)\s+(?:me|us)|stop\s+harassing"
    rf"|report(?:ed|ing)?\s+(?:you|this|your|it)\s+(?:to\s+(?:the\s+)?{_AUTHORITY}|as\s+(?:spam|phishing|abuse|a\s+scam))"
    r"|(?:my|our)\s+(?:lawyers?|attorneys?|solicitors?|legal\s+(?:team|department|counsel))\s+(?:will|shall)\s+"
    r"(?:be\s+in\s+touch|be\s+contacting|contact|deal|handle|take\s+action|follow\s+up)"
    rf"|(?:file|filing|lodge|lodging)\s+a\s+complaint|complain\w*\s+(?:to|with)\s+(?:the\s+)?{_AUTHORITY}"
    r"|(?:violat\w+|breach\w*)\s+(?:of\s+)?(?:the\s+)?(?:can-?spam|gdpr|popia|tcpa|law))\b",
    re.I,
)
# Someone who asks to stop and names a law is making a legal request: it needs a person, not just a suppression.
_LEGAL_BASIS = re.compile(r"\b(?:gdpr|popia|can-?spam|data\s+protection|privacy\s+(?:law|act)|information\s+regulator)\b", re.I)
# Words that raise a flag but are also what a real prospect asks about: a person looks, nobody is suppressed.
_SOFT_LEGAL = re.compile(
    r"\b(?:spam(?:mer|ming)?|scam|fraud|phishing|gdpr|popia|can-?spam|data\s+protection|privacy\s+(?:policy|law|act|notice)|information\s+regulator)\b",
    re.I,
)
_OOO = re.compile(
    r"(out of (the )?office|automatic reply|auto-?reply|on (annual )?leave|on vacation|on holiday|away from (my )?(desk|email)|"
    r"will (be )?(back|return)|limited access to (email|my email))",
    re.I,
)
_BOUNCE_SENDERS = re.compile(r"^(mailer-daemon|postmaster|mail-daemon|no-?reply.*bounce)@", re.I)
_BOUNCE_SUBJECT = re.compile(r"(undeliver|delivery status notification|returned mail|failure notice|mail delivery (failed|subsystem))", re.I)
# A reply, or a forward: either is someone answering or passing on one of our emails.
_REPLYISH_SUBJECT = re.compile(r"^\s*(?:re|aw|sv|fwd?|wg|tr|rv)\s*:", re.I)


@dataclass(frozen=True)
class Known:
    """Who we expect to hear from. Addresses are kept in base form (lower case, plus tag removed)."""
    emails: frozenset = frozenset()
    domains: frozenset = frozenset()
    suppressed: frozenset = frozenset()
    sent: dict = field(default_factory=dict)  # Message-ID of a reply we sent -> the address it was sent to

    def __post_init__(self):
        object.__setattr__(self, "emails", frozenset(base_address(e) for e in self.emails))
        object.__setattr__(self, "suppressed", frozenset(base_address(e) for e in self.suppressed))
        object.__setattr__(self, "sent", {k: base_address(v) for k, v in dict(self.sent).items()})


def _rule(category: str, reason: str, mailbox: str, confidence: float = 1.0) -> Decision:
    return Decision(category, confidence, reason, "rule", mailbox)


def our_mailbox(mail: InboundMail, cfg: Config) -> str:
    """Which campaign mailbox the person wrote to.

    Our mail server records the address a message was originally delivered to (X-Pm-Original-To), even on the copies it
    forwards to the tracking mailbox. That header is ours, so it wins: the To and Cc lines are typed by the sender, who
    could otherwise choose which of our mailboxes the reply goes out from. Without it (other servers, older mail) we fall
    back to To and Cc, then the other delivery headers.
    """
    ours = {m.lower() for m in cfg.campaign_mailboxes}
    original = mail.header("x-pm-original-to").strip().lower()
    if original:
        return original if original in ours else ""
    for addr in mail.to_addrs:
        if addr in ours:
            return addr
    for name in ("x-original-to", "delivered-to"):
        value = mail.header(name).strip().lower()
        if value in ours:
            return value
    return ""


def load_known(cfg: Config, suppressed=(), sent=None) -> Known:
    """Read the lead lists. A list that is missing or has no email column is an error: silence here would hide every real reply."""
    emails: set[str] = set()
    for path in cfg.lead_files:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"lead list not found: {p}. Fix lead_files in outputs/outreach/reply-agent.json")
        with p.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            cols = [c for c in (reader.fieldnames or []) if "email" in c.lower()]
            if not cols:
                raise ValueError(f"{p} has no email column")
            for row in reader:
                for col in cols:
                    value = (row.get(col) or "").strip().lower()
                    if "@" in value:
                        emails.add(base_address(value))
    domains = {e.split("@")[-1] for e in emails} - FREE_MAIL
    return Known(frozenset(emails), frozenset(domains), frozenset(suppressed), dict(sent or {}))


def trust_level(mail: InboundMail, known: Known) -> str:
    """exact: an address we wrote to or hold a lead for. domain: someone at a lead's company. none: nobody we know."""
    addr = base_address(mail.from_addr)
    if addr in known.emails:
        return "exact"
    ids = [i for i in (mail.in_reply_to, *mail.references) if i]
    if any(known.sent.get(i) == addr for i in ids):
        return "exact"  # a reply to something we sent to this very address
    return "domain" if addr.split("@")[-1] in known.domains else "none"


def looks_like_reply(mail: InboundMail) -> bool:
    """Is this someone answering, or passing on, one of our emails? (A subject of Re: or Fwd:, or a reply header.)"""
    return bool(mail.in_reply_to or mail.references or _REPLYISH_SUBJECT.match(mail.subject or ""))


def _is_ours(addr: str, cfg: Config) -> bool:
    mine = {m.lower() for m in cfg.campaign_mailboxes} | {cfg.tracking_mailbox.lower()}
    return addr in mine


def _report_type(mail: InboundMail) -> str:
    content_type = re.sub(r"[\s\"']", "", mail.header("content-type").lower())
    found = re.search(r"multipart/report.*report-type=([a-z-]+)", content_type)
    return found.group(1) if found else ""


def _is_machine_mail(mail: InboundMail) -> bool:
    """An automatic reply, which no person typed. These headers are put there by the program that answered."""
    auto = mail.header("auto-submitted").lower()
    return bool((auto and auto != "no") or mail.header("x-autoreply") or mail.header("x-autorespond"))


def _looks_bulk(mail: InboundMail) -> bool:
    """Signs of a mailing list or a bulk sender. Exchange and many CRMs put some of these on ordinary mail, so they only
    count against senders we do not know."""
    return bool(mail.header("list-unsubscribe") or mail.header("x-auto-response-suppress")
                or mail.header("precedence").lower() in {"bulk", "junk", "auto_reply", "list"})


def _scan_text(mail: InboundMail) -> str:
    """What the person typed, one line per line of the message, for the stop and legal checks.

    No signature or disclaimer (everything from a "-- " line, "Sent from my", "Confidentiality notice" and the like down), and
    not the subject line, which is usually our own email's subject, unless the person wrote next to nothing (a mail client's
    unsubscribe button sends an empty body and the word "unsubscribe" as the subject).
    """
    lines = [line.strip() for line in (mail.body or "").splitlines()]
    cut = next((i for i, line in enumerate(lines) if i > 0 and _FOOTER_START.match(line)), len(lines))
    body = "\n".join(kept for kept in (normalise(line) for line in lines[:cut]) if kept)
    if len(body.split()) >= 2:
        return body
    return "\n".join(part for part in (normalise(mail.subject), body) if part)


def _sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    left = max(text.rfind(c, 0, start) for c in ".!?\n") + 1
    stops = [i for i in (text.find(c, end) for c in ".!?\n") if i != -1]
    return left, (min(stops) + 1) if stops else len(text)


def _asks_about_it(scan: str, found: re.Match) -> bool:
    """Is the match part of a question ("Is there a way to opt out?") rather than a command ("Please remove me, who is this?")?"""
    left, right = _sentence_span(scan, found.start(), found.end())
    sentence = scan[left:right]
    if not sentence.rstrip().endswith("?") or _POLITE_REQUEST.search(sentence):
        return False
    clause = re.split(r"[,;:]", scan[left:found.start()])[-1].strip()
    return bool(_INTERROGATIVE_START.match(clause or scan[found.start():right].strip()))


def _stop_signal(scan: str) -> tuple[str, str]:
    """("firm", words) for a clear request to stop, ("maybe", words) for wording that could go either way, ("", "") for none."""
    for line in [ln for ln in scan.split("\n") if ln.strip()][:3]:  # a lone "Stop." or "Remove." near the top
        for part in re.split(r"[.!?]+", line):
            if _BARE_STOP.match(part.strip()):
                return "firm", part.strip()[:60]
    maybe = ""
    for found in _STOP.finditer(scan):
        line = scan[scan.rfind("\n", 0, found.start()) + 1:(scan.find("\n", found.end()) if "\n" in scan[found.end():] else len(scan))]
        if _FOOTER_LINK.search(line) or _CONDITIONAL_BEFORE.search(scan[max(0, found.start() - 90):found.start()]):
            continue  # a link or footer line, or "if you would like to unsubscribe ...": something we were told, not asked
        words = strip_controls(found.group(0))[:60]
        talks_about_it = bool(_OPT_OUT_NOUN.match(found.group(0)) and _DETERMINER_BEFORE.search(scan[max(0, found.start() - 24):found.start()]))
        if _asks_about_it(scan, found) or talks_about_it:
            maybe = maybe or words  # "Is there a way to opt out?" or "an opt-out button would help" is about it, not a request
            continue
        return "firm", words
    return ("maybe", maybe) if maybe else ("", "")


def prefilter(mail: InboundMail, cfg: Config, known: Known, verified: bool | None = None) -> Decision | None:
    """Return a Decision when the rules settle it, or None when the model should look."""
    box = our_mailbox(mail, cfg)
    text = normalise(f"{mail.subject}\n{mail.body}")
    lowered = text.lower()
    sender = base_address(mail.from_addr)
    report = _report_type(mail)
    level = trust_level(mail, known)
    if verified is None:
        verified = authenticated(mail, cfg.auth_host)
    trusted = level == "exact" or (level == "domain" and verified)  # a known lead, or a verified colleague of one

    if _is_ours(mail.from_addr, cfg):
        return _rule("ignore", "sent by one of our own mailboxes", box)
    if (_BOUNCE_SENDERS.match(mail.from_addr) or report == "delivery-status" or mail.failed_recipients
            or _BOUNCE_SUBJECT.search(mail.subject)):
        return _rule("bounce", "delivery failure notice", box)
    if report:  # read receipts and other machine reports
        return _rule("auto_reply", "automatic report", box)
    if any(tag and tag.lower() in lowered for tag in cfg.warmup_tags):
        return _rule("ignore", "warmup mail (carries the warmup tag)", box)
    if sender in known.suppressed:
        return _rule("ignore", "sender is on the do-not-write list", box)
    if _is_machine_mail(mail) or (_looks_bulk(mail) and not trusted):  # a footer that says "unsubscribe" is not a person asking to
        return _rule("out_of_office" if _OOO.search(text) else "auto_reply", "automatic reply", box)

    scan = _scan_text(mail)
    stop, words = _stop_signal(scan)
    threat = _THREAT.search(scan)
    soft_legal = _SOFT_LEGAL.search(scan)
    if stop == "firm" and (threat or _LEGAL_BASIS.search(scan)):  # "stop spamming me" is only a rude unsubscribe
        return _rule("complaint", f"asked to stop and raised legal or complaint wording, a person must handle this (they wrote: '{words}')", box)
    if stop == "firm":
        return _rule("unsubscribe", f"asked to stop (they wrote: '{words}')", box)
    if threat:
        return _rule("complaint", f"legal or complaint wording, a person must handle this (they wrote: '{strip_controls(threat.group(0))[:60]}')", box)
    if stop == "maybe":
        return _rule("other", f"mentions opting out or stopping in a question, so a person decides (they wrote: '{words}')", box, 0.5)
    if soft_legal:
        return _rule("other", f"mentions spam, privacy or data wording, so a person decides (they wrote: '{strip_controls(soft_legal.group(0))[:60]}')", box, 0.5)
    if _looks_bulk(mail) and _OOO.search(text):  # a trusted sender's mail with bulk-looking headers is a reply, unless it says they are away
        return _rule("out_of_office", "automatic reply", box)
    if _OOO.search(mail.subject):
        return _rule("out_of_office", "out of office subject", box)
    if level == "none":
        return _rule("unknown_sender", "not on any lead list and not a reply to us", box, 0.9)
    return None
