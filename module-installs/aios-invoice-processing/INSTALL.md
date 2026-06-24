# Installing AIOS Invoice Processing

> **If you are Claude Code:** walk the user through these steps one at a time, in plain
> English. Run the commands for them where you can, and verify each step before moving on.
> Don't dump all the steps at once.

This module turns supplier invoices into a clean, downloadable spreadsheet using LlamaParse.
Setup takes about 5 minutes — it only needs one API key.

---

## Step 0 — What you need

- A **LlamaCloud** account (free, no card) — [cloud.llamaindex.ai](https://cloud.llamaindex.ai)
- A few invoice PDFs to test with (or use the sample generator in Step 4)

## Step 1 — Get the API key

1. Sign in at [cloud.llamaindex.ai](https://cloud.llamaindex.ai) with Google or GitHub
2. Go to **Settings → API Keys → Create Key**
3. Copy the key (it starts with `llx-`)

## Step 2 — Add the key to .env

In your **project root** `.env` (create it if needed, and make sure `.env` is gitignored),
add:

```
LLAMA_CLOUD_API_KEY=llx-your-key-here
```

## Step 3 — Install the Python requirements

From this module's `scripts/` folder (use the project's virtual environment if it has one):

```
pip install -r requirements.txt
```

## Step 4 — Make some test invoices (optional, free)

If you don't have invoices handy, generate realistic fake ones (this costs no API credits):

```
python generate_samples.py      # 4 invoices in ./samples/
python generate_bulk.py         # 100 invoices in ./demo-invoices-100/  (for volume demos)
```

## Step 5 — Run it

```
python -m streamlit run dashboard.py --server.port 8503
```

Or just double-click `run.bat`. A browser opens. Drop invoice PDFs onto the upload box,
click **Read Invoices**, and the table fills in. Click **Download Spreadsheet** for the CSV.

## Step 6 — (Demo only) Pre-warm for instant results

Reading an invoice takes about 6–10 seconds the first time. For a smooth on-camera demo,
read them once ahead of time so they're cached and appear instantly:

```
python warm_cache.py                 # warms samples/ and demo-invoices-100/
python warm_cache.py samples         # or warm one folder
```

Results are cached to `scripts/.cache/` and stay warm across restarts. Add `.cache/` to
`.gitignore`.

---

## Day-to-day use

- **Process real invoices**: drop them on the dashboard, download the CSV, import into your
  accounting software
- **From your own code**: `from invoice_extract import get_agent, extract_invoice, to_rows`
  — `extract_invoice(get_agent(), file_bytes, filename)` returns the structured dict
- **Point it at a Drive folder** (advanced): reuse the Drive connector from the
  `AIOS-data-pooling-v2` module to auto-read an "Invoices" folder instead of manual upload

## Customising

- **Fields extracted**: edit the `Invoice` / `LineItem` schema in `invoice_extract.py`
- **Reading mode / cost**: `ExtractMode.FAST` in `invoice_extract.py` (cheapest). Use
  `BALANCED` or `PREMIUM` only for messy scans — they cost more credits.
- **Dashboard look / copy**: the CSS and headings in `dashboard.py`
- **Time-saved estimate**: `MANUAL_MIN_PER_DOC` in `dashboard.py`

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `LLAMA_CLOUD_API_KEY is missing` | Add it to `.env` (Step 2) |
| Upload reads but returns nothing | Confirm the PDF actually contains an invoice; check the key is valid |
| Reads are slow on camera | Pre-warm first (Step 6) — cached invoices are instant |
| Burning credits faster than expected | Make sure the mode is `FAST` in `invoice_extract.py`, not `PREMIUM` |
| `402` / out of credits | Free tier is 10k credits/month; it resets at the start of the next cycle |
