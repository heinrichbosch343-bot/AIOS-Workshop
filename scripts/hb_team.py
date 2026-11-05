"""The Harties Board team board: who is working on what, and one ship lock so deploys happen in sequence.

Several Claude sessions work on Harties Board at once, each in its own folder and branch. They cannot see each
other's work, so this file is where they meet. It holds nothing secret and lives in outputs/community-app/team/
(gitignored, on this machine). Read TEAM.md there to see the whole picture.

  python scripts/hb_team.py status
  python scripts/hb_team.py join --as NAME --branch B --folder F --task "what I am doing" [--touches lib/board.ts,lib/areas.ts]
  python scripts/hb_team.py note --as NAME "what I shipped or changed, and what the others must do about it"
  python scripts/hb_team.py lock --as NAME [--branch B]       # before shipping; fails if someone else holds it
  python scripts/hb_team.py unlock --as NAME                  # after the deploy answered 200, or if you gave up
  python scripts/hb_team.py unlock --as NAME --force          # take over a lock someone left behind (only when it is stale)

NAME is the session's own name from ListAgents (for example aios-starter-kit-33). The deploy script refuses to run
unless its --as NAME holds a fresh ship lock, which is what puts the deploys in a line.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEAM_DIR = Path(os.environ.get("HB_TEAM_DIR") or ROOT / "outputs" / "community-app" / "team")
STATE = TEAM_DIR / "team.json"
LOCK = TEAM_DIR / "ship.lock"
BOARD = TEAM_DIR / "TEAM.md"
STALE_AFTER = timedelta(minutes=60)
LOG_KEEP = 60

RULES = """\
## How we work together

1. **One folder and one branch each.** Never write into another session's folder or branch, and never copy data over
   its `data/seed.local.json` or `public/media`. To get something from another session, message it (SendMessage to its
   name from ListAgents) and let it do it.
2. **Sign in** with `hb_team.py join` when you start, and `note` when you finish a piece of work. Read the notes before
   you start something that touches shared files.
3. **Ships go one at a time.** Before `npm run ship`, take the lock (`hb_team.py lock --as NAME`). Then: merge
   `origin/live` into your branch, run the checks, `npm run ship -- --branch=YOURS`, `git fetch origin live:live`,
   `python scripts/hartisboard_deploy.py --as NAME`, and only when the live site answers, `hb_team.py unlock --as NAME`.
   If anything fails, unlock too. A lock older than 60 minutes counts as left behind.
4. **Heinrich's go is still needed for every deploy.** The lock puts the deploys in a line, it does not replace his word.
5. **After a ship, write a note** saying what changed and what others must do (for example "rerun harties_geo.py on your seed").
6. **Shared files** (the seed, `lib/board.ts`, `lib/areas.ts`, `lib/types.ts`, `app/globals.css`, `app/components.css`):
   say in your `join` or a note when you are changing one, so the next session merges instead of overwriting.
7. **The seed pipeline order** is `harties_refresh.py` (directory, numbers, events, pictures, dedupe) and then
   `harties_geo.py`. Whoever changes the seed reruns the last step too.
