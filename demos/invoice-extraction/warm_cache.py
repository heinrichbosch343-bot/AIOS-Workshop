"""
Pre-warm the demo: read every invoice once and cache the result to disk.

Run this ONCE before recording. By default it warms BOTH the 4 samples/ and the
100 demo-invoices-100/ (about 12-18 min, ~600 credits on FAST mode):
    python warm_cache.py

Or point it at one specific folder:
    python warm_cache.py samples
    python warm_cache.py demo-invoices-100

After this, launching the dashboard and dropping the same invoices returns instantly —
no waiting on camera.
"""
import sys
import time
from pathlib import Path

import invoice_extract as ix

HERE = Path(__file__).resolve().parent
if len(sys.argv) > 1:
    folders = [HERE / sys.argv[1]]
else:
    folders = [HERE / "samples", HERE / "demo-invoices-100"]

samples = []
for folder in folders:
    if folder.exists():
        samples.extend(sorted(folder.glob("*.pdf")))
if not samples:
    raise SystemExit(f"No PDFs found in {[f.name for f in folders]}. Run generate_samples.py / generate_bulk.py first.")

print("Pre-warming reader...")
agent = ix.get_agent()
print(f"Warming {len(samples)} invoice(s) into the on-disk cache:\n")
for p in samples:
    t = time.time()
    data = ix.extract_invoice(agent, p.read_bytes(), p.name)
    flag = "" if data.get("invoice_number") else "  (no invoice number — left blank)"
    print(f"  {p.name:34} {data.get('vendor','?')[:28]:28} {data.get('total','?'):>14}  [{time.time()-t:.1f}s]{flag}")

print("\nWarm. The dashboard now returns these invoices instantly. Ready to film.")
