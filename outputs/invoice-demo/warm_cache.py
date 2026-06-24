"""
Pre-warm the demo: read every sample invoice once and cache the result to disk.

Run this ONCE before recording (takes ~1-2 minutes for the four samples):
    python warm_cache.py

After this, launching the dashboard and dropping the same invoices returns instantly —
no waiting on camera. Add new sample PDFs to samples/ and re-run to warm them too.
"""
import time
from pathlib import Path

import invoice_extract as ix

samples = sorted((Path(__file__).resolve().parent / "samples").glob("*.pdf"))
if not samples:
    raise SystemExit("No PDFs in samples/. Run generate_samples.py first.")

print("Pre-warming reader...")
agent = ix.get_agent()
print(f"Warming {len(samples)} invoice(s) into the on-disk cache:\n")
for p in samples:
    t = time.time()
    data = ix.extract_invoice(agent, p.read_bytes(), p.name)
    flag = "" if data.get("invoice_number") else "  (no invoice number — left blank)"
    print(f"  {p.name:34} {data.get('vendor','?')[:28]:28} {data.get('total','?'):>14}  [{time.time()-t:.1f}s]{flag}")

print("\nWarm. The dashboard now returns these invoices instantly. Ready to film.")