8. **Messages:** the first line says what it is about. Do not ask a peer to do something that was denied to you.
"""


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def stamp(t: datetime | None = None) -> str:
    return (t or now()).isoformat(sep=" ")


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sessions": {}, "log": []}


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def save_state(state: dict) -> None:
    state["log"] = state.get("log", [])[-LOG_KEEP:]
    write_atomic(STATE, json.dumps(state, indent=1, ensure_ascii=False) + "\n")
    render(state)


def read_lock() -> dict | None:
    try:
        return json.loads(LOCK.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def lock_is_fresh(lock: dict | None) -> bool:
    if not lock:
        return False
    try:
        return now() - datetime.fromisoformat(lock["since"]) < STALE_AFTER
    except (KeyError, ValueError):
        return False


def may_ship(who: str | None) -> tuple[bool, str]:
    """Used by hartisboard_deploy.py: may this session deploy right now?"""
    lock = read_lock()
    if not who:
        return False, "Say who is deploying: --as <your session name>. Take the ship lock first: python scripts/hb_team.py lock --as <your session name>"
    if not lock_is_fresh(lock):
        return False, f"{who} does not hold the ship lock. Take it first: python scripts/hb_team.py lock --as {who} (one deploy at a time; see outputs/community-app/team/TEAM.md)"
    if lock["owner"] != who:
        return False, f"{lock['owner']} holds the ship lock (since {lock['since']}, branch {lock.get('branch', '?')}). Wait for them to finish, or message them."
    return True, "ok"


def render(state: dict) -> None:
    lock = read_lock()
    lines = ["# Harties Board team board", "", f"Updated {stamp()}. Written by `scripts/hb_team.py`; do not edit by hand.", ""]
    if lock_is_fresh(lock):
        lines.append(f"**Ship lock: held by {lock['owner']}** since {lock['since']} (branch {lock.get('branch', '?')}). Wait for it to be released before you ship.")
    elif lock:
        lines.append(f"**Ship lock: left behind by {lock['owner']}** at {lock['since']} (more than 60 minutes ago). Take it over with `unlock --as YOU --force` if they are gone.")
    else:
        lines.append("**Ship lock: free.**")
    lines += ["", "## Sessions", "", "| Session | Branch | Folder | Working on | Touches | Last seen |", "|---|---|---|---|---|---|"]
    for name, s in sorted(state.get("sessions", {}).items()):
        lines.append(f"| {name} | {s.get('branch', '')} | {s.get('folder', '')} | {s.get('task', '')} | {s.get('touches', '')} | {s.get('updated', '')} |")
    lines += ["", "## Notes, newest first", ""]
    for entry in reversed(state.get("log", [])):
        lines.append(f"- {entry['at']} **{entry['who']}**: {entry['text']}")
    lines += ["", RULES]
    write_atomic(BOARD, "\n".join(lines) + "\n")


def cmd_join(a: argparse.Namespace) -> int:
    state = read_state()
    s = state["sessions"].setdefault(a.who, {})
    for key, value in (("branch", a.branch), ("folder", a.folder), ("task", a.task), ("touches", a.touches)):
        if value is not None:
            s[key] = value
    s["updated"] = stamp()
    save_state(state)
    print(f"{a.who} is on the board. Read {BOARD} (the rules are at the bottom).")
    return 0


def cmd_note(a: argparse.Namespace) -> int:
    state = read_state()
    state.setdefault("log", []).append({"at": stamp(), "who": a.who, "text": a.text})
    if a.who in state["sessions"]:
        state["sessions"][a.who]["updated"] = stamp()
    save_state(state)
    print("noted")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    state = read_state()
    render(state)
    print(BOARD.read_text(encoding="utf-8"))
    return 0


def cmd_lock(a: argparse.Namespace) -> int:
    TEAM_DIR.mkdir(parents=True, exist_ok=True)
    existing = read_lock()
    if existing and lock_is_fresh(existing) and existing["owner"] != a.who:
        print(f"Not taken: {existing['owner']} holds the ship lock since {existing['since']} (branch {existing.get('branch', '?')}). Wait, or message them.")
        return 1
    if existing and not lock_is_fresh(existing) and existing["owner"] != a.who:
        print(f"Taking over a lock {existing['owner']} left behind at {existing['since']}.")
    body = json.dumps({"owner": a.who, "branch": a.branch or "", "since": stamp()})
    write_atomic(LOCK, body)
    state = read_state()
    state.setdefault("log", []).append({"at": stamp(), "who": a.who, "text": f"took the ship lock{f' for {a.branch}' if a.branch else ''}"})
    save_state(state)
    print(f"{a.who} holds the ship lock. Merge origin/live into your branch, check, ship, deploy with --as {a.who}, then unlock.")
    return 0


def cmd_unlock(a: argparse.Namespace) -> int:
    existing = read_lock()
    if not existing:
        print("The ship lock was already free.")
        return 0
    if existing["owner"] != a.who and not (a.force and not lock_is_fresh(existing)):
        print(f"Not released: it is {existing['owner']}'s" + (" and it is not old enough to take over." if a.force else ". (--force only works on a lock older than 60 minutes.)"))
        return 1
    LOCK.unlink(missing_ok=True)
    state = read_state()
    state.setdefault("log", []).append({"at": stamp(), "who": a.who, "text": "released the ship lock" + ("" if existing["owner"] == a.who else f" (left behind by {existing['owner']})")})
    save_state(state)
    print("The ship lock is free.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("join", "note", "lock", "unlock"):
        p = sub.add_parser(name)
        p.add_argument("--as", dest="who", required=True)
        if name == "join":
            p.add_argument("--branch")
            p.add_argument("--folder")
            p.add_argument("--task")
            p.add_argument("--touches")
        if name == "note":
            p.add_argument("text")
        if name == "lock":
            p.add_argument("--branch")
        if name == "unlock":
            p.add_argument("--force", action="store_true")
    sub.add_parser("status")
    args = ap.parse_args(argv)
    return {"join": cmd_join, "note": cmd_note, "status": cmd_status, "lock": cmd_lock, "unlock": cmd_unlock}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
