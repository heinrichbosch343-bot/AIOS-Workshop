"""
seed_demo_company.py — populates data/jarvis_demo.db with Meridian Manufacturing (Pty) Ltd.

A fictional mid-size industrial pumps & valves manufacturer in Cape Town (~85 staff).
All data is hardcoded and deterministic so the demo answers identically every run.

Run directly:  python seed_demo_company.py [--force]
Or import:     from seed_demo_company import seed; seed()
"""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store

# ---------------------------------------------------------------- financials
# Story arc: steady growth, one dip in 2025-Q2 (load-shedding + lost Karoo Water
# contract), margins climb from 31% to 36% after the Benoni Steel renegotiation
# in 2025-Q3. "This quarter" = 2026-Q2.
FINANCIALS = [
    # quarter, revenue, margin_pct, opex, headcount, notes
    ("2024-Q3", 18_200_000, 31.0, 4_200_000, 78, "Steady quarter; PetroSA maintenance volumes carried revenue."),
    ("2024-Q4", 19_100_000, 31.5, 4_300_000, 79, "Year-end spares rush from mining clients lifted revenue."),
    ("2025-Q1", 19_800_000, 32.0, 4_400_000, 80, "New Tongaat Hulett account onboarded; margin steady."),
    ("2025-Q2", 17_600_000, 30.5, 4_550_000, 80, "Down quarter: Stage-6 load-shedding cut foundry output and the Karoo Water contract was lost to a cheaper import."),
    ("2025-Q3", 20_900_000, 34.0, 4_600_000, 81, "Recovery quarter: backup generators online and the Benoni Steel supply renegotiation lifted gross margin 3.5 points."),
    ("2025-Q4", 22_300_000, 35.0, 4_700_000, 82, "Strongest Q4 on record; Benoni Steel pricing fully in effect."),
    ("2026-Q1", 23_400_000, 35.5, 4_800_000, 84, "PetroSA 3-year maintenance contract signed; two machinists hired."),
    ("2026-Q2", 24_600_000, 36.0, 4_900_000, 85, "Record quarter: revenue up 40% on the Q2 2025 dip, margin at a company-best 36%."),
]

# ------------------------------------------------------------------ pipeline
PIPELINE = [
    ("Transnet pump station retrofit", "Transnet Port Terminals", "Negotiation", 4_200_000, "Pieter",
     "2026-08-15", "2026-05-22",
     "Biggest open deal. Stuck in Transnet procurement review for 6 weeks — waiting on BEE scorecard verification. Needs executive escalation."),
    ("Sasol valve supply renewal", "Sasol Secunda", "Proposal", 2_800_000, "Thandi",
     "2026-07-31", "2026-07-02",
     "3-year renewal proposal submitted; procurement reviewing volume discount tiers."),
    ("AngloGold slurry pump order", "AngloGold Ashanti", "Negotiation", 3_100_000, "Thandi",
     "2026-07-18", "2026-07-03",
     "Technical specs approved in May; final pricing call booked. Expected to close this month."),
    ("Cape Town water works upgrade", "City of Cape Town", "Qualified", 1_900_000, "Ruan",
     "2026-09-30", "2026-06-28",
     "Tender shortlist confirmed; site walkthrough done end June."),
    ("Distell bottling line retrofit", "Distell Group", "Qualified", 1_200_000, "Pieter",
     "2026-09-15", "2026-06-26",
     "Upsell born from the June seal-failure complaint — client impressed with the 48-hour turnaround."),
    ("Karoo Agri irrigation valves", "Karoo Agri Co-op", "Lead", 650_000, "Ruan",
     "2026-10-15", "2026-06-15",
     "Inbound enquiry after the Nampo expo; first call done."),
    ("Koeberg spares framework", "Eskom Koeberg", "Lead", 850_000, "Thandi",
     "2026-11-30", "2026-06-10",
     "Early-stage; vendor registration paperwork in progress."),
    ("PetroSA maintenance contract", "PetroSA", "Closed Won", 2_400_000, "Pieter",
     "2026-05-30", "2026-05-30",
     "3-year rotating equipment maintenance contract — signed 30 May 2026."),
    ("Tongaat Hulett pump replacement", "Tongaat Hulett", "Closed Won", 1_150_000, "Ruan",
     "2026-04-12", "2026-04-12",
     "Eight process pumps delivered and commissioned April 2026."),
    ("Namib Mining valve package", "Namib Mining Corp", "Closed Lost", 980_000, "Thandi",
     "2026-06-05", "2026-06-05",
     "Lost to a Chinese import on price — 22% below our floor. Decision: hold pricing discipline."),
]

