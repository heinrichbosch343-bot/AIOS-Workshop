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
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF

TZ = ZoneInfo("Africa/Johannesburg")
BUSINESS_PATH = Path(__file__).parent.parent / "quote_business.json"

_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]

# The document's palette: near-black, one steel accent, greys for everything else.
INK = (18, 22, 28)
ACCENT = (27, 110, 243)
MUTED = (122, 134, 148)
RULE = (222, 228, 235)
PAPER_MUTED = (246, 248, 250)


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

def _fill(template: str, quote: dict) -> str:
    biz = business()
    return (str(template)
            .replace("{first_name}", first_name(quote.get("customer_name")))
            .replace("{business}", biz["name"])
            .replace("{short_name}", biz.get("short_name", biz["name"]))
            .replace("{quote_number}", str(quote.get("quote_number", "")))
            .replace("{total}", fmt_money(quote.get("total"), quote.get("currency", "ZAR")))
            .replace("{validity_days}", str(biz.get("validity_days", 30)))
            .replace("{phone}", biz.get("phone", ""))
            .replace("{email}", biz.get("email", "")))


def customer_message(quote: dict, link: str = "", with_attachment: bool = True) -> str:
    """The WhatsApp the customer gets. The copy comes from quote_business.json; the
    line items and total are rendered here so they always match the attached PDF."""
    biz = business()
    copy = biz["customer_message"]
    currency = quote.get("currency", "ZAR")

    parts = [_fill(copy["greeting"], quote), "", _fill(copy["thanks"], quote), "",
             _fill(copy["intro"], quote), ""]

    for item in quote.get("line_items") or []:
        amount = item.get("amount")
        suffix = f"  —  {fmt_money(amount, currency)}" if amount is not None else ""
        parts.append(f"• {item.get('description', '')}{suffix}")

    parts += ["", f"*Total: {fmt_money(quote.get('total'), currency)}*", ""]

    if with_attachment:
        parts.append(_fill(copy["attached"], quote))
        if link:
            parts.append(link)
    elif link:
        # No PDF attached, so the link IS the quote and has to carry the weight.
        parts.append("Your full quote is here — it's valid for "
                     f"{biz.get('validity_days', 30)} days:\n{link}")
    parts.append("")

    for promise in biz.get("promises", []):
        parts.append(f"✓ {promise}")

    parts += ["", _fill(copy["cta"], quote), "", _fill(copy["signoff"], quote)]
    return "\n".join(parts)


def customer_email(quote: dict, link: str = "") -> tuple:
    """(subject, body) for the emailed copy, with the same PDF attached."""
    biz = business()
    copy = biz["customer_email"]
    promises = "\n".join(f"  • {p}" for p in biz.get("promises", []))
    body = _fill(copy["body"], quote).replace("{promises}", promises)
    if link:
        body += f"\n\nYou can also view it online:\n{link}"
    return _fill(copy["subject"], quote), body


