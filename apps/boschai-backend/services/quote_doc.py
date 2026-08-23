"""The quote as a document: the PDF, the web page, and the words the customer reads.

Everything here is deterministic. Given a quote you get the same PDF, the same page
and the same message every time — which is the point. The model writes the prose the
technician sees; this file writes every number that leaves the building.

The PDF is fpdf2, not headless Chromium. Chromium needs a system package on the host,
a longer build and about 400MB; it renders beautifully and it has never once been
proven on a real Railway deploy. fpdf2 is pure Python, installs from requirements.txt
like anything else, and renders in about 30ms. For a one-page A4 quote that trade is
not close.
"""
import json
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF

TZ = ZoneInfo("Africa/Johannesburg")
BUSINESS_PATH = Path(__file__).parent.parent / "quote_business.json"

_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]

# The document's palette. INK and ACCENT come from quote_business.json so the PDF and
# the web page are skinned by the same two values -- a client's brand should never be
# spread across a config file AND a set of constants in here, because then half of it
# gets changed and the quote goes out in two identities at once.
#
# The greys are deliberately NOT configurable. They are the paper the brand sits on,
# and letting them be set per client is how you end up with unreadable body text.
MUTED = (122, 134, 148)
RULE = (222, 228, 235)
PAPER_MUTED = (246, 248, 250)

_DEFAULT_INK = "#12161c"
_DEFAULT_ACCENT = "#1b6ef3"


def _rgb(value: str, fallback: tuple) -> tuple:
    """'#1a6e80' -> (26, 110, 128). Falls back rather than raising: a typo in a colour
    must never be the reason a customer cannot get their quote."""
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return fallback
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def _tint(rgb: tuple, amount: float) -> tuple:
    """Mix a colour toward white. Used for a label sitting on the dark brand band: a
    fixed light blue was hardcoded there, and it clashed the moment the brand stopped
    being blue."""
    return tuple(int(c + (255 - c) * amount) for c in rgb)


def ink() -> tuple:
    return _rgb((business().get("brand") or {}).get("ink", _DEFAULT_INK), (18, 22, 28))


def accent() -> tuple:
    return _rgb((business().get("brand") or {}).get("accent", _DEFAULT_ACCENT),
                (27, 110, 243))


# ─────────────────────────────────────────────────────────────────── the business

@lru_cache(maxsize=1)
def business() -> dict:
    return json.loads(BUSINESS_PATH.read_text(encoding="utf-8"))


def technician_name(number: str) -> str:
    """The name printed under 'Quoted by'. An unlisted technician still works — his
    number is printed instead, which is better than a blank line on a document."""
    return business().get("technicians", {}).get(number) or display_phone(number) or number


# ───────────────────────────────────────────────────────────── formatting basics

def today() -> date:
    return datetime.now(TZ).date()


def now_iso() -> str:
    return datetime.now(TZ).isoformat()


def fmt_date(d) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return f"{d.day} {_MONTHS[d.month - 1][:3]} {d.year}"


def fmt_money(amount, currency: str = "ZAR") -> str:
    """'R 11 500.00' — space as the thousands separator, the way prices are written
    here and the way the existing Boschly invoices already read."""
    if amount is None:
        return ""
    symbol = "R" if currency == "ZAR" else f"{currency} "
    whole, cents = f"{float(amount):,.2f}".split(".")
    return f"{symbol} {whole.replace(',', ' ')}.{cents}"


def first_name(full) -> str:
    return (str(full or "").strip().split() or ["there"])[0]


# ───────────────────────────────────────────────────────────────────────── phones

def normalize_sa_phone(raw):
    """Anything a technician might type → E.164, or None if it cannot be a number.

    He types '076 389 7179', '0763897179', '+27 76 389 7179', '27763897179'. All four
    are the same phone and all four have to come out identical, because the customer's
    number is how their reply is matched back to their quote.
    """
    if not raw:
        return None
    text = str(raw).strip()
    plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    if plus:
        return f"+{digits}" if len(digits) >= 10 else None
    if len(digits) == 10 and digits.startswith("0"):
        return f"+27{digits[1:]}"
    if len(digits) == 11 and digits.startswith("27"):
        return f"+{digits}"
    if len(digits) == 9 and digits[0] in "678":
        return f"+27{digits}"
    return None


