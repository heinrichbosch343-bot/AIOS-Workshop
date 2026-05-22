#!/usr/bin/env python3
"""GTD inbox writer — append items to gtd/inbox.md with file locking.

Safely adds items to the GTD inbox from any source (scripts, pipelines,
cron jobs). Uses platform-appropriate file locking.

Usage:
    # As a module
    from scripts.inbox_writer import capture_to_inbox
    capture_to_inbox("Call Sarah about the proposal", source="manual")

    # From command line
    python scripts/inbox_writer.py "Call Sarah about the proposal"
"""

import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_WORKSPACE_ROOT = _SCRIPT_DIR.parent
if not (_WORKSPACE_ROOT / "gtd").is_dir():
    _WORKSPACE_ROOT = _WORKSPACE_ROOT.parent

INBOX_PATH = _WORKSPACE_ROOT / "gtd" / "inbox.md"
EMPTY_MARKER = "_(Empty — inbox is at zero)_"


def _timestamp() -> str:
    """Current timestamp in inbox format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _lock_file(f):
    """Apply an exclusive file lock (cross-platform)."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_EX)


def _unlock_file(f):
    """Release file lock (cross-platform)."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(f, fcntl.LOCK_UN)


def capture_to_inbox(item: str, source: str = "manual") -> str:
    """
    Append a single item to gtd/inbox.md with file locking.

    Args:
        item: The text to capture
        source: Source identifier (manual, telegram, claude, voice, meeting)

    Returns:
        The formatted line that was written
    """
    if not INBOX_PATH.exists():
        raise FileNotFoundError(
            f"Inbox not found at {INBOX_PATH} — make sure the GTD module is installed"
        )

    timestamp = _timestamp()
    line = f"- [{timestamp}] (source:{source}) {item}"

    with open(INBOX_PATH, "r+", encoding="utf-8") as f:
        try:
            _lock_file(f)
            content = f.read()

            if EMPTY_MARKER in content:
                content = content.replace(EMPTY_MARKER, "").rstrip()

            if content and not content.endswith("\n"):
                content += "\n"

            content += line + "\n"

            f.seek(0)
            f.truncate()
            f.write(content)
        finally:
            _unlock_file(f)

    return line


def capture_batch(items: list, source: str = "manual") -> int:
    """Append multiple items to inbox."""
    for item in items:
        capture_to_inbox(item, source=source)
    return len(items)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        result = capture_to_inbox(text, source="cli")
        print(f"Captured: {result}")
    else:
        print("Usage: python scripts/inbox_writer.py \"Your item here\"")
