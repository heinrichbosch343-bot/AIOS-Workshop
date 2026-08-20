"""Turn a technician's messy WhatsApp message into a real quote document.

The premise: the person who already knows the price is standing in the driveway.
Every hour that number spends travelling back to an office is an hour the customer
spends phoning a competitor. So the technician says it once, in whatever words come
out, and this turns it into a numbered PDF the customer can act on.

Nothing sends without a human replying SEND. The parse is always a draft.
"""
import json
import os
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

from config import ANTHROPIC_API_KEY

TZ = ZoneInfo("Africa/Johannesburg")
_BASE = Path(__file__).parent.parent
TEMPLATE_PATH = _BASE / "templates" / "quote.html"
BUSINESS_PATH = _BASE / "quote_business.json"

# The model every other service in this backend is proven on. QUOTE_PARSING_MODEL
# overrides it — claude-sonnet-5 is newer, but a demo is a bad place to find out
# whether a model id is enabled on the account.
MODEL = os.getenv("QUOTE_PARSING_MODEL", "claude-sonnet-4-6")

_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


# --------------------------------------------------------------- business config

def business() -> dict:
    """Read on every call, so editing the JSON takes effect without a redeploy."""
    return json.loads(BUSINESS_PATH.read_text(encoding="utf-8"))


# -------------------------------------------------------------------- formatting

def fmt_money(amount: float, currency: str = "ZAR") -> str:
    """R 11 500.00 -- space thousands separator, matching the invoices we already send."""
    symbol = "R" if currency == "ZAR" else currency + " "
    whole, cents = f"{float(amount):,.2f}".split(".")
    return f"{symbol} {whole.replace(',', ' ')}.{cents}"


def fmt_date(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1][:3]} {d.year}"


def normalize_sa_phone(raw):
    """South African numbers into E.164. Returns None if it cannot be trusted.

    A wrong number here sends a customer's quote to a stranger, so anything
    ambiguous fails rather than guesses.
    """
    if not raw:
        return None
    digits = re.sub(r"[^\d+]", "", str(raw))
    if digits.startswith("+27") and len(digits) == 12:
        return digits
    if digits.startswith("27") and len(digits) == 11:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+27" + digits[1:]
    if len(digits) == 9 and digits[0] in "678":
        return "+27" + digits
    if digits.startswith("+") and 10 <= len(digits) <= 16:
        return digits  # already international, some other country
    return None


def display_phone(e164) -> str:
    """E.164 is how machines address a phone; nobody writes their own number that way.
    On a customer-facing document +27825551234 reads as a reference code, so South
    African numbers go back to 082 555 1234."""
    if not e164:
        return ""
    if e164.startswith("+27") and len(e164) == 12:
        n = e164[3:]
        return f"0{n[:2]} {n[2:5]} {n[5:]}"
    return e164


def technician_name(number: str) -> str:
    """Who to print under 'Quoted by'. Falls back to the number, which is still
    better than an empty box on a document a customer keeps."""
    people = business().get("technicians") or {}
    return people.get(number) or display_phone(number) or "On site"


def is_whatsapp_capable(e164) -> bool:
    """Only South African mobiles reach WhatsApp: 06x, 07x and 081-084.

    Everything else fails, and the two ways it fails are both silent. A landline
    (021, 011) obviously has no WhatsApp. Worse are 086 and 087 share-call numbers:
    they look like mobiles, the message appears to send, and it is never delivered
    or bounced. FIXITT's own published glass line is an 087, which is exactly how
    this became a rule rather than a nicety.
    """
    if not e164 or not e164.startswith("+27"):
        return True  # not our rule to apply outside SA
    national = e164[3:]
    if not national:
        return False
    if national[0] in "67":
        return True
    return national[0] == "8" and len(national) > 1 and national[1] in "1234"


# ---------------------------------------------------------------------- the parse

