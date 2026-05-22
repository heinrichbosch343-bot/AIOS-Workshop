# Slash Command Toolkit — AIOS Module Installer

> A plug-and-play module from the AAA Accelerator.
> Grab this and 15+ more at [aaaaccelerator.com](https://aaaaccelerator.com)

<!-- MODULE METADATA
module: slash-commands
version: v1
status: RELEASED
released: 2026-02-27
requires: [context-os]
phase: 5
category: Toolkit
complexity: simple
api_keys: 0
setup_time: 5-10 minutes
-->

---

## FOR CLAUDE

You are helping a user install this AIOS Module. Follow these rules:

**Behavior:**
- Assume the user is non-technical unless they tell you otherwise
- Explain what you are doing at each step in plain English BEFORE doing it
- Celebrate small wins ("Commands installed — you've got two new superpowers!")
- If something fails, do not dump error logs — explain the problem simply and suggest the fix
- Never skip verification steps — if a check fails, stop and help the user fix it
- Use encouraging language throughout — they are building something real

**Pacing:**
- Do NOT rush. Pause after major milestones.
- After prerequisites: "Everything looks good. Ready to install the commands?"
- After installation: "Both commands are installed. Let me show you how to use them."
- After test: "It works! You now have two commands that help you figure out what to build and how to build it."

**Error handling:**
- If .claude/commands/ doesn't exist → create it (it's just a folder)
- If CLAUDE.md doesn't exist → warn that ContextOS should be installed first
- If a command file already exists → ask if they want to replace it or keep the existing one
- Never say "check the logs" — find the problem and explain it

---

## OVERVIEW

This module gives you two slash commands that help you figure out **what to build** and **how to build it** in your workspace.

**`/brainstorm`** — Scans your workspace, finds tasks and processes you're still doing manually, and brainstorms what systems you could build to automate them. Think of it as your "what should I work on next?" command. It looks at your task lists, your current setup, and helps you spot the best opportunities.

**`/explore [idea]`** — Takes an idea (from a brainstorm session or your own thinking) and walks you through shaping it into something concrete. What does it do? How should it work? What's the simplest version? By the end, you have a clear concept ready to hand off to `/implement`.

Together, they create a build cycle: brainstorm what to build → explore how to build it → implement it → repeat.

**Setup time:** 5-10 minutes
**API keys needed:** 0
**Running cost:** Free
**What you need:** ContextOS installed (your workspace needs a CLAUDE.md)

---

## SCOPING

**RECOMMENDED** (Install both commands with smart defaults)
- `/explore` — Interactive feature discovery and shaping
- `/brainstorm` — Workspace scan + opportunity finder
Estimated setup time: 5 minutes

**CUSTOM** (Choose which commands to install)
- Option 1: Install only `/explore` (if you already know what you want to build)
- Option 2: Install only `/brainstorm` (if you want help figuring out what to build)
- Option 3: Install both (recommended — they work together)

Ask: "Want to go with RECOMMENDED (both commands), or would you like to pick just one?"

If RECOMMENDED → install both.
If CUSTOM → install only the selected command(s).

---

## PREREQUISITES

Check each prerequisite before proceeding.

### Claude Code CLI
```bash
claude --version
```
If this shows a version number, you're good.
If not installed: `npm install -g @anthropic-ai/claude-code`

### CLAUDE.md exists
```bash
test -f CLAUDE.md && echo "CLAUDE.md found" || echo "CLAUDE.md not found"
```
If found → good, proceed.
If not found → tell the user: "You need ContextOS installed first — that creates your CLAUDE.md, which these commands need to understand your workspace. Install ContextOS from the module library, then come back to this."

### .claude/commands/ folder exists
```bash
test -d .claude/commands && echo "Commands folder exists" || echo "Commands folder not found"
```
If found → good, proceed.
If not found → create it:
```bash
mkdir -p .claude/commands
```

[VERIFY] All three checks should pass. If CLAUDE.md is missing, stop here — ContextOS must be installed first.

Ask: "Everything checks out. Ready to install the commands?"

