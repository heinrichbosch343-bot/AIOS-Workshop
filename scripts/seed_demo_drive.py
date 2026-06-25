"""
seed_demo_drive.py  —  creates a "BoschAI · Demo Proposals" folder in Google Drive
and populates it with 7 realistic mock proposals as Google Docs.

Run once before the LinkedIn video:
    python scripts/seed_demo_drive.py

Requires credentials.json from the data-pooling module (already set up).
Opens a browser once for write-permission consent (uses a separate token so
the existing read-only token is untouched).
"""

import sys
from pathlib import Path

# Resolve credentials from the data-pooling module
SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "module-installs" / "AIOS-data-pooling-v2" / "AIOS Data Pooling" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))
import pool_config  # loads .env

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_PATH = SCRIPTS_DIR / "token_write.json"
CREDS_PATH = pool_config.GOOGLE_CREDENTIALS_FILE
FOLDER_NAME = "BoschAI - Demo Proposals"
EXISTING_FOLDER_ID = "1StDGhS9VF1Y2Nvdm_NrzKIu6Rxdxv_qZ"  # already created — reuse it

# ── Auth ──────────────────────────────────────────────────────────────────────

def get_write_credentials() -> Credentials:
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
    TOKEN_PATH.write_text(creds.to_json())
    return creds


# ── Proposal content ──────────────────────────────────────────────────────────

