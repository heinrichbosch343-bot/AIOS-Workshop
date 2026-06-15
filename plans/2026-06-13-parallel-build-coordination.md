# Parallel Build Coordination — BoschAI Backend

**Created:** 2026-06-13
**Purpose:** Run two Claude terminals in parallel to build the LinkedIn engine and the follow-up bot **without the two stepping on each other.** Companion to [2026-06-13-boschai-system-build.md](./2026-06-13-boschai-system-build.md).

---

## The sequence

```
PHASE 1 — Foundation (SOLO, must finish first)
  Fork connie-backend -> apps/boschai-backend, rebrand, boot, COMMIT to main.
  Everything below branches off this commit. Cannot be parallelized.
        |
        v
PHASE 2 — Two worktrees off the foundation commit (PARALLEL)
  Terminal A: branch `linkedin`     Terminal B: branch `followups`
        |
        v
PHASE 3 — Merge both branches back to main (architect chat coordinates)
```

The foundation is a genuine bottleneck — both lanes need the forked backend to exist. The two terminals go truly parallel only in Phase 2. While Phase 1 runs, the best parallel use of Heinrich's time is: populate `.env` (Supabase URL+key, BoschAI Telegram token + chat ID, Gmail) and send 5–10 past LinkedIn posts for the voice profile.

---

## Worktree setup (run after the foundation is committed to main)

Worktrees live as sibling folders **outside** the repo so the two terminals are physically separate working directories:

```bash
# from the repo root: c:\Users\gamin\BoschAI\BoschAI\aios-starter-kit
git worktree add ../boschai-linkedin  -b linkedin
git worktree add ../boschai-followups -b followups
git worktree list   # confirm both exist
```

- Terminal A opens Claude Code in `c:\Users\gamin\BoschAI\BoschAI\boschai-linkedin`
- Terminal B opens Claude Code in `c:\Users\gamin\BoschAI\BoschAI\boschai-followups`

They cannot overwrite each other — different folders, different branches. Merge later with:

```bash
# back in the main repo
git merge linkedin
git merge followups
git worktree remove ../boschai-linkedin
git worktree remove ../boschai-followups
```

---

## File ownership (the no-interference contract)

### Lane A — LinkedIn (branch `linkedin`)
Owns, exclusively:
- `apps/boschai-backend/services/linkedin.py` (new — all LinkedIn logic + tool defs live here)
- `apps/boschai-backend/prompts/linkedin_voice.md` (new)
- `apps/boschai-backend/db/migrations/004_linkedin.sql` (new, optional)
- `context/linkedin/content-pillars.md`, `idea-backlog.md`, `accounts-to-engage.md`, `cadence.md` (new)

### Lane B — Follow-ups (branch `followups`)
Owns, exclusively:
- `apps/boschai-backend/services/followup.py` (new — all follow-up logic lives here)
- `apps/boschai-backend/db/migrations/003_followups.sql` (new)
- `context/email/followup-rules.md` (new)

### Shared files (BOTH lanes add to these — the only collision surface)
- `apps/boschai-backend/services/agent.py` — register tools
- `apps/boschai-backend/bot/command_os.py` — register Telegram commands
- `apps/boschai-backend/config.py` — env vars / settings
- `apps/boschai-backend/services/scheduler.py` — scheduled jobs

**Contract to keep merges trivial:**
1. Keep all real logic in your OWN module (`linkedin.py` / `followup.py`). In the shared files, add only a one-line import + a registration entry.
2. Append your entries at the **end** of the relevant list/section, never in the middle.
3. Wrap your additions in a marked block so the diff is unambiguous:
   ```python
   # === BoschAI: LinkedIn (lane A) — BEGIN ===
   ...
   # === BoschAI: LinkedIn (lane A) — END ===
   ```
   (Lane B uses `Follow-ups (lane B)`.)
4. Because every edit is purely additive and at the tail, a git merge is either clean or a two-line "keep both" conflict. Never delete or reorder the other lane's block.

---

## Terminal A — ready-to-paste prompt (LinkedIn engine)

> You are building the **LinkedIn growth engine** in this worktree (branch `linkedin`). Read `plans/2026-06-13-boschai-system-build.md` Step 4 and `plans/2026-06-13-parallel-build-coordination.md` first. Build ONLY the files Lane A owns; in the four shared files (`services/agent.py`, `bot/command_os.py`, `config.py`, `services/scheduler.py`) add only registration entries inside a `# === BoschAI: LinkedIn (lane A) ===` marked block appended at the end. Keep all logic in `services/linkedin.py`. Deliverables: `draft_post`, `draft_reply`, `draft_comment`, `suggest_ideas` functions loading `prompts/linkedin_voice.md` + the installed writing-style rules; agent tools `draft_linkedin_post`, `draft_linkedin_reply`, `suggest_linkedin_ideas`; Telegram commands `/post`, `/reply`, `/ideas`; and the `context/linkedin/*` content-ops files. Do not touch `followup.py`, `003_followups.sql`, or `context/email/*` — that's Lane B. Commit on the `linkedin` branch only.

## Terminal B — ready-to-paste prompt (Follow-up bot)

> You are building the **email auto-follow-up engine** in this worktree (branch `followups`). Read `plans/2026-06-13-boschai-system-build.md` Step 5 and `plans/2026-06-13-parallel-build-coordination.md` first. Build ONLY the files Lane B owns; in the four shared files add only registration entries inside a `# === BoschAI: Follow-ups (lane B) ===` marked block appended at the end. Keep all logic in `services/followup.py`. Deliverables: a `followups` table migration (`003_followups.sql`); `services/followup.py` that scans sent-no-reply threads past a delay, drafts via existing email/autodraft logic, then gates on allowlist + daily cap + kill switch + warmup(draft-only); env vars `FOLLOWUP_ENABLED/ALLOWLIST/DELAY_DAYS/DAILY_CAP/KILL_SWITCH/WARMUP`; a scheduler job; Telegram `/followups` and `/killswitch`; and `context/email/followup-rules.md`. Default to warmup (draft-only). Do not touch `linkedin.py`, `004_linkedin.sql`, or `context/linkedin/*` — that's Lane A. Commit on the `followups` branch only.

---

## Status

- [x] Phase 1 — backend copied to `apps/boschai-backend` (54 files, caches stripped)
- [ ] Phase 1 — rebrand Connie/Osun -> Heinrich/BoschAI (agent running)
- [ ] Phase 1 — `.env` populated + boot `/health` ok
- [ ] Phase 1 — commit foundation to main
- [ ] Phase 2 — worktrees created, two terminals building
- [ ] Phase 3 — merge both lanes
