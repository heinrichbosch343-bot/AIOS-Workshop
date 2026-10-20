"""Settings. Defaults live here, Heinrich's edits live in outputs/outreach/reply-agent.json.

Every value read from the JSON is checked for type and range: a setting that looks right but is the wrong type
(`"live": "false"` is a non-empty string, which Python treats as true) must stop the agent, not quietly open a gate.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from .models import MODES

REPO = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO / "outputs" / "outreach" / "reply-agent.json"
LOCAL_PATH = CONFIG_PATH.with_name("reply-agent.local.json")
DB_PATH = REPO / "outputs" / "outreach" / "replies" / "replies.db"

BOOKING_LINK = "https://cal.com/heinrich-bosch-yrvh1y/meets?duration=30"

DEFAULT_MODES = {
    "interested": "review",
    "question": "review",
    "referral": "review",
    "soft_no": "review",
}

BANNED_WORDS = (
    "leverage", "robust", "seamless", "streamline", "tailored", "cutting-edge", "unlock",
    "elevate", "empower", "synergy", "game-changer", "revolutionize", "delighted",
)
BANNED_PHRASES = (
    "i hope this email finds you well", "i hope this finds you well", "as an ai", "language model",
    "bid desk", "guarantee", "no obligation", "reach out",
    "touch base", "circle back", "per my last",
)


@dataclass(frozen=True)
class Config:
    tracking_mailbox: str = ""
    campaign_mailboxes: tuple[str, ...] = ()
    sender_name: str = "Heinrich"
    sign_off: str = "Best regards,"  # the line above the name at the end of every drafted reply
    full_name: str = "Heinrich Bosch"
    notify_to: str = ""  # where the hosted agent emails "replies are waiting"; empty means no email
    booking_link: str = BOOKING_LINK
    modes: dict = field(default_factory=lambda: dict(DEFAULT_MODES))
    live: bool = False  # sending needs this AND the --live flag
    max_per_day: int = 40
    max_per_mailbox_per_day: int = 10
    delay_minutes: tuple[float, float] = (4, 22)
    warmup_tags: tuple[str, ...] = ()
    lead_files: tuple[str, ...] = ()
    banned_words: tuple[str, ...] = BANNED_WORDS
    banned_phrases: tuple[str, ...] = BANNED_PHRASES
    max_words: int = 110
    max_grade: float = 8.5
    classify_model: str = "haiku"
    draft_model: str = "sonnet"
    imap_host: str = "imap.purelymail.com"
    smtp_host: str = "smtp.purelymail.com"
    auth_host: str = "purelymail.com"  # whose Authentication-Results header we believe
    require_verified_for_auto: bool = True  # automatic sending only for senders our own server verified
    stale_after_hours: int = 12  # an approved draft not sent within this long goes back to a person
    park_after_hours: int = 24  # a mail the model could not read for this long is handed to a person
    max_model_mails_per_sender_per_day: int = 6
    max_model_mails_per_day: int = 200
    facts: tuple[str, ...] = ()
    examples: tuple[dict, ...] = ()
    db_path: str = str(DB_PATH)

    def mode_for(self, category: str) -> str:
        mode = self.modes.get(category, "off")
        return mode if mode in MODES else "off"

    def with_overrides(self, **changes) -> "Config":
        return replace(self, **changes)


_BOOL_FIELDS = {"live", "require_verified_for_auto"}
_INT_FIELDS = {  # name -> smallest allowed value
    "max_per_day": 0, "max_per_mailbox_per_day": 0, "max_words": 1, "stale_after_hours": 1, "park_after_hours": 1,
    "max_model_mails_per_sender_per_day": 0, "max_model_mails_per_day": 0,
}
_STR_FIELDS = {"sender_name", "sign_off", "full_name", "classify_model", "draft_model", "imap_host", "smtp_host", "auth_host", "db_path"}
_STR_LIST_FIELDS = {"campaign_mailboxes", "warmup_tags", "lead_files", "banned_words", "banned_phrases", "facts"}


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check(key: str, value):
    """Return the value in its final form, or raise ValueError saying which setting is wrong and how."""
    if key in _BOOL_FIELDS:
        if value is not True and value is not False:
            raise ValueError(f"{key} must be true or false (without quotes), got {value!r}")
        return value
    if key in _INT_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int) or value < _INT_FIELDS[key]:
            raise ValueError(f"{key} must be a whole number of at least {_INT_FIELDS[key]}, got {value!r}")
        return value
    if key == "max_grade":
        if not _is_number(value) or not 0 < value <= 30:
            raise ValueError(f"max_grade must be a number between 0 and 30, got {value!r}")
        return float(value)
    if key == "delay_minutes":
        if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(_is_number(v) for v in value) \
                or not 0 <= value[0] <= value[1]:
            raise ValueError(f"delay_minutes must be two numbers, smallest first, got {value!r}")
        return (value[0], value[1])
    if key in _STR_FIELDS:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty piece of text, got {value!r}")
        return value
    if key in ("tracking_mailbox", "notify_to"):
        if not isinstance(value, str) or (value and not re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}", value)):
            raise ValueError(f"{key} must be one email address or empty, got {value!r}")
        return value.lower()
    if key == "booking_link":
        if not isinstance(value, str) or not value.startswith("https://"):
            raise ValueError(f"booking_link must be an https:// link, got {value!r}")
        return value
    if key in _STR_LIST_FIELDS:
        if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) and v.strip() for v in value):
            raise ValueError(f"{key} must be a list of text values")
        items = tuple(value)
        if key == "campaign_mailboxes":
            if not all("@" in v for v in items):
                raise ValueError("campaign_mailboxes must all be email addresses")
            items = tuple(v.lower() for v in items)
        return items
    if key == "examples":
        if not isinstance(value, (list, tuple)) or not all(isinstance(x, dict) and "in" in x and "out" in x for x in value):
            raise ValueError("examples must be a list of {in, out} pairs")
        return tuple(dict(x) for x in value)
    if key == "modes":
        if not isinstance(value, dict):
            raise ValueError("modes must be an object")
        bad = {k: v for k, v in value.items() if v not in MODES}
        if bad:
            raise ValueError(f"modes must be one of {MODES}, got {bad}")
        return {**DEFAULT_MODES, **value}
    return value


def from_dict(data: dict) -> Config:
    """Build a Config from a JSON-style dict. Unknown keys are ignored, wrong types and ranges are refused."""
    known = set(Config.__dataclass_fields__)
    return Config(**{key: _check(key, value) for key, value in data.items() if key in known})


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} must hold one JSON object")
    return data


def load_shared(path: Path | str | None = None) -> Config:
    """Only the shareable file: voice, facts, examples and limits. This is what the repository itself ships."""
    return from_dict(_read(Path(path) if path else CONFIG_PATH))


def load(path: Path | str | None = None) -> Config:
    """The shareable file with the private one laid over it.

    Mailbox addresses, warmup tags and the lead list path live in `<name>.local.json` next to it. Git ignores that file,
    because this repository is public and those details would only help someone spoof or flood the agent.
    """
    p = Path(path) if path else CONFIG_PATH
    local = LOCAL_PATH if path is None else p.with_name(f"{p.stem}.local{p.suffix}")
    return from_dict({**_read(p), **_read(local)})
