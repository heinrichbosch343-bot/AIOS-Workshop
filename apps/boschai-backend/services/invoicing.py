"""
Recurring invoicing - generates and sends monthly maintenance invoices.

The scheduler calls run() once a day. For every active row in recurring_billing
whose next_invoice_date has arrived, it renders the Boschly invoice template
(templates/invoice.html) to a PDF via headless Chromium (Playwright), emails it
to the client, logs it in invoices, and advances next_invoice_date one month.

Whether it actually SENDS or just drafts + pings Telegram is gated by
INVOICE_AUTOSEND_ENABLED (same off-by-default pattern as the email drip and
drip auto-reply) - off means every invoice still gets generated and staged as
a Gmail draft, with a Telegram heads-up, so nothing is silently skipped.
"""
import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright

from config import INVOICE_AUTOSEND_ENABLED
from db.client import supabase
from services import email as email_service
from services.notify import send_telegram

TZ = ZoneInfo("Africa/Johannesburg")
TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "invoice.html"

_MONTHS = ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"]


def _today() -> date:
    return datetime.now(TZ).date()


def _fmt_date(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1][:3]} {d.year}"


def _fmt_amount(amount: float, currency: str = "ZAR") -> str:
    """'R 1 000.00' style: space as thousands separator, matching the existing invoices."""
    symbol = "R" if currency == "ZAR" else currency + " "
    whole, cents = f"{amount:,.2f}".split(".")
    whole = whole.replace(",", " ")
    return f"{symbol} {whole}.{cents}"


def _next_invoice_number(year: int) -> str:
    """BOSCHLY-{year}-{seq:03d}, continuing from the highest existing number this year."""
    rows = (supabase.table("invoices")
            .select("invoice_number")
            .like("invoice_number", f"BOSCHLY-{year}-%")
            .execute()).data
    seqs = []
    for r in rows:
        try:
            seqs.append(int(r["invoice_number"].rsplit("-", 1)[-1]))
        except ValueError:
            continue
    next_seq = (max(seqs) + 1) if seqs else 1
    return f"BOSCHLY-{year}-{next_seq:03d}"


def _render_html(invoice_number: str, client_name: str, client_email: str,
                  client_address: str | None, client_phone: str | None,
                  issued: date, due: date, terms_days: int,
                  item_heading: str, item_description: str, amount_str: str) -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    address_lines = "".join(
        f'<div class="line">{line}</div>' for line in (client_address or "").splitlines() if line.strip()
    )
    phone_line = f'<div class="line">{client_phone}</div>' if client_phone else ""
    tokens = {
        "{{INVOICE_NUMBER}}": invoice_number,
        "{{CLIENT_NAME}}": client_name,
        "{{CLIENT_ADDRESS_LINES}}": address_lines,
        "{{CLIENT_EMAIL}}": client_email,
        "{{CLIENT_PHONE_LINE}}": phone_line,
        "{{ISSUED_DATE}}": _fmt_date(issued),
        "{{DUE_DATE}}": _fmt_date(due),
        "{{TERMS_DAYS}}": str(terms_days),
        "{{ITEM_HEADING}}": item_heading,
        "{{ITEM_DESCRIPTION}}": item_description,
        "{{AMOUNT}}": amount_str,
    }
    for token, value in tokens.items():
        html = html.replace(token, value)
    return html


