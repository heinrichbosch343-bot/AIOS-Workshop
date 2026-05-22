# GTD Methodology — Reference Guide

> Distilled from *Getting Things Done* by David Allen, adapted for your AI-assisted workspace.
> Referenced by /process, /review, and all GTD commands.

---

## Core Philosophy

GTD is built on one fundamental insight: **your mind is for having ideas, not holding them.** The human brain is a terrible office — it reminds you of things at the wrong time, creates anxiety by cycling through open loops, and wastes cognitive resources on unresolved commitments. GTD provides a trusted external system that frees your mind to focus on the work at hand.

### "Mind Like Water"

In karate, "mind like water" describes the state of perfect readiness. Imagine throwing a pebble into a still pond — the water responds totally appropriately to the force and mass of the input, then returns to calm. It does not overreact or underreact.

GTD's promise is to restore this state: **relaxed control** where you can dedicate 100% of your attention to whatever you choose, with confidence that nothing is falling through the cracks.

---

## The Five Steps of GTD

### 1. Capture (Collect)

Get everything out of your head and into a trusted collection tool. Every open loop — anything incomplete, anything pulling at your attention — must be captured into a collection bucket outside your mind.

### 2. Clarify (Process)

Decide what each item means and what to do about it. Apply the Processing Decision Tree (see below).

### 3. Organize

Put the results of your processing into the right buckets:
- **Projects list** — outcomes requiring 2+ actions
- **Next Actions lists** — organized by context
- **Waiting For list** — delegated items and expectations
- **Calendar** — date/time-specific actions only
- **Someday/Maybe list** — things you might want to do but not now
- **Reference filing** — information with no action required
- **Trash** — anything with no future value

### 4. Reflect (Review)

Look at your system regularly to maintain trust.
- **Daily:** Check calendar, scan Next Actions
- **Weekly:** Full Weekly Review (GET CLEAR → GET CURRENT → GET CREATIVE)

### 5. Engage (Do)

Choose your actions with confidence using four criteria: Context, Time available, Energy available, Priority.

---

## The Processing Decision Tree

```
"STUFF" from inbox
   |
"Is it actionable?"
   |
   NO --> Trash / Someday-Maybe / Reference
   |
   YES --> "What is the desired outcome?"
           If 2+ steps --> Add to PROJECTS list
           |
           "What is the NEXT physical action?"
           |
           Takes <2 minutes? --> DO IT NOW
           |
           Someone else? --> Delegate --> WAITING FOR list
           |
           Me, >2 min, specific date? --> CALENDAR
           Me, >2 min, ASAP? --> NEXT ACTIONS list (by context)
```

**Critical processing rules:**
- Process items one at a time, starting from the top
- Never put anything back into "in" — once you pick it up, decide about it
- The next action must be a physical, visible activity (not "think about it")

---

## Key Concepts

### Projects
Any desired result requiring more than one action step. You cannot "do" a project — you can only do actions related to it. Every active project must have at least one next action defined. If it doesn't, it's stuck.

### Next Actions
The very next physical, visible activity needed to move something forward.

**Bad (vague):** "Handle insurance"
**Good (concrete):** "Call Allstate at 555-0123 for auto insurance quote"

**Context tags:**
- **@me** — decisions, approvals, creative work only you can do
- **@claude** — work to do in Claude Code sessions
- **@calls** — phone/video calls to make
- **@team** — items requiring team coordination (specify who)
- **@errands** — physical, in-person tasks
- **@think** — creative thinking, brainstorming, reflection
- **@record** — things to capture, document, write up

### Waiting For
Everything you've delegated or are expecting from others. Each item should be dated. Review weekly and follow up as needed.

### Someday/Maybe
The parking lot for things you might want to do someday but aren't committed to now. Review weekly — items may become active projects when circumstances change.

### Calendar
Sacred territory. Only three things go on it:
1. Time-specific actions (appointments, meetings)
2. Day-specific actions (must be done on a specific day)
3. Day-specific information (context for a meeting, reminders)

Nothing else. No daily to-do lists. No "hope-to-do" items.

---

## The Weekly Review

The single most important GTD habit. Without it, lists go stale and your mind takes back the job of remembering.

**Phase 1: GET CLEAR** — Empty all inboxes, capture everything floating in your head
**Phase 2: GET CURRENT** — Review all lists, ensure every project has a next action
**Phase 3: GET CREATIVE** — Scan Someday/Maybe, scan Areas, open brainstorm

Run with `/review`. Target 30-60 minutes, Fridays recommended.

---

## 10 Core Principles

1. Your mind is for having ideas, not holding them
2. Capture everything — don't rely on memory
3. Define "done" and "doing" for every commitment
4. The next action must be a physical, visible activity
5. A project is any outcome requiring more than one action step
6. Every project needs at least one next action (the stuck project test)
7. Review weekly to maintain trust in the system
8. Context determines what you can do now
9. Two-minute rule: if it takes <2 min, do it immediately
10. "Someday/Maybe" is not a graveyard — review it weekly

---

## Common Mistakes

- **Confusing projects with actions:** "Set up new accounting system" is a project. "Research accounting software options" is an action.
- **Using the calendar as a to-do list:** Dilutes its trustworthiness.
- **Not capturing everything:** If 20% of open loops are still in your head, the system fails.
- **Skipping the Weekly Review:** The #1 reason GTD systems collapse.
- **Vague next actions:** "Call bank" → "Call Wells Fargo (555-0199) to dispute $47 charge"

---

## Your Workspace File Map

| GTD Concept | File | Notes |
|-------------|------|-------|
| Inbox | `gtd/inbox.md` | Capture everything, process to zero via `/process` |
| Projects | `gtd/projects.md` | Master project index by area |
| Next Actions | `gtd/next-actions.md` | Organized by context (@me, @claude, @calls, @team, @errands, @think, @record) |
| Waiting For | `gtd/waiting-for.md` | Who, what, project, date requested |
| Someday/Maybe | `gtd/someday-maybe.md` | Back-burner ideas by category |
| Areas | `gtd/areas.md` | Professional + personal with health notes |
| Dashboard | `gtd/dashboard.md` | Operational hub — counts, flagged, recent completions |
| Review Protocol | `gtd/review-checklist.md` | Decision tree, trigger lists, review phases |
| Process Command | `.claude/commands/process.md` | `/process` — process inbox to zero |
| Review Command | `.claude/commands/review.md` | `/review` — guided weekly review |
| Methodology | `reference/gtd-methodology.md` | This file |
