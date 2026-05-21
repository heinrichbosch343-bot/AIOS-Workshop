"""
Daily Brief — Funnel Metrics Builder

Reads your funnel.md and queries the database to build a structured
metrics snapshot. Each metric includes today's value and a 7-day average
for trend comparison.

This module adapts to YOUR data — it reads funnel.md to know what stages
and metrics matter for your business, then queries only the tables you have.
"""

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def find_funnel_file():
    """Find the funnel.md file in the workspace."""
    candidates = [
        WORKSPACE_ROOT / "context" / "funnel.md",
        WORKSPACE_ROOT / "context" / "group" / "funnel.md",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def parse_funnel(funnel_path=None):
    """Parse funnel.md into a structured dict."""
    path = funnel_path or find_funnel_file()
    if not path or not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    result = {"currency": "USD", "stages": [], "targets": {}}

    currency_match = re.search(r"## Currency\s*\n(\w+)", text)
    if currency_match:
        result["currency"] = currency_match.group(1).strip()

    stage_pattern = re.compile(
        r"### \d+\.\s*(.+?)\n(.*?)(?=### \d+\.|## Monthly Targets|## Targets|\Z)",
        re.DOTALL,
    )
    for match in stage_pattern.finditer(text):
        stage_name = match.group(1).strip()
        stage_body = match.group(2).strip()

        lines = stage_body.split("\n")
        description = ""
        metrics = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            metric_match = re.match(
                r"^-\s*(.+?)\s*→\s*(\w+)\.(\w+)\s*$", line
            )
            if metric_match:
                metrics.append({
                    "label": metric_match.group(1).strip(),
                    "table": metric_match.group(2).strip(),
                    "column": metric_match.group(3).strip(),
                })
            elif not metrics and not description:
                description = line.lstrip("- ").strip()

        result["stages"].append({
            "name": stage_name,
            "description": description,
            "metrics": metrics,
        })

    targets_match = re.search(
        r"## (?:Monthly )?Targets\s*\n(.*?)(?=##|\Z)", text, re.DOTALL
    )
    if targets_match:
        for line in targets_match.group(1).strip().split("\n"):
            line = line.strip()
            target_match = re.match(r"^-\s*(.+?):\s*(.+)$", line)
            if target_match:
                result["targets"][target_match.group(1).strip()] = (
                    target_match.group(2).strip()
                )

    return result


def _ensure_pipeline_view(conn):
    """Create a pipeline_daily view so funnel.md can reference pipeline stage counts.

    This view counts clients by status so the funnel metrics system can query
    pipeline data the same way it queries time-series data.
    """
    try:
        conn.execute("""
            CREATE VIEW IF NOT EXISTS pipeline_daily AS
            SELECT
                date('now', 'localtime') AS date,
                SUM(CASE WHEN LOWER(status) = 'prospect' THEN 1 ELSE 0 END) AS prospects,
                SUM(CASE WHEN LOWER(status) = 'assessment_booked' THEN 1 ELSE 0 END) AS assessment_booked,
                SUM(CASE WHEN LOWER(status) = 'assessment_delivered' THEN 1 ELSE 0 END) AS assessment_delivered,
                SUM(CASE WHEN LOWER(status) = 'proposal_sent' THEN 1 ELSE 0 END) AS proposal_sent,
                SUM(CASE WHEN LOWER(status) = 'active_build' THEN 1 ELSE 0 END) AS active_build,
                SUM(CASE WHEN LOWER(status) = 'handoff_complete' THEN 1 ELSE 0 END) AS handoff_complete,
                COUNT(*) AS total_pipeline
            FROM clients
        """)
        conn.commit()
    except Exception:
        pass  # View may already exist or clients table missing — both are fine


def _table_or_view_exists(conn, name):
    """Check if a table OR view exists in the database."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE (type='table' OR type='view') AND name=?",
        (name,)
    ).fetchone()
    return row is not None


# Keep old name as alias for compatibility
_table_exists = _table_or_view_exists


def _get_metric_value(conn, table, column, date):
    """Get a metric value for a specific date."""
    try:
        row = conn.execute(
            f"SELECT {column} FROM {table} WHERE date = ?", (date,)
        ).fetchone()
        return dict(row)[column] if row else None
    except Exception:
        return None


def _get_latest_value(conn, table, column):
    """Get the most recent value for a metric."""
    try:
        row = conn.execute(
            f"SELECT {column}, date FROM {table} ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if row:
            r = dict(row)
            return r[column], r["date"]
        return None, None
    except Exception:
        return None, None


def _get_7day_avg(conn, table, column, end_date):
    """Calculate 7-day average for a metric ending on end_date."""
    try:
        start = (
            datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=7)
        ).strftime("%Y-%m-%d")
        rows = conn.execute(
            f"SELECT {column} FROM {table} WHERE date > ? AND date <= ?",
            (start, end_date),
        ).fetchall()
        values = [dict(r)[column] for r in rows if dict(r)[column] is not None]
        if values:
            return round(sum(values) / len(values), 1)
        return None
    except Exception:
        return None


def build_funnel_metrics(conn, target_date=None):
    """Build a complete funnel metrics snapshot from the database."""
    if target_date is None:
        target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Ensure pipeline view exists for CRM-style pipeline metrics
    _ensure_pipeline_view(conn)

    funnel = parse_funnel()
    if not funnel:
        return {"date": target_date, "currency": "USD", "stages": [], "targets": {}}

    result = {
        "date": target_date,
        "currency": funnel["currency"],
        "stages": [],
        "targets": funnel.get("targets", {}),
    }

    for stage in funnel["stages"]:
        stage_data = {
            "name": stage["name"],
            "description": stage["description"],
            "metrics": [],
        }

        for metric in stage["metrics"]:
            if not _table_or_view_exists(conn, metric["table"]):
                continue

            value = _get_metric_value(
                conn, metric["table"], metric["column"], target_date
            )
            date_used = target_date

            if value is None:
                value, date_used = _get_latest_value(
                    conn, metric["table"], metric["column"]
                )

            avg_7d = _get_7day_avg(
                conn, metric["table"], metric["column"], date_used or target_date
            )

            direction = "on_par"
            if value is not None and avg_7d is not None and avg_7d > 0:
                ratio = value / avg_7d
                if ratio > 1.05:
                    direction = "above"
                elif ratio < 0.95:
                    direction = "below"

            stage_data["metrics"].append({
                "label": metric["label"],
                "value": value,
                "avg_7d": avg_7d,
                "direction": direction,
                "date": date_used,
            })

        if any(m["value"] is not None for m in stage_data["metrics"]):
            result["stages"].append(stage_data)

    return result


def format_metrics_text(metrics):
    """Format funnel metrics as plain text for the LLM prompt."""
    if not metrics or not metrics.get("stages"):
        return "No funnel metrics available."

    lines = [f"Date: {metrics['date']}", f"Currency: {metrics['currency']}", ""]

    for stage in metrics["stages"]:
        lines.append(f"{stage['name'].upper()}:")
        if stage["description"]:
            lines.append(f"  ({stage['description']})")

        for m in stage["metrics"]:
            val = m["value"]
            avg = m["avg_7d"]

            if val is None:
                lines.append(f"  {m['label']}: No data")
                continue

            if isinstance(val, float) and val > 1000:
                val_str = f"{val:,.0f}"
            elif isinstance(val, float):
                val_str = f"{val:.1f}"
            else:
                val_str = f"{val:,}" if isinstance(val, int) else str(val)

            avg_str = ""
            if avg is not None:
                if isinstance(avg, float) and avg > 1000:
                    avg_str = f" (7d avg: {avg:,.0f})"
                elif isinstance(avg, float):
                    avg_str = f" (7d avg: {avg:.1f})"
                else:
                    avg_str = f" (7d avg: {avg})"

            arrow = ""
            if m["direction"] == "above":
                arrow = " ↑"
            elif m["direction"] == "below":
                arrow = " ↓"

            lines.append(f"  {m['label']}: {val_str}{arrow}{avg_str}")

        lines.append("")

    if metrics.get("targets"):
        lines.append("MONTHLY TARGETS:")
        for name, target in metrics["targets"].items():
            lines.append(f"  {name}: {target}")

    return "\n".join(lines)


if __name__ == "__main__":
    """Quick test — show funnel structure and current metrics."""
    funnel = parse_funnel()
    if funnel:
        print(f"Currency: {funnel['currency']}")
        print(f"Stages: {len(funnel['stages'])}")
        for s in funnel["stages"]:
            print(f"  {s['name']}: {len(s['metrics'])} metrics")
            for m in s["metrics"]:
                print(f"    - {m['label']} → {m['table']}.{m['column']}")
    else:
        print("No funnel.md found.")
