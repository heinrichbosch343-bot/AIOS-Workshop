"""
Anti-AI-slop writing rules for anything Heinrich's brain WRITES (emails, drafts).

Loads the vendored copy of the `writing-style` skill (prompts/writing_style.md) once
and exposes it as a prompt block. Keep prompts/writing_style.md in sync with the source
skill at .claude/skills/writing-style/SKILL.md.
"""
from functools import lru_cache
from pathlib import Path

_RULES_PATH = Path(__file__).resolve().parent.parent / "prompts" / "writing_style.md"


@lru_cache(maxsize=1)
def _rules() -> str:
    try:
        return _RULES_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def writing_style_block() -> str:
    """A system-prompt section enforcing human-sounding writing. Empty if rules missing."""
    rules = _rules()
    if not rules:
        return ""
    return (
        "\n\n=== WRITING RULES (only when composing prose for Heinrich to send or publish) ===\n"
        "These apply ONLY when you write something Heinrich will send or publish — an email body, a "
        "letter, outreach, a document, a report section. They make that prose sound like Heinrich, "
        "not an AI. They do NOT apply to how you talk to Heinrich in chat, and they are not a reason "
        "to turn a request into a piece of writing. If she just wants an answer, analysis, or a "
        "plan, give that.\n\n"
        f"{rules}\n"
        "=== END WRITING RULES ==="
    )