def display_phone(e164) -> str:
    """Back to the way it is written on a business card: 076 389 7179."""
    if not e164:
        return ""
    text = str(e164)
    if text.startswith("+27") and len(text) == 12:
        n = "0" + text[3:]
        return f"{n[:3]} {n[3:6]} {n[6:]}"
    return text


def is_whatsapp_capable(e164) -> bool:
    """Only South African mobiles reach WhatsApp: 06x, 07x and 081-084.

    086 and 087 are share-call numbers. They look like mobiles, they get quoted like
    mobiles, and a WhatsApp to one fails silently — so nobody finds out the quote
    never arrived. Which is the exact failure this system exists to remove.
    """
    text = str(e164 or "")
    if not text.startswith("+27"):
        return True          # not South African; we cannot judge, so let it through
    national = text[3:]
    if not national:
        return False
    if national[0] in "67":
        return True
    return national[0] == "8" and len(national) > 1 and national[1] in "1234"


def why_no_whatsapp(e164) -> str:
    """Name the actual reason. 'That number will not work' invites an argument;
    'that is a share-call number, not a mobile' ends one."""
    text = str(e164 or "")
    national = text[3:] if text.startswith("+27") else ""
    if national.startswith(("86", "87")):
        return "086 and 087 are share-call numbers, not mobiles"
    if national[:1] in ("1", "2", "3", "4", "5"):
        return "that is a landline"
    return "it is not a South African mobile"


# ─────────────────────────────────────────── what the technician sees on WhatsApp

def summary_card(job: dict) -> str:
    """The figures, rendered by code so they cannot drift from the PDF.

    The model writes the sentence around this ("Got it.", "Nice one, that's her
    sorted."). It never writes a price. A model that paraphrases R11 500 as R11 000
    cannot cost anyone money if it is never asked to type a price at all.
    """
    currency = job.get("currency") or "ZAR"
    lines = [f"*{job.get('customer_name') or 'Customer'}*"]

    contact = [c for c in (display_phone(job.get("customer_phone")),
                           job.get("customer_email")) if c]
    if contact:
        lines.append(" · ".join(contact))
    if job.get("site_address"):
        lines.append(str(job["site_address"]))

    lines.append("")
    for item in job.get("line_items") or []:
        amount = item.get("amount")
        suffix = f"  —  {fmt_money(amount, currency)}" if amount is not None else ""
        lines.append(f"• {item.get('description', '')}{suffix}")

    lines += ["", f"*Total: {fmt_money(job.get('total'), currency)}*"]
    if job.get("notes"):
        lines += ["", f"_{job['notes']}_"]
    return "\n".join(lines)


# ───────────────────────────────────────────── what the customer sees on WhatsApp

def payment_policy() -> dict:
    return business().get("payment") or {}


# The four fields that make a South African EFT possible. Anything less is not a
# banking section, it is a half-written one on a customer's screen.
_BANK_FIELDS = ("bank", "account_name", "account_number", "branch_code")


def banking_details():
    """The EFT details, or None while they are still placeholders.

    Deliberately fails CLOSED. An unfinished banking block is worse than no banking
    block: a customer who tries to pay a made-up account number loses money and trust
    in the same afternoon, and it is the business that gets the phone call. So the
    section only renders once every field has been filled in with something that is
    not obviously a placeholder.
    """
    details = business().get("banking") or {}
    values = [str(details.get(f) or "").strip() for f in _BANK_FIELDS]
    if not all(values):
        return None
    if any(v.upper().startswith("FILL") or "FILL IN" in v.upper() for v in values):
        return None
    return details


