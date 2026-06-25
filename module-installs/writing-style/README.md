# Writing Style — AIOS Module

**Stops Claude from writing like an AI. Bans 40+ dead words, enforces 12 rules, self-checks every output.**

---

## What This Is

A Claude Code skill that enforces human-sounding writing across every piece of text Claude produces — emails, reports, marketing copy, strategy docs, newsletters, content scripts, anything.

Claude has deeply ingrained AI writing patterns: em dashes, words like "leverage" and "delve", binary contrast formulas, uniform paragraph blocks, filler transitions. This skill eliminates all of them with a concrete ruleset and a self-check protocol Claude runs before every prose output.

## What It Does

- Bans 40+ specific words that appear 50-150x more in AI writing than human writing
- Enforces 12 core rules (no em dashes, vary sentence length, start with content, no binary contrasts, etc.)
- Eliminates structural patterns that mark AI output — dramatic fragmentation, rule of three, compulsive summaries
- Adds 8 Claude-specific tells to watch for (epistemic hedging, copula avoidance, over-qualification, etc.)
- Runs a self-check protocol before every text output without needing to ask

## What's In The Box

```
writing-style/
├── INSTALL.md     # Give this to Claude Code to set up
├── README.md      # This file
```

Everything is embedded inline in INSTALL.md — no extra files, no API keys, no dependencies.

## Setup

**Hand the folder to Claude Code and say:**

> "Read INSTALL.md and help me set this up step by step."

Takes 2 minutes. No API keys. No scripts.

**Requirements:** Claude Code CLI only.

---

> Part of the AAA Accelerator AIOS Module Library.
> [aaaaccelerator.com](https://aaaaccelerator.com)