---

## INSTALL

### Step 1: Install the /explore command

Read the file `commands/explore.md` from this module folder, then write its complete contents to `.claude/commands/explore.md` in the user's workspace.

Explain to the user: "I'm installing `/explore` — this is the command you'll use when you have an idea and want to shape it into something buildable."

[VERIFY]
```bash
test -f .claude/commands/explore.md && echo "/explore installed" || echo "Installation failed"
```

### Step 2: Install the /brainstorm command

Read the file `commands/brainstorm.md` from this module folder, then write its complete contents to `.claude/commands/brainstorm.md` in the user's workspace.

Explain to the user: "I'm installing `/brainstorm` — this scans your workspace and helps you figure out what to build next."

[VERIFY]
```bash
test -f .claude/commands/brainstorm.md && echo "/brainstorm installed" || echo "Installation failed"
```

### Step 3: Update CLAUDE.md with command documentation

Add documentation for the new commands to the user's CLAUDE.md. Find the section where other commands are documented (look for `/prime`, `/commit`, `/implement`, or a "Commands" heading) and add:

```markdown
### /explore [idea]
Interactive feature discovery. Takes an idea and walks you through shaping it into a clear, scoped concept through 5 stages: Discovery (understand the vision) → Research (explore what's possible) → Shape (define the feature) → Scope (break it down) → Output (write the exploration doc). Produces a feature doc in `plans/` ready for `/implement`.

### /brainstorm [topic]
Workspace scanner and opportunity finder. Scans your tasks, processes, and current setup to find manual work that could be automated. Ranks opportunities by impact and feasibility, deep-dives the top picks, and points you to `/explore` or `/implement` for the next step. Run without arguments to scan everything, or with a topic to focus on a specific area.
```

[VERIFY] Read CLAUDE.md and confirm both commands are documented.

Ask: "Both commands are installed and documented. Let me show you how they work."

---

## TEST

### Quick test — /explore

Tell the user to start a new Claude Code session in their workspace, then run:
```
/explore a simple daily summary of what I accomplished today
```

Expected behavior:
- Claude reads their CLAUDE.md and workspace context
- Claude summarizes the idea in 2-3 sentences
- Claude asks 2-4 clarifying questions
- Claude STOPS and waits for the user's response

If this happens: "It works! `/explore` is walking you through shaping your idea step by step. You can keep going or cancel — either way, the command works."

If Claude doesn't stop and wait: "The command loaded but Claude ran ahead. That's fine — sometimes Claude gets excited. Next time, it should pause at each stage."

### Quick test — /brainstorm

Tell the user to run:
```
/brainstorm
```

Expected behavior:
- Claude reads the workspace and looks for tasks, processes, and existing systems
- Claude presents a summary of what's automated vs. what's still manual
- Claude STOPS and asks for the user's reaction

If this happens: "It works! `/brainstorm` is scanning your workspace and finding opportunities."

---

## WHAT'S NEXT

Now that you have `/explore` and `/brainstorm`, here's the workflow:

1. **Start with `/brainstorm`** — Run it to see what opportunities exist in your workspace. It'll scan your tasks and find the best things to automate.

2. **Pick an idea and `/explore` it** — Take your favorite opportunity from the brainstorm and run `/explore [idea]` to shape it into a clear concept.

3. **Build it with `/implement`** — Once `/explore` produces a feature doc, run `/implement` to actually build it.

4. **Repeat** — Your workspace gets more powerful with every cycle. Run `/brainstorm` again after building something — it'll find the next opportunity.

**The cycle:** `/brainstorm` (what to build?) → `/explore` (how to build it?) → `/implement` (build it!) → repeat

**Pro tip:** Keep a task audit file somewhere in your workspace — a list of everything you do regularly and whether it's automated or manual. `/brainstorm` will find it and use it to give better suggestions.

---

> A plug-and-play module from Liam Ottley's AAA Accelerator — the #1 AI business launch
> & AIOS program. Grab this and 15+ more at [aaaaccelerator.com](https://aaaaccelerator.com)