_PARSE_SYSTEM = """You turn a tradesman's rough WhatsApp message into structured quote data.

He is standing on site. He types fast, abbreviates, mixes English and Afrikaans, and puts
things in any order. Never ask him to be tidier -- read what he meant.

Return ONLY a JSON object. No prose, no code fence:

{
  "customer_name": string or null,
  "customer_phone": string or null,
  "customer_email": string or null,
  "site_address": string or null,
  "line_items": [ { "description": string, "amount": number or null } ],
  "total": number or null,
  "notes": string or null
}

Rules:
- Write descriptions up properly, for a customer to read. "2 slidin panels lounge 1.8x2.1
  6.38 lam" becomes "Supply and install 2 sliding panels, lounge -- 1800 x 2100mm, 6.38mm
  laminated safety glass". Expand trade shorthand. Keep every measurement and spec exactly
  as given. Never invent a spec he did not state.
- Money: "11.5k", "R11 500" and "eleven and a half thousand" all mean 11500.
- One lump sum for the whole job is one line item, and the total.
- If items carry their own prices, the total is their sum unless he states otherwise.
- Never invent a price, a name, an email or a phone number. Missing means null.
- "incl labour" belongs inside the description, not as a separate line item.
- notes is for anything that belongs on the quote but is not a priced item, such as
  access arrangements or lead times."""


