#!/usr/bin/env python3
"""Sync the local CRM email queue with the Railway drip sender.

Two directions, one run:
  PUSH  local outputs/crm/email-queue.csv rows with status=queued go up to the
        backend (POST /email/drip/queue). Locally they become status=cloud so
        the local drip script can never double-send them.
  PULL  cloud statuses come back down (GET /email/drip/status): rows the cloud
        has sent are marked sent locally, logged to activity-log.csv (so the
        dashboard counters move), and the matching CRM contact goes to
        contacted.

Needs two lines in .env:
  BOSCHAI_BACKEND_URL=https://<your-service>.up.railway.app
  API_SECRET_KEY=<same key the backend uses>

Usage:
    uv run --no-project --system-certs --with requests python scripts/crm_cloud_sync.py
"""

import csv
import sys
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CRM_DIR = ROOT / "outputs" / "crm"
QUEUE_CSV = CRM_DIR / "email-queue.csv"
CRM_CSV = CRM_DIR / "crm.csv"
ACTIVITY_CSV = CRM_DIR / "activity-log.csv"

QUEUE_FIELDS = ["id", "to", "name", "firm", "subject", "body",
                "status", "queued_at", "sent_at", "error"]


def read_env():
    env = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def read_rows(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_queue(rows):
    with open(QUEUE_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=QUEUE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def log_activity(row):
    exists = ACTIVITY_CSV.exists()
    with open(ACTIVITY_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "date", "channel", "qty", "name", "firm", "action", "outcome", "notes"])
        if not exists:
            writer.writeheader()
        writer.writerow({
            "date": (row.get("sent_at") or datetime.now().isoformat())[:10],
            "channel": "email",
            "qty": 1,
            "name": row.get("name", ""),
            "firm": row.get("firm", ""),
            "action": "email_sent",
            "outcome": "sent",
            "notes": f"cloud drip: {row.get('subject', '')[:60]}",
        })


def mark_crm_contacted(to_addr):
    rows = read_rows(CRM_CSV)
    if not rows:
        return
    changed = False
    for r in rows:
        if (r.get("email", "").strip().lower() == to_addr.lower()
                and r.get("status") in ("", "new")):
            r["status"] = "contacted"
            r["last_touch"] = datetime.now().strftime("%Y-%m-%d")
            changed = True
    if changed:
        with open(CRM_CSV, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()),
                                    extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def main():
    env = read_env()
    base = env.get("BOSCHAI_BACKEND_URL", "").rstrip("/")
    key = env.get("API_SECRET_KEY", "")
    if not base or not key:
        print("Missing BOSCHAI_BACKEND_URL or API_SECRET_KEY in .env — "
              "add both, then run this again.")
        return 1
    headers = {"x-api-key": key}

    queue = read_rows(QUEUE_CSV)

    # PUSH: hand queued rows to the cloud
    to_push = [r for r in queue if r.get("status") == "queued"
               and "@" in r.get("to", "")]
    if to_push:
        resp = requests.post(f"{base}/email/drip/queue", headers=headers,
                             json={"items": [{
                                 "local_id": r["id"], "to": r["to"],
                                 "name": r.get("name", ""),
                                 "firm": r.get("firm", ""),
                                 "subject": r["subject"], "body": r["body"],
                             } for r in to_push]},
                             timeout=30)
        resp.raise_for_status()
        result = resp.json()
        pushed_ids = {r["id"] for r in to_push}
        queue = [{**r, "status": "cloud"} if r["id"] in pushed_ids else r
                 for r in queue]
        write_queue(queue)
        print(f"pushed {result.get('queued', 0)} to the cloud queue "
              f"({result.get('duplicates', 0)} already there)")
    else:
        print("nothing new to push")

    # PULL: mirror cloud sends back into the local files
    resp = requests.get(f"{base}/email/drip/status", headers=headers, timeout=30)
    resp.raise_for_status()
    cloud = {r["local_id"]: r for r in resp.json().get("rows", []) if r.get("local_id")}

    synced = 0
    updated_queue = []
    for r in queue:
        c = cloud.get(r["id"])
        if c and c["status"] in ("sent", "failed", "skipped") and r["status"] != c["status"]:
            fresh = {**r, "status": c["status"],
                     "sent_at": c.get("sent_at") or "",
                     "error": c.get("error") or ""}
            if c["status"] == "sent":
                log_activity(fresh)
                mark_crm_contacted(fresh.get("to", ""))
                synced += 1
            updated_queue.append(fresh)
        else:
            updated_queue.append(r)
    if synced or updated_queue != queue:
        write_queue(updated_queue)
    counts = resp.json().get("counts", {})
    print(f"cloud queue now: {counts} | new sends mirrored locally: {synced}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
