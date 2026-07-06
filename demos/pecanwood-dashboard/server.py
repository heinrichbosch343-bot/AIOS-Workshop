"""
server.py — FastAPI backend for the Pecanwood Portfolio dashboard demo (port 8509).

Routes:
    GET /                the dashboard
    GET /api/portfolio   the merged real-data portfolio (see build_data.py)
    GET /api/health      status booleans/counts
    /static/*            UI assets, vendored Chart.js, and the 3 seller-update PDFs

All market data is real (scraped from public seeff.com + property24.com pages on
2026-07-06). Per-listing portal activity is deterministic sample data and is
labeled SAMPLE in the UI.
"""
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
PORTFOLIO = HERE / "data" / "portfolio.json"

app = FastAPI(title="Boschly — Pecanwood Portfolio Demo")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/portfolio")
def portfolio() -> JSONResponse:
    return JSONResponse(json.loads(PORTFOLIO.read_text(encoding="utf-8")))


@app.get("/api/health")
def health() -> dict:
    data = json.loads(PORTFOLIO.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "captured": data["captured"],
        "listings": len(data["listings"]),
        "reports": sum(1 for l in data["listings"] if l.get("report")),
    }


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