def deposit_for(quote: dict):
    """What the customer is asked for up front, in rand — or None for no link at all.

    `deposit_percent` 0 (or `enabled` false) switches payments off without touching
    code, which is how Zaheer turns it off for a job type that is settled on
    completion. Nothing else in the system decides whether to charge.
    """
    policy = payment_policy()
    if not policy.get("enabled"):
        return None
    percent = Decimal(str(policy.get("deposit_percent") or 0))
    total = Decimal(str(quote.get("total") or 0))
    if percent <= 0 or total <= 0:
        return None

    # At 100% the answer is the total, exactly, with no arithmetic in between.
    # Not a shortcut -- rounding it would be wrong. A total of R1 234.565 quantized
    # HALF_UP comes back R1 234.57, which asks the customer for half a cent MORE than
    # the job they agreed to. Rare, but "we charged you more than the quote" is the
    # one arithmetic error a quoting system must never make.
    if percent >= 100:
        return float(total)

    # Below 100, Decimal and ROUND_HALF_UP, matching services/payments.to_cents
    # exactly. Half of R2 499.99 is R1 249.995, and in plain floats round() answers
    # R1 249.99 -- the deposit and the balance then no longer add up to the quote.
    return float((total * percent / 100).quantize(Decimal("0.01"),
                                                  rounding=ROUND_HALF_UP))


def deposit_is_full(quote: dict = None) -> bool:
    """At 100% it is not a deposit, it is the bill — and calling it a deposit on a
    customer's phone is the kind of small wrongness that costs trust."""
    return float(payment_policy().get("deposit_percent") or 0) >= 100


def _payment_copy(quote: dict, key: str) -> str:
    """Pick the deposit or the full-amount wording for the same slot.

    Falls back to the deposit wording when the full-amount one is missing, rather
    than returning "". That fallback is not tidiness — two of these keys were once
    named `web_button_full` instead of `full_web_button`, so at 100% the lookup
    missed and the customer's Pay button rendered as a green rectangle with no words
    on it. Slightly wrong wording is a typo; an unlabelled button is a dead end on
    the one screen that has to work.
    """
    policy = payment_policy()
    if deposit_is_full():
        return policy.get(f"full_{key}") or policy.get(key, "")
    return policy.get(key, "")


def _fill(template: str, quote: dict) -> str:
    biz = business()
    deposit = deposit_for(quote)
    return (str(template)
            .replace("{deposit}", fmt_money(deposit, quote.get("currency", "ZAR"))
                     if deposit is not None else "")
            .replace("{first_name}", first_name(quote.get("customer_name")))
            .replace("{business}", biz["name"])
            .replace("{short_name}", biz.get("short_name", biz["name"]))
            .replace("{quote_number}", str(quote.get("quote_number", "")))
            .replace("{total}", fmt_money(quote.get("total"), quote.get("currency", "ZAR")))
            .replace("{validity_days}", str(biz.get("validity_days", 30)))
            .replace("{phone}", biz.get("phone", ""))
            .replace("{email}", biz.get("email", "")))


def customer_message(quote: dict, link: str = "", with_attachment: bool = False,
                     payment_url: str = "") -> str:
    """The WhatsApp the customer gets: one short message carrying one link.

    It used to be the whole quote — every line item, the total, the promises, an
    attached PDF and a second Paystack URL underneath. That is three things to look
    at and a document a phone opens in a viewer she then has to back out of, and the
    two links competed with each other.

    Now the link IS the quote. It opens a branded page with the line items, the
    banking details and one big Pay button, so there is a single thing to tap. The
    message only has to earn that tap: who it is from, what it is, what it costs.

    `with_attachment` and `payment_url` are kept so nothing that calls this breaks,
    but neither adds a second link any more — the page carries the payment.
    """
    biz = business()
    copy = biz["customer_message"]

    parts = [_fill(copy["greeting"], quote), "",
             _fill(copy["thanks"], quote),
             _fill(copy["intro"], quote), ""]

    if link:
        parts += [_fill(copy.get("link_line", "Tap here to view it:"), quote), link, ""]

    # Normally empty. It is filled only when the payment link could NOT be stored on
    # the quote, which means the page will render without a Pay button — so the raw
    # checkout URL comes here instead rather than leaving her no way to pay at all.
    if payment_url:
        parts += [_fill(_payment_copy(quote, "quote_line"), quote), payment_url, ""]

    parts += [_fill(copy.get("validity", ""), quote), "",
              _fill(copy["cta"], quote), "", _fill(copy["signoff"], quote)]
    return "\n".join(p for p in parts if p is not None)


