"""
Recurring invoicing API — proving, before the 1st of the month, that the invoice
will actually go out on the 1st of the month.

GET /invoices/ready    — unguarded, PII-free: is this thing able to invoice right
                          now, and if not, what is missing?
GET /invoices/preview  — guarded dry run: render the exact PDF that the next run
                          would send, without writing a row or emailing anybody.

Why an unguarded probe: the invoicing job runs once a day, at 07:00, unattended,
with Telegram notifications switched off. Every failure mode it has — no Chromium
on the host, an expired Google token, a scheduler that never started — looks
identical from outside, which is to say invisible. This makes it checkable.
"""
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Response

from config import API_SECRET_KEY, INVOICE_AUTOSEND_ENABLED, TELEGRAM_ENABLED
from db.client import supabase
from services import invoicing

router = APIRouter(tags=["invoicing"])

# Bumped by hand whenever this file changes, so /invoices/ready proves which build
# Railway is actually running rather than which build we hope it is running.
BUILD = "invoicing-2 (2026-09-09, drafts endpoint + token notes corrected)"

TZ = ZoneInfo("Africa/Johannesburg")
_BOOTED_AT = time.time()

# A real Chromium render is the only honest answer to "can this host make a PDF",
# because the binary being present and the binary being able to start are different
# questions. Cached, so an open endpoint can never be used to make us spawn browsers.
_PDF_CACHE: dict = {}
_PDF_TTL = 300


def _pdf_engine() -> dict:
    """Actually render a throwaway PDF. Anything less doesn't prove anything."""
    hit = _PDF_CACHE.get("result")
    if hit and time.time() - hit[0] < _PDF_TTL:
        return hit[1]
    try:
        import asyncio
        pdf = asyncio.run(invoicing._html_to_pdf("<html><body>ok</body></html>"))
        value = {"ok": True, "engine": "chromium (playwright)", "bytes": len(pdf)}
    except Exception as exc:
        value = {"ok": False, "engine": "chromium (playwright)",
                 "detail": str(exc)[:300],
                 "fix": ("Chromium isn't usable on this host. nixpacks.toml installs it "
                         "after the pip phase — check that phase ran in the Railway build log.")}
    _PDF_CACHE["result"] = (time.time(), value)
    return value


def _billing_rows() -> list[dict]:
    return (supabase.table("recurring_billing").select("*")
            .eq("active", True).order("next_invoice_date").execute()).data


