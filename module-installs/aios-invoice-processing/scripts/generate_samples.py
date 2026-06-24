"""
Generate realistic (but fictional) South African supplier invoices as PDFs for the demo.

Run once:  python generate_samples.py
Outputs to ./samples/. All companies, numbers, and VAT details are invented.
One invoice (Highveld Electrical) deliberately omits the invoice number so the demo
can show the reader leaving a field blank instead of guessing.
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

SAMPLES = Path(__file__).resolve().parent / "samples"
SAMPLES.mkdir(exist_ok=True)
styles = getSampleStyleSheet()


def build(filename, vendor, address, vat_no, inv_no, date, bill_to, due, items,
          vat_rate=0.15, accent="#1d4ed8"):
    path = SAMPLES / filename
    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=18 * mm)
    e = []
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=19,
                           textColor=colors.HexColor(accent))
    e.append(Paragraph(vendor, title))
    line = address + (f" &nbsp;|&nbsp; VAT No: {vat_no}" if vat_no else "")
    e.append(Paragraph(line, styles["Normal"]))
    e.append(Spacer(1, 8 * mm))

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
        total = qty * unit
        subtotal += total
        rows.append([desc, str(qty), f"R {unit:,.2f}", f"R {total:,.2f}"])
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

    vat_amt = subtotal * vat_rate
    grand = subtotal + vat_amt
    totals = Table([
        ["Subtotal:", f"R {subtotal:,.2f}"],
        [f"VAT ({int(vat_rate*100)}%):", f"R {vat_amt:,.2f}"],
        ["TOTAL DUE:", f"R {grand:,.2f}"],
    ], colWidths=[110 * mm, 30 * mm])
    totals.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 2), (-1, 2), colors.HexColor(accent)),
    ]))
    e.append(totals)
    doc.build(e)
    print(f"  wrote {filename}  (total R {grand:,.2f})")


def main():
    print("Generating sample invoices in", SAMPLES)

    build("01_nexgen_manufacturing.pdf",
          "NEXGEN MANUFACTURING (PTY) LTD",
          "12 Marshall Street, Johannesburg, 2001", "4120198345",
          "NX-2026-0417", "14 June 2026", "BrightPath Logistics CC", "14 July 2026",
          [("Steel pipe 50mm (6m length)", 40, 120.00),
           ("Galvanised fittings (box of 10)", 12, 200.00),
           ("Welding consumables kit", 5, 340.00),
           ("Delivery & handling", 1, 650.00)])

    build("02_karoo_fresh_produce.pdf",
          "KAROO FRESH PRODUCE CC",
          "Plot 7, Prince Albert Road, Western Cape, 6930", "4980221176",
          "KFP-1182", "16 June 2026", "Hartley Retail Group", "30 June 2026",
          [("Mixed salad greens (5kg crate)", 18, 145.00),
           ("Heirloom tomatoes (10kg box)", 9, 280.00),
           ("Free-range eggs (tray of 30)", 24, 95.00),
           ("Cold-chain transport", 1, 480.00)],
          accent="#0f766e")

    build("03_summit_office_supplies.pdf",
          "SUMMIT OFFICE SUPPLIES",
          "Block C, Northgate Park, Pretoria, 0182", "4310667788",
          "SOS-2026-3391", "18 June 2026", "Osun Consulting Group", "18 July 2026",
          [("A4 paper (box of 5 reams)", 15, 320.00),
           ("Toner cartridge HP 26X", 6, 1450.00),
           ("Ergonomic office chair", 4, 2200.00),
           ("Stationery bundle", 10, 180.00)],
          accent="#7c3aed")

    # Trust-beat invoice: NO invoice number on the document.
    build("04_highveld_electrical.pdf",
          "HIGHVELD ELECTRICAL SUPPLIES",
          "44 Voortrekker Road, Germiston, 1401", "4671009923",
          "", "20 June 2026", "Nexgen Manufacturing (Pty) Ltd", "20 July 2026",
          [("Industrial cable 2.5mm (100m roll)", 8, 890.00),
           ("Circuit breakers 32A", 25, 145.00),
           ("LED high-bay light 150W", 14, 620.00)],
          accent="#b45309")

    print("Done. 4 invoices ready in samples/ (Highveld has no invoice number on purpose).")


if __name__ == "__main__":
    main()