# ------------------------------------------------------------------ meetings
# (date, title, type, attendees, summary, action_items, transcript)
MEETINGS = [
    ("2026-07-01", "Q2 2026 Executive Review", "exec",
     "Marius (CEO), Elaine (CFO), Sipho (Ops Director), Pieter (Sales Director)",
     "Reviewed record Q2 results: R24.6M revenue at 36% gross margin. Approved hiring two fitters, agreed Marius will escalate the stalled Transnet deal, and greenlit the predictive maintenance pilot.",
     ["Marius to call the Transnet executive sponsor this week",
      "Elaine to release budget for two additional fitters",
      "Sipho to scope the predictive maintenance pilot by end July"],
     """Marius: Right, Q2 close-out. Elaine, give us the headline.
Elaine: Best quarter we've ever had. Revenue came in at 24.6 million rand, gross margin at 36 percent — that's a company record on both. Net profit just over 3.9 million. Compare that to Q2 last year when load-shedding knocked us down to 17.6 million, we're up about 40 percent year on year.
Marius: And the margin — that's the Benoni Steel deal still paying off?
Elaine: Exactly. We were at 30.5 percent this time last year. The renegotiation in Q3 plus better foundry utilisation got us to 36.
Sipho: Foundry is running flat out. If AngloGold and Transnet both land, we'll need two more fitters or lead times slip.
Marius: Approved — Elaine, release the budget. Now, Transnet. Pieter, it's been six weeks.
Pieter: Stuck in their procurement review. BEE scorecard verification. Our paperwork is in, but nobody's moving it. I think it needs to come from you, Marius — call their exec sponsor directly.
Marius: I'll call him this week. That's 4.2 million we're not leaving on the table. Anything else?
Sipho: The predictive maintenance pilot. Three clients have asked. I want to scope it properly.
Marius: Do it — scope by end of July. Good quarter, everyone. Let's not get comfortable.""",
     ),
    ("2026-06-27", "Weekly Sales Pipeline Review", "sales",
     "Pieter (Sales Director), Thandi, Ruan",
     "Pipeline sits at roughly R14.7M open. Transnet flagged as stalled — no movement in five weeks. AngloGold on track to close 18 July. Distell retrofit added to pipeline after the complaint turnaround.",
     ["Pieter to brief Marius on the Transnet stall before the exec review",
      "Thandi to lock the AngloGold pricing call for the first week of July",
      "Ruan to prepare the Cape Town tender documents"],
     """Pieter: Open pipeline this morning is fourteen point seven million. Let's go deal by deal. Thandi, AngloGold?
Thandi: On track. Specs were approved in May, pricing call is being booked now. I'm confident for the 18th of July. Three point one million.
Pieter: Good. Sasol renewal?
Thandi: Proposal is in. They're chewing on the volume discount tiers. Should hear back mid-July.
Pieter: Transnet. Elephant in the room.
Thandi: Five weeks of silence now. Last real contact was the negotiation session on the 22nd of May.
Pieter: I know. Procurement wants BEE scorecard verification and it's sitting in a queue. This needs Marius to call their exec sponsor — I'll raise it at the exec review. Ruan, Cape Town?
Ruan: Shortlisted. Site walkthrough done Friday. Tender docs due end of September, I'll start drafting.
Pieter: And I'm adding Distell to the board — the retrofit. After we turned their seal failure around in 48 hours, they asked for a proposal. One point two million, calling it Qualified.
Ruan: From complaint to upsell. Love it.
Pieter: That's how it should work. Right — targets for next week on the board. Go sell.""",
     ),
    ("2026-06-24", "Ops Weekly — Production & Supply", "ops",
     "Sipho (Ops Director), Anika (Production Manager), Johan (Procurement)",
     "Benoni Steel supply agreement continues to hold margin gains — casting input costs down 11% year on year. Casting lead times improved from six weeks to four. Foundry at 94% utilisation.",
     ["Johan to extend the Benoni Steel agreement option for 2027",
      "Anika to publish the revised four-week lead time to sales"],
     """Sipho: Quick one today. Johan, supply first.
Johan: Benoni Steel is still the best decision we made last year. Casting inputs are down eleven percent year on year against the old SteelCorp pricing. That's what's holding gross margin at 36.
Sipho: And that's exactly what Elaine will present at the exec review. Any risk on their side?
Johan: None visible. They want to talk about extending into 2027 — I say we take the option.
Sipho: Take it. Anika, production?
Anika: Foundry utilisation is at 94 percent. Casting lead time is down to four weeks — was six this time last year. But if both big deals land in Q3, we're at the ceiling.
Sipho: Understood — I'm tabling headcount at the exec review. Publish the four-week lead time to the sales team, they should be selling it.
Anika: Will do. One more thing — the Distell replacement seals shipped and fitted. Zero failures since.
Sipho: Good. That one turned into a sales opportunity, believe it or not. Done — back to work.""",
     ),
    ("2026-06-26", "Client Call — Distell Follow-up", "client",
     "Pieter (Sales Director), Anika (Production Manager), Werner (Distell Engineering Manager)",
     "Follow-up after the seal failure resolution. Distell confirmed zero failures since the replacement batch. Werner requested a formal proposal for retrofitting the remaining bottling line — new R1.2M opportunity.",
     ["Pieter to submit the bottling line retrofit proposal by 10 July",
      "Anika to include the new seal spec in the retrofit design"],
     """Pieter: Werner, thanks for making time. Main thing we wanted to hear — how are the pumps running?
Werner: Honestly? Faultless. Three weeks since your team fitted the replacement seals, not a single trip. Whatever that new seal spec is, it works.
Anika: It's a different elastomer grade — the failed batch came from a supplier we've since dropped. Root cause report is with you.
Werner: Read it. Look, I'll be straight — when the line went down I was ready to pull the contract. The 48-hour turnaround changed my mind. Nobody else moves that fast.
Pieter: That's what we want to be known for.
Werner: Which brings me to why I asked for this call. The rest of the bottling line is running pumps from 2011. If your retrofit numbers make sense, I want a proposal for the full line.
Pieter: We'll have it to you by the 10th of July. Anika will spec the same seal grade throughout.
Werner: Good. Send it. And tell your team the Windhoek plant manager may come knocking too.""",
     ),
    ("2026-06-19", "Client Call — Sasol Renewal Scope", "client",
     "Thandi, Marius (CEO), Lindiwe (Sasol Procurement Lead)",
     "Scoped the 3-year valve supply renewal with Sasol. Lindiwe pushed for tiered volume discounts; Meridian offered 4% at tier two in exchange for a firm 3-year term. Proposal to follow within a week.",
     ["Thandi to submit the renewal proposal with tiered pricing by 26 June",
      "Marius to sign off the tier-two discount floor"],
     """Lindiwe: Let's get to it — we're happy with the product, it's the commercials we need to land. Three-year term is on the table if the pricing works.
Thandi: That's what we want too. What does procurement need to see?
Lindiwe: Volume tiers. Flat pricing made sense three years ago; our draw has grown 30 percent since.
Marius: We can work with tiers. What I'd propose: current pricing to tier one, four percent off at tier two volumes — in exchange for the firm three-year term, not an evergreen with a break clause.
Lindiwe: Four percent is thinner than I hoped.
Marius: It's honest pricing. You've seen what happened with the import valves at Secunda West — cheap until the first unplanned shutdown.
Lindiwe: That's fair, and privately, engineering agrees with you. Put the four percent in writing with the tier thresholds and I'll take it to the committee.
Thandi: You'll have the full proposal by the 26th.
Lindiwe: Then let's aim to wrap this by end of July.""",
     ),
    ("2026-06-12", "Client Call — Distell Seal Failures (Complaint)", "client",
     "Pieter (Sales Director), Sipho (Ops Director), Werner (Distell Engineering Manager)",
     "Urgent complaint call: repeated mechanical seal failures on the bottling line pumps caused two production stoppages. Meridian committed to replacement seals on site within 48 hours and a root cause report within a week.",
     ["Sipho to airfreight replacement seals and a fitting team within 48 hours",
      "Anika to deliver a root cause analysis report by 19 June",
      "Pieter to call Werner daily until resolved"],
     """Werner: I'll be blunt. Two stoppages in ten days, both your seals. My line lost eleven hours of production. I've got Cape Town head office asking why we moved to Meridian.
Pieter: Werner, you're right to be angry, and we're not going to hide behind warranty language. Sipho is on this call because we're treating it as our top priority.
Sipho: Here's the commitment. Replacement seals — a different batch, different supplier — will be on your site with our fitting team within 48 hours. Full root cause analysis in writing within a week.
Werner: I've heard 48 hours before from suppliers.
Sipho: You'll have a flight confirmation in your inbox tonight.
Werner: And if these fail too?
Sipho: Then we retrofit the pumps at our cost. But they won't — we believe it's a bad elastomer batch, and the replacements are from a different supplier entirely.
Pieter: I'll call you personally every day until your line manager tells me to stop.
Werner: Fine. Forty-eight hours. Prove it.""",
     ),
    ("2026-06-05", "Monthly Exec — May Review & Namib Post-mortem", "exec",
     "Marius (CEO), Elaine (CFO), Sipho (Ops Director), Pieter (Sales Director)",
     "May revenue tracking ahead of plan. Namib Mining loss reviewed: beaten 22% on price by an import. Decision: hold pricing discipline, compete on lead time and lifecycle cost, not price. PetroSA contract celebrated.",
     ["Pieter to build a lifecycle-cost comparison sheet for sales calls",
      "Elaine to model the margin impact if import competition spreads"],
     """Marius: May first. Elaine?
Elaine: Tracking about eight percent ahead of plan for the quarter. PetroSA's first monthly invoice is out — 2.4 million over three years, signed on the 30th.
Marius: Good. Now the one that stings — Namib Mining. Thandi's deal. What happened?
Pieter: A Chinese import came in 22 percent below our floor. We couldn't match it without selling at a loss, so we didn't. Thandi ran it well — we lost on price, not on execution.
Marius: Do we chase these down in future?
Elaine: I modelled it. If we discount to import levels, our gross margin drops below 28 percent and the whole growth story unwinds.
Marius: Then we don't. Decision on record: we hold pricing discipline. We win on four-week lead times, on being on site in 48 hours, on lifecycle cost. Pieter, I want a lifecycle-cost sheet the team can put in front of every mining client.
Pieter: By mid-June.
Marius: The Namibs will come back when the cheap valves start failing. Be gracious when they do.""",
     ),
    ("2026-05-29", "Ops — Load-shedding Mitigation Review", "ops",
     "Sipho (Ops Director), Anika (Production Manager), Elaine (CFO)",
     "One year after the generator investment: zero production hours lost to load-shedding in 2026 versus 340 hours lost in H1 2025. The R3.8M generator installation has effectively paid for itself.",
     ["Elaine to include the generator ROI story in the annual report",
      "Anika to schedule the generators' annual service for July"],
     """Sipho: A year ago we were bleeding. I wanted this on record. Anika, the numbers.
Anika: First half of 2025 we lost 340 production hours to load-shedding — that's most of why Q2 2025 came in at 17.6 million. Since the generators went live in August: zero hours lost. None.
Elaine: And the investment was 3.8 million all-in. By my maths the avoided losses covered that inside ten months.
Sipho: Which is why Q3 2025 bounced to 20.9 and we haven't looked back.
Elaine: I want this in the annual report. It's the best capital decision we made and shareholders should see it.
Anika: One caution — the units need their annual service. Booking it for July, low-risk window.
Sipho: Approved. Anything else? Then short and sweet — that's the meeting.""",
     ),
    ("2026-05-22", "Transnet Negotiation Session", "sales",
     "Pieter (Sales Director), Marius (CEO), Nomsa (Transnet Procurement), David (Transnet Engineering)",
     "Negotiation on the R4.2M pump station retrofit. Engineering fully behind the proposal; procurement raised BEE scorecard verification as a gate before award. Documents submitted same day — this was the last substantive contact on the deal.",
     ["Pieter to submit BEE scorecard documentation (done same day)",
      "Nomsa to confirm verification timeline (outstanding)"],
     """David: Engineering has no further questions. The retrofit design is the best submission we received, and the four-week lead time matters to us.
Marius: Good to hear. So what stands between us and an award?
Nomsa: Process. Before award I need your current BEE scorecard through our verification portal, plus two reference letters from state-owned entity clients.
Pieter: Scorecard goes in today. References — PetroSA and Eskom Koeberg will both provide letters this week.
Nomsa: Then it goes into the verification queue.
Marius: How long is that queue, Nomsa? We've held pricing for ninety days.
Nomsa: Officially, fifteen working days. I'll be honest — the verification office is backed up.
Marius: Can we do anything to help it along?
Nomsa: Not at my level.
David: For what it's worth, engineering will keep flagging this as urgent. Those pump stations are running on borrowed time.
Pieter: Then we'll have everything submitted by close of business today. Over to you.""",
     ),
    ("2026-05-15", "Client Call — AngloGold Technical Review", "client",
     "Thandi, Anika (Production Manager), Kobus (AngloGold Reliability Engineer)",
     "Technical review of the slurry pump order. Kobus approved the duty specs and the hardened impeller option. Deal moves to Negotiation — pricing call to be scheduled once budget clears.",
     ["Thandi to prepare final pricing with the hardened impeller option",
      "Anika to reserve foundry capacity for a July production slot"],
     """Kobus: I've been through the datasheets twice. The duty point calculations are right, which is more than I can say for two of your competitors.
Anika: We sized against the slurry densities you actually reported, not the nameplate figures.
Kobus: Noticed. One question — the hardened impeller option. Real-world wear life?
Anika: On comparable duty at Tongaat we're seeing eighteen months versus about seven on standard. It's 12 percent on the unit price.
Kobus: That pays for itself twice over in downtime alone. Spec it on all six units.
Thandi: Done. So technically we're approved?
Kobus: Technically approved, yes. Commercially — budget release is with our finance people. Expect the pricing call in early July.
Thandi: We'll be ready. If you confirm by mid-July we can hold a July production slot.
Kobus: Reserve it. This order is coming — the current pumps are eating impellers every quarter.""",
     ),
    ("2026-05-08", "Ops — Quality Review (Seal Batch Investigation)", "ops",
     "Sipho (Ops Director), Anika (Production Manager), Johan (Procurement)",
     "Investigated early seal failure reports traced to elastomer batch EL-2247 from supplier Polyflex. Decision: quarantine the batch, switch seal elastomers to Hendrickse Polymers, notify affected clients proactively.",
     ["Johan to quarantine batch EL-2247 and return stock to Polyflex",
      "Anika to identify all client sites that received the batch",
      "Sipho to approve Hendrickse Polymers as the new elastomer supplier"],
     """Anika: We've got a pattern. Three early seal failures in four weeks, all traced to one elastomer batch — EL-2247 from Polyflex.
Sipho: Confirmed root cause?
Anika: Lab says the compound cured wrong — hardness is out of spec. It embrittles under heat cycling. Every failure is that batch.
Sipho: Where has it gone?
Anika: Mostly internal stock, but some shipped. Distell's bottling line pumps got seals from this batch in April. If they're going to fail anywhere first, it's there — that line heat-cycles constantly.
Sipho: Then we get ahead of it. Johan, quarantine everything from EL-2247 today.
Johan: Already flagged. I also want to move elastomers to Hendrickse Polymers — better QC, local, and they batch-test with certificates.
Sipho: Approved. Anika, list every client site that received this batch. If Distell calls before we call them, we've failed twice.
Anika: On it. For the record — this is exactly why we log batch numbers per shipment.
Sipho: And it's about to prove its worth. Move.""",
     ),
    ("2026-04-28", "Exec — FY25 Wrap & FY26 Targets", "exec",
     "Marius (CEO), Elaine (CFO), Sipho (Ops Director), Pieter (Sales Director)",
     "Closed the FY25 books: R80.6M full-year revenue. Set FY26 targets: R100M revenue at 36%+ gross margin, headcount below 90. Growth to come from state-owned entity contracts and maintenance recurring revenue.",
     ["Elaine to circulate the FY26 budget by 9 May",
      "Pieter to build a state-owned entity target account list",
      "Sipho to present a maintenance-as-a-service model in June"],
     """Marius: FY25 is closed. Elaine, the year in one breath.
Elaine: Eighty point six million for the twelve months — 2025 Q1 through Q4 plus the strong finish. Up 13 percent on FY24 despite the Q2 hole. Margin exited at 35.
Marius: And the target I want on the wall for FY26: one hundred million rand. Is it real?
Elaine: It's a stretch, not a fantasy. It needs roughly 25 million a quarter by year end.
Pieter: The pipeline supports it if the big state-owned deals land — Transnet alone is 4.2. My worry is those procurement cycles.
Marius: Which is why we diversify the growth: Sipho, talk about recurring revenue.
Sipho: Maintenance contracts. PetroSA is the template — predictable monthly revenue, our margins, sticky for three years. I want to package it properly: maintenance-as-a-service. I'll present a model in June.
Marius: Do it. Targets on record: one hundred million revenue, 36-plus margin, headcount under 90. Lean and profitable — we don't hire our way to growth.
Elaine: Budget circulated by the 9th.
Marius: Good. FY26 starts now.""",
     ),
]