def customer_email(quote: dict, link: str = "") -> tuple:
    """(subject, body) for the emailed copy, with the same PDF attached."""
    biz = business()
    copy = biz["customer_email"]
    promises = "\n".join(f"  • {p}" for p in biz.get("promises", []))
    body = _fill(copy["body"], quote).replace("{promises}", promises)
    if link:
        body += f"\n\nYou can also view it online:\n{link}"
    return _fill(copy["subject"], quote), body


def customer_ack(quote: dict, accepted: bool, payment_url: str = "") -> str:
    """What the customer hears back when they reply.

    A yes with an unpaid link attached gets the link again. Saying yes and then waiting
    for someone to send banking details is the same failure as a quote that never
    arrives, one step later on.
    """
    copy = business()["customer_reply_ack"]
    text = _fill(copy["accepted" if accepted else "other"], quote)
    if accepted and payment_url:
        text += "\n\n" + _fill(_payment_copy(quote, "accept_line"), quote) + "\n" + payment_url
    return text


def payment_received_ack(quote: dict) -> str:
    return _fill(payment_policy().get("paid_ack", "Payment received, thank you."), quote)


_EMAIL_SHAPE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def looks_like_an_email(value) -> bool:
    """Good enough to catch what Paystack rejects, without pretending to be RFC 5322."""
    text = str(value or "").strip()
    if not _EMAIL_SHAPE.match(text):
        return False
    # Reserved TLDs (RFC 2606). They look valid and every payment gateway refuses them.
    return not text.lower().endswith((".invalid", ".test", ".example", ".localhost"))


def receipt_email(quote: dict) -> str:
    """Where Paystack should send the payment receipt.

    Paystack REQUIRES an email on every transaction, and most jobs are quoted with a
    name, a number and a price — no address. The first version invented
    `{reference}@quotes.invalid`, which Paystack rejects outright with "Invalid Email
    Address Passed", so no link was ever created for those jobs. The quote still went
    out, so it looked like the payment link had simply been forgotten.

    Falling back to the BUSINESS's own address is both deliverable and correct: if the
    customer gave us no email, the receipt belongs with the people who did the work.
    """
    customer = str(quote.get("customer_email") or "").strip()
    if looks_like_an_email(customer):
        return customer
    biz = business()
    fallback = (payment_policy().get("receipt_fallback_email") or "").strip()
    if looks_like_an_email(fallback):
        return fallback
    if looks_like_an_email(biz.get("email")):
        return biz["email"]
    return ""


# ────────────────────────────────────────────────────────────────────────── the PDF

_SUBS = {
    "—": "-", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "•": "-", "…": "...",
    " ": " ", "✓": "-", "·": "-",
}


def _pdf_text(value) -> str:
    """fpdf2's core fonts are latin-1. Typographic characters fold to their plain
    equivalents; anything left over (an emoji in a job description, say) is dropped
    rather than printed as a box or raising mid-render."""
    text = str(value if value is not None else "")
    for fancy, plain in _SUBS.items():
        text = text.replace(fancy, plain)
    return text.encode("latin-1", "ignore").decode("latin-1")


class _Quote(FPDF):
    """Absolute positioning throughout — every element goes at a known x/y rather
    than flowing, so the layout cannot drift when one description wraps to two lines."""

    def txt(self, x, y, text, size=9.5, style="", color=None, w=0, align="L"):
        color = ink() if color is None else color
        self.set_xy(x, y)
        self.set_font("Helvetica", style, size)
        self.set_text_color(*color)
        self.cell(w, 5, _pdf_text(text), align=align)

    def para(self, x, y, w, text, size=8.5, color=MUTED, height=4.2) -> float:
        self.set_xy(x, y)
        self.set_font("Helvetica", "", size)
        self.set_text_color(*color)
        self.multi_cell(w, height, _pdf_text(text))
        return self.get_y()

    def rule(self, x, y, w, color=RULE, weight=0.25):
        self.set_draw_color(*color)
        self.set_line_width(weight)
        self.line(x, y, x + w, y)

    def label(self, x, y, text, w=0, align="L"):
        """Small-caps section label. Uppercase plus grey does the job of letterspacing,
        which the core fonts cannot do."""
        self.txt(x, y, str(text).upper(), size=7, style="B", color=MUTED, w=w, align=align)


