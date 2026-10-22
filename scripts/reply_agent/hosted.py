"""Running the agent on the always-on host (a small Railway service of its own).

Everything private lives in one folder on a Railway volume, never in the public repository:

  shared.json   voice, facts, examples and limits (the shareable settings)
  local.json    mailboxes, warmup tags and where to email "replies are waiting"
  leads.csv     the lead list, email addresses only
  secret.json   the tracking mailbox password (owner-only file permissions)
  replies.db    the agent's database
  status.json   what the last pass did, read by the ready check
  notify.json   what Heinrich was last emailed about, so he is told once per new item

`python -m reply_agent railway-setup` on Heinrich's PC fills the folder over an authenticated call to the host
(scripts/reply_agent/web.py). Who may call the host's pages at all is that web layer's job, checked against one
shared key read from an environment variable there; this module knows nothing about that key.
"""
from __future__ import annotations

import json
import os
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from . import config as config_mod
from .agent import Agent
from .config import Config
from .llm import LLM
from .mailbox import FilingSender, ImapSource, SmtpSender
from .models import MODEL_CATEGORIES
from .store import Store
from .textnorm import one_line, strip_controls

FOLDER_NAME = "reply-agent"
REQUIRED = ("shared.json", "local.json", "leads.csv", "secret.json")
MAX_LEADS = 50_000
MAX_SUPPRESSED = 20_000
NOTIFY_EVERY = timedelta(minutes=30)
# A person writing back. Bounces, auto-replies, warmup, our own mail and strangers are "filed away", not replies.
REPLY_CATEGORIES = MODEL_CATEGORIES + ("unsubscribe", "complaint")
SNIPPET = 600
_LOCK = threading.Lock()  # notify.json is read and rewritten whole


def data_folder(env=None) -> Path | None:
    """REPLY_AGENT_DIR when set, else <Railway volume>/reply-agent, else None: without a disk nothing may run, because the
    database (and with it the do-not-write list and who has had a reply) would vanish on every deploy."""
    env = os.environ if env is None else env
    explicit = (env.get("REPLY_AGENT_DIR") or "").strip()
    if explicit:
        return Path(explicit)
    volume = (env.get("RAILWAY_VOLUME_MOUNT_PATH") or "").strip()
    return Path(volume) / FOLDER_NAME if volume else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


def _write_atomic(path: Path, data: bytes, private: bool = False) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600 if private else 0o644)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
    if private:
        os.chmod(path, 0o600)


def _json_bytes(data) -> bytes:
    return json.dumps(data, indent=2, ensure_ascii=True).encode("ascii")


def _sum(counts: dict) -> int:
    return sum(v for k, v in counts.items() if k in REPLY_CATEGORIES)


def _clip(value, limit: int, one_line_only: bool = False) -> str:
    text = (one_line if one_line_only else strip_controls)(str(value or ""))
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _is_address(value) -> bool:
    return (isinstance(value, str) and 3 <= len(value) <= 254 and value.count("@") == 1
            and not any(c in value for c in " ,;<>\"'\r\n\t"))


