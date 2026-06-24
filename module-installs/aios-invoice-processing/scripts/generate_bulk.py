"""
Generate 100 realistic (but fictional) SA supplier invoices for the volume demo.

Local only — costs ZERO LlamaParse credits (PDFs are built on your machine).
Run:  python generate_bulk.py
Output: ./demo-invoices-100/  (inv_001.pdf ... inv_100.pdf)

Each invoice has 3-5 line items (medium depth), varied suppliers, items, dates,
and totals so the batch never looks copy-pasted. A handful deliberately omit the
invoice number so the "it leaves blanks instead of guessing" point still holds at scale.
"""
import random
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

OUT = Path(__file__).resolve().parent / "demo-invoices-100"
OUT.mkdir(exist_ok=True)
styles = getSampleStyleSheet()
random.seed(42)  # reproducible batch

ACCENTS = ["#1d4ed8", "#0f766e", "#7c3aed", "#b45309", "#be123c", "#0369a1", "#4d7c0f"]

# (vendor, city, vat_no, [ (item, low, high) ... ])
VENDORS = [
    ("NEXGEN MANUFACTURING (PTY) LTD", "Johannesburg, 2001", "4120198345",
     [("Steel pipe 50mm (6m length)", 90, 160), ("Galvanised fittings (box of 10)", 150, 260),
      ("Welding consumables kit", 280, 420), ("Sheet metal 2mm (per m2)", 200, 340),
      ("Delivery & handling", 450, 800)]),
    ("KAROO FRESH PRODUCE CC", "Western Cape, 6930", "4980221176",
     [("Mixed salad greens (5kg crate)", 110, 180), ("Heirloom tomatoes (10kg box)", 240, 320),
      ("Free-range eggs (tray of 30)", 80, 120), ("Baby spinach (2kg bag)", 70, 110),
      ("Cold-chain transport", 380, 620)]),
    ("SUMMIT OFFICE SUPPLIES", "Pretoria, 0182", "4310667788",
     [("A4 paper (box of 5 reams)", 280, 360), ("Toner cartridge HP 26X", 1200, 1700),
      ("Ergonomic office chair", 1900, 2600), ("Stationery bundle", 140, 220),
      ("Whiteboard 1200x900", 700, 1000)]),
    ("HIGHVELD ELECTRICAL SUPPLIES", "Germiston, 1401", "4671009923",
     [("Industrial cable 2.5mm (100m roll)", 800, 980), ("Circuit breakers 32A", 120, 180),
      ("LED high-bay light 150W", 540, 720), ("Distribution board 12-way", 900, 1300),
      ("Cable trunking (per 3m)", 95, 160)]),
    ("ATLANTIC PACKAGING CO", "Cape Town, 7405", "4220556610",
     [("Corrugated boxes (bundle of 25)", 180, 260), ("Pallet wrap (heavy duty roll)", 130, 200),
      ("Packing tape (pack of 6)", 70, 120), ("Bubble wrap (100m roll)", 240, 360),
      ("Wooden pallets (each)", 120, 190)]),
    ("UMHLANGA TECH DISTRIBUTORS", "Durban, 4319", "4790338821",
     [("USB-C docking station", 900, 1400), ("Wireless mouse + keyboard set", 350, 560),
      ("27-inch monitor", 2400, 3400), ("Network switch 8-port", 700, 1100),
      ("HDMI cable 3m (pack of 5)", 150, 240)]),
    ("BUSHVELD CLEANING SOLUTIONS", "Polokwane, 0700", "4150771234",
     [("Industrial floor cleaner (25L)", 320, 480), ("Hand sanitiser (5L refill)", 140, 220),
      ("Paper towel (case of 12)", 180, 280), ("Bin liners (box of 200)", 90, 150),
      ("Mop & bucket set", 200, 320)]),
    ("GARDEN ROUTE TIMBER", "George, 6529", "4330119988",
     [("Pine planks 38x114 (per 3m)", 110, 180), ("Plywood sheet 16mm", 380, 560),
      ("Wood screws (box of 500)", 130, 210), ("Varnish 5L", 420, 640),
      ("Decking boards (per m)", 95, 150)]),
    ("VAAL INDUSTRIAL FASTENERS", "Vereeniging, 1930", "4610223377",
     [("Hex bolts M12 (box of 100)", 220, 340), ("Washers assorted (tub)", 80, 140),
      ("Threaded rod 1m", 70, 120), ("Anchor bolts (pack of 50)", 260, 400),
      ("Nuts M10 (box of 200)", 150, 240)]),
    ("CAPE PENINSULA PRINTERS", "Bellville, 7530", "4980665512",
     [("Business cards (500)", 280, 420), ("Branded folders (pack of 50)", 600, 900),
      ("Roll-up banner", 700, 1100), ("Flyers A5 (1000)", 450, 700),
      ("Letterhead (ream)", 320, 480)]),
]

