"""
seed_100_proposals.py — generates 100 realistic SA business proposals
and uploads them as Google Docs into the existing "BoschAI - Demo Proposals" folder.

Run:  python scripts/seed_100_proposals.py
"""

import sys
from pathlib import Path

SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "module-installs" / "AIOS-data-pooling-v2" / "AIOS Data Pooling" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_DIR))
import pool_config

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_PATH = SCRIPTS_DIR / "token_write.json"
CREDS_PATH = pool_config.GOOGLE_CREDENTIALS_FILE
FOLDER_ID = "1StDGhS9VF1Y2Nvdm_NrzKIu6Rxdxv_qZ"


def get_creds():
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return creds


PROPOSALS = [
    # ── Manufacturing ──────────────────────────────────────────────────────────
    {
        "title": "Proposal 001 — Nexgen Manufacturing (AI Process Automation)",
        "body": """CLIENT: Nexgen Manufacturing (Pty) Ltd
CONTACT: Sipho Dlamini, Head of Operations | sipho@nexgenmfg.co.za
DATE: 12 May 2026 | STATUS: Pending — awaiting CFO sign-off | VALID UNTIL: 30 Jun 2026

SCOPE: Full audit of production floor workflows + AIOS build integrating with SAP B1.
Automate shift reports, defect classification, supplier follow-ups.

INVESTMENT: Build R 255,000 | Monthly retainer R 12,500/month
PAYMENT: 50% upfront, 25% Phase 2 kickoff, 25% on completion.
NOTES: CFO concern re legacy SAP 6.0 compatibility. Heinrich to confirm by 20 Jun.""",
    },
    {
        "title": "Proposal 002 — Steelcore Industries (Predictive Maintenance AI)",
        "body": """CLIENT: Steelcore Industries CC
CONTACT: André Venter, Plant Manager | aventer@steelcore.co.za
DATE: 3 Jun 2026 | STATUS: In negotiation | VALID UNTIL: 31 Jul 2026

SCOPE: Predictive maintenance layer across 14 CNC machines. Sensor data ingestion,
anomaly detection, automated maintenance scheduling, and downtime cost reporting.

INVESTMENT: Build R 310,000 | Monthly retainer R 14,000/month
NOTES: André wants a pilot on 3 machines first before full rollout. Pilot pricing: R 75,000.""",
    },
    {
        "title": "Proposal 003 — Highveld Electrical Components (Inventory Intelligence)",
        "body": """CLIENT: Highveld Electrical Components (Pty) Ltd
CONTACT: Lerato Mokoena, Supply Chain Director | lmokoena@highveldelec.co.za
DATE: 28 Apr 2026 | STATUS: APPROVED — start 1 Aug 2026 | VALID UNTIL: N/A (signed)

SCOPE: AI inventory layer across 3 warehouses. Auto-reorder triggers, supplier
performance scoring, and monthly cost-variance brief to the board.

INVESTMENT: Build R 195,000 | Monthly retainer R 9,000/month
NOTES: Contract signed 20 May 2026. Integration with Sage 200 confirmed.""",
    },
    {
        "title": "Proposal 004 — Karoo Plastics (Quality Control Automation)",
        "body": """CLIENT: Karoo Plastics Manufacturing
CONTACT: Frikkie Botha, QC Manager | fbotha@karooplastics.co.za
DATE: 15 Jun 2026 | STATUS: Proposal sent — response expected 30 Jun | VALID UNTIL: 15 Aug 2026

SCOPE: Computer vision QC system for injection moulding line. Defect classification,
rejection rate tracking, and weekly quality brief to ops team.

INVESTMENT: Build R 420,000 | Monthly retainer R 18,500/month
NOTES: Frikkie flagged that current rejection rate is 4.2% — target is below 1%.""",
    },
    {
        "title": "Proposal 005 — Cape Metal Fabricators (Quoting Automation)",
        "body": """CLIENT: Cape Metal Fabricators CC
CONTACT: Pieter du Plessis, MD | pduplessis@capemetal.co.za
DATE: 22 May 2026 | STATUS: CLOSED — lost to competitor | VALID UNTIL: Expired

SCOPE: Automated quoting system pulling material costs from 5 suppliers in real-time.
Quote generation time target: under 4 minutes from spec to PDF.

INVESTMENT: Build R 145,000 | Monthly retainer R 6,500/month
OUTCOME: Client chose a cheaper offshore dev shop. Follow up in 6 months.""",
    },
    # ── Retail ────────────────────────────────────────────────────────────────
    {
        "title": "Proposal 006 — Hartley Retail Group (Customer Intelligence System)",
        "body": """CLIENT: Hartley Retail Group
CONTACT: Anri Hartley, CEO | anri@hartleyretail.co.za
DATE: 28 Apr 2026 | STATUS: APPROVED — project starting 1 Jul 2026 | VALID UNTIL: N/A (signed)

SCOPE: Customer intelligence layer across 12 branches. POS + loyalty + foot traffic
consolidated into AI dashboard with weekly brief and stock anomaly alerts.

INVESTMENT: Build R 320,000 | Monthly retainer R 18,000/month (12-month min)
NOTES: Contract signed 15 May 2026. First brief must be live before school holidays.""",
    },
    {
        "title": "Proposal 007 — Sunshine Supermarkets (Shrinkage & Theft Detection)",
        "body": """CLIENT: Sunshine Supermarkets (9 stores)
CONTACT: Desiree Jacobs, Loss Prevention Manager | djacobs@sunshinefood.co.za
DATE: 10 Jun 2026 | STATUS: Pending — board presentation 15 Jul | VALID UNTIL: 31 Aug 2026

SCOPE: AI shrinkage detection layer integrating CCTV metadata, POS voids, and
stock variance. Weekly risk report and flagged-incident summary per store.

INVESTMENT: Build R 275,000 | Monthly retainer R 12,000/month
NOTES: Current shrinkage estimated at R 2.1M/year. ROI case: payback in 4 months.""",
    },
    {
        "title": "Proposal 008 — Urban Thread Clothing (Demand Forecasting)",
        "body": """CLIENT: Urban Thread Clothing (Pty) Ltd
CONTACT: Ntombi Zulu, Head of Buying | nzulu@urbanthread.co.za
DATE: 5 May 2026 | STATUS: In negotiation — size of pilot being scoped | VALID UNTIL: 5 Jul 2026

SCOPE: Seasonal demand forecasting tool for apparel buying. Integrates with their
SYSPRO ERP. Output: per-SKU buy recommendations 10 weeks ahead of season.

INVESTMENT: Pilot (20 SKUs) R 85,000 | Full rollout R 230,000 | Monthly R 10,500/month
NOTES: Ntombi wants to run pilot on winter 2027 buy before committing to full system.""",
    },
    {
        "title": "Proposal 009 — Cornerstone Home & Garden (Supplier Intelligence)",
        "body": """CLIENT: Cornerstone Home & Garden Stores
CONTACT: Mark Swanepoel, Procurement Director | mswanepoel@cornerstone.co.za
DATE: 18 Mar 2026 | STATUS: CLOSED — client paused budget | VALID UNTIL: Expired

SCOPE: Supplier intelligence dashboard scoring 47 suppliers on lead time, quality,
and price stability. Automated monthly scorecard emails to each supplier.

INVESTMENT: Build R 160,000 | Monthly retainer R 7,500/month
NOTES: Budget freeze due to Rand volatility impacting import costs. Re-engage Oct 2026.""",
    },
    {
        "title": "Proposal 010 — Freshfields Pharmacy Group (Stock & Compliance AI)",
        "body": """CLIENT: Freshfields Pharmacy Group (22 branches)
CONTACT: Dr. Yusuf Patel, Group Operations Director | ypatel@freshfields.co.za
DATE: 2 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 2 Aug 2026

SCOPE: Controlled substance stock monitoring, expiry tracking, and SAHPRA compliance
reporting automation across all branches. Alert system for stock deviations.

INVESTMENT: Build R 340,000 | Monthly retainer R 15,000/month
NOTES: Yusuf mentioned SAHPRA audit is due Q4 — urgency is high. Call this week.""",
    },
    # ── Logistics & Fleet ─────────────────────────────────────────────────────
    {
        "title": "Proposal 011 — BrightPath Logistics (Fleet & Driver Intelligence)",
        "body": """CLIENT: BrightPath Logistics CC
CONTACT: Trevor Mokoena, Operations Director | tmokoena@brightpath.co.za
DATE: 3 Jun 2026 | STATUS: In negotiation — price sensitivity flagged | VALID UNTIL: 15 Jul 2026

SCOPE: AI layer monitoring 47-vehicle fleet. Driver scorecards, route optimisation,
fuel anomaly detection, daily SMS to drivers.

INVESTMENT: Build R 165,000 | Monthly retainer R 8,000/month (18-month commitment)
NOTES: Competing quote at R 140k build-only (no AI). Send value comparison by 18 Jun.""",
    },
    {
        "title": "Proposal 012 — Summit Couriers (Last-Mile Route Optimisation)",
        "body": """CLIENT: Summit Couriers (Pty) Ltd
CONTACT: Kagiso Sithole, Head of Fleet | ksithole@summitcouriers.co.za
DATE: 1 Apr 2026 | STATUS: APPROVED — live since 1 Jun 2026 | VALID UNTIL: N/A (active)

SCOPE: Real-time last-mile route optimisation for 120-vehicle fleet. Dynamic
re-routing on traffic events. Daily fuel cost report and on-time delivery score.

INVESTMENT: Build R 285,000 | Monthly retainer R 13,500/month
NOTES: System is live. Client saving avg R 67,000/month on fuel since go-live.""",
    },
    {
        "title": "Proposal 013 — Pan-Africa Transport (Cross-Border Compliance AI)",
        "body": """CLIENT: Pan-Africa Transport CC
CONTACT: Blessing Ndlovu, Compliance Manager | bndlovu@patransport.co.za
DATE: 14 Jun 2026 | STATUS: Discovery call scheduled 2 Jul | VALID UNTIL: TBD

SCOPE: Cross-border documentation automation for SA/ZIM/MOZ/BOT corridors.
AI pre-checks permits, carnet documents, and axle load compliance before dispatch.

INVESTMENT: Estimated R 380,000 build | Monthly TBD
NOTES: Currently losing avg 6 hours/trip to manual document errors at borders.""",
    },
    {
        "title": "Proposal 014 — Rapid Cold Chain (Temperature Compliance Monitoring)",
        "body": """CLIENT: Rapid Cold Chain Logistics
CONTACT: Simone van der Berg, QA Director | svanderberg@rapidcold.co.za
DATE: 25 May 2026 | STATUS: Pending — awaiting internal sign-off | VALID UNTIL: 25 Jul 2026

SCOPE: IoT temperature data ingestion across 38 refrigerated vehicles. Real-time
breach alerts, automated FSCA compliance reports, client-facing delivery certificates.

INVESTMENT: Build R 220,000 | Monthly retainer R 10,000/month
NOTES: One cold breach last year cost them a R 1.8M fish consignment. High urgency.""",
    },
    {
        "title": "Proposal 015 — Goldline Trucking (Driver Fatigue & Safety AI)",
        "body": """CLIENT: Goldline Trucking (Pty) Ltd
CONTACT: Amos Cele, Safety Officer | acele@goldlinetrucking.co.za
DATE: 8 Jun 2026 | STATUS: CLOSED — lost to internal solution | VALID UNTIL: Expired

SCOPE: Driver fatigue monitoring using shift data + telematics. Automated
rest-stop recommendations and weekly safety scorecard per driver.

INVESTMENT: Build R 175,000 | Monthly retainer R 8,500/month
OUTCOME: IT team decided to add basic alerting to existing Ctrack subscription.
Re-engage if fatigue incidents increase — Amos flagged this risk himself.""",
    },
    # ── Property & Real Estate ────────────────────────────────────────────────
    {
        "title": "Proposal 016 — Elevate Property Group (Investment Intelligence Dashboard)",
        "body": """CLIENT: Elevate Property Group
CONTACT: Nomsa Khumalo, Investment Director | nkhumalo@elevateprops.co.za
DATE: 7 Jun 2026 | STATUS: Proposal sent — response expected 23 Jun | VALID UNTIL: 31 Jul 2026

SCOPE: Portfolio intelligence layer across 34 commercial properties. Health score,
tenant risk flags, market comparables, monthly board PDF brief.

INVESTMENT: Build R 285,000 | Monthly retainer R 15,500/month
NOTES: Referred by Anri Hartley. Warm lead. Reviewed our Hartley work before meeting.""",
    },
    {
        "title": "Proposal 017 — Bayview Property Management (Tenant Experience AI)",
        "body": """CLIENT: Bayview Property Management
CONTACT: Candice Farmer, MD | cfarmer@bayviewpm.co.za
DATE: 20 Apr 2026 | STATUS: APPROVED — in build phase | VALID UNTIL: N/A (signed)

SCOPE: Tenant communication AI handling maintenance requests, lease renewals, and
levy queries across 1,200 residential units. Escalation routing to human agents.

INVESTMENT: Build R 245,000 | Monthly retainer R 11,500/month
NOTES: Build is 60% complete. Go-live target 15 Jul 2026.""",
    },
    {
        "title": "Proposal 018 — Sandton Office Spaces (Vacancy Intelligence System)",
        "body": """CLIENT: Sandton Office Spaces CC
CONTACT: Gavin Olivier, Leasing Director | golivier@sandtonoffice.co.za
DATE: 30 May 2026 | STATUS: In negotiation | VALID UNTIL: 30 Jul 2026

SCOPE: AI vacancy intelligence pulling Lightstone, PropData, and internal data.
Weekly opportunity brief: which spaces to reprice, which tenants are flight risks.

INVESTMENT: Build R 190,000 | Monthly retainer R 9,000/month
NOTES: Gavin wants to include competitor vacancy rates — need PropData API access.""",
    },
    {
        "title": "Proposal 019 — Heritage Estate Developers (Project Cost Intelligence)",
        "body": """CLIENT: Heritage Estate Developers (Pty) Ltd
CONTACT: Ruan Jacobs, Project Director | rjacobs@heritageestate.co.za
DATE: 11 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 11 Aug 2026

SCOPE: Construction cost intelligence across 6 active developments. Track actuals
vs budget per trade, flag overruns early, and auto-generate weekly cost reports.

INVESTMENT: Build R 230,000 | Monthly retainer R 10,500/month
NOTES: Current process: manual Excel consolidation taking 2 days per week.""",
    },
    {
        "title": "Proposal 020 — TownSquare Commercial (Lease Management Automation)",
        "body": """CLIENT: TownSquare Commercial Properties
CONTACT: Zanele Dube, Asset Manager | zdube@townsquarecp.co.za
DATE: 17 Mar 2026 | STATUS: CLOSED — budget frozen | VALID UNTIL: Expired

SCOPE: Lease lifecycle automation: renewal reminders, escalation calculations,
CPI adjustment letters, and expiry risk dashboard.

INVESTMENT: Build R 155,000 | Monthly retainer R 7,000/month
NOTES: Budget frozen due to interest rate environment. Re-engage Q4 2026.""",
    },
    # ── Healthcare & Medical ──────────────────────────────────────────────────
    {
        "title": "Proposal 021 — Sandstone Medical Group (HR & Compliance Automation)",
        "body": """CLIENT: Sandstone Medical Group
CONTACT: Dr. Fatima Essop, Practice Manager | fessop@sandstonemedical.co.za
DATE: 18 Mar 2026 | STATUS: CLOSED — went with internal IT | VALID UNTIL: Expired

SCOPE: HR onboarding automation, HPCSA renewal tracking, BLS certification monitoring,
and monthly payroll summary across 3 practices.

INVESTMENT: Build R 145,000 | Monthly retainer R 7,500/month
OUTCOME: Built internally. Dr. Essop open to revisit in 12 months if build stalls.""",
    },
    {
        "title": "Proposal 022 — MedCore Hospital Group (Clinical Ops Intelligence)",
        "body": """CLIENT: MedCore Hospital Group (4 facilities)
CONTACT: Thabo Nkosi, COO | tnkosi@medcore.co.za
DATE: 4 Jun 2026 | STATUS: Pending — ethics committee review required | VALID UNTIL: 4 Sep 2026

SCOPE: Clinical ops AI: theatre utilisation optimisation, bed occupancy forecasting,
and weekly capacity brief to hospital managers.

INVESTMENT: Build R 480,000 | Monthly retainer R 22,000/month
NOTES: Ethics committee meets quarterly — next meeting 15 Jul. Thabo is a champion.""",
    },
    {
        "title": "Proposal 023 — Northside Dental Group (Patient Retention AI)",
        "body": """CLIENT: Northside Dental Group (8 practices)
CONTACT: Dr. Leon Marais, Group Owner | lmarais@northsidedental.co.za
DATE: 22 May 2026 | STATUS: APPROVED — build starting Jul | VALID UNTIL: N/A (signed)

SCOPE: Patient recall automation: AI identifies overdue patients, generates
personalised recall messages via SMS/WhatsApp, and tracks conversion rates.

INVESTMENT: Build R 125,000 | Monthly retainer R 6,000/month
NOTES: Current recall rate 34%. Target 65%. Leon estimates R 280k additional revenue/year.""",
    },
    {
        "title": "Proposal 024 — Vitality Wellness Clinics (Health Data Intelligence)",
        "body": """CLIENT: Vitality Wellness Clinics CC (12 locations)
CONTACT: Dr. Priya Naidoo, Clinical Director | pnaidoo@vitalitywellness.co.za
DATE: 9 Jun 2026 | STATUS: In negotiation | VALID UNTIL: 9 Aug 2026

SCOPE: Patient outcome intelligence: anonymised aggregate health trend reports
per clinic, NPS tracking, and monthly benchmark report across all 12 locations.

INVESTMENT: Build R 265,000 | Monthly retainer R 12,000/month
NOTES: POPIA compliance review required. Heinrich to loop in legal advisor.""",
    },
    {
        "title": "Proposal 025 — PharmaCure Dispensaries (Controlled Substance AI)",
        "body": """CLIENT: PharmaCure Dispensaries (6 branches)
CONTACT: Hendrik Steyn, Regulatory Manager | hsteyn@pharmacure.co.za
DATE: 14 Apr 2026 | STATUS: CLOSED — scope too narrow for their needs | VALID UNTIL: Expired

SCOPE: Schedule 5 & 6 substance dispensing intelligence. Auto-generate DEA reports,
flag unusual dispensing patterns, and weekly audit trail summaries.

INVESTMENT: Build R 180,000 | Monthly retainer R 8,500/month
OUTCOME: Client wanted full ERP integration we couldn't offer in scope. Lost.""",
    },
    # ── Education ─────────────────────────────────────────────────────────────
    {
        "title": "Proposal 026 — TechBridge Academy (Student Performance AI)",
        "body": """CLIENT: TechBridge Academy (4 campuses)
CONTACT: Mr. Deon Fredericks, Executive Principal | dfredericks@techbridgeacademy.co.za
DATE: 1 Jun 2026 | STATUS: Pending — board presentation 30 Jun | VALID UNTIL: 31 Aug 2026

SCOPE: Student performance AI across 4 campuses (3 SIS platforms normalised).
At-risk student flagging, weekly campus briefs, parent communication automation.

INVESTMENT: Build R 380,000 | Monthly retainer R 16,000/month
NOTES: ROI = student retention. Each student = ~R 85,000/year in fees.""",
    },
    {
        "title": "Proposal 027 — Prestige College Group (Admissions Intelligence)",
        "body": """CLIENT: Prestige College Group (7 campuses)
CONTACT: Miriam Boateng, Head of Admissions | mboateng@prestige.co.za
DATE: 19 May 2026 | STATUS: APPROVED — in build | VALID UNTIL: N/A (signed)

SCOPE: Admissions funnel AI: lead scoring for enquiries, automated follow-up
sequences, and conversion tracking dashboard by campus and programme.

INVESTMENT: Build R 210,000 | Monthly retainer R 9,500/month
NOTES: Build 40% complete. Miriam wants first cohort data by August intake.""",
    },
    {
        "title": "Proposal 028 — Kidsmart Early Learning (Parent Engagement AI)",
        "body": """CLIENT: Kidsmart Early Learning Centres (19 centres)
CONTACT: Adele van Niekerk, CEO | avannikerk@kidsmart.co.za
DATE: 7 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 7 Aug 2026

SCOPE: Parent communication AI: daily updates per child, incident reporting automation,
fee reminder sequences, and monthly centre health report to franchise owners.

INVESTMENT: Build R 175,000 | Monthly retainer R 8,000/month
NOTES: Adele managing 19 franchise owners — consistency of comms is main pain point.""",
    },
    {
        "title": "Proposal 029 — SA Online Academy (Student Success Prediction)",
        "body": """CLIENT: SA Online Academy
CONTACT: Ronel Kruger, Academic Dean | rkruger@saonlineacademy.co.za
DATE: 25 Mar 2026 | STATUS: CLOSED — funding not secured | VALID UNTIL: Expired

SCOPE: Dropout prediction model using engagement data, assignment submission patterns,
and login frequency. Early intervention alerts to academic advisors.

INVESTMENT: Build R 155,000 | Monthly retainer R 7,000/month
NOTES: Ronel was a strong champion. Budget dependent on SETA funding that fell through.
Follow up when next funding cycle opens (Feb 2027).""",
    },
    {
        "title": "Proposal 030 — Brainwave Tutoring Network (Tutor Matching AI)",
        "body": """CLIENT: Brainwave Tutoring Network
CONTACT: Jason Liu, CTO | jliu@brainwave.co.za
DATE: 12 Jun 2026 | STATUS: Discovery call scheduled 1 Jul | VALID UNTIL: TBD

SCOPE: AI tutor-student matching engine. Matches based on learning style, subject
gaps, location/online preference, and historical tutor ratings.

INVESTMENT: Estimated R 290,000 build | Monthly TBD
NOTES: Currently matching manually — 2 FTEs doing this full-time.""",
    },
    # ── Agriculture ───────────────────────────────────────────────────────────
    {
        "title": "Proposal 031 — Cape Agri Cooperative (Seasonal Demand Forecasting)",
        "body": """CLIENT: Cape Agri Cooperative
CONTACT: Pieter van Zyl, GM | pjvanzyl@capeagri.co.za
DATE: 20 May 2026 | STATUS: Pending — gone quiet since 1 Jun | VALID UNTIL: 20 Jul 2026

SCOPE: Seasonal demand forecasting for 220 member farmers. Weather API + 3 years
historical sales. Weekly planting and stock recommendations via WhatsApp.

INVESTMENT: Build R 210,000 | Monthly retainer R 11,000/month
NOTES: Pieter unresponsive since 10 Jun. Possible drought-related budget freeze. HIGH risk.""",
    },
    {
        "title": "Proposal 032 — Osun Consulting Group (Annual Reports & RFP Automation)",
        "body": """CLIENT: Osun Consulting Group
CONTACT: Connie, Managing Director | connie@osunconsulting.co.za
DATE: 15 Apr 2026 | STATUS: APPROVED — ANCHOR CLIENT | VALID UNTIL: N/A (active)

SCOPE: Annual report compilation automation, RFP response drafting AI,
and governance document intelligence layer. 5-opportunity expansion roadmap agreed.

INVESTMENT: Build R 195,000 | Monthly retainer R 10,500/month
NOTES: Priority client. Full build delivered. Expanding into 5 additional modules.""",
    },
    {
        "title": "Proposal 033 — Karoo Fresh Produce (Harvest & Distribution Intelligence)",
        "body": """CLIENT: Karoo Fresh Produce CC
CONTACT: Louis Joubert, Operations Manager | ljoubert@karoofresh.co.za
DATE: 28 May 2026 | STATUS: In negotiation | VALID UNTIL: 28 Jul 2026

SCOPE: Harvest scheduling + distribution route optimisation for fresh produce
delivery to 40 wholesale clients. Shelf-life tracking and waste reduction alerts.

INVESTMENT: Build R 185,000 | Monthly retainer R 8,500/month
NOTES: Currently losing R 18,000/month in spoilage. Target ROI payback: 3 months.""",
    },
    {
        "title": "Proposal 034 — Highveld Grain (Commodity Price Intelligence)",
        "body": """CLIENT: Highveld Grain (Pty) Ltd
CONTACT: Bennie Erasmus, Trading Director | berasmus@highveldgrain.co.za
DATE: 6 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 6 Aug 2026

SCOPE: Commodity price monitoring (SAFEX + international benchmarks) with
daily brief, basis tracking, and automated hedge ratio alerts to the trading desk.

INVESTMENT: Build R 240,000 | Monthly retainer R 11,500/month
NOTES: Bennie currently spending 3 hours/day manually pulling price data.""",
    },
    {
        "title": "Proposal 035 — Green Valley Nurseries (Growing Cycle Optimisation)",
        "body": """CLIENT: Green Valley Nurseries
CONTACT: Sophia Muller, Head Grower | smuller@greenvalleynurseries.co.za
DATE: 14 Mar 2026 | STATUS: CLOSED — too small for current pricing | VALID UNTIL: Expired

SCOPE: Growing cycle optimisation AI using soil sensors + weather data.
Automated irrigation scheduling and yield forecasting per growing block.

INVESTMENT: Build R 130,000 | Monthly retainer R 6,000/month
OUTCOME: Revenue too small to justify retainer. Revisit with lower-cost module in 2027.""",
    },
    # ── Financial Services ────────────────────────────────────────────────────
    {
        "title": "Proposal 036 — Pinnacle Wealth Advisors (Client Intelligence Platform)",
        "body": """CLIENT: Pinnacle Wealth Advisors (Pty) Ltd
CONTACT: Gareth Thornton, MD | gthornton@pinnaclewealth.co.za
DATE: 2 Jun 2026 | STATUS: Pending — compliance review | VALID UNTIL: 2 Sep 2026

SCOPE: Client intelligence layer: portfolio health alerts, rebalancing opportunities,
and automated client review preparation briefs for advisors.

INVESTMENT: Build R 295,000 | Monthly retainer R 13,500/month
NOTES: FSP compliance sign-off required before contract. FSCA timeline: 6-8 weeks.""",
    },
    {
        "title": "Proposal 037 — Coastline Insurance Brokers (Claims Intelligence)",
        "body": """CLIENT: Coastline Insurance Brokers CC
CONTACT: Mpho Mahlangu, Claims Director | mmahlangu@coastlineins.co.za
DATE: 19 May 2026 | STATUS: APPROVED — go-live 1 Aug | VALID UNTIL: N/A (signed)

SCOPE: Claims pattern analysis to flag fraudulent claims, auto-triage incoming
claims by complexity, and weekly broker performance scorecard.

INVESTMENT: Build R 260,000 | Monthly retainer R 12,000/month
NOTES: Signed 1 Jun 2026. Build starts 1 Jul. Mpho wants fraud module live first.""",
    },
    {
        "title": "Proposal 038 — FirstBond Credit (Lending Risk Intelligence)",
        "body": """CLIENT: FirstBond Credit (Pty) Ltd
CONTACT: Themba Dlamini, Risk Officer | tdlamini@firstbondcredit.co.za
DATE: 10 Jun 2026 | STATUS: In negotiation — legal reviewing | VALID UNTIL: 10 Aug 2026

SCOPE: Credit risk AI enhancing existing scorecard. Integrates bureau data,
bank statements, and behavioural signals. NCA compliance built-in.

INVESTMENT: Build R 350,000 | Monthly retainer R 16,000/month
NOTES: Legal team reviewing NCA compliance angle. Expected sign-off 25 Jun.""",
    },
    {
        "title": "Proposal 039 — Vantage Asset Management (Portfolio Intelligence)",
        "body": """CLIENT: Vantage Asset Management
CONTACT: Dr. Sarah Nkosi, CIO | snkosi@vantageam.co.za
DATE: 24 Apr 2026 | STATUS: CLOSED — bought competitor product | VALID UNTIL: Expired

SCOPE: Portfolio intelligence layer for fund managers: automated fact sheets,
performance attribution, and investor reporting automation.

INVESTMENT: Build R 420,000 | Monthly retainer R 19,000/month
OUTCOME: Chose a Morningstar reporting tool. No custom AI. Revisit in 12 months.""",
    },
    {
        "title": "Proposal 040 — BlueSky Tax Consultants (Tax Compliance Automation)",
        "body": """CLIENT: BlueSky Tax Consultants
CONTACT: Werner Botha, Senior Partner | wbotha@blueskytax.co.za
DATE: 17 Jun 2026 | STATUS: Discovery call scheduled 3 Jul | VALID UNTIL: TBD

SCOPE: SARS submission automation, deadline tracking across 200+ client portfolio,
and AI-assisted query response drafting for SARS correspondence.

INVESTMENT: Estimated R 200,000 build | Monthly TBD
NOTES: Werner's team spending avg 40 hours/month on manual deadline tracking.""",
    },
    # ── Mining & Resources ────────────────────────────────────────────────────
    {
        "title": "Proposal 041 — Goldfields Contractors (Site Safety Intelligence)",
        "body": """CLIENT: Goldfields Contractors CC
CONTACT: Nkosinathi Zulu, HSE Manager | nzulu@goldfieldscontractors.co.za
DATE: 8 May 2026 | STATUS: APPROVED — Phase 1 complete | VALID UNTIL: N/A (active)

SCOPE: Safety incident pattern analysis across 6 mine sites. Predictive risk scoring
per shift, automated DMR reporting, and weekly HSE brief.

INVESTMENT: Build R 310,000 | Monthly retainer R 14,500/month
NOTES: Phase 1 live. DMR report generation saving 3 days/month for compliance team.""",
    },
    {
        "title": "Proposal 042 — Platinum Ridge Mining Services (Equipment Intelligence)",
        "body": """CLIENT: Platinum Ridge Mining Services
CONTACT: Kobus van Wyk, Engineering Director | kvanwyk@platinumridge.co.za
DATE: 27 May 2026 | STATUS: Pending — awaiting CAPEX approval | VALID UNTIL: 27 Aug 2026

SCOPE: Heavy equipment health monitoring across 28 units. Failure prediction,
automated maintenance work orders, and OEE tracking dashboard.

INVESTMENT: Build R 480,000 | Monthly retainer R 22,000/month
NOTES: CAPEX committee meets quarterly — next window: August. Kobus is aligned.""",
    },
    {
        "title": "Proposal 043 — Baobab Aggregates (Production Intelligence)",
        "body": """CLIENT: Baobab Aggregates (Pty) Ltd
CONTACT: Tanya Pretorius, COO | tpretorius@baobabagg.co.za
DATE: 16 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 16 Aug 2026

SCOPE: Crushing plant production intelligence: shift output tracking, yield
optimisation, and customer order fulfilment forecasting.

INVESTMENT: Build R 195,000 | Monthly retainer R 9,000/month
NOTES: Tanya replacing retiring ops manager — wants AI layer before handover.""",
    },
    {
        "title": "Proposal 044 — Kalahari Salt Works (Process Optimisation AI)",
        "body": """CLIENT: Kalahari Salt Works CC
CONTACT: Etienne Fouche, Plant Manager | efouche@kalaharisalt.co.za
DATE: 3 Apr 2026 | STATUS: CLOSED — project shelved | VALID UNTIL: Expired

SCOPE: Evaporation pond monitoring using satellite imagery + weather data.
Harvest timing optimisation and quality grade prediction.

INVESTMENT: Build R 225,000 | Monthly retainer R 10,500/month
NOTES: Project shelved due to drought reducing pond capacity. Revisit 2027.""",
    },
    {
        "title": "Proposal 045 — Eastlands Chrome (Ore Sorting Intelligence)",
        "body": """CLIENT: Eastlands Chrome Mining
CONTACT: Siphamandla Dube, Head of Processing | sdube@eastlandschrome.co.za
DATE: 11 Jun 2026 | STATUS: In negotiation | VALID UNTIL: 11 Aug 2026

SCOPE: Ore grade intelligence using XRF sensor data + geological models.
Real-time sorting recommendations to improve Cr2O3 recovery rate by 8-12%.

INVESTMENT: Build R 390,000 | Monthly retainer R 17,500/month
NOTES: Current recovery at 68%. Competitor achieving 79%. Urgency is high.""",
    },
    # ── Hospitality & Tourism ─────────────────────────────────────────────────
    {
        "title": "Proposal 046 — Safari Retreats SA (Guest Experience Intelligence)",
        "body": """CLIENT: Safari Retreats SA (8 lodges)
CONTACT: Melinda Grobler, Group GM | mgrobler@safariretreats.co.za
DATE: 30 Apr 2026 | STATUS: APPROVED — in build | VALID UNTIL: N/A (signed)

SCOPE: Guest preference AI across 8 lodges. Pre-arrival personalisation, in-stay
experience scoring, and automated post-stay review request sequences.

INVESTMENT: Build R 230,000 | Monthly retainer R 10,500/month
NOTES: Build 70% complete. Target go-live: 1 Jul ahead of peak season.""",
    },
    {
        "title": "Proposal 047 — City Stays Hotels (Revenue Management AI)",
        "body": """CLIENT: City Stays Hotels (14 properties)
CONTACT: Ahmed Moosa, Revenue Director | amoosa@citystays.co.za
DATE: 22 May 2026 | STATUS: Pending — piloting on 2 properties first | VALID UNTIL: 22 Aug 2026

SCOPE: Dynamic pricing AI integrating OTA data, events calendar, and competitor
rates. Daily rate recommendations per property type.

INVESTMENT: Pilot (2 properties) R 95,000 | Full rollout R 380,000 | Monthly R 17,000/month
NOTES: Ahmed running pilot vs their current manual process. Results review 15 Aug.""",
    },
    {
        "title": "Proposal 048 — Cape Winelands Tourism Board (Visitor Intelligence)",
        "body": """CLIENT: Cape Winelands Tourism Board
CONTACT: Mariette de Bruyn, CEO | mdebruyn@winelandstourism.co.za
DATE: 6 Jun 2026 | STATUS: Proposal sent — government procurement process | VALID UNTIL: 6 Oct 2026

SCOPE: Visitor flow intelligence across 140+ member estates. Aggregate sentiment
analysis, seasonal demand forecasting, and annual tourism impact report.

INVESTMENT: Build R 350,000 | Monthly retainer R 15,000/month
NOTES: Government entity — procurement process adds 8-12 weeks. RFQ closes 15 Jul.""",
    },
    {
        "title": "Proposal 049 — Umhlanga Beach Resort (Maintenance Intelligence)",
        "body": """CLIENT: Umhlanga Beach Resort
CONTACT: Carlos Pereira, Facilities Manager | cpereira@umhlangaresort.co.za
DATE: 15 Mar 2026 | STATUS: CLOSED — ownership change paused procurement | VALID UNTIL: Expired

SCOPE: Preventative maintenance AI for 280-room resort. Work order intelligence,
contractor scheduling, and guest impact minimisation scoring.

INVESTMENT: Build R 170,000 | Monthly retainer R 8,000/month
NOTES: New ownership taking over Jul 2026. Re-engage after transition settles.""",
    },
    {
        "title": "Proposal 050 — Kruger Base Camps (Booking & Capacity Intelligence)",
        "body": """CLIENT: Kruger Base Camps (12 camps)
CONTACT: Willem Joubert, Operations Director | wjoubert@krugerbasecamps.co.za
DATE: 19 Jun 2026 | STATUS: Discovery call scheduled 5 Jul | VALID UNTIL: TBD

SCOPE: Booking pattern intelligence across 12 camps. Demand forecasting by species
sighting patterns, automated upsell sequences, and guide allocation optimisation.

INVESTMENT: Estimated R 260,000 build | Monthly TBD
NOTES: Currently leaving 22% capacity empty on shoulder-season weekends.""",
    },
    # ── Construction ──────────────────────────────────────────────────────────
    {
        "title": "Proposal 051 — BuildRight Contractors (Project Cost Intelligence)",
        "body": """CLIENT: BuildRight Contractors (Pty) Ltd
CONTACT: Franco Rossouw, QS Director | frossouw@buildrightsa.co.za
DATE: 10 May 2026 | STATUS: APPROVED — live | VALID UNTIL: N/A (active)

SCOPE: Real-time project cost tracking across 9 active sites. Budget vs actuals
per trade, variation order intelligence, and weekly cost-to-complete forecasting.

INVESTMENT: Build R 215,000 | Monthly retainer R 10,000/month
NOTES: System live 1 Jun. Already caught a R 340,000 overrun on Site 4 early.""",
    },
    {
        "title": "Proposal 052 — Coastal Civils (Tender Intelligence System)",
        "body": """CLIENT: Coastal Civils CC
CONTACT: Hanri Mostert, Estimating Manager | hmostert@coastalcivils.co.za
DATE: 3 Jun 2026 | STATUS: In negotiation | VALID UNTIL: 3 Aug 2026

SCOPE: Public tender monitoring (eTender Portal + CIDB) + AI bid-or-no-bid scoring.
Historical win-rate analysis and subcontractor database intelligence.

INVESTMENT: Build R 185,000 | Monthly retainer R 8,500/month
NOTES: Team currently missing tenders because monitoring is manual and inconsistent.""",
    },
    {
        "title": "Proposal 053 — Meridian Developments (Subcontractor Intelligence)",
        "body": """CLIENT: Meridian Developments
CONTACT: Brendan Casey, Contracts Manager | bcasey@meridiandevelopments.co.za
DATE: 26 May 2026 | STATUS: Pending | VALID UNTIL: 26 Jul 2026

SCOPE: Subcontractor performance scoring (quality, timing, cost, safety) across 80+
subs. Automated performance reviews and blacklist alert system.

INVESTMENT: Build R 200,000 | Monthly retainer R 9,500/month
NOTES: Brendan had a R 1.2M defects claim from a sub last year. Pain point is real.""",
    },
    {
        "title": "Proposal 054 — Peak Infrastructure (Labour Intelligence)",
        "body": """CLIENT: Peak Infrastructure Group
CONTACT: Nandi Mthembu, HR Director | nmthembu@peakinfra.co.za
DATE: 7 Apr 2026 | STATUS: CLOSED — SLA not met | VALID UNTIL: Expired

SCOPE: Daily labour allocation intelligence across 14 active projects. Skills matching,
absenteeism prediction, and weekly productivity scorecard per site.

INVESTMENT: Build R 240,000 | Monthly retainer R 11,000/month
OUTCOME: Could not meet their 48-hour build timeline for a pilot. Lost on timeline.""",
    },
    {
        "title": "Proposal 055 — Sunstone Interiors (Procurement Intelligence)",
        "body": """CLIENT: Sunstone Interiors (Pty) Ltd
CONTACT: Vanessa Lin, Procurement Manager | vlin@sunstoneinteriors.co.za
DATE: 13 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 13 Aug 2026

SCOPE: Material procurement intelligence for high-end residential fit-outs.
Supplier price tracking, lead time alerts, and project margin forecasting.

INVESTMENT: Build R 155,000 | Monthly retainer R 7,000/month
NOTES: Vanessa currently managing R 8M/month in procurement via spreadsheets.""",
    },
    # ── Technology & SaaS ─────────────────────────────────────────────────────
    {
        "title": "Proposal 056 — DataFlow Systems (Customer Success Intelligence)",
        "body": """CLIENT: DataFlow Systems (Pty) Ltd
CONTACT: Keegan van Rensburg, Head of CS | kvanrensburg@dataflow.co.za
DATE: 20 May 2026 | STATUS: APPROVED — live | VALID UNTIL: N/A (active)

SCOPE: Churn prediction model across 340 SaaS clients. Health score per account,
automated at-risk alerts to CS team, and monthly churn forecast to the board.

INVESTMENT: Build R 190,000 | Monthly retainer R 9,000/month
NOTES: Live since 15 May. Already flagged 12 at-risk accounts, 3 saved so far.""",
    },
    {
        "title": "Proposal 057 — Techvault Security Software (Sales Intelligence)",
        "body": """CLIENT: Techvault Security Software
CONTACT: Rowan Gerber, VP Sales | rgerber@techvault.co.za
DATE: 8 Jun 2026 | STATUS: Pending | VALID UNTIL: 8 Aug 2026

SCOPE: CRM intelligence layer on Hubspot. Deal velocity tracking, rep performance
scoring, and weekly pipeline health brief to the sales director.

INVESTMENT: Build R 165,000 | Monthly retainer R 7,500/month
NOTES: Rowan's team has a R 42M pipeline. Even a 5% win rate improvement = R 2.1M.""",
    },
    {
        "title": "Proposal 058 — CloudBridge IT Solutions (Support Intelligence)",
        "body": """CLIENT: CloudBridge IT Solutions CC
CONTACT: Sibongile Khumalo, Support Manager | skhumalo@cloudbridge.co.za
DATE: 28 Apr 2026 | STATUS: In negotiation — Freshdesk integration scoping | VALID UNTIL: 28 Jun 2026

SCOPE: Support ticket intelligence: auto-triage, sentiment scoring, SLA breach
prediction, and monthly support health report with root cause analysis.

INVESTMENT: Build R 175,000 | Monthly retainer R 8,000/month
NOTES: Freshdesk API integration confirmed. Scoping custom fields this week.""",
    },
    {
        "title": "Proposal 059 — Nexus Analytics (Data Product Intelligence)",
        "body": """CLIENT: Nexus Analytics (Pty) Ltd
CONTACT: Dr. Brian Osei, Chief Data Officer | bosei@nexusanalytics.co.za
DATE: 5 Mar 2026 | STATUS: CLOSED — built in-house | VALID UNTIL: Expired

SCOPE: Internal data catalogue intelligence. Auto-tagging data assets, usage tracking,
and data quality scoring across their 400+ datasets.

INVESTMENT: Build R 280,000 | Monthly retainer R 13,000/month
OUTCOME: Brian's team built a basic version internally. Quality gap likely — follow up H2.""",
    },
    {
        "title": "Proposal 060 — PixelForge Studios (Project Intelligence Dashboard)",
        "body": """CLIENT: PixelForge Studios (digital agency)
CONTACT: Ash Kumari, Studio Director | akumari@pixelforge.co.za
DATE: 16 Jun 2026 | STATUS: Discovery call scheduled 30 Jun | VALID UNTIL: TBD

SCOPE: Agency project intelligence: utilisation tracking, margin per client,
scope creep alerts, and monthly profitability brief to founders.

INVESTMENT: Estimated R 140,000 build | Monthly TBD
NOTES: 35-person studio. Ash suspects 3-4 clients are unprofitable but can't prove it.""",
    },
    # ── Professional Services ─────────────────────────────────────────────────
    {
        "title": "Proposal 061 — Morrison & Associates Attorneys (Matter Intelligence)",
        "body": """CLIENT: Morrison & Associates Attorneys
CONTACT: Advocate Claire Morrison, Managing Partner | cmorrison@morrisonlaw.co.za
DATE: 12 May 2026 | STATUS: Pending — conflict check in progress | VALID UNTIL: 12 Jul 2026

SCOPE: Matter management intelligence. Billing realisation tracking, deadline monitoring,
and monthly client profitability brief per partner.

INVESTMENT: Build R 195,000 | Monthly retainer R 9,000/month
NOTES: Conflict check for legal AI tools taking 4 weeks. Claire is a strong champion.""",
    },
    {
        "title": "Proposal 062 — Grant Thornton SA (Audit Intelligence Pilot)",
        "body": """CLIENT: Grant Thornton SA (Pty) Ltd
CONTACT: Sipho Mahlangu, Audit Partner | smahlangu@grantthornton.co.za
DATE: 3 Jun 2026 | STATUS: Pending — IRBA guidance awaited | VALID UNTIL: 3 Sep 2026

SCOPE: Audit workpaper intelligence pilot for 10 audit files. AI-assisted anomaly
detection and sampling optimisation.

INVESTMENT: Pilot R 120,000 | Full rollout TBD
NOTES: IRBA releasing AI-in-audit guidance Q3 2026. Sipho waiting for clarity.""",
    },
    {
        "title": "Proposal 063 — Patel & Partners Accountants (Client Reporting AI)",
        "body": """CLIENT: Patel & Partners Accountants
CONTACT: Priya Patel, Senior Partner | ppatel@patelpartners.co.za
DATE: 22 Apr 2026 | STATUS: APPROVED — live | VALID UNTIL: N/A (active)

SCOPE: Automated monthly management accounts compilation for 45 SME clients.
Narrative generation, variance commentary, and branded PDF delivery.

INVESTMENT: Build R 155,000 | Monthly retainer R 7,500/month
NOTES: Live since May. Priya reclaiming 60 hours/month of senior staff time.""",
    },
    {
        "title": "Proposal 064 — Momentum Consulting Engineers (Proposal Intelligence)",
        "body": """CLIENT: Momentum Consulting Engineers
CONTACT: Dr. Elias Sithole, Director | esithole@momentumeng.co.za
DATE: 14 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 14 Aug 2026

SCOPE: RFP response intelligence: auto-draft technical sections from past project
database, compliance checklist automation, and win/loss analysis.

INVESTMENT: Build R 175,000 | Monthly retainer R 8,000/month
NOTES: Team writing 3-5 RFPs/month. Each takes avg 40 hours. Target: cut to 15.""",
    },
    {
        "title": "Proposal 065 — Clearwater HR Solutions (Recruitment Intelligence)",
        "body": """CLIENT: Clearwater HR Solutions
CONTACT: Tamzin Kruger, MD | tkruger@clearwaterhr.co.za
DATE: 29 Mar 2026 | STATUS: CLOSED — went with LinkedIn Recruiter AI | VALID UNTIL: Expired

SCOPE: CV screening AI, candidate ranking, and interview preparation briefs
across their 120 active vacancies per month.

INVESTMENT: Build R 140,000 | Monthly retainer R 6,500/month
OUTCOME: LinkedIn launched their own AI screening — Tamzin chose native tool.""",
    },
    # ── Food & Beverage ───────────────────────────────────────────────────────
    {
        "title": "Proposal 066 — Harvest Table Restaurants (Kitchen Intelligence)",
        "body": """CLIENT: Harvest Table Restaurants (11 locations)
CONTACT: Chef Marco da Silva, Group Executive Chef | mdasilva@harvesttable.co.za
DATE: 18 May 2026 | STATUS: APPROVED — Phase 1 live | VALID UNTIL: N/A (active)

SCOPE: Kitchen waste intelligence: daily waste logging, recipe yield optimisation,
and weekly food cost vs menu price analysis per location.

INVESTMENT: Build R 165,000 | Monthly retainer R 7,500/month
NOTES: Phase 1 live. Food cost dropped from 34% to 29% in first month.""",
    },
    {
        "title": "Proposal 067 — Sunbrew Craft Beer Co. (Production Intelligence)",
        "body": """CLIENT: Sunbrew Craft Beer Co.
CONTACT: Jaco Fourie, Head Brewer | jfourie@sunbrew.co.za
DATE: 4 Jun 2026 | STATUS: In negotiation | VALID UNTIL: 4 Aug 2026

SCOPE: Brewing batch intelligence: fermentation parameter monitoring, yield
optimisation, and quality consistency scoring across 6 fermenters.

INVESTMENT: Build R 145,000 | Monthly retainer R 6,500/month
NOTES: Jaco losing avg 8% per batch to inconsistency. Target: under 2%.""",
    },
    {
        "title": "Proposal 068 — FreshBake Bakery Group (Demand Intelligence)",
        "body": """CLIENT: FreshBake Bakery Group (18 outlets)
CONTACT: Carin Engelbrecht, Operations Director | cengelbrecht@freshbake.co.za
DATE: 23 Apr 2026 | STATUS: Pending | VALID UNTIL: 23 Jun 2026

SCOPE: Daily bake quantity optimisation per outlet. Sales history + weather +
local events = AI bake plan reducing waste and out-of-stock incidents.

INVESTMENT: Build R 170,000 | Monthly retainer R 8,000/month
NOTES: Currently wasting R 25,000/day across outlets. Follow up urgently — deadline.""",
    },
    {
        "title": "Proposal 069 — Cape Winery Collective (Wine Club Intelligence)",
        "body": """CLIENT: Cape Winery Collective (7 member estates)
CONTACT: Liezel du Toit, Marketing Director | ldutoit@capewinerycollective.co.za
DATE: 9 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 9 Aug 2026

SCOPE: Wine club member intelligence: churn prediction, personalised allocation
recommendations, and automated tasting note personalisation at scale.

INVESTMENT: Build R 195,000 | Monthly retainer R 9,000/month
NOTES: Collective has 8,400 wine club members across 7 estates.""",
    },
    {
        "title": "Proposal 070 — Durban Spice Trading Co. (Import Intelligence)",
        "body": """CLIENT: Durban Spice Trading Co.
CONTACT: Ravi Govender, MD | rgovender@durbanspice.co.za
DATE: 19 Feb 2026 | STATUS: CLOSED — too early stage | VALID UNTIL: Expired

SCOPE: Import cost intelligence monitoring 12 spice commodity prices across
3 source markets (India, Indonesia, Sri Lanka) with hedge opportunity alerts.

INVESTMENT: Build R 155,000 | Monthly retainer R 7,000/month
NOTES: Business too small currently. Ravi growing fast — re-engage at R 15M revenue.""",
    },
    # ── Government & NGO ──────────────────────────────────────────────────────
    {
        "title": "Proposal 071 — Johannesburg Metro (Service Delivery Intelligence)",
        "body": """CLIENT: City of Johannesburg Metropolitan Municipality
CONTACT: Nomvula Mthethwa, Chief Digital Officer | nmthethwa@joburg.org.za
DATE: 25 May 2026 | STATUS: Pending — SCM process | VALID UNTIL: 25 Nov 2026

SCOPE: Service delivery complaint intelligence. AI categorisation, SLA tracking,
and ward-level performance dashboard for the mayoral committee.

INVESTMENT: Build R 680,000 | Monthly retainer R 28,000/month
NOTES: Government SCM — 6 month procurement timeline. RFP closes 31 Jul.""",
    },
    {
        "title": "Proposal 072 — ChildSafe NGO (Donor Intelligence Platform)",
        "body": """CLIENT: ChildSafe NGO
CONTACT: Rebecca Adams, Executive Director | radams@childsafe.org.za
DATE: 8 Apr 2026 | STATUS: Approved — pro-bono partnership | VALID UNTIL: N/A (active)

SCOPE: Donor retention AI: at-risk donor flags, personalised impact update automation,
and grant deadline tracking across 40+ active funders.

INVESTMENT: Build R 0 (pro-bono) | Monthly retainer R 2,000/month (cost recovery)
NOTES: Strategic pro-bono for portfolio. Case study in development.""",
    },
    {
        "title": "Proposal 073 — Green Future Trust (Impact Reporting Automation)",
        "body": """CLIENT: Green Future Trust (environmental NPO)
CONTACT: Dr. Amina Hassan, CEO | ahassan@greenfuturetrust.org
DATE: 14 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 14 Oct 2026

SCOPE: Environmental impact data consolidation from 34 project sites.
Auto-generate donor reports, carbon credit calculations, and SARS 18A certificates.

INVESTMENT: Build R 225,000 | Monthly retainer R 10,000/month
NOTES: Funder-required impact reporting taking 2 weeks/quarter to compile manually.""",
    },
    {
        "title": "Proposal 074 — SA Teachers Union (Member Intelligence System)",
        "body": """CLIENT: SA Teachers Union (SATU)
CONTACT: Lungelo Dlamini, General Secretary | ldlamini@satu.org.za
DATE: 2 Jun 2026 | STATUS: In negotiation — NEC approval needed | VALID UNTIL: 2 Sep 2026

SCOPE: Member engagement intelligence across 140,000 members. Renewal risk scoring,
regional rep performance tracking, and monthly membership health brief.

INVESTMENT: Build R 380,000 | Monthly retainer R 17,000/month
NOTES: NEC meets bi-monthly. Next meeting 15 Jul. Lungelo recommending approval.""",
    },
    {
        "title": "Proposal 075 — Tshwane Development Agency (Economic Intelligence)",
        "body": """CLIENT: Tshwane Development Agency
CONTACT: Dikeledi Sefularo, Research Director | dsefularo@tda.org.za
DATE: 28 Feb 2026 | STATUS: CLOSED — funding cut | VALID UNTIL: Expired

SCOPE: Economic activity intelligence for the Tshwane Metro. Business registration
trend analysis, sector growth mapping, and quarterly investor report generation.

INVESTMENT: Build R 290,000 | Monthly retainer R 13,000/month
NOTES: Budget cut in April Metro adjustment budget. Re-engage with new financial year.""",
    },
    # ── Media & Marketing ─────────────────────────────────────────────────────
    {
        "title": "Proposal 076 — Pulse Media Group (Content Intelligence Platform)",
        "body": """CLIENT: Pulse Media Group
CONTACT: Jade Thompson, Digital Director | jthompson@pulsemedia.co.za
DATE: 11 May 2026 | STATUS: APPROVED — live | VALID UNTIL: N/A (active)

SCOPE: Content performance intelligence across 5 digital publications. AI topic
recommendations, audience segment analysis, and weekly editorial brief.

INVESTMENT: Build R 185,000 | Monthly retainer R 8,500/month
NOTES: Live since 1 Jun. Time-on-site up 23% in first 3 weeks.""",
    },
    {
        "title": "Proposal 077 — Ignite Marketing Agency (Campaign Intelligence)",
        "body": """CLIENT: Ignite Marketing Agency
CONTACT: Steph Venter, MD | sventer@ignitemarketing.co.za
DATE: 25 May 2026 | STATUS: Pending | VALID UNTIL: 25 Jul 2026

SCOPE: Multi-channel campaign performance intelligence. Unified reporting across
Meta, Google, LinkedIn, and email. Weekly ROI brief per client account.

INVESTMENT: Build R 175,000 | Monthly retainer R 8,000/month
NOTES: Steph managing 22 clients. Monthly reporting taking 3 days. Target: 3 hours.""",
    },
    {
        "title": "Proposal 078 — Spotlight Events (Event Intelligence System)",
        "body": """CLIENT: Spotlight Events (Pty) Ltd
CONTACT: Ryan Petersen, CEO | rpetersen@spotlightevents.co.za
DATE: 6 Jun 2026 | STATUS: In negotiation | VALID UNTIL: 6 Aug 2026

SCOPE: Event performance intelligence: ticket sales forecasting, sponsor ROI reporting,
and post-event sentiment analysis from social + survey data.

INVESTMENT: Build R 160,000 | Monthly retainer R 7,500/month
NOTES: Ryan running 40+ events/year. Sponsors asking for ROI data he doesn't have.""",
    },
    {
        "title": "Proposal 079 — RadioWave SA (Audience Intelligence)",
        "body": """CLIENT: RadioWave SA (regional radio group, 5 stations)
CONTACT: Thandi Molefe, Group Programming Director | tmolefe@radiowavesa.co.za
DATE: 16 Apr 2026 | STATUS: CLOSED — internal politics | VALID UNTIL: Expired

SCOPE: Listener audience intelligence: sentiment tracking from social + call-in data,
music playlist optimisation AI, and weekly audience health brief per station.

INVESTMENT: Build R 250,000 | Monthly retainer R 11,500/month
NOTES: Board conflict between traditional vs digital strategy. Stalled. Revisit Q4.""",
    },
    {
        "title": "Proposal 080 — Brandcraft Studio (Proposal Automation System)",
        "body": """CLIENT: Brandcraft Studio (creative agency)
CONTACT: Mia Steenkamp, Business Director | msteenkamp@brandcraft.co.za
DATE: 18 Jun 2026 | STATUS: Discovery call scheduled 2 Jul | VALID UNTIL: TBD

SCOPE: Client proposal automation: AI drafts creative briefs, scope sections,
and fee estimates from a structured client intake form.

INVESTMENT: Estimated R 130,000 build | Monthly TBD
NOTES: Team writing proposals for 8-10 pitches/month. Each takes 6-8 hours.""",
    },
    # ── Energy & Utilities ────────────────────────────────────────────────────
    {
        "title": "Proposal 081 — SolarEdge SA (Installation Intelligence System)",
        "body": """CLIENT: SolarEdge SA (solar installer, 200+ installs/month)
CONTACT: Darryl Botes, Operations Manager | dbotes@solaredgesa.co.za
DATE: 6 May 2026 | STATUS: APPROVED — live | VALID UNTIL: N/A (active)

SCOPE: Installation scheduling intelligence: crew allocation, permitting deadline
tracking, and client communication automation from quote to commissioning.

INVESTMENT: Build R 210,000 | Monthly retainer R 9,500/month
NOTES: Live since 1 Jun. Install cycle reduced from 19 days to 11 days average.""",
    },
    {
        "title": "Proposal 082 — PowerSave Energy Consultants (Client Energy Intelligence)",
        "body": """CLIENT: PowerSave Energy Consultants
CONTACT: Gerrit Fourie, MD | gfourie@powersave.co.za
DATE: 19 May 2026 | STATUS: In negotiation | VALID UNTIL: 19 Jul 2026

SCOPE: Energy consumption intelligence for their 65 commercial clients. Automated
monthly energy audit reports and tariff optimisation recommendations.

INVESTMENT: Build R 190,000 | Monthly retainer R 9,000/month
NOTES: Gerrit manually producing energy reports — 2 days each. 65 clients = untenable.""",
    },
    {
        "title": "Proposal 083 — Greentech Biogas (Production Monitoring AI)",
        "body": """CLIENT: Greentech Biogas (Pty) Ltd
CONTACT: Dr. Yolanda Ndaba, Chief Scientist | yndaba@greentechbiogas.co.za
DATE: 10 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 10 Aug 2026

SCOPE: Anaerobic digestion monitoring AI: feedstock ratio optimisation, biogas
yield prediction, and automated NERSA compliance reporting.

INVESTMENT: Build R 295,000 | Monthly retainer R 13,500/month
NOTES: Current yield at 62% of theoretical maximum. AI target: 80%+.""",
    },
    {
        "title": "Proposal 084 — Cape Town Water Authority (Usage Intelligence)",
        "body": """CLIENT: City of Cape Town (Water & Sanitation)
CONTACT: Nadia van Zyl, Chief Engineer | nvanZyl@capetown.gov.za
DATE: 14 Apr 2026 | STATUS: CLOSED — chose SAP solution | VALID UNTIL: Expired

SCOPE: Consumer water usage intelligence: drought demand prediction, anomaly
detection for leaks/waste, and daily consumption dashboard for management.

INVESTMENT: Build R 520,000 | Monthly retainer R 22,000/month
OUTCOME: CoCT chose to extend existing SAP contract. AI features less capable.""",
    },
    {
        "title": "Proposal 085 — EcoVolt Battery Storage (Performance Intelligence)",
        "body": """CLIENT: EcoVolt Battery Storage Solutions
CONTACT: Marcus Tan, CTO | mtan@ecovolt.co.za
DATE: 16 Jun 2026 | STATUS: Discovery call scheduled 3 Jul | VALID UNTIL: TBD

SCOPE: Battery system health intelligence across 850+ residential and commercial
installations. Degradation forecasting, warranty claim prediction, and fleet health brief.

INVESTMENT: Estimated R 280,000 build | Monthly TBD
NOTES: Marcus managing a R 120M fleet with no centralised monitoring. Urgent need.""",
    },
    # ── Transport & Automotive ────────────────────────────────────────────────
    {
        "title": "Proposal 086 — Prestige Auto Group (Dealership Intelligence)",
        "body": """CLIENT: Prestige Auto Group (8 dealerships)
CONTACT: Chantelle Meyer, Group GM | cmeyer@prestigeauto.co.za
DATE: 28 Apr 2026 | STATUS: APPROVED — live | VALID UNTIL: N/A (active)

SCOPE: Dealership performance intelligence across 8 branches. Gross profit per unit,
F&I penetration tracking, and weekly GM brief with competitor pricing alerts.

INVESTMENT: Build R 230,000 | Monthly retainer R 10,500/month
NOTES: Live since May. Flagged a R 890,000 gross profit leak in Service department.""",
    },
    {
        "title": "Proposal 087 — Roadlink Bus Services (Passenger Intelligence)",
        "body": """CLIENT: Roadlink Bus Services
CONTACT: Sbusiso Nkosi, Network Planning Manager | snkosi@roadlink.co.za
DATE: 15 May 2026 | STATUS: Pending | VALID UNTIL: 15 Jul 2026

SCOPE: Passenger demand intelligence across 34 routes. AI scheduling optimisation,
load forecasting, and automated delay notification system for commuters.

INVESTMENT: Build R 260,000 | Monthly retainer R 12,000/month
NOTES: Two routes running at 38% capacity while others are overcrowded. Low-hanging fruit.""",
    },
    {
        "title": "Proposal 088 — MotoFix Panel Beaters (Workshop Intelligence)",
        "body": """CLIENT: MotoFix Panel Beaters (14 workshops)
CONTACT: Craig Abrahams, Operations Director | cabrahams@motofix.co.za
DATE: 2 Jun 2026 | STATUS: In negotiation | VALID UNTIL: 2 Aug 2026

SCOPE: Workshop throughput intelligence: job card analysis, parts ordering optimisation,
and insurer authorisation delay tracking per workshop.

INVESTMENT: Build R 175,000 | Monthly retainer R 8,000/month
NOTES: Average insurer authorisation delay costing each workshop R 45,000/month.""",
    },
    {
        "title": "Proposal 089 — Trans-Kalahari Freight (Border Compliance AI)",
        "body": """CLIENT: Trans-Kalahari Freight CC
CONTACT: Freddie Bosman, Compliance Director | fbosman@transkalahari.co.za
DATE: 11 Mar 2026 | STATUS: CLOSED — regulatory uncertainty | VALID UNTIL: Expired

SCOPE: Cross-border freight documentation AI for Botswana and Namibia corridors.
Permit pre-checking, customs declaration automation, and broker communication.

INVESTMENT: Build R 200,000 | Monthly retainer R 9,000/month
NOTES: New customs regulation from BURS created uncertainty. Revisit after Q3 clarity.""",
    },
    {
        "title": "Proposal 090 — DriveWell Fleet Management (ESG Reporting AI)",
        "body": """CLIENT: DriveWell Fleet Management
CONTACT: Paula Mostert, Sustainability Lead | pmostert@drivewell.co.za
DATE: 19 Jun 2026 | STATUS: Discovery call scheduled 8 Jul | VALID UNTIL: TBD

SCOPE: Fleet ESG intelligence: carbon emissions per vehicle, fuel efficiency
benchmarking, and automated Scope 1 emissions report for client reporting.

INVESTMENT: Estimated R 210,000 build | Monthly TBD
NOTES: Three of their top clients now requiring Scope 1 data for their own ESG reports.""",
    },
    # ── Telecommunications ────────────────────────────────────────────────────
    {
        "title": "Proposal 091 — ConnectSA ISP (Network Fault Intelligence)",
        "body": """CLIENT: ConnectSA Internet Services
CONTACT: Justin van der Merwe, NOC Manager | jvandermerwe@connectsa.co.za
DATE: 5 May 2026 | STATUS: APPROVED — in build | VALID UNTIL: N/A (signed)

SCOPE: Network fault prediction using SNMP + syslog data. Pre-emptive maintenance
alerts before customer impact, and automated ticket creation in JIRA.

INVESTMENT: Build R 295,000 | Monthly retainer R 13,500/month
NOTES: Signed 1 Jun. Build 30% complete. Go-live target 1 Sep 2026.""",
    },
    {
        "title": "Proposal 092 — TelecomPlus (Customer Churn Intelligence)",
        "body": """CLIENT: TelecomPlus (MVNO, 85,000 subscribers)
CONTACT: Ayesha Moosa, Head of Retention | amoosa@telecomplus.co.za
DATE: 22 May 2026 | STATUS: Pending | VALID UNTIL: 22 Jul 2026

SCOPE: Subscriber churn prediction model. At-risk segments, automated win-back
campaign triggers, and monthly churn forecast by product tier.

INVESTMENT: Build R 240,000 | Monthly retainer R 11,000/month
NOTES: Monthly churn at 3.2% — industry benchmark is 1.8%. Urgency is high.""",
    },
    {
        "title": "Proposal 093 — FibreNow (Rollout Intelligence System)",
        "body": """CLIENT: FibreNow Infrastructure (Pty) Ltd
CONTACT: Brendan Shaw, Head of Rollout | bshaw@fibrenow.co.za
DATE: 10 Jun 2026 | STATUS: In negotiation | VALID UNTIL: 10 Aug 2026

SCOPE: Fibre rollout project intelligence: trench permit tracking, contractor
progress monitoring, and go-live forecasting across 14 active suburbs.

INVESTMENT: Build R 215,000 | Monthly retainer R 10,000/month
NOTES: Currently missing go-live dates by avg 6 weeks. Contractors self-reporting.""",
    },
    {
        "title": "Proposal 094 — Dial-In Contact Centre (Agent Performance AI)",
        "body": """CLIENT: Dial-In Contact Centre Solutions
CONTACT: Thandiwe Mokoena, QA Manager | tmokoena@dialin.co.za
DATE: 28 Mar 2026 | STATUS: CLOSED — tool conflict with existing system | VALID UNTIL: Expired

SCOPE: Agent performance intelligence: call quality scoring, handle time analysis,
and automated coaching brief per agent weekly.

INVESTMENT: Build R 180,000 | Monthly retainer R 8,500/month
NOTES: Existing Genesys contract covers basic reporting. Custom AI not approved.""",
    },
    {
        "title": "Proposal 095 — SatLink VSAT (Remote Site Intelligence)",
        "body": """CLIENT: SatLink VSAT Solutions
CONTACT: Eric Hendricks, Technical Director | ehendricks@satlink.co.za
DATE: 15 Jun 2026 | STATUS: Proposal sent | VALID UNTIL: 15 Aug 2026

SCOPE: Remote site connectivity intelligence across 340 VSAT installations (mines,
farms, game lodges). Uptime prediction, outage cause classification, SLA breach alerts.

INVESTMENT: Build R 310,000 | Monthly retainer R 14,000/month
NOTES: Manual site monitoring requires 2 NOC staff 24/7. AI target: 1 staff with alerts.""",
    },
    # ── Retail Banking & Fintech ──────────────────────────────────────────────
    {
        "title": "Proposal 096 — PayBridge Fintech (Transaction Intelligence)",
        "body": """CLIENT: PayBridge Fintech (Pty) Ltd
CONTACT: Nhlanhla Msibi, Chief Risk Officer | nmsibi@paybridgefintech.co.za
DATE: 8 Jun 2026 | STATUS: In negotiation — SARB notification required | VALID UNTIL: 8 Sep 2026

SCOPE: Real-time transaction pattern intelligence: fraud velocity detection,
merchant risk scoring, and daily regulatory risk brief.

INVESTMENT: Build R 420,000 | Monthly retainer R 19,000/month
NOTES: SARB notification for AI in payment processing — 30-day window. Filing 15 Jun.""",
    },
    {
        "title": "Proposal 097 — MicroLend SA (Portfolio Intelligence Dashboard)",
        "body": """CLIENT: MicroLend SA (microfinance, 42,000 active loans)
CONTACT: Zodwa Mthembu, Portfolio Manager | zmthembu@microlendsa.co.za
DATE: 19 May 2026 | STATUS: APPROVED — live | VALID UNTIL: N/A (active)

SCOPE: Loan portfolio intelligence: arrears prediction, collections prioritisation,
and weekly portfolio health brief with NPL trend forecasting.

INVESTMENT: Build R 265,000 | Monthly retainer R 12,000/month
NOTES: Live since 15 May. Collections efficiency up 18% in first month.""",
    },
    {
        "title": "Proposal 098 — CryptoSafe Exchange (Compliance Intelligence)",
        "body": """CLIENT: CryptoSafe Exchange
CONTACT: Ethan Clarke, Chief Compliance Officer | eclarke@cryptosafe.co.za
DATE: 4 Jun 2026 | STATUS: Pending — FSCA CASP registration pending | VALID UNTIL: 4 Sep 2026

SCOPE: FICA compliance intelligence: transaction monitoring, SAR generation automation,
and monthly AML risk report for the compliance committee.

INVESTMENT: Build R 340,000 | Monthly retainer R 15,500/month
NOTES: CASP registration required before build can start. Expected FSCA approval Aug 2026.""",
    },
    {
        "title": "Proposal 099 — Capital Growth Advisors (Wealth Intelligence Platform)",
        "body": """CLIENT: Capital Growth Advisors
CONTACT: Taryn Smit, Head of Wealth | tsmit@capitalgrowth.co.za
DATE: 13 Jun 2026 | STATUS: Proposal sent — response expected 1 Jul | VALID UNTIL: 13 Aug 2026

SCOPE: Wealth client intelligence: portfolio drift alerts, annual review preparation
briefs, and next-best-action recommendations per advisor.

INVESTMENT: Build R 275,000 | Monthly retainer R 12,500/month
NOTES: Taryn managing 180 HNW clients. Quarterly review prep taking 1 day per client.""",
    },
    {
        "title": "Proposal 100 — BoschAI Internal (AIOS Master Intelligence Layer)",
        "body": """CLIENT: BoschAI (internal — Heinrich's own agency)
CONTACT: Heinrich Bosch, Founder | heinrich@boschai.co.za
DATE: 1 Jan 2026 | STATUS: ACTIVE — live 24/7 on Railway | VALID UNTIL: N/A (ongoing)

SCOPE: The full BoschAI AIOS — intelligence layer for the agency itself.
Email follow-up bot, LinkedIn growth system, pipeline intelligence, daily brief,
Telegram command centre, invoice processing, and Drive intelligence Q&A.

INVESTMENT: Internal build — tools + API costs ~R 1,200/month
NOTES: This IS the reference build used to deliver the same system for clients.
Every module built here becomes a productised offering. The product IS the proof.""",
    },
]