def parse_message(text: str, prior=None) -> dict:
    """Message in, structured quote out. `prior` is an existing draft being corrected."""
    if prior:
        prompt = (
            "The current draft is:\n"
            + json.dumps(prior, indent=2)
            + "\n\nHe has just sent a correction:\n"
            + text
            + "\n\nApply it and return the COMPLETE corrected object, not just the change."
        )
    else:
        prompt = text

    resp = _ai.messages.create(
        model=MODEL, max_tokens=1500, system=_PARSE_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    data = json.loads(raw)

    items = [i for i in (data.get("line_items") or []) if i.get("description")]
    total = data.get("total")
    if total is None and items and all(i.get("amount") is not None for i in items):
        total = sum(i["amount"] for i in items)
    if len(items) == 1 and items[0].get("amount") is None and total is not None:
        items[0]["amount"] = total
    data["line_items"], data["total"] = items, total

    missing = []
    if not data.get("customer_name"):
        missing.append("customer name")
    if not normalize_sa_phone(data.get("customer_phone")):
        missing.append("a valid mobile number")
    if not items:
        missing.append("what the job is")
    if total is None:
        missing.append("the price")
    data["missing"] = missing
    return data


# --------------------------------------------------------------------- numbering

_seq_cache = {}


def next_quote_number(prefix: str, today_: date) -> str:
    """PREFIX-YYYY-NNN, continuing from the highest already issued this year.

    Prefers the `quotes` table so numbering survives a redeploy; falls back to an
    in-process counter when that table does not exist yet (migration 013). The
    fallback is fine for a demo and wrong for a business.
    """
    year = today_.year
    try:
        from db.client import supabase
        rows = (supabase.table("quotes")
                .select("quote_number")
                .like("quote_number", f"{prefix}-{year}-%")
                .execute()).data
        seqs = []
        for r in rows:
            try:
                seqs.append(int(r["quote_number"].rsplit("-", 1)[-1]))
            except (ValueError, KeyError, TypeError):
                continue
        nxt = (max(seqs) + 1) if seqs else 1
    except Exception:
        key = f"{prefix}-{year}"
        nxt = _seq_cache.get(key, 0) + 1
        _seq_cache[key] = nxt
    return f"{prefix}-{year}-{nxt:03d}"


# --------------------------------------------------------------------- rendering

def _esc(s) -> str:
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_html(quote: dict) -> str:
    biz = business()
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    currency = biz.get("currency", "ZAR")

    rows = ""
    for i in quote["line_items"]:
        amount = (fmt_money(i["amount"], currency)
                  if i.get("amount") is not None else "&mdash;")
        rows += ('<tr><td><div class="item-h">' + _esc(i["description"])
                 + '</div></td><td class="r">' + amount + "</td></tr>")
    if quote.get("notes"):
        rows += ('<tr><td colspan="2"><div class="item-p">'
                 + _esc(quote["notes"]) + "</div></td></tr>")

    issued = date.fromisoformat(quote["issued_date"])
    valid_until = issued + timedelta(days=int(biz.get("validity_days", 30)))

    vat_note = ""
    if biz.get("vat_registered") and biz.get("vat_number"):
        vat_note = "Total includes VAT at 15%. VAT No. " + _esc(biz["vat_number"])

    address_lines = "".join(
        '<div class="line">' + _esc(l) + "</div>" for l in biz.get("address_lines", []))
    site_lines = "".join(
        '<div class="line">' + _esc(l) + "</div>"
        for l in (quote.get("site_address") or "").splitlines() if l.strip())

    tokens = {
        "{{BUSINESS_NAME}}": _esc(biz["name"]),
        "{{BUSINESS_TAGLINE}}": _esc(biz.get("tagline")),
        "{{BUSINESS_ADDRESS_LINES}}": address_lines,
        "{{BUSINESS_PHONE}}": _esc(biz.get("phone")),
        "{{BUSINESS_EMAIL}}": _esc(biz.get("email")),
        "{{BUSINESS_WEBSITE}}": _esc(biz.get("website")),
        "{{QUOTE_NUMBER}}": _esc(quote["quote_number"]),
        "{{CUSTOMER_NAME}}": _esc(quote["customer_name"]),
        "{{CUSTOMER_ADDRESS_LINES}}": site_lines,
        "{{CUSTOMER_PHONE_LINE}}": (
            '<div class="line">' + _esc(display_phone(quote.get("customer_phone"))) + "</div>"
            if quote.get("customer_phone") else ""),
        "{{CUSTOMER_EMAIL_LINE}}": (
            '<div class="line">' + _esc(quote.get("customer_email")) + "</div>"
            if quote.get("customer_email") else ""),
        "{{ISSUED_DATE}}": fmt_date(issued),
        "{{VALID_UNTIL}}": fmt_date(valid_until),
        "{{QUOTED_BY}}": _esc(quote.get("quoted_by") or "-"),
        "{{LINE_ITEMS}}": rows,
        "{{TOTAL}}": fmt_money(quote["total"], currency),
        "{{VAT_NOTE}}": vat_note,
        "{{PROMISES}}": "".join("<li>" + _esc(p) + "</li>" for p in biz.get("promises", [])),
        "{{ACCEPT_LINE}}": _esc(biz.get("accept_line")),
        "{{TERMS}}": _esc((biz.get("terms") or "").replace(
            "{validity_days}", str(biz.get("validity_days", 30)))),
    }
    for token, value in tokens.items():
        html = html.replace(token, value)
    return html


async def html_to_pdf(html: str) -> bytes:
    """Chromium via Playwright, same as the invoice renderer. Raises if Chromium
    is missing on the host -- the caller degrades to a link instead of failing."""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="load")
        pdf = await page.pdf(format="A4", print_background=True,
                             margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        await browser.close()
        return pdf


# ------------------------------------------------- in-memory store (demo-grade)
#
# Drafts are short-lived by nature: the technician confirms within a minute or two.
# Issued quotes are kept so their PDF stays fetchable. Both die on redeploy, which
# is acceptable for a demo and not for a business -- migration 013 adds the table.

DRAFTS = {}   # technician whatsapp number -> draft
ISSUED = {}   # public token -> issued quote, with rendered html and pdf bytes
_MAX_ISSUED = 500


def save_draft(technician: str, draft: dict) -> None:
    DRAFTS[technician] = draft


def get_draft(technician: str):
    return DRAFTS.get(technician)


def clear_draft(technician: str) -> None:
    DRAFTS.pop(technician, None)


def new_token() -> str:
    return secrets.token_urlsafe(12)


def store_issued(token: str, quote: dict) -> None:
    if len(ISSUED) >= _MAX_ISSUED:
        for k in list(ISSUED)[: _MAX_ISSUED // 5]:
            ISSUED.pop(k, None)
    ISSUED[token] = quote


def get_issued(token: str):
    return ISSUED.get(token)


def today() -> date:
    return datetime.now(TZ).date()