PROPOSALS = [
    {
        "title": "Proposal — Nexgen Manufacturing (AI Process Automation)",
        "body": """CLIENT: Nexgen Manufacturing (Pty) Ltd
CONTACT: Sipho Dlamini, Head of Operations
DATE: 12 May 2026
STATUS: Pending — awaiting sign-off from CFO
VALID UNTIL: 30 June 2026

SCOPE OF WORK
Phase 1 — Process Audit & Automation Mapping (4 weeks)
  Full audit of current production floor workflows, quality control checks, and
  shift reporting processes. Identify the top 8 automation candidates.

Phase 2 — AIOS Build & Integration (8 weeks)
  Build custom AI layer integrating with their existing ERP (SAP B1).
  Automate shift reports, defect classification, and supplier follow-ups.

Phase 3 — Training & Handover (2 weeks)
  Onsite training with operations team. Full documentation delivered.

INVESTMENT
  Phase 1: R 45,000
  Phase 2: R 185,000
  Phase 3: R 25,000
  Monthly Retainer (post-handover): R 12,500/month

TOTAL PROJECT VALUE: R 255,000 + retainer
PAYMENT TERMS: 50% upfront, 25% at Phase 2 kickoff, 25% on completion.

NOTES
Client expressed concern about integration with legacy SAP version (6.0).
Heinrich to confirm compatibility before sign-off. Decision expected by 20 June.
""",
    },
    {
        "title": "Proposal — Hartley Retail Group (Customer Intelligence System)",
        "body": """CLIENT: Hartley Retail Group
CONTACT: Anri Hartley, CEO
DATE: 28 April 2026
STATUS: APPROVED — project starting 1 July 2026
VALID UNTIL: N/A (signed)

SCOPE OF WORK
Build a customer intelligence layer across 12 retail branches.
Consolidate POS data, loyalty programme, and in-store foot traffic into a single
AI dashboard that generates weekly insights and flags stock anomalies.

Deliverables:
  - Central data pool ingesting from 12 branch POS systems
  - Weekly AI-generated brief delivered to Anri every Monday 7am
  - Stock anomaly alerts via WhatsApp
  - Competitor pricing monitor (web scrape + weekly summary)

INVESTMENT
  Setup & Build: R 320,000
  Monthly Retainer: R 18,000/month (12-month minimum)

PAYMENT TERMS: R 80,000 upfront, balance billed in 4 monthly instalments.
CONTRACT START: 1 July 2026
CONTRACT LENGTH: 12 months minimum

NOTES
Contract signed 15 May 2026. Kick-off meeting scheduled 25 June 2026.
Anri wants the first weekly brief live before the school holiday trading period.
""",
    },
    {
        "title": "Proposal — BrightPath Logistics (Fleet & Driver Intelligence)",
        "body": """CLIENT: BrightPath Logistics CC
CONTACT: Trevor Mokoena, Operations Director
DATE: 3 June 2026
STATUS: In negotiation — price sensitivity flagged
VALID UNTIL: 15 July 2026

SCOPE OF WORK
AIOS layer to monitor 47-vehicle fleet: automated driver scorecards, route
optimisation summaries, and fuel anomaly detection. Weekly AI brief to Trevor
and daily SMS to each driver with their score.

Phases:
  Phase 1 — Telematics data integration (Ctrack API): 3 weeks
  Phase 2 — Scoring model + dashboard build: 5 weeks
  Phase 3 — Driver comms automation (WhatsApp/SMS): 2 weeks

INVESTMENT (original quote)
  Build: R 195,000
  Monthly: R 9,500/month

REVISED QUOTE (after negotiation, 10 June)
  Build: R 165,000
  Monthly: R 8,000/month
  Condition: 18-month retainer commitment

NOTES
Trevor pushed back on original price — he has a competing quote from a local dev
shop at R 140k build-only (no AI, no retainer model). Heinrich to send a value
comparison doc by 18 June. Decision expected EOD 25 June.
""",
    },
    {
        "title": "Proposal — Sandstone Medical Group (HR & Compliance Automation)",
        "body": """CLIENT: Sandstone Medical Group
CONTACT: Dr. Fatima Essop, Practice Manager
DATE: 18 March 2026
STATUS: CLOSED — client went with internal IT team
VALID UNTIL: Expired

SCOPE OF WORK
Automate HR onboarding for clinical and admin staff, compliance document
tracking (HPCSA renewals, BLS certifications), and monthly payroll summary
generation across 3 practices.

INVESTMENT
  Build: R 145,000
  Monthly: R 7,500/month

OUTCOME
Client decided to build internally using a junior developer. Decision made
4 May 2026. Relationship maintained — Dr. Essop open to revisiting in 12 months
if internal build stalls (she flagged this explicitly).

LESSON LEARNED
Medical clients have longer decision cycles due to committee buy-in requirements.
Follow up with Sandstone in November 2026.
""",
    },
    {
        "title": "Proposal — Cape Agri Cooperative (Seasonal Demand Forecasting)",
        "body": """CLIENT: Cape Agri Cooperative
CONTACT: Pieter van Zyl, General Manager
DATE: 20 May 2026
STATUS: Pending — follow-up required (gone quiet since 1 June)
VALID UNTIL: 20 July 2026

SCOPE OF WORK
Build a seasonal demand forecasting tool fed by 3 years of historical sales data,
weather API, and regional crop cycle data. Output: a weekly planting and stock
recommendation for the co-op's 220 member farmers.

Deliverables:
  - Data ingestion pipeline (Excel exports + weather API)
  - Forecasting model (AI-driven, retrained monthly)
  - Member-facing weekly WhatsApp summary
  - GM dashboard with override controls

INVESTMENT
  Build: R 210,000
  Monthly: R 11,000/month

PAYMENT TERMS: Milestone-based — 4 equal payments of R 52,500.

NOTES
Pieter was enthusiastic in the first meeting but has not responded to follow-up
emails sent 3 June and 10 June. Possible budget freeze due to drought conditions
affecting member revenues. Heinrich to call directly before 25 June. Risk: HIGH.
""",
    },
    {
        "title": "Proposal — Elevate Property Group (Investment Intelligence Dashboard)",
        "body": """CLIENT: Elevate Property Group
CONTACT: Nomsa Khumalo, Investment Director
DATE: 7 June 2026
STATUS: Proposal sent — first response expected week of 23 June
VALID UNTIL: 31 July 2026

SCOPE OF WORK
Build an investment intelligence layer across Elevate's portfolio of 34 commercial
properties. Consolidate rental income, vacancy rates, maintenance costs, and market
comparables into a single AI-powered dashboard. Monthly AI brief to the board.

Key features:
  - Portfolio health score (AI-generated, updated monthly)
  - Automated tenant risk flags (missed payments, upcoming renewals)
  - Market comparable tracker (auto-pulls from PropData API)
  - Board-ready PDF brief generated on the 1st of each month

INVESTMENT
  Build: R 285,000
  Monthly Retainer: R 15,500/month

PAYMENT TERMS: 40% upfront (R 114,000), 60% on go-live.
ESTIMATED GO-LIVE: 10 weeks from contract signature.

NOTES
Nomsa was referred by Anri Hartley (Hartley Retail Group — existing client).
Warm lead. She reviewed our work for Hartley before the meeting. Strong fit.
""",
    },
    {
        "title": "Proposal — TechBridge Academy (Student Performance AI)",
        "body": """CLIENT: TechBridge Academy (Private School Group — 4 campuses)
CONTACT: Mr. Deon Fredericks, Executive Principal
DATE: 1 June 2026
STATUS: Pending — board presentation scheduled 30 June 2026
VALID UNTIL: 31 August 2026

SCOPE OF WORK
Phase 1 — Data Consolidation (6 weeks)
  Ingest student performance data from 4 campuses (currently in 3 different SIS
  platforms). Normalise and pool into a central data store.

Phase 2 — Intelligence Layer (6 weeks)
  AI model to flag at-risk students (attendance + performance trends).
  Weekly brief to each campus head. Monthly board summary.

Phase 3 — Parent Communication Automation (4 weeks)
  Auto-generate personalised progress reports and flag parents when intervention
  is recommended.

INVESTMENT
  Build (all 3 phases): R 380,000
  Monthly Retainer: R 16,000/month

PAYMENT TERMS: 3 milestone payments — R 127,000 per phase completion.
NOTES
Board is conservative — Deon believes they'll approve if Heinrich can present
ROI in terms of student retention (each student = ~R 85,000/year in fees).
Heinrich to prepare a 1-page ROI case before the 30 June board meeting.
Decision by 15 July 2026.
""",
    },
]