def create_doc(drive_service, folder_id, title, body):
    meta = {
        "name": title + ".txt",
        "parents": [folder_id],
    }
    media = MediaInMemoryUpload(body.encode("utf-8"), mimetype="text/plain")
    drive_service.files().create(body=meta, media_body=media, fields="id").execute()


def main():
    print("Authenticating...")
    creds = get_creds()
    drive = build("drive", "v3", credentials=creds)

    print(f"Uploading {len(PROPOSALS)} proposals to folder {FOLDER_ID}...\n")
    for i, p in enumerate(PROPOSALS, 1):
        print(f"  [{i:03d}/{len(PROPOSALS)}] {p['title'][:60]}...")
        create_doc(drive, FOLDER_ID, p["title"], p["body"])

    print(f"\nDone! {len(PROPOSALS)} proposals uploaded.")
    print(f"Open your Drive Intelligence dashboard and select the 'Proposals Demo' folder.")
    print("\nPower demo questions:")
    print("  1. How much total revenue is at risk from pending proposals?")
    print("  2. Which proposals have gone quiet and need urgent follow-up?")
    print("  3. What industries do our approved clients come from?")
    print("  4. Which pending deal has the highest monthly retainer?")
    print("  5. List all closed-lost deals and the reasons we lost them.")
    print("  6. What is the total value of all signed contracts on retainer?")


if __name__ == "__main__":
    main()