# ----------------------------------------------------------------- documents
DOCUMENTS = [
    ("2026-06-02", "Invoice INV-2418 — PetroSA (Maintenance, June)", "invoice",
     """INVOICE INV-2418
Date: 2026-06-02 | Client: PetroSA | Terms: 30 days
Rotating equipment maintenance — monthly fee per contract MSA-PET-2026: R66,667 excl. VAT.
First invoice under the 3-year maintenance contract signed 2026-05-30 (total contract value R2,400,000).
VAT (15%): R10,000 | Total due: R76,667."""),
    ("2026-04-15", "Invoice INV-2402 — Tongaat Hulett (Pump Replacement)", "invoice",
     """INVOICE INV-2402
Date: 2026-04-15 | Client: Tongaat Hulett | Terms: 30 days
Supply, delivery and commissioning of 8 x MP-340 process pumps per order TH-8841: R1,150,000 excl. VAT.
Includes commissioning (completed 2026-04-12) and 24-month warranty.
VAT (15%): R172,500 | Total due: R1,322,500. Status: PAID 2026-05-09."""),
    ("2026-06-20", "Invoice INV-2431 — Sasol Secunda (Valve Spares)", "invoice",
     """INVOICE INV-2431
Date: 2026-06-20 | Client: Sasol Secunda | Terms: 30 days
Valve spares and gasket kits per call-off order SAS-2216: R310,000 excl. VAT.
VAT (15%): R46,500 | Total due: R356,500."""),
    ("2026-05-30", "Contract MSA-PET-2026 — PetroSA Maintenance Agreement", "contract",
     """MASTER SERVICE AGREEMENT — MSA-PET-2026
Parties: Meridian Manufacturing (Pty) Ltd and PetroSA. Signed: 2026-05-30.
Scope: rotating equipment maintenance (pumps, valves, seals) at the Mossel Bay facility.
Term: 36 months (2026-06-01 to 2029-05-31). Value: R2,400,000 over term, invoiced monthly at R66,667.
SLA: 48-hour on-site response for breakdowns; quarterly condition-monitoring reports.
Account owner: Pieter. Escalation: Sipho (Ops Director)."""),
    ("2025-08-18", "Contract SUP-BEN-2025 — Benoni Steel Supply Agreement", "contract",
     """SUPPLY AGREEMENT — SUP-BEN-2025
Parties: Meridian Manufacturing (Pty) Ltd and Benoni Steel Works. Signed: 2025-08-18.
Scope: casting-grade steel and iron inputs for the Cape Town foundry.
Pricing: fixed schedule 11% below prior SteelCorp rates; quarterly review capped at PPI.
Term: 2025-09-01 to 2026-12-31, with option to extend through 2027.
Note: this renegotiation is the primary driver of the gross margin improvement from 31% to 36% between FY24 and FY26."""),
    ("2026-04-30", "Monthly Ops Report — April 2026", "report",
     """OPS REPORT — APRIL 2026
Output: 412 units (record month). Foundry utilisation: 91%. Casting lead time: 4.5 weeks.
Downtime: 0 hours load-shedding (generators), 14 hours planned maintenance.
Safety: 0 lost-time injuries, 289 days LTI-free.
Quality: 3 early seal failure reports under investigation — traced to elastomer batch EL-2247 (Polyflex). Quarantine initiated.
Deliveries: Tongaat Hulett 8-pump order commissioned 12 April."""),
    ("2026-05-31", "Monthly Ops Report — May 2026", "report",
     """OPS REPORT — MAY 2026
Output: 428 units. Foundry utilisation: 93%. Casting lead time: 4.2 weeks.
Downtime: 0 hours load-shedding, 8 hours planned maintenance.
Safety: 0 lost-time injuries, 320 days LTI-free.
Quality: batch EL-2247 quarantined and returned; elastomer supply switched to Hendrickse Polymers. Client sites notified.
Commercial: PetroSA 3-year maintenance contract signed 30 May."""),
    ("2026-06-30", "Monthly Ops Report — June 2026", "report",
     """OPS REPORT — JUNE 2026
Output: 435 units. Foundry utilisation: 94%. Casting lead time: 4.0 weeks.
Downtime: 0 hours load-shedding, 6 hours planned maintenance.
Safety: 1 minor first-aid case, 0 lost-time injuries.
Quality: Distell replacement seals (Hendrickse) at 3 weeks zero failures; root cause report delivered.
Capacity note: at 94% utilisation, incoming AngloGold + Transnet orders will require 2 additional fitters (raised at Q2 exec review)."""),
    ("2026-04-22", "Proposal PRO-1088 — Transnet Pump Station Retrofit", "proposal",
     """PROPOSAL PRO-1088 — TRANSNET PORT TERMINALS PUMP STATION RETROFIT
Date: 2026-04-22. Value: R4,200,000 excl. VAT. Validity: 90 days (extended once).
Scope: retrofit of 12 pump sets across two port terminal stations — new MP-520 pumps,
hardened impellers, control panel upgrades, commissioning and 12-month support.
Delivery: phased over 14 weeks from award; four-week lead time on first units.
Status: technical approval received from Transnet Engineering (May); awaiting procurement
BEE verification before award. Owner: Pieter."""),
    ("2026-06-26", "Proposal PRO-1102 — Sasol Valve Supply Renewal", "proposal",
     """PROPOSAL PRO-1102 — SASOL SECUNDA VALVE SUPPLY RENEWAL
Date: 2026-06-26. Value: R2,800,000 over 3 years. Validity: 60 days.
Scope: continued supply of control and isolation valves plus spares to Sasol Secunda.
Pricing: tier one at current rates; 4% discount at tier-two volumes (per 19 June scoping call).
Term: firm 36 months, no break clause. Status: submitted, procurement committee review.
Owner: Thandi."""),
]