def customer_ack(quote: dict, accepted: bool) -> str:
    copy = business()["customer_reply_ack"]
    return _fill(copy["accepted" if accepted else "other"], quote)


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

    def txt(self, x, y, text, size=9.5, style="", color=INK, w=0, align="L"):
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
    pdf.set_fill_color(*INK)
    pdf.rect(0, 0, 210, 42, "F")
    pdf.txt(15, 11, biz["name"], size=19, style="B", color=(255, 255, 255))
    pdf.txt(15, 22, biz.get("tagline", ""), size=8.5, color=(150, 162, 176))
    pdf.txt(115, 11.5, "QUOTATION", size=8, style="B", color=(120, 170, 255),
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
    pdf.rule(15, y, 180, color=INK, weight=0.4)
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
            style="B", color=INK, w=73, align="R")
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
        pdf.set_fill_color(*ACCENT)
        pdf.ellipse(21, py + 1.9, 1.6, 1.6, "F")
        pdf.txt(26, py, promise, size=9, color=(45, 54, 66))
        py += 6.5
    y += box_h + 8

    # ── terms and how to accept
    terms = biz.get("terms", "").replace("{validity_days}",
                                         str(biz.get("validity_days", 30)))
    y = pdf.para(15, y, 180, terms, size=8, color=MUTED) + 2
    pdf.para(15, y, 180, biz["customer_message"]["cta"].replace("*", ""),
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
    """The same quote as a phone-friendly page: what the customer taps, and the
    fallback whenever the PDF could not be attached."""
    biz = business()
    currency = quote.get("currency", "ZAR")

    items = "".join(
        f'<tr><td>{_esc(i.get("description"))}</td>'
        f'<td class="amt">{_esc(fmt_money(i.get("amount"), currency))}</td></tr>'
        for i in (quote.get("line_items") or [])
    )
    promises = "".join(f"<li>{_esc(p)}</li>" for p in biz.get("promises", []))
    contact = "<br>".join(x for x in (
        _esc(display_phone(quote.get("customer_phone"))),
        _esc(quote.get("customer_email")), _esc(quote.get("site_address"))) if x)
    download = (f'<a class="dl" href="{_esc(pdf_url)}">Download the PDF</a>'
                if pdf_url else "")
    terms = _esc(biz.get("terms", "").replace("{validity_days}",
                                              str(biz.get("validity_days", 30))))
    cta = _esc(biz["customer_message"]["cta"].replace("*", ""))
    address = _esc(", ".join(biz.get("address_lines", [])))

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        f"<title>{_esc(quote.get('quote_number'))} &middot; {_esc(biz['name'])}</title>"
        "<style>"
        ":root{--ink:#12161c;--accent:#1b6ef3;--muted:#7a8694;--rule:#dee4eb}"
        "*{box-sizing:border-box}"
        "body{margin:0;background:#eef1f5;color:var(--ink);"
        "font:16px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}"
        ".sheet{max-width:720px;margin:0 auto;background:#fff;min-height:100vh}"
        "header{background:var(--ink);color:#fff;padding:26px 22px}"
        "header h1{margin:0;font-size:21px;letter-spacing:-.2px}"
        "header p{margin:5px 0 0;color:#96a2b0;font-size:13px}"
        ".num{margin-top:16px;display:flex;justify-content:space-between;align-items:baseline}"
        ".num strong{font-size:20px}.num span{color:#96a2b0;font-size:13px}"
        "main{padding:22px}"
        ".lbl{font-size:11px;letter-spacing:.09em;text-transform:uppercase;"
        "color:var(--muted);font-weight:700;margin:22px 0 7px}"
        "table{width:100%;border-collapse:collapse}"
        "td{padding:11px 0;border-bottom:1px solid var(--rule);vertical-align:top}"
        ".amt{text-align:right;white-space:nowrap;padding-left:14px}"
        ".total{display:flex;justify-content:space-between;align-items:center;"
        "background:#f6f8fa;padding:15px 17px;margin-top:16px;border-radius:9px}"
        ".total b{font-size:21px}"
        "ul{list-style:none;padding:0;margin:16px 0}"
        "ul li{padding:8px 0 8px 25px;position:relative;font-size:14.5px}"
        "ul li::before{content:'';position:absolute;left:4px;top:14px;width:7px;"
        "height:7px;border-radius:50%;background:var(--accent)}"
        ".dl{display:block;text-align:center;background:var(--accent);color:#fff;"
        "text-decoration:none;padding:14px;border-radius:9px;font-weight:600;margin:22px 0}"
        ".terms{color:var(--muted);font-size:12.5px;margin-top:22px}"
        "footer{border-top:1px solid var(--rule);margin-top:26px;padding:18px 22px 40px;"
        "color:var(--muted);font-size:12px}"
        "@media(prefers-color-scheme:dark){body{background:#0b0e12}"
        ".sheet{background:#151a21;color:#e7ecf2}td{border-color:#252c36}"
        ".total{background:#1c232c}footer{border-color:#252c36}}"
        "</style></head><body><div class=\"sheet\"><header>"
        f"<h1>{_esc(biz['name'])}</h1><p>{_esc(biz.get('tagline', ''))}</p>"
        f"<div class=\"num\"><strong>{_esc(quote.get('quote_number'))}</strong>"
        f"<span>{_esc(fmt_date(quote.get('issued_date') or today()))}</span></div>"
        "</header><main>"
        "<div class=\"lbl\">Quoted for</div>"
        f"<div><strong>{_esc(quote.get('customer_name'))}</strong><br>{contact}</div>"
        "<div class=\"lbl\">The work</div>"
        f"<table>{items}</table>"
        "<div class=\"total\"><span>Total</span>"
        f"<b>{_esc(fmt_money(quote.get('total'), currency))}</b></div>"
        f"{download}<ul>{promises}</ul>"
        f"<p class=\"terms\">{terms}</p><p class=\"terms\">{cta}</p>"
        "</main><footer>"
        f"{address}<br>{_esc(biz.get('phone', ''))} &middot; "
        f"{_esc(biz.get('email', ''))} &middot; {_esc(biz.get('website', ''))}"
        "</footer></div></body></html>"
    )
