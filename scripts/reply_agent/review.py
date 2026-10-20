"""What a person looks at: drafts waiting for a decision, mail the agent could not settle, and anything that may have gone wrong.

Everything that came from outside is washed of terminal control characters before it is printed, so a hostile sender
cannot repaint the screen to hide what a draft says or what the checks found.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .config import Config
from .store import Store
from .textnorm import one_line, strip_controls

MODEL_SEES = 3000  # characters of a message the model reads, and so what a reviewer must be able to read too
RECENT_SUPPRESSIONS_DAYS = 7
RECENT_SUPPRESSIONS_SHOWN = 50

_DRAFT_LABELS = (
    ("pending", "PENDING, needs your approval"),
    ("held", "HELD, a person answers this one"),
    ("failed", "FAILED to send (it did not go out), retry it if it is safe to"),
)
_ATTENTION_HELP = {
    "complaint": "legal or complaint wording",
    "other": "needs a person to decide what this is",
    "unknown_reply": "someone we have no lead for replied to something",
    "unverified": "someone at a lead's company wrote, but the sender could not be verified",
    "suppressed_wrote": "someone on the do-not-write list wrote again",
    "bounced_reply": "a reply we sent did not arrive",
    "flood": "far more strangers wrote today than can be listed",
    "stuck": "could not be handled automatically",
    "unreadable": "could not be read automatically",
    "too_large": "too large to read automatically",
    "limit": "a lead hit today's limit for messages read by the model",
}


def _clean(value) -> str:
    return strip_controls(str(value or ""))


def _line(value) -> str:
    """For a field printed on one line: no line breaks, so its text can never start a fake entry of its own."""
    return one_line(str(value or ""))


def _indent(text: str, pad: str = "    ") -> str:
    return "\n".join(pad + line for line in _clean(text).splitlines()) or pad


def _who(row) -> str:
    name, addr = _line(row["from_name"]), _line(row["from_addr"])
    who = f"{name} <{addr}>" if name else addr
    return f"{who}, {'sender verified' if row['verified'] else 'NOT VERIFIED (the From line could be forged)'}"


def _their_words(text: str) -> str:
    body = _clean(text)
    shown = body[:MODEL_SEES]
    cut = "\n[... cut here: the model reads only the first 3000 characters]" if len(body) > MODEL_SEES else ""
    return _indent(shown) + cut


def _draft_block(row, label: str) -> str:
    lines = [f"[{row['id']}] {label} | {row['category']} | {_who(row)}",
             f"  subject: {_line(row['subject'])}",
             f"  answering from: {_line(row['mailbox']) or '(not one of our mailboxes)'}",
             "  they wrote:", _their_words(row["their_body"]),
             "  draft:", _indent(row["body"]) if row["body"] else "    (none, a person answers this one)"]
    if row["problems"]:
        lines.append(f"  checks: {_line(row['problems'])}")
    if row["note"]:
        lines.append(f"  note: {_line(row['note'])}")
    return "\n".join(lines) + "\n"


def _attention_block(row) -> str:
    kind = row["kind"]
    head = f"({row['id']}) ATTENTION | {kind}: {_ATTENTION_HELP.get(kind, kind)}"
    if row["from_addr"] is None:  # a mail the agent could not even save
        return f"{head}\n  {_line(row['message_id'])}\n  {_line(row['note'])}\n  clear it with: python -m reply_agent resolve {row['id']}\n"
    lines = [head + f" | {_who(row)}", f"  subject: {_line(row['subject'])}",
             f"  wrote to: {_line(row['mailbox']) or '(not one of our mailboxes)'}"]
    if row["note"]:
        lines.append(f"  why: {_line(row['note'])}")
    if row["body"]:
        lines += ["  they wrote:", _their_words(row["body"])]
    lines.append(f"  clear it with: python -m reply_agent resolve {row['id']}")
    return "\n".join(lines) + "\n"


def _doubtful_label(row) -> str:
    return (f"NEEDS A LOOK: this was going out when the connection broke, so it may or may not have been delivered. Find out "
            f"(ask them, or check their side), then run: python -m reply_agent settle {row['id']} --sent   (it arrived)   "
            f"or   python -m reply_agent settle {row['id']} --not-sent   (it did not)")


def _recent_suppressions(store: Store, now: datetime) -> str:
    since = (now - timedelta(days=RECENT_SUPPRESSIONS_DAYS)).astimezone(timezone.utc).isoformat(timespec="seconds")
    rows = [r for r in store.suppression_rows() if (r["at"] or "") >= since]
    if not rows:
        return ""
    lines = [f"ADDED TO THE DO-NOT-WRITE LIST in the last {RECENT_SUPPRESSIONS_DAYS} days (also add them to PlusVibe's block list). "
             "If one is wrong: python -m reply_agent unsuppress ADDRESS"]
    shown = rows[-RECENT_SUPPRESSIONS_SHOWN:]
    lines += [f"  {_line(r['addr'])} | {_line(r['reason'])} | {_line((r['at'] or '')[:10])}" for r in shown]
    if len(rows) > len(shown):
        lines.append(f"  ... and {len(rows) - len(shown)} more, older than these. `python -m reply_agent suppressed` lists them all")
    return "\n".join(lines) + "\n"


def review_text(store: Store, cfg: Config, now: datetime | None = None) -> str:
    blocks: list[str] = []
    for status, label in _DRAFT_LABELS:
        blocks += [_draft_block(row, label) for row in store.drafts(status)]
    blocks += [_draft_block(row, _doubtful_label(row)) for row in store.drafts("sending")]
    blocks += [_attention_block(row) for row in store.open_attention()]
    waiting = store.waiting_retries()
    if waiting:
        blocks.append(f"WAITING for the model or a retry: {len(waiting)} message(s), the oldest since {waiting[0]['first_at']}. "
                      f"Last problem: {_line(waiting[0]['last_error'])}\n")
    approved = len(store.drafts("approved"))
    if approved:
        blocks.append(f"{approved} approved draft(s) are lined up and go out on the next live pass.\n")
    recent = _recent_suppressions(store, now or datetime.now(timezone.utc))
    if recent:
        blocks.append(recent)
    return "\n".join(blocks) if blocks else "Nothing waiting."
