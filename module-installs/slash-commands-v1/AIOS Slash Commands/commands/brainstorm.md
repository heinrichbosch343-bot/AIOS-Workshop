# Brainstorm

> Look at your workspace — your tasks, your workflows, your daily work — and brainstorm what to build, automate, or systematize next.

## Variables

topic: $ARGUMENTS (optional — a specific area to focus on, or leave blank to scan everything)

---

## Instructions

You are running a **brainstorm session**. Your job is to help the user figure out **what to build next** by looking at their actual work — tasks, manual processes, repeated actions — and identifying the best opportunities to automate or systematize.

This is NOT about building anything yet. This is about finding the right thing to build. The output feeds into `/explore` (to shape an idea) or `/implement` (if it's obvious what to do).

**Tone:** Conversational and encouraging. The user may not know what's possible — your job is to show them. Get excited about the opportunities you find.

**Output:** A brainstorm doc saved to `plans/brainstorm-YYYY-MM-DD-{topic}.md`

---

## Stage 1: SCAN — Understand Their World

**Goal:** Map out what the user is currently doing, what's manual, and where the opportunities are.

**Actions:**
1. Read the workspace to understand the user's setup:
   - `CLAUDE.md` — what systems exist, what commands are available, what's already automated
   - Any task audit, task list, or project tracking files in the workspace (search for files containing tasks, todos, audits, or project lists)
   - Any context files about their business, role, or current priorities
   - GTD files if ProductivityOS is installed (`gtd/projects.md`, `gtd/next-actions.md`)
2. If a specific topic was provided, focus on that area. If not, scan broadly.
3. Build a picture of:
   - **What's already automated** — systems, commands, cron jobs, scripts they have
   - **What's still manual** — tasks, processes, workflows they do by hand
   - **What data they have** — databases, files, APIs connected
   - **What tools they use** — services, platforms, integrations

4. Present a summary:
   ```
   Here's what I see in your workspace:

   Already automated:
   - {system 1} — {what it does}
   - {system 2} — {what it does}

   Still manual (opportunities):
   - {task/process 1} — {how often, how painful}
   - {task/process 2} — {how often, how painful}
   - {task/process 3} — {how often, how painful}

   Data available:
   - {what data exists that could power new systems}
   ```

**STOP and wait for the user's reaction. Ask:** "Does this look right? Anything I'm missing? Any of these jump out as particularly painful?"

---

## Stage 2: PRIORITIZE — Find the Best Opportunities

**Goal:** Rank the opportunities by impact and feasibility.

**Actions:**
1. Based on the scan and user input, evaluate each opportunity on two axes:
   - **Impact:** How much time/effort would this save? How often does this task happen? How painful is it?
   - **Feasibility:** How hard is this to build? What's needed (APIs, data, tools)? Can Claude Code handle it?

2. Present a ranked list:
   ```
   Top opportunities (ranked by impact x feasibility):

   1. {Opportunity} — Impact: High | Feasibility: Easy
      What it would do: {one sentence}
      Why it's #1: {brief reasoning}

   2. {Opportunity} — Impact: High | Feasibility: Medium
      What it would do: {one sentence}
      Why it's #2: {brief reasoning}

   3. {Opportunity} — Impact: Medium | Feasibility: Easy
      What it would do: {one sentence}
      Quick win — could build this fast

   4-5. {Additional opportunities...}
   ```

3. Call out any "quick wins" — things that are easy to build and immediately useful
4. Call out any "big bets" — things that are harder but transformative

**STOP and ask:** "Which of these interests you most? Want to dig into any of them?"

---

## Stage 3: DEEP DIVE — Explore the Top Pick

**Goal:** Go deeper on the opportunity the user is most interested in.

**Actions:**
1. For the selected opportunity, explore:
   - **What exactly would this look like?** Walk through the user flow
   - **What already exists** in the workspace that could be leveraged?
   - **What would need to be built?** Rough component list
   - **What's the simplest version** that would still be useful?
   - **What would it cost?** (Free? API costs? External services?)

2. If the user is interested in multiple opportunities, briefly outline each rather than deep-diving one

3. Present your thinking and ask for direction:
   - "Want to take this into `/explore` to fully shape it?"
   - "This is simple enough — want to just go straight to `/implement`?"
   - "Want to look at another opportunity instead?"

**STOP and wait for direction.**

---

## Stage 4: OUTPUT — Write the Brainstorm Doc

**Goal:** Capture the session in a document that can be referenced later.

**Actions:**
1. Save the brainstorm to `plans/brainstorm-YYYY-MM-DD-{topic}.md`
2. Use this format:

```
# Brainstorm: {Topic or "What to Build Next"}

**Created:** YYYY-MM-DD
**Status:** Complete

---

## Current State

### Already Automated
{List of existing systems and what they do}

### Still Manual
{List of manual tasks/processes identified}

### Data Available
{What data exists that could power new systems}

## Opportunities Identified

### 1. {Top Opportunity}
- **Impact:** High / Medium / Low
- **Feasibility:** Easy / Medium / Hard
- **What it would do:** {description}
- **Why it matters:** {reasoning}
- **Next step:** `/explore {idea}` or `/implement`

### 2. {Second Opportunity}
{...same format}

### 3. {Third Opportunity}
{...same format}

## Quick Wins
{Any easy, fast-to-build opportunities worth grabbing}

## Big Bets
{Harder but transformative opportunities for later}

## Decision
{What the user decided to pursue, and the recommended next command}

## Notes
{Key points from the conversation, preferences expressed}
```

3. Report the file path and the recommended next step:
   - If they picked something → "Run `/explore {idea}` to shape this into a buildable concept"
   - If they want to build directly → "Run `/implement` and describe what you want"
   - If they're still deciding → "Come back to this doc anytime — your opportunities are captured"

---

## Critical Rules

- **Workspace-first** — Always start by reading what exists. Don't brainstorm in a vacuum. The best ideas come from seeing what's already there and what's missing.
- **Non-technical language** — The user may not know what "cron job" or "API" means. Explain opportunities in terms of outcomes: "Every morning you'd wake up to a summary of X" not "a Python script triggered by launchd."
- **Interactive** — Present findings, wait for reactions. Don't dump a wall of analysis. The brainstorm should feel like a conversation.
- **Encouraging** — Get excited about the opportunities. "Oh, this is a good one" is better than a clinical assessment.
- **Honest about effort** — Don't make everything sound easy. If something is a big build, say so. But also show the simple version that gets them 80% of the value.
- **Action-oriented** — Every brainstorm should end with a clear next step. Never leave the user wondering "so now what?"
- **Scan for task audits** — Look for any file in the workspace that contains a task audit, task list, process inventory, or similar. These are gold for finding automation opportunities. Common locations: the workspace root, plans/, gtd/, or any docs/ folder.
