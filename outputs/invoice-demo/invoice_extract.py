"""
Invoice extraction via LlamaParse (LlamaExtract).

One schema, one reusable agent. The agent is created once and reused across runs
(the "pre-warm"), so the only cost per invoice is the read itself. Results are cached
by the caller so a second read of the same file is instant on camera.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# On-disk result cache so a warmed invoice stays instant across restarts (camera-ready).
CACHE_DIR = Path(__file__).resolve().parent / ".cache"

# Load the project .env (walk up from this file to the workspace root)
_HERE = Path(__file__).resolve()
for _p in [_HERE.parent, *_HERE.parents]:
    if (_p / ".env").exists():
        load_dotenv(_p / ".env")
        break

API_KEY = os.environ.get("LLAMA_CLOUD_API_KEY", "")
AGENT_NAME = "boschai-invoice-reader"


class LineItem(BaseModel):
    description: str = Field(description="What the line is for")
    qty: Optional[float] = Field(default=None, description="Quantity")
    unit_price: Optional[str] = Field(default=None, description="Price per unit, as written")
    line_total: Optional[str] = Field(default=None, description="Total for this line, as written")


class Invoice(BaseModel):
    vendor: str = Field(description="Company that issued the invoice")
    invoice_number: Optional[str] = Field(default=None, description="Invoice/reference number")
    invoice_date: Optional[str] = Field(default=None, description="Date the invoice was issued")
    bill_to: Optional[str] = Field(default=None, description="Customer being billed")
    line_items: List[LineItem] = Field(default_factory=list)
    subtotal: Optional[str] = Field(default=None)
    vat: Optional[str] = Field(default=None, description="VAT / tax amount")
    total: Optional[str] = Field(default=None, description="Total amount due")


def get_agent():
    """Return the reusable extraction agent, creating it once if needed (pre-warm).

    Uses FAST extraction mode — the cheapest setting (~6 credits/page). Our invoices are
    clean, computer-generated PDFs, so Fast reads them perfectly. Premium modes cost up to
    10x more and are only worth it for messy scans or photos.
    """
    if not API_KEY:
        raise RuntimeError("LLAMA_CLOUD_API_KEY is missing from .env")
    from llama_cloud_services import LlamaExtract
    from llama_cloud import ExtractConfig, ExtractMode

    extractor = LlamaExtract(api_key=API_KEY)
    config = ExtractConfig(extraction_mode=ExtractMode.FAST)
    try:
        agent = extractor.get_agent(name=AGENT_NAME)
        try:  # make sure an existing agent is pinned to the cheap mode too
            agent.config = config
            agent.save()
        except Exception:
            pass
        return agent
    except Exception:
        return extractor.create_agent(name=AGENT_NAME, data_schema=Invoice, config=config)


def _raw_extract(agent, file_bytes: bytes, filename: str) -> dict:
    suffix = Path(filename).suffix or ".pdf"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(file_bytes)
        tmp.close()
        result = agent.extract(tmp.name)
        return result.data or {}
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def extract_invoice(agent, file_bytes: bytes, filename: str) -> dict:
    """Read one invoice and return structured fields, using the on-disk cache when warm.

    A given file's bytes always produce the same cache key, so once an invoice has been
    read it returns instantly forever (until you clear .cache/). This is the pre-warm:
    run warm_cache.py once, then the demo never waits on camera.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    key = hashlib.md5(file_bytes).hexdigest()
    cached = CACHE_DIR / f"{key}.json"
    if cached.exists():
        try:
            return json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    data = _raw_extract(agent, file_bytes, filename)
    try:
        cached.write_text(json.dumps(data, default=str), encoding="utf-8")
    except OSError:
        pass
    return data


def to_rows(data: dict, source: str) -> List[dict]:
    """Flatten one invoice's structured data into one row per line item for the table."""
    vendor = data.get("vendor") or ""
    inv_no = data.get("invoice_number") or ""
    date = data.get("invoice_date") or ""
    items = data.get("line_items") or []
    if not items:
        # Still show the header-level info even if no line items were found
        return [{
            "Source": source, "Vendor": vendor, "Invoice #": inv_no, "Date": date,
            "Description": "", "Qty": "", "Unit Price": "", "Line Total": "",
        }]
    rows = []
    for it in items:
        rows.append({
            "Source": source,
            "Vendor": vendor,
            "Invoice #": inv_no,
            "Date": date,
            "Description": it.get("description") or "",
            "Qty": it.get("qty") if it.get("qty") is not None else "",
            "Unit Price": it.get("unit_price") or "",
            "Line Total": it.get("line_total") or "",
        })
    return rows


def money_to_float(s) -> float:
    """Best-effort parse of 'R 10,982.50' -> 10982.50. Returns 0.0 on anything unparseable."""
    if not s:
        return 0.0
    keep = "".join(c for c in str(s) if c.isdigit() or c == ".")
    try:
        return float(keep) if keep else 0.0
    except ValueError:
        return 0.0