# ── Drive helpers ─────────────────────────────────────────────────────────────

def create_folder(service, name: str) -> str:
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    f = service.files().create(body=meta, fields="id").execute()
    return f["id"]


def create_doc(service, folder_id: str, title: str, body: str) -> str:
    meta = {
        "name": title,
        "mimeType": "application/vnd.google-apps.document",
        "parents": [folder_id],
    }
    f = service.files().create(body=meta, fields="id").execute()
    file_id = f["id"]

    # Write the body text via the Docs API
    docs = build("docs", "v1", credentials=get_write_credentials())
    docs.documents().batchUpdate(
        documentId=file_id,
        body={"requests": [{"insertText": {"location": {"index": 1}, "text": body}}]},
    ).execute()
    return file_id


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("Authenticating with Google Drive...")
    creds = get_write_credentials()
    drive = build("drive", "v3", credentials=creds)

    print(f'\nCreating folder: "{FOLDER_NAME}"')
    folder_id = create_folder(drive, FOLDER_NAME)
    print(f"  Folder ID: {folder_id}")

    for i, p in enumerate(PROPOSALS, 1):
        print(f"  [{i}/{len(PROPOSALS)}] Creating: {p['title']}")
        create_doc(drive, folder_id, p["title"], p["body"])

    folder_url = f"https://drive.google.com/drive/folders/{folder_id}"
    print(f"\nDone! Your demo folder is ready:")
    print(f"  {folder_url}")
    print(f"\nNow open the dashboard and select '{FOLDER_NAME}' from the dropdown.")
    print("Suggested questions to ask on camera:")
    print("  1. Which proposals are still pending and what is the total value at risk?")
    print("  2. Which client is most likely to go cold and why?")
    print("  3. What are the payment terms across all proposals?")
    print("  4. Summarise the status of every proposal in one paragraph.")
    print("  5. Which proposal has the highest monthly retainer value?")


if __name__ == "__main__":
    main()