def seed(force: bool = False) -> dict:
    """Populate the demo DB. Returns row counts. No-op if already seeded (unless force)."""
    store.ensure_db()
    if store.is_seeded() and not force:
        return {"status": "already-seeded"}

    conn = sqlite3.connect(str(store.DB_PATH))
    try:
        for table in ("financials", "pipeline", "meetings", "documents"):
            conn.execute(f"DELETE FROM {table}")

        for quarter, revenue, margin, opex, headcount, notes in FINANCIALS:
            cogs = round(revenue * (1 - margin / 100))
            net = revenue - cogs - opex
            conn.execute(
                "INSERT INTO financials (quarter, revenue_zar, cogs_zar, opex_zar, "
                "gross_margin_pct, net_profit_zar, headcount, notes) VALUES (?,?,?,?,?,?,?,?)",
                (quarter, revenue, cogs, opex, margin, net, headcount, notes),
            )

        conn.executemany(
            "INSERT INTO pipeline (deal_name, company, stage, value_zar, owner, "
            "expected_close, last_activity, notes) VALUES (?,?,?,?,?,?,?,?)",
            PIPELINE,
        )

        for date, title, mtype, attendees, summary, actions, transcript in MEETINGS:
            conn.execute(
                "INSERT INTO meetings (meeting_date, title, meeting_type, attendees, "
                "summary, action_items, transcript) VALUES (?,?,?,?,?,?,?)",
                (date, title, mtype, attendees, summary, json.dumps(actions), transcript),
            )

        conn.executemany(
            "INSERT INTO documents (doc_date, title, doc_type, content) VALUES (?,?,?,?)",
            DOCUMENTS,
        )
        conn.commit()

        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("financials", "pipeline", "meetings", "documents")
        }
        return {"status": "seeded", **counts}
    finally:
        conn.close()


if __name__ == "__main__":
    result = seed(force="--force" in sys.argv)
    print(f"Jarvis demo DB at {store.DB_PATH}")
    print(result)
