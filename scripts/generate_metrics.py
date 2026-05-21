"""
DataOS — Key Metrics Generator

Reads the database and generates a human-readable key-metrics.md file.
This file is loaded by your /prime command so your AI always has fresh data.

Usage:
    python scripts/generate_metrics.py
"""

import sqlite3
from datetime import datetime
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = WORKSPACE_ROOT / "data" / "data.db"
OUTPUT_PATH = WORKSPACE_ROOT / "context" / "group" / "key-metrics.md"


# --- Formatting helpers ---

def fmt_number(value, prefix="", suffix=""):
    if value is None:
        return "No data"
    if isinstance(value, float):
        return f"{prefix}{value:,.0f}{suffix}"
    return f"{prefix}{value:,}{suffix}"


def fmt_currency(value, symbol="$"):
    if value is None:
        return "No data"
    return f"{symbol}{value:,.0f}"


def fmt_pct(value):
    if value is None:
        return "No data"
    return f"{value:.1f}%"


def query_one(conn, sql):
    try:
        row = conn.execute(sql).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def query_all(conn, sql):
    try:
        return [dict(r) for r in conn.execute(sql).fetchall()]
    except Exception:
        return []


def table_exists(conn, name):
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return r is not None


# ============================================================
# SECTION GENERATORS
# ============================================================

def section_pipeline(conn):
    """Sales pipeline — prospects, stages, and deal values."""
    if not table_exists(conn, "pipeline"):
        return []
    lines = ["## Sales Pipeline", ""]

    # Active pipeline summary
    row = query_one(conn, """
        SELECT
            COUNT(*) as total_leads,
            SUM(CASE WHEN stage NOT IN ('Closed Won', 'Closed Lost') THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN stage = 'Closed Won' THEN 1 ELSE 0 END) as won,
            SUM(CASE WHEN stage = 'Closed Lost' THEN 1 ELSE 0 END) as lost,
            SUM(CASE WHEN stage NOT IN ('Closed Won', 'Closed Lost') THEN setup_fee_quoted ELSE 0 END) as pipeline_value,
            SUM(CASE WHEN stage NOT IN ('Closed Won', 'Closed Lost') THEN retainer_quoted ELSE 0 END) as pipeline_mrr
        FROM pipeline
        WHERE date = (SELECT MAX(date) FROM pipeline)
    """)
    if row:
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Active prospects | {fmt_number(row.get('active'))} |")
        lines.append(f"| Pipeline value (setup fees) | {fmt_currency(row.get('pipeline_value'))} |")
        lines.append(f"| Pipeline MRR (retainers) | {fmt_currency(row.get('pipeline_mrr'))}/mo |")
        lines.append(f"| Closed Won | {fmt_number(row.get('won'))} clients |")
        lines.append(f"| Closed Lost | {fmt_number(row.get('lost'))} |")
        lines.append("")

    # Stage breakdown
    stages = query_all(conn, """
        SELECT stage, COUNT(*) as count
        FROM pipeline
        WHERE date = (SELECT MAX(date) FROM pipeline)
          AND stage NOT IN ('Closed Won', 'Closed Lost')
        GROUP BY stage
        ORDER BY CASE stage
            WHEN 'Lead' THEN 1
            WHEN 'Discovery Scheduled' THEN 2
            WHEN 'Discovery Done' THEN 3
            WHEN 'Proposal Sent' THEN 4
            WHEN 'Negotiating' THEN 5
            ELSE 6
        END
    """)
    if stages:
        lines.append("**By Stage:**")
        for s in stages:
            lines.append(f"- {s['stage']}: {s['count']}")
        lines.append("")

    return lines


def section_revenue(conn):
    """Revenue — setup fees collected, MRR, progress to $50k target."""
    if not table_exists(conn, "revenue"):
        return []
    lines = ["## Revenue", ""]

    row = query_one(conn, """
        SELECT
            SUM(setup_fee_collected) as total_setup_fees,
            SUM(CASE WHEN active = 1 THEN monthly_retainer ELSE 0 END) as current_mrr,
            COUNT(CASE WHEN active = 1 THEN 1 END) as active_clients,
            COUNT(*) as total_clients
        FROM revenue
        WHERE date = (SELECT MAX(date) FROM revenue)
    """)
    if row:
        total = (row.get('total_setup_fees') or 0)
        target = 50000
        pct = (total / target * 100) if target else 0
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total revenue collected | {fmt_currency(total)} |")
        lines.append(f"| Progress to $50k target | {pct:.1f}% |")
        lines.append(f"| Current MRR (retainers) | {fmt_currency(row.get('current_mrr'))}/mo |")
        lines.append(f"| Active clients | {fmt_number(row.get('active_clients'))} |")
        lines.append(f"| Total clients (all time) | {fmt_number(row.get('total_clients'))} |")
        lines.append("")

    return lines


