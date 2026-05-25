# Explore

> Interactive exploration of a new feature, system, or capability for your workspace.

## Variables

idea: $ARGUMENTS (describe the feature, system, or capability you want to explore)

---

## Instructions

You are running an **interactive exploration session**. Your job is to help the user shape an idea into a clear, well-scoped concept through structured Q&A. Do NOT run through all stages autonomously — present your findings at each stage, ask questions, and wait for responses before proceeding.

**Tone:** Friendly and encouraging. The user may not be technical — explain concepts in plain English. Celebrate progress. If something is complex, break it down.

**Output:** A feature exploration doc saved to `plans/explore-YYYY-MM-DD-{descriptive-name}.md`

**Downstream:** The explore doc can be fed to `/create-plan` for implementation planning, or passed directly to `/implement` if it's clear enough to build.

---

## Stage 1: DISCOVERY — Understand the Vision

**Goal:** Understand what the user wants and establish scope boundaries.

**Actions:**
1. Read the idea/arguments provided
2. Read relevant workspace context:
   - `CLAUDE.md` for workspace structure and existing systems
   - Any context files referenced in CLAUDE.md that relate to this idea
   - Any existing scripts, commands, or tools that touch the same area
3. Summarize your understanding of the idea in 2-3 sentences
4. Ask 2-4 clarifying questions to establish:
   - What problem does this solve? (What's painful or slow right now?)
   - Who uses this and when? (You personally? Your team? Automatically?)
   - What does "done" look like? (What should happen when this works?)
   - What's explicitly out of scope? (What should this NOT do?)

**STOP and wait for responses before proceeding.**

---

## Stage 2: RESEARCH — Explore What's Possible

**Goal:** Understand what exists, what's possible, and what constraints apply.

**Actions:**
1. Search the workspace for relevant existing systems, commands, scripts, or patterns that relate to this idea
2. If the idea involves external tools or APIs:
   - Check if the workspace already has API keys configured (look at `.env` or `.env.example`)
   - Research what services could help (web search if needed)
   - Note what's free vs. paid
3. If the idea touches data, check the workspace database (if one exists) to understand what data is available
4. Present findings:
   - **What already exists** that's relevant (don't rebuild what's there)
   - **What options are available** (with pros/cons for each)
   - **What constraints or dependencies** you've found
   - **Rough complexity estimate:** Simple (afternoon project) / Medium (focused session) / Large (multi-session build)

**STOP and wait for input on which direction to take before proceeding.**

---

## Stage 3: SHAPE — Define the Feature

**Goal:** Converge on a clear feature definition.

**Actions:**
1. Based on discovery + research + user input, define:
   - **What it does** — clear description of the feature/system in plain English
   - **How it works** — user flow or interaction model (step by step: "You run this command, it does X, then Y, and you get Z")
   - **What it produces** — outputs, artifacts, or changes (files created, messages sent, data updated, etc.)
   - **How it connects** — relationship to existing workspace systems (does it read from your database? Update your context files? Send a Telegram message?)
2. If there are meaningful design choices, present 2-3 options with tradeoffs and a clear recommendation
3. Flag anything that feels risky, complex, or uncertain — be honest about hard problems

**STOP and wait for confirmation or adjustments before proceeding.**

---

## Stage 4: SCOPE — Break It Down

**Goal:** Turn the shaped concept into a scoped breakdown with a clear build path.

**Actions:**
1. Break the feature into logical components or phases
2. For each component, note:
   - What it involves (in plain terms)
   - Dependencies (does anything need to exist first?)
   - Rough effort: Small (a few files) / Medium (multiple files + config) / Large (significant build)
3. Recommend a phasing if the feature is large:
   - **Start here:** The minimum viable version — the smallest thing that's actually useful
   - **Then add:** Nice-to-have features that build on top
   - **Later:** Full vision — everything working together
4. Be clear about what's the core (must have) vs. extras (can wait)

**STOP and present the breakdown for review.**

---

## Stage 5: OUTPUT — Write the Exploration Doc

**Goal:** Capture everything in a structured document ready to hand off to `/create-plan` or `/implement`.

**Actions:**
1. Compile the exploration into a doc and save to `plans/explore-YYYY-MM-DD-{descriptive-name}.md`
2. Use this format:

```
# Explore: {Feature Name}

**Created:** YYYY-MM-DD
**Status:** Explored
**Origin:** {One-line description of the original idea}

---

## Vision

{2-3 sentences on what this is and why it matters}

## Problem Statement

{What problem does this solve? Who has this problem? What's the current pain?}

## Proposed Solution

### What It Does
{Clear description in plain English}

### How It Works
{Step-by-step user flow or interaction model}

### What It Produces
{Outputs, artifacts, changes — what the user gets}

## Scope

### Minimum Viable Version
{The smallest useful version — what to build first}

### Full Vision
{The complete version with all features}

### Components

| Component | Description | Effort | Dependencies |
|-----------|-------------|--------|--------------|
| {name}    | {what it does} | S / M / L | {what it needs} |

### Out of Scope
{What this explicitly does NOT include — yet}

## Technical Considerations

{APIs needed, credentials required, external services, database changes, scheduling, cost estimates}

## Connections

{How this relates to other workspace systems — what it reads from, writes to, or extends}

## Next Steps

{Recommended path: /create-plan or /implement, with the specific command to run}

## Discovery Notes

{Key decisions made during the exploration, alternatives considered, user preferences}
```

3. Report the file path and recommend next steps:
   - If the feature is well-defined and ready → suggest `/implement plans/explore-YYYY-MM-DD-{name}.md`
   - If it needs a detailed plan first → suggest `/create-plan` with a summary of what to build

---

## Critical Rules

- **Interactive** — Present findings, wait for responses. Never complete all stages autonomously. The best results come from the conversation.
- **Plain English** — Explain everything simply. No jargon. If you must use a technical term, explain it in parentheses.
- **Honest about complexity** — Flag hard problems clearly. Don't underestimate effort. It's better to say "this is a bigger build than it sounds" than to let someone start something they can't finish.
- **Workspace-aware** — Always ground recommendations in what already exists. Don't suggest building something that's already there. Don't ignore existing patterns.
- **Encouraging** — The user is building something real. Celebrate good ideas. Be enthusiastic about what's possible.
- **Not a plan** — The explore doc captures the "what" and "why." Detailed implementation steps belong in `/create-plan` or `/implement`. Keep this focused on shaping the idea.
- **Respect decisions** — Once the user has made a choice, move forward. Don't relitigate unless there's a strong reason.