@router.get("/invoices/ready")
def ready():
    """Will an invoice actually go out on its due date, and if not, why not?

    Deliberately UNGUARDED, on the same reasoning as /quotebot/ready: the moment
    something breaks is the moment a key-protected endpoint is hardest to reach.
    Safe to leave open because it reports only whether things WORK — no client
    names, no email addresses, no amounts, and booleans in place of secrets.

    `blockers` is the whole point: it says what to go and do, in order.
    """
    from services import delivery_health, scheduler

    today = datetime.now(TZ).date()
    blockers: list[str] = []
    notes: list[str] = []

    # 1. Is the daily job actually on the live scheduler?
    job = scheduler.job_status("invoicing")
    if not job["scheduler_running"]:
        blockers.append("The scheduler isn't running on this instance, so nothing is "
                        "scheduled at all. It starts only on Railway, and DISABLE_TELEGRAM_BOT=1 "
                        "switches it off — check that variable.")
    elif not job["registered"]:
        blockers.append("The scheduler is running but has no 'invoicing' job registered — "
                        "this build predates the invoicing feature.")

    # 2. Do the tables exist, and is anything actually on billing?
    tables, rows = {}, []
    for table in ("invoices", "recurring_billing"):
        try:
            supabase.table(table).select("*").limit(1).execute()
            tables[table] = "ok"
        except Exception as exc:
            tables[table] = f"MISSING ({str(exc)[:80]})"
            blockers.append(f"Table '{table}' is missing — run db/migrations/012_invoicing.sql "
                            f"once in the Supabase SQL editor.")
    if all(v == "ok" for v in tables.values()):
        rows = _billing_rows()
        if not rows:
            blockers.append("No active rows in recurring_billing, so nothing will ever be due. "
                            "Add the client's standing arrangement to that table.")

    # 3. Can this host make a PDF, and can it still send mail as us?
    pdf = _pdf_engine()
    if not pdf["ok"]:
        blockers.append("This host can't render a PDF, so a due invoice would fail: "
                        + pdf.get("detail", "")[:120])

    email = delivery_health.email_health()
    if not email.get("ok"):
        blockers.append("Gmail won't authenticate, so a due invoice can be generated but not "
                        "delivered: " + str(email.get("fix") or email.get("detail", ""))[:160])
    else:
        notes.append("The consent screen is published, so the Google refresh token no longer "
                     "expires on a clock. What still kills it: changing the Google account "
                     "password (Gmail scopes are invalidated on a password change), revoking "
                     "access, or six months unused. After a password change, re-authorise at "
                     "/auth/google or the next invoice silently fails.")

    # 4. Sending vs drafting: not a blocker, but the difference between a client
    #    being invoiced and a draft sitting in Gmail waiting for a human.
    if not INVOICE_AUTOSEND_ENABLED:
        blockers.append("INVOICE_AUTOSEND_ENABLED is 0, so a due invoice is drafted in Gmail "
                        "rather than sent. Set it to 1 in the Railway variables to invoice "
                        "automatically.")

    if not TELEGRAM_ENABLED:
        notes.append("Telegram is off, so invoicing failures are emailed to the connected "
                     "mailbox instead — nothing fails silently.")

    return {
        "build": BUILD,
        "ready_to_invoice": not blockers,
        "blockers": blockers or ["none"],
        "notes": notes,
        "mode": "SENDS to the client" if INVOICE_AUTOSEND_ENABLED else "drafts only (autosend off)",
        "schedule": {"runs": "07:00 SAST daily", **job},
        "today": today.isoformat(),
        "billing": {
            "active_arrangements": len(rows),
            "due_today_or_earlier": sum(1 for r in rows if r["next_invoice_date"] <= today.isoformat()),
            "next_due_date": rows[0]["next_invoice_date"] if rows else None,
            "monthly_total": round(sum(float(r["amount"]) for r in rows), 2) if rows else 0,
        },
        "tables": tables,
        "pdf_engine": pdf,
        "gmail": {"ok": email.get("ok", False)},
        # Uptime is how you tell a service that stays awake from one that sleeps
        # between requests — a sleeping service never reaches its own 07:00 job.
        "uptime_hours": round((time.time() - _BOOTED_AT) / 3600, 1),
    }


@router.get("/invoices/preview")
def preview(key: str = "", json: int = 0):
    """The exact PDF the next run would produce, rendered from the live billing row.

    A dry run in the strictest sense: no invoices row is written, no next_invoice_date
    moves, no email is drafted or sent. It exists so the September invoice can be read
    in full in August, while there is still time to fix what it says.

    Guarded, because unlike /ready this one carries the client's name, address and
    what they're charged.
    """
    if key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    rows = _billing_rows()
    if not rows:
        raise HTTPException(status_code=404, detail="No active recurring_billing rows")
    row = rows[0]

    # Render it as the due date, not as today, so the month label and the dates read
    # exactly as the client will see them.
    issued = max(date.fromisoformat(row["next_invoice_date"]), datetime.now(TZ).date())
    due = issued + timedelta(days=row["payment_terms_days"])
    number = invoicing._next_invoice_number(issued.year)
    heading = f"{row['item_heading']}, {invoicing._MONTHS[issued.month - 1]} {issued.year}"
    amount = invoicing._fmt_amount(row["amount"], row.get("currency", "ZAR"))

    html = invoicing._render_html(
        invoice_number=number, client_name=row["client_name"],
        client_email=row["client_email"], client_address=row.get("client_address"),
        client_phone=row.get("client_phone"), issued=issued, due=due,
        terms_days=row["payment_terms_days"], item_heading=heading,
        item_description=row["item_description"], amount_str=amount,
    )

    if json:
        return {"build": BUILD, "dry_run": True, "would_issue": number,
                "client": row["client_name"], "to": row["client_email"],
                "line_item": heading, "amount": amount,
                "issued": issued.isoformat(), "due": due.isoformat(),
                "then_next_due": invoicing._advance_one_month(
                    date.fromisoformat(row["next_invoice_date"])).isoformat(),
                "unfilled_tokens": html.count("{{")}

    import asyncio
    pdf = asyncio.run(invoicing._html_to_pdf(html))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{number}-preview.pdf"'})