def section_outreach(conn):
    """Cold outreach — Instantly AI campaign performance."""
    if not table_exists(conn, "outreach_summary"):
        return []
    lines = ["## Outreach Performance", ""]

    # Latest week
    row = query_one(conn, """
        SELECT * FROM outreach_summary
        ORDER BY week DESC LIMIT 1
    """)
    if row:
        emails = row.get('emails_sent') or 0
        replies = row.get('replies') or 0
        calls = row.get('calls_booked') or 0
        proposals = row.get('proposals_sent') or 0
        reply_rate = (replies / emails * 100) if emails else 0
        lines.append(f"*Latest week: {row.get('week')}*")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Emails sent | {fmt_number(emails)} |")
        lines.append(f"| Replies | {fmt_number(replies)} ({reply_rate:.1f}%) |")
        lines.append(f"| Calls booked | {fmt_number(calls)} |")
        lines.append(f"| Proposals sent | {fmt_number(proposals)} |")
        lines.append("")

    # Last 4 weeks trend
    rows = query_all(conn, """
        SELECT week, emails_sent, replies, calls_booked
        FROM outreach_summary
        ORDER BY week DESC LIMIT 4
    """)
    if len(rows) > 1:
        lines.append("**4-Week Trend:**")
        lines.append("| Week | Emails | Replies | Calls |")
        lines.append("|------|--------|---------|-------|")
        for r in rows:
            lines.append(f"| {r['week']} | {fmt_number(r.get('emails_sent'))} | {fmt_number(r.get('replies'))} | {fmt_number(r.get('calls_booked'))} |")
        lines.append("")

    return lines


def section_fx_rates(conn):
    """FX rates — starter collector."""
    if not table_exists(conn, "fx_rates"):
        return []
    lines = ["## Exchange Rates (USD base)", ""]
    lines.append("| Currency | Rate | As Of |")
    lines.append("|----------|------|-------|")
    rows = query_all(conn, """
        SELECT date, currency, rate FROM fx_rates
        WHERE date = (SELECT MAX(date) FROM fx_rates)
        ORDER BY currency
    """)
    for r in rows:
        lines.append(f"| {r['currency']} | {r['rate']:.4f} | {r['date']} |")
    lines.append("")
    return lines


# Register all section functions — order = order in key-metrics.md
SECTIONS = [
    section_revenue,
    section_pipeline,
    section_outreach,
    section_fx_rates,
]


def generate(conn):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# Key Metrics",
        "",
        f"> Auto-generated from database. Last updated: {today}",
        f"> Source: `data/data.db` | Regenerate: `python scripts/generate_metrics.py`",
        "",
    ]

    for section_fn in SECTIONS:
        try:
            section_lines = section_fn(conn)
            if section_lines:
                lines.extend(section_lines)
        except Exception as e:
            lines.append(f"<!-- Error in {section_fn.__name__}: {e} -->")
            lines.append("")

    # Data freshness
    lines.append("## Data Freshness")
    lines.append("| Source | Latest Record | Status |")
    lines.append("|--------|---------------|--------|")

    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name != 'collection_log' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()

    for t in tables:
        name = t["name"]
        try:
            row = conn.execute(f"SELECT MAX(date) as d FROM {name}").fetchone()
            if row and row["d"]:
                lines.append(f"| {name} | {row['d']} | Connected |")
            else:
                lines.append(f"| {name} | — | Empty |")
        except Exception:
            lines.append(f"| {name} | — | No date column |")

    lines.append("")
    return "\n".join(lines)


def main():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        print("Run collection first: python scripts/collect.py")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    content = generate(conn)
    conn.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(content)
    print(f"Key metrics written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