async def _html_to_pdf(html: str) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html, wait_until="load")
        pdf = await page.pdf(format="A4", print_background=True,
                              margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        await browser.close()
        return pdf


def _already_invoiced_this_month(recurring_billing_id: str, today: date) -> bool:
    month_start = today.replace(day=1).isoformat()
    rows = (supabase.table("invoices")
            .select("id")
            .eq("recurring_billing_id", recurring_billing_id)
            .gte("issued_date", month_start)
            .execute()).data
    return bool(rows)


def _advance_one_month(d: date) -> date:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


def generate_and_send(row: dict) -> None:
    """Generate and dispatch one invoice for a single recurring_billing row."""
    today = _today()
    if _already_invoiced_this_month(row["id"], today):
        print(f"[invoicing] {row['client_name']}: already invoiced this month, skipping", flush=True)
        return

    issued = today
    due = today + timedelta(days=row["payment_terms_days"])
    invoice_number = _next_invoice_number(issued.year)
    month_label = f"{_MONTHS[issued.month - 1]} {issued.year}"
    full_item_heading = f"{row['item_heading']}, {month_label}"
    amount_str = _fmt_amount(row["amount"], row.get("currency", "ZAR"))

    html = _render_html(
        invoice_number=invoice_number, client_name=row["client_name"],
        client_email=row["client_email"], client_address=row.get("client_address"),
        client_phone=row.get("client_phone"), issued=issued, due=due,
        terms_days=row["payment_terms_days"], item_heading=full_item_heading,
        item_description=row["item_description"], amount_str=amount_str,
    )
    pdf_bytes = asyncio.run(_html_to_pdf(html))
    filename = f"{invoice_number}-{row['client_name'].lower().replace(' ', '-')}.pdf"

    subject = f"Invoice {invoice_number}: {row['item_heading']}, {month_label}"
    body = (
        f"Hi,\n\n"
        f"Here's this month's invoice for {row['item_heading'].lower()}, "
        f"{amount_str}, due {_fmt_date(due)}. Payment details are on the invoice.\n\n"
        f"Thanks,\nHeinrich"
    )

    status = "sent"
    try:
        if INVOICE_AUTOSEND_ENABLED:
            email_service.send_new_with_attachment(
                row["client_email"], subject, body, pdf_bytes, filename)
            telegram_msg = (f"\U0001f9fe Invoice <b>{invoice_number}</b> sent to "
                             f"{row['client_name']} ({amount_str}, due {_fmt_date(due)}).")
        else:
            email_service.create_draft_with_attachment(
                row["client_email"], subject, body, pdf_bytes, filename)
            status = "draft"
            telegram_msg = (f"\U0001f9fe Invoice <b>{invoice_number}</b> for {row['client_name']} "
                             f"({amount_str}) is drafted in Gmail, ready to send. "
                             f"Set INVOICE_AUTOSEND_ENABLED=1 in Railway to send these automatically.")
    except Exception as exc:
        print(f"[invoicing] FAILED to send/draft {invoice_number} for {row['client_name']}: {exc}", flush=True)
        send_telegram(f"⚠️ Invoice {invoice_number} for {row['client_name']} failed: {exc}")
        return

    supabase.table("invoices").insert({
        "invoice_number": invoice_number,
        "recurring_billing_id": row["id"],
        "client_name": row["client_name"],
        "client_email": row["client_email"],
        "description": full_item_heading,
        "amount": row["amount"],
        "currency": row.get("currency", "ZAR"),
        "issued_date": issued.isoformat(),
        "due_date": due.isoformat(),
        "status": status,
        "sent_at": datetime.now(TZ).isoformat(),
    }).execute()

    next_date = _advance_one_month(date.fromisoformat(row["next_invoice_date"]))
    supabase.table("recurring_billing").update({
        "next_invoice_date": next_date.isoformat(),
        "updated_at": datetime.now(TZ).isoformat(),
    }).eq("id", row["id"]).execute()

    send_telegram(telegram_msg)
    print(f"[invoicing] {status} -> {invoice_number} for {row['client_name']} ({amount_str})", flush=True)


def run() -> None:
    """Scheduler entry point: dispatch every recurring_billing row due today or earlier."""
    today = _today()
    rows = (supabase.table("recurring_billing")
            .select("*")
            .eq("active", True)
            .lte("next_invoice_date", today.isoformat())
            .execute()).data
    for row in rows:
        try:
            generate_and_send(row)
        except Exception as exc:
            print(f"[invoicing] {row['client_name']}: unexpected error: {exc}", flush=True)
            send_telegram(f"⚠️ Invoicing failed for {row['client_name']}: {exc}")