class Hosted:
    def __init__(self, folder: Path | str | None, clock=None):
        self.folder = Path(folder) if folder else None
        self.clock = clock or _now

    def _path(self, name: str) -> Path:
        assert self.folder is not None
        return self.folder / name

    def _read(self, name: str, default=None) -> dict:
        path = self._path(name)
        if not path.exists():
            if default is not None:
                return default
            raise FileNotFoundError(name)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{name} must hold one JSON object")
        return data

    # --- readiness and settings ---------------------------------------------------------------
    def blockers(self) -> list[str]:
        """Plain-English reasons the agent cannot run here yet. Empty when it can."""
        if self.folder is None:
            return ["No disk for the reply agent yet: add a Railway volume to this service."]
        missing = [name for name in REQUIRED if not self._path(name).exists()]
        if missing:
            return [f"Not set up yet: run `python -m reply_agent railway-setup` on Heinrich's PC (missing {', '.join(missing)})."]
        try:
            cfg = self.config()
        except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
            return [f"The settings on the disk cannot be used: {str(exc)[:200]}"]
        if not cfg.tracking_mailbox or not cfg.campaign_mailboxes:
            return ["The settings name no tracking mailbox or no campaign mailboxes."]
        if not self.password():
            return ["No mailbox password on the disk: run `python -m reply_agent railway-setup` again."]
        return []

    def config(self, send: bool = False) -> Config:
        merged = {**self._read("shared.json"), **self._read("local.json"),
                  "lead_files": [str(self._path("leads.csv"))], "db_path": str(self._path("replies.db"))}
        return config_mod.from_dict(merged).with_overrides(live=send is True)

    def password(self) -> str:
        return str(self._read("secret.json", {}).get("password") or "")

    def store(self) -> Store:
        return Store(self._path("replies.db"))

    # --- setup, sent from Heinrich's PC -------------------------------------------------------
    def apply_setup(self, payload) -> dict:
        """Check everything first, then write. A bad setting or list is refused whole, so a half-written setup never runs."""
        if self.folder is None:
            raise ValueError("this host has no disk for the reply agent: add a Railway volume to this service first")
        if not isinstance(payload, dict):
            raise ValueError("the setup must be one JSON object")
        shared, local = payload.get("shared"), payload.get("local")
        if not isinstance(shared, dict) or not isinstance(local, dict):
            raise ValueError("shared and local must both be JSON objects")
        local = {k: v for k, v in local.items() if k not in ("lead_files", "db_path")}
        cfg = config_mod.from_dict({**shared, **local})
        if not cfg.tracking_mailbox or not cfg.campaign_mailboxes:
            raise ValueError("tracking_mailbox and campaign_mailboxes are required")
        leads = payload.get("leads")
        if not isinstance(leads, list) or not leads or len(leads) > MAX_LEADS or not all(_is_address(e) for e in leads):
            raise ValueError(f"leads must be a list of 1 to {MAX_LEADS} plain email addresses")
        password = payload.get("password")
        if not isinstance(password, str) or not password.strip() or len(password) > 500:
            raise ValueError("password is missing")
        suppressed = payload.get("suppressed", [])
        if not isinstance(suppressed, list) or len(suppressed) > MAX_SUPPRESSED or not all(
                isinstance(r, dict) and _is_address(r.get("addr")) and isinstance(r.get("reason", ""), str)
                and isinstance(r.get("at", ""), str) and len(r.get("at", "")) <= 40 for r in suppressed):
            raise ValueError("suppressed must be a list of {addr, reason, at}")

        self.folder.mkdir(parents=True, exist_ok=True)
        _write_atomic(self._path("shared.json"), _json_bytes(shared))
        _write_atomic(self._path("local.json"), _json_bytes(local))
        emails = sorted({e.strip().lower() for e in leads})
        _write_atomic(self._path("leads.csv"), ("email\n" + "\n".join(emails) + "\n").encode("utf-8"))
        _write_atomic(self._path("secret.json"), _json_bytes({"password": password}), private=True)
        store = self.store()
        try:
            already = store.suppressed()
            added = 0
            for row in suppressed:
                addr = row["addr"].strip().lower()
                if addr not in already:
                    store.suppress(addr, str(row.get("reason") or "copied from the PC")[:200], row.get("at") or None)
                    added += 1
        finally:
            store.close()
        return {"leads": len(emails), "mailboxes": len(cfg.campaign_mailboxes), "suppressed_added": added,
                "notify": bool(cfg.notify_to)}

    # --- one pass -------------------------------------------------------------------------------
    def run_pass(self, llm: LLM, send: bool, notify_link: str = "") -> dict:
        """Read the tracking mailbox once, send approved replies that are due (only when `send`), then tell Heinrich about
        anything new that waits for him. The outcome is saved for the ready check either way."""
        started = self.clock()
        try:
            cfg = self.config(send=send)
            password = self.password()
            source = ImapSource(cfg.imap_host, cfg.tracking_mailbox, password)
            sender = FilingSender(SmtpSender(cfg.smtp_host, cfg.tracking_mailbox, password), source) if send else None
            store = Store(cfg.db_path)
            try:
                agent = Agent(cfg, store, llm, sender=sender)
                try:
                    outcomes = agent.run_once(source, live=send)
                finally:
                    source.close()
                counts = dict(Counter(o.action for o in outcomes))
                waiting = self.waiting(store)
                notice_error = ""
                try:
                    notified = self._notify(cfg, store, password, notify_link)
                except Exception as exc:  # noqa: BLE001  a failed notice must not make the mail work look failed
                    notified, notice_error = False, f"{type(exc).__name__}: {str(exc)[:200]}"
            finally:
                store.close()
        except Exception as exc:
            self._save_status({"last_pass_at": _iso(started), "ok": False,
                               "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
            raise
        result = {"last_pass_at": _iso(started), "ok": True, "error": "", "counts": counts,
                  "waiting": {k: len(v) for k, v in waiting.items()}, "notified": notified, "notice_error": notice_error}
        self._save_status(result)
        return result

    def _save_status(self, data: dict) -> None:
        if self.folder is None or not self.folder.exists():
            return
        old = self._read("status.json", {})
        if data.get("ok"):
            data["last_ok_at"] = data["last_pass_at"]
        elif old.get("last_ok_at"):
            data["last_ok_at"] = old["last_ok_at"]
        _write_atomic(self._path("status.json"), _json_bytes(data))

    def status(self) -> dict:
        if self.folder is None or not self.folder.exists():
            return {}
        try:
            return self._read("status.json", {})
        except (OSError, ValueError):
            return {}

    # --- what the Replies page inside Twenty shows ------------------------------------------------
    def summary(self, *, enabled: bool, live: bool, interval_minutes: int = 1, limit: int = 20) -> dict:
        """Counts, the newest replies with what we drafted, and whether the agent is alive. It carries what people wrote,
        so the web layer only hands it out behind the key."""
        now = self.clock()
        status = self.status()
        out = {"enabled": enabled, "live": live, "interval_minutes": interval_minutes,
               "last_pass_at": status.get("last_pass_at"), "last_ok_at": status.get("last_ok_at"),
               "online": False, "why_not": "", "replies": {"day": 0, "week": 0, "month": 0, "all": 0},
               "by_category_month": {}, "filed_away_month": 0,
               "drafts": {"waiting": 0, "approved": 0, "sent": 0, "skipped": 0, "failed": 0, "checking": 0},
               "needs_you": 0, "recent": []}
        blockers = self.blockers()
        if blockers:
            out["why_not"] = blockers[0]
            return out
        out["online"], out["why_not"] = self._online(enabled, status, interval_minutes, now)
        store = self.store()
        try:
            def since(delta: timedelta) -> dict:
                return store.handled_by_category_since(_iso(now - delta))
            month = since(timedelta(days=30))
            out["replies"] = {"day": _sum(since(timedelta(days=1))), "week": _sum(since(timedelta(days=7))),
                              "month": _sum(month), "all": _sum(store.handled_by_category_since(""))}
            out["by_category_month"] = {k: v for k, v in month.items() if k in REPLY_CATEGORIES}
            out["filed_away_month"] = sum(v for k, v in month.items() if k not in REPLY_CATEGORIES)
            drafts = store.draft_status_counts()
            out["drafts"] = {"waiting": drafts.get("pending", 0) + drafts.get("held", 0), "approved": drafts.get("approved", 0),
                             "sent": drafts.get("sent", 0), "skipped": drafts.get("skipped", 0),
                             "failed": drafts.get("failed", 0), "checking": drafts.get("sending", 0)}
            out["needs_you"] = len(store.open_attention())
            out["recent"] = [{"at": r["handled_at"], "from_name": _clip(r["from_name"], 80, True),
                              "from_addr": _clip(r["from_addr"], 254, True), "mailbox": _clip(r["mailbox"], 254, True),
                              "subject": _clip(r["subject"], 200, True), "category": r["category"],
                              "their_words": _clip(r["body"], SNIPPET), "draft_status": r["draft_status"] or "",
                              "draft": _clip(r["draft_body"], SNIPPET), "sent_at": r["sent_at"] or ""}
                             for r in store.recent_mails(REPLY_CATEGORIES, limit)]
        finally:
            store.close()
        return out

    @staticmethod
    def _online(enabled: bool, status: dict, interval_minutes: int, now: datetime) -> tuple[bool, str]:
        if not enabled:
            return False, "The background check is switched off (REPLY_AGENT_ENABLED is not 1 on Railway)."
        if status.get("ok") is False:
            return False, f"The last check of the inbox failed: {status.get('error') or 'no reason given'}"
        if not status.get("last_ok_at"):
            return False, "It has not finished a check of the inbox yet."
        age = now - datetime.fromisoformat(status["last_ok_at"])
        if age > timedelta(minutes=max(15, 3 * interval_minutes)):
            return False, f"Its last good check of the inbox was {int(age.total_seconds() // 60)} minutes ago."
        return True, ""

    @staticmethod
    def waiting(store: Store) -> dict[str, list[int]]:
        return {
            "drafts": [r["id"] for r in store.drafts("pending") + store.drafts("held")],
            "attention": [r["id"] for r in store.open_attention()],
            "doubtful": [r["id"] for r in store.drafts("sending")],
            "failed": [r["id"] for r in store.drafts("failed")],
        }

    # --- telling Heinrich -------------------------------------------------------------------------
    def _notify(self, cfg: Config, store: Store, password: str, notify_link: str) -> bool:
        """Email Heinrich when something new waits for him: at most once every 30 minutes, never twice about the same item."""
        if not cfg.notify_to or not notify_link:
            return False
        waiting = self.waiting(store)
        keys = {f"{kind[0]}{i}" for kind, ids in waiting.items() for i in ids}
        with _LOCK:
            state = self._read("notify.json", {})
            told = set(state.get("told") or [])
            last = state.get("at") or ""
            if not keys - told:
                if told - keys:  # items he dealt with: forget them, so their numbers can never block a later notice
                    _write_atomic(self._path("notify.json"), _json_bytes({"told": sorted(keys & told), "at": last}))
                return False
            if last and self.clock() - datetime.fromisoformat(last) < NOTIFY_EVERY:
                return False
            SmtpSender(cfg.smtp_host, cfg.tracking_mailbox, password).send(self._notice(cfg, waiting, notify_link))
            _write_atomic(self._path("notify.json"), _json_bytes({"told": sorted(keys), "at": _iso(self.clock())}))
        return True

    @staticmethod
    def _notice(cfg: Config, waiting: dict[str, list[int]], link: str) -> EmailMessage:
        parts = []
        if waiting["drafts"]:
            parts.append(f"{len(waiting['drafts'])} draft repl{'y' if len(waiting['drafts']) == 1 else 'ies'} to read")
        if waiting["attention"]:
            parts.append(f"{len(waiting['attention'])} email{'' if len(waiting['attention']) == 1 else 's'} that need you")
        if waiting["doubtful"]:
            parts.append(f"{len(waiting['doubtful'])} send{'' if len(waiting['doubtful']) == 1 else 's'} to check")
        if waiting["failed"]:
            parts.append(f"{len(waiting['failed'])} failed send{'' if len(waiting['failed']) == 1 else 's'}")
        summary = ", ".join(parts) or "something to look at"
        msg = EmailMessage()
        msg["From"] = f"Reply agent <{cfg.tracking_mailbox}>"
        msg["To"] = cfg.notify_to
        msg["Subject"] = f"Reply agent: {summary}"
        msg["Message-ID"] = make_msgid(domain=cfg.tracking_mailbox.split("@")[-1])
        msg["Date"] = formatdate(localtime=False)
        msg["Auto-Submitted"] = "auto-generated"
        msg.set_content(f"Waiting for you: {summary}.\n\nOpen the review page:\n{link}\n\nNothing is sent until you press Send on it.\n")
        return msg