CUSTOMERS = [
    "BrightPath Logistics CC", "Hartley Retail Group", "Osun Consulting Group",
    "Nexgen Manufacturing (Pty) Ltd", "Elevate Property Group", "Cape Agri Cooperative",
    "TechBridge Academy", "Sandstone Medical Group", "Summit Trading (Pty) Ltd",
    "Coastal Foods CC",
]

MONTHS = [("April", 4), ("May", 5), ("June", 6)]


def build(path, vendor, city, vat_no, inv_no, date, bill_to, due, items, accent):
    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=18 * mm)
    e = []
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=18, textColor=colors.HexColor(accent))
    e.append(Paragraph(vendor, title))
    line = f"{city}" + (f" &nbsp;|&nbsp; VAT No: {vat_no}" if vat_no else "")
    e.append(Paragraph(line, styles["Normal"]))
    e.append(Spacer(1, 7 * mm))

    meta_rows = [["TAX INVOICE", ""]]
    if inv_no:
        meta_rows.append(["Invoice No:", inv_no])
    meta_rows += [["Date:", date], ["Bill To:", bill_to], ["Due Date:", due]]
    meta = Table(meta_rows, colWidths=[40 * mm, 100 * mm])
    meta.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor(accent)),
    ]))
    e.append(meta)
    e.append(Spacer(1, 6 * mm))

    rows = [["Description", "Qty", "Unit Price", "Line Total"]]
    subtotal = 0.0
    for desc, qty, unit in items:
        tot = qty * unit
        subtotal += tot
        rows.append([desc, str(qty), f"R {unit:,.2f}", f"R {tot:,.2f}"])
    t = Table(rows, colWidths=[80 * mm, 20 * mm, 30 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(accent)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    e.append(t)
    e.append(Spacer(1, 4 * mm))

    vat_amt = subtotal * 0.15
    grand = subtotal + vat_amt
    totals = Table([["Subtotal:", f"R {subtotal:,.2f}"], ["VAT (15%):", f"R {vat_amt:,.2f}"],
                    ["TOTAL DUE:", f"R {grand:,.2f}"]], colWidths=[110 * mm, 30 * mm])
    totals.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.HexColor(accent)),
    ]))
    e.append(totals)
    doc.build(e)
    return grand


def main():
    print(f"Generating 100 invoices into {OUT}  (no API credits used)")
    grand_total = 0.0
    no_number_count = 0
    for i in range(1, 101):
        vendor, city, vat_no, catalog = random.choice(VENDORS)
        accent = random.choice(ACCENTS)
        n_items = random.randint(3, 5)
        picks = random.sample(catalog, n_items)
        items = [(desc, random.randint(2, 40), round(random.uniform(lo, hi), 2)) for desc, lo, hi in picks]
        month_name, mnum = random.choice(MONTHS)
        day = random.randint(1, 28)
        date = f"{day} {month_name} 2026"
        due = f"{day} {MONTHS[min(MONTHS.index((month_name, mnum)) + 1, 2)][0]} 2026"
        bill_to = random.choice(CUSTOMERS)
        # ~1 in 12 invoices has no number (keeps the trust point alive at scale)
        if random.random() < 0.08:
            inv_no = ""
            no_number_count += 1
        else:
            prefix = "".join(w[0] for w in vendor.split()[:2]).upper()
            inv_no = f"{prefix}-2026-{random.randint(1000, 9999)}"
        path = OUT / f"inv_{i:03d}.pdf"
        grand_total += build(path, vendor, city, vat_no, inv_no, date, bill_to, due, items, accent)

    print(f"Done. 100 invoices in {OUT.name}/")
    print(f"  Combined value across the batch: R {grand_total:,.2f}")
    print(f"  Invoices with no number (blank on purpose): {no_number_count}")


if __name__ == "__main__":
    main()
