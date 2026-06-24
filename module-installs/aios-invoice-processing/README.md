# AIOS Invoice Processing

Turn a pile of supplier invoices into a clean spreadsheet you can actually use, in
seconds, with nothing typed by hand and nothing invented.

Drop in PDFs (invoices, scans, email attachments), and the system reads each one and
returns structured data: vendor, invoice number, date, every line item, VAT, and total.
Download it as a CSV that drops straight into Xero, QuickBooks, Sage, or a spreadsheet.

## What it does

1. **Reads** any invoice PDF using LlamaParse (LlamaExtract), which handles real-world
   layouts, scans, and messy formatting
2. **Extracts** the fields that matter into typed, structured data (numbers as numbers,
   dates as dates)
3. **Leaves blanks where the document is blank** — if a field isn't on the invoice, it
   stays empty instead of being guessed. Safe to trust with money.
4. **Shows** the result as a clean table on a simple web dashboard, with running totals and
   a time-saved counter
5. **Exports** to CSV for accounting import, spend analysis, VAT returns, and reporting

## Why it matters

A 30-person company gets roughly 300 invoices a month. Typing each into accounting software
takes about 4 minutes, which is around 20 hours a month, every month, spent retyping numbers
that are already printed on the page. This system gives those hours back, kills the typos
that cause payment disputes, and finally lets the business see where its money goes (sort by
supplier, total a column, spot duplicates).

## What's in the box

| File | Role |
| --- | --- |
| `scripts/invoice_extract.py` | The reader — schema, LlamaExtract call, and on-disk result cache |
| `scripts/dashboard.py` | The web dashboard (Streamlit) — drop invoices, get a table, download CSV |
| `scripts/generate_samples.py` | Makes 4 realistic sample invoices for testing/demos (no API cost) |
| `scripts/generate_bulk.py` | Makes 100 varied sample invoices for a high-volume demo (no API cost) |
| `scripts/warm_cache.py` | Pre-reads invoices into the cache so a demo is instant on camera |
| `scripts/requirements.txt` | Python dependencies |
| `scripts/run.bat` | One-click launch of the dashboard |

## Keys you need

| Key | Where to get it | Used for |
| --- | --- | --- |
| `LLAMA_CLOUD_API_KEY` | [cloud.llamaindex.ai](https://cloud.llamaindex.ai) → Settings → API Keys (Google/GitHub login, no card) | Reading the invoices |

Free tier: **10,000 credits/month**. On the cheapest "Fast" mode (~6 credits/page), that's
over 1,600 invoices a month at no cost.

## Install

Give this folder to Claude Code and say **"read INSTALL.md and set this up"** — or follow
INSTALL.md yourself. Setup is: add one key to `.env` → install requirements → run it.

## Cost

- **Reading invoices**: ~6 credits each on Fast mode. The free 10k/month covers ~1,600
  invoices. Premium modes (for genuinely terrible scans) cost up to 10x more and aren't
  needed for clean documents.
- **Generating sample invoices**: free (built locally, no API).