def render_pdf(quote: dict) -> bytes:
    biz = business()
    currency = quote.get("currency", "ZAR")
    pdf = _Quote(format="A4", unit="mm")
    pdf.set_auto_page_break(False)
    pdf.set_title(_pdf_text(f"{quote.get('quote_number', 'Quote')} - {biz['name']}"))
    pdf.add_page()

    # ── header band
    pdf.set_fill_color(*ink())
    pdf.rect(0, 0, 210, 42, "F")
    pdf.txt(15, 11, biz["name"], size=19, style="B", color=(255, 255, 255))
    pdf.txt(15, 22, biz.get("tagline", ""), size=8.5, color=(150, 162, 176))
    # A light tint of the brand rather than a fixed blue, which clashed the moment the
    # brand stopped being blue. Mixed toward white so it stays legible on the dark band.
    pdf.txt(115, 11.5, "QUOTATION", size=8, style="B", color=_tint(accent(), 0.55),
            w=80, align="R")
    pdf.txt(115, 19, quote.get("quote_number", ""), size=15, style="B",
            color=(255, 255, 255), w=80, align="R")
    pdf.txt(115, 28, fmt_date(quote.get("issued_date") or today()), size=8.5,
            color=(150, 162, 176), w=80, align="R")

    # ── who it is for, and the particulars
    y = 56
    pdf.label(15, y, "Quoted for")
    pdf.txt(15, y + 6, quote.get("customer_name", ""), size=12, style="B")
    detail_y = y + 13
    for line in (display_phone(quote.get("customer_phone")),
                 quote.get("customer_email"), quote.get("site_address")):
        if line:
            pdf.txt(15, detail_y, line, size=9.5, color=(70, 80, 92))
            detail_y += 5

    pdf.label(120, y, "Details")
    row_y = y + 7
    for key, value in (("Date issued", fmt_date(quote.get("issued_date") or today())),
                       ("Valid until", fmt_date(quote["valid_until"])
                        if quote.get("valid_until") else ""),
                       ("Quoted by", quote.get("quoted_by_name", ""))):
        if not value:
            continue
        pdf.txt(120, row_y, key, size=8.5, color=MUTED)
        pdf.txt(120, row_y, value, size=9, style="B", w=75, align="R")
        row_y += 5.6

    # ── the work
    y = max(detail_y, row_y) + 10
    pdf.label(15, y, "Description")
    pdf.label(120, y, "Amount", w=75, align="R")
    y += 7
    pdf.rule(15, y, 180, color=ink(), weight=0.4)
    y += 4

    for item in quote.get("line_items") or []:
        if y > 232:                       # keep the total and terms on this page
            pdf.add_page()
            y = 20
        amount = item.get("amount")
        end = pdf.para(15, y, 100, item.get("description", ""), size=10,
                       color=(35, 42, 52), height=5)
        if amount is not None:
            pdf.txt(120, y, fmt_money(amount, currency), size=10, w=75, align="R")
        y = max(end, y + 5) + 3.5
        pdf.rule(15, y - 1.5, 180)

    # ── the total
    y += 3
    pdf.set_fill_color(*PAPER_MUTED)
    pdf.rect(110, y, 85, 14, "F")
    pdf.txt(116, y + 4.5, "Total", size=10, style="B", color=(70, 80, 92))
    pdf.txt(116, y + 4, fmt_money(quote.get("total"), currency), size=13.5,
            style="B", color=ink(), w=73, align="R")
    y += 18

    if biz.get("vat_registered") and biz.get("vat_number"):
        pdf.txt(110, y, f"VAT inclusive. VAT no. {biz['vat_number']}", size=8,
                color=MUTED, w=85, align="R")
        y += 6
    # If VAT is not confirmed the document says nothing about it. Claiming either way
    # would put an unverified number on a legal document.

    if quote.get("notes"):
        pdf.label(15, y, "Notes")
        y = pdf.para(15, y + 6, 180, quote["notes"], size=9, color=(70, 80, 92)) + 5

    # ── the promises
    # Anchored near the foot of the page so the closing block sits in the same place
    # on every quote, however much work is listed above it.
    y = max(y + 6, 196)
    promises = biz.get("promises", [])
    box_h = 10 + len(promises) * 6.5
    pdf.set_fill_color(*PAPER_MUTED)
    pdf.rect(15, y, 180, box_h, "F")
    py = y + 5
    for promise in promises:
        pdf.set_fill_color(*accent())
        pdf.ellipse(21, py + 1.9, 1.6, 1.6, "F")
        pdf.txt(26, py, promise, size=9, color=(45, 54, 66))
        py += 6.5
    y += box_h + 8

    # ── terms and how to accept
    terms = biz.get("terms", "").replace("{validity_days}",
                                         str(biz.get("validity_days", 30)))
    y = pdf.para(15, y, 180, terms, size=8, color=MUTED) + 2
    y = pdf.para(15, y, 180, biz["customer_message"]["cta"].replace("*", ""),
                 size=8.5, color=(45, 54, 66))

    # The document names the deposit but never carries the link itself: a PDF gets
    # forwarded, printed and filed, and a live payment URL sitting in a filing cabinet
    # is a way to be paid twice for one job.
    if quote.get("payment_url") and deposit_for(quote) is not None:
        pdf.para(15, y, 180, _fill(_payment_copy(quote, "pdf_line"), quote),
                 size=8.5, color=(45, 54, 66))

    # ── footer
    pdf.rule(15, 277, 180)
    foot = " · ".join(filter(None, [
        ", ".join(biz.get("address_lines", [])),
        biz.get("phone", ""), biz.get("email", ""), biz.get("website", ""),
    ]))
    pdf.para(15, 280, 180, foot, size=7.5, color=MUTED, height=3.6)

    return bytes(pdf.output())


# ───────────────────────────────────────────────────────────────────── the web page

def _esc(value) -> str:
    return (str(value if value is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_html(quote: dict, pdf_url: str = "") -> str:
    """The page the customer opens — and now the ONLY thing she is sent.

    The WhatsApp used to carry the quote, a PDF and a payment link. It carries one
    link to here instead, so this page has to do all of it: prove who it is from,
    show the work and the price, offer the EFT details for people who will never tap
    a card button, and put one unmissable Pay at the end of the scroll.

    Ordered the way she reads it, not the way a document is laid out. The amount comes
    before the detail, because the first question is always "how much"; the Pay button
    sits after the line items rather than above them, because a button offered before
    she has seen what she is paying for reads as a demand.

    Colours come from quote_business.json, so re-skinning it for another client — or
    for FIXITT's real palette once it is confirmed — is a config edit.
    """
    biz = business()
    currency = quote.get("currency", "ZAR")
    brand = biz.get("brand") or {}
    ink = brand.get("ink", "#12161c")
    accent = brand.get("accent", "#1b6ef3")
    pay_colour = brand.get("pay", "#0b8f4d")

    items = "".join(
        f'<tr><td>{_esc(i.get("description"))}</td>'
        f'<td class="amt">{_esc(fmt_money(i.get("amount"), currency))}</td></tr>'
        for i in (quote.get("line_items") or [])
    )
    promises = "".join(f"<li>{_esc(p)}</li>" for p in biz.get("promises", []))
    trust = "".join(f"<span>{_esc(t)}</span>" for t in biz.get("trust", []))
    trust_strip = f'<div class="trust">{trust}</div>' if trust else ""
    contact = "<br>".join(x for x in (
        _esc(display_phone(quote.get("customer_phone"))),
        _esc(quote.get("customer_email")), _esc(quote.get("site_address"))) if x)
    download = (f'<a class="dl" href="{_esc(pdf_url)}">Download this quote as a PDF</a>'
                if pdf_url else "")

    # The pay button sits AFTER the work and the total, not before -- she has to see
    # what she is paying for first. Only rendered while the quote is actually unpaid;
    # showing "Pay now" on something already settled is how you get an angry call.
    pay = ""
    deposit = deposit_for(quote)
    paid = quote.get("payment_status") == "paid"
    if quote.get("payment_url") and deposit is not None and not paid:
        label = _fill(_payment_copy(quote, "web_button"), quote)
        pay = (f'<a class="pay" href="{_esc(quote["payment_url"])}">{_esc(label)}</a>'
               '<p class="secure">Secured by Paystack &middot; Visa, Mastercard '
               '&amp; instant EFT</p>')
    elif paid:
        pay = '<div class="paid">Paid in full — thank you</div>'

    # EFT details for the customers who will never tap a card button. Renders only
    # once the real account is filled in; see banking_details().
    bank = banking_details()
    banking_block = ""
    if bank and not paid:
        rows = "".join(
            f'<tr><td>{_esc(lbl)}</td><td class="bv">{_esc(bank.get(key, ""))}</td></tr>'
            for lbl, key in (("Bank", "bank"), ("Account name", "account_name"),
                             ("Account number", "account_number"),
                             ("Branch code", "branch_code")))
        reference = _esc(bank.get("reference_label") or "Use your quote number as the reference")
        banking_block = (
            '<div class="lbl">Rather pay by EFT?</div>'
            f'<table class="bank">{rows}'
            f'<tr><td>Reference</td><td class="bv">{_esc(quote.get("quote_number"))}</td></tr>'
            f'</table><p class="ref">{reference}</p>')
    terms = _esc(biz.get("terms", "").replace("{validity_days}",
                                              str(biz.get("validity_days", 30))))
    cta = _esc(biz["customer_message"]["cta"].replace("*", ""))
    address = _esc(", ".join(biz.get("address_lines", [])))

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_esc(quote.get('quote_number'))} &middot; {_esc(biz['name'])}</title>"
        "<style>"
        f":root{{--ink:{ink};--accent:{accent};--pay:{pay_colour};"
        "--muted:#7a8694;--rule:#dee4eb;--paper:#fff;--wash:#f6f8fa}"
        "*{box-sizing:border-box}"
        "body{margin:0;background:#eef1f5;color:var(--ink);"
        "font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
        "'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased}"
        ".sheet{max-width:640px;margin:0 auto;background:var(--paper);min-height:100vh}"
        # The header carries the identity: name, what they do, and the amount. She
        # should know who this is from and what it costs before she scrolls at all.
        "header{background:var(--ink);color:#fff;padding:28px 24px 26px}"
        "header h1{margin:0;font-size:22px;letter-spacing:-.3px;font-weight:700}"
        "header .tag{margin:6px 0 0;color:#9aa6b4;font-size:12.5px}"
        ".hero{margin-top:22px;padding-top:20px;border-top:1px solid rgba(255,255,255,.13)}"
        ".hero .cap{color:#9aa6b4;font-size:11px;letter-spacing:.1em;"
        "text-transform:uppercase;font-weight:700}"
        ".hero .big{font-size:34px;font-weight:800;letter-spacing:-1px;margin-top:4px}"
        ".hero .meta{color:#9aa6b4;font-size:12.5px;margin-top:6px}"
        ".trust{background:var(--wash);border-bottom:1px solid var(--rule);"
        "padding:13px 24px;display:flex;flex-wrap:wrap;gap:6px 16px}"
        ".trust span{color:var(--muted);font-size:11.5px;position:relative;"
        "padding-left:15px;line-height:1.45}"
        ".trust span::before{content:'\\2713';position:absolute;left:0;top:0;"
        "color:var(--ink);font-weight:700}"
        "main{padding:6px 24px 24px}"
        ".lbl{font-size:11px;letter-spacing:.1em;text-transform:uppercase;"
        "color:var(--muted);font-weight:700;margin:26px 0 8px}"
        "table{width:100%;border-collapse:collapse}"
        "td{padding:12px 0;border-bottom:1px solid var(--rule);vertical-align:top;"
        "font-size:15px}"
        ".amt{text-align:right;white-space:nowrap;padding-left:14px;font-variant-numeric:"
        "tabular-nums}"
        ".total{display:flex;justify-content:space-between;align-items:center;"
        "background:var(--wash);padding:16px 18px;margin-top:18px;border-radius:10px}"
        ".total b{font-size:22px;font-variant-numeric:tabular-nums}"
        "ul{list-style:none;padding:0;margin:14px 0 0}"
        "ul li{padding:7px 0 7px 25px;position:relative;font-size:14.5px}"
        "ul li::before{content:'';position:absolute;left:4px;top:14px;width:7px;"
        "height:7px;border-radius:50%;background:var(--accent)}"
        # The button people came to press. Full width, high contrast, and it sticks to
        # the bottom of the viewport on a phone so it is never more than a thumb away.
        ".pay{display:block;text-align:center;background:var(--pay);color:#fff;"
        "text-decoration:none;padding:19px;border-radius:11px;font-weight:800;"
        "font-size:18px;letter-spacing:-.2px;margin:26px 0 8px;"
        "box-shadow:0 6px 16px rgba(0,0,0,.20)}"
        ".pay:active{transform:translateY(1px)}"
        ".secure{text-align:center;color:var(--muted);font-size:12px;margin:0 0 6px}"
        ".paid{text-align:center;background:#e8f6ee;color:#0b6b3a;padding:17px;"
        "border-radius:11px;font-weight:800;margin:26px 0}"
        ".bank td{font-size:14px}.bank .bv{text-align:right;font-weight:600;"
        "font-variant-numeric:tabular-nums}"
        ".ref{color:var(--muted);font-size:12px;margin:8px 0 0}"
        ".dl{display:block;text-align:center;border:1px solid var(--rule);"
        "color:var(--ink);text-decoration:none;padding:14px;border-radius:10px;"
        "font-weight:600;margin:22px 0 0;font-size:14.5px}"
        ".terms{color:var(--muted);font-size:12.5px;margin-top:20px}"
        "footer{border-top:1px solid var(--rule);margin-top:26px;padding:20px 24px 44px;"
        "color:var(--muted);font-size:12px;line-height:1.7}"
        "@media(prefers-color-scheme:dark){body{background:#0b0e12}"
        ".sheet{background:#151a21;color:#e7ecf2}"
        ":root{--paper:#151a21;--wash:#1c232c;--rule:#252c36}"
        "td{border-color:#252c36}.trust{background:#11161d;border-color:#252c36}"
        ".dl{border-color:#2b3542}footer{border-color:#252c36}}"
        "</style></head><body><div class=\"sheet\"><header>"
        f"<h1>{_esc(biz['name'])}</h1>"
        f"<p class=\"tag\">{_esc(biz.get('tagline', ''))}</p>"
        "<div class=\"hero\"><div class=\"cap\">Your quote</div>"
        f"<div class=\"big\">{_esc(fmt_money(quote.get('total'), currency))}</div>"
        f"<div class=\"meta\">{_esc(quote.get('quote_number'))} &middot; "
        f"{_esc(fmt_date(quote.get('issued_date') or today()))} &middot; "
        f"valid {_esc(str(biz.get('validity_days', 30)))} days</div>"
        "</div></header>"
        f"{trust_strip}<main>"
        "<div class=\"lbl\">Prepared for</div>"
        f"<div><strong>{_esc(quote.get('customer_name'))}</strong><br>{contact}</div>"
        "<div class=\"lbl\">The work</div>"
        f"<table>{items}</table>"
        "<div class=\"total\"><span>Total</span>"
        f"<b>{_esc(fmt_money(quote.get('total'), currency))}</b></div>"
        f"{pay}{banking_block}"
        "<div class=\"lbl\">What you get</div>"
        f"<ul>{promises}</ul>{download}"
        f"<p class=\"terms\">{terms}</p><p class=\"terms\">{cta}</p>"
        "</main><footer>"
        f"<strong>{_esc(biz['name'])}</strong><br>{address}<br>"
        f"{_esc(biz.get('phone', ''))} &middot; "
        f"{_esc(biz.get('email', ''))} &middot; {_esc(biz.get('website', ''))}"
        "</footer></div></body></html>"
    )
