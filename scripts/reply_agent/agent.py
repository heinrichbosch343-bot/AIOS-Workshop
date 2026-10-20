"""The loop: read, sort, draft, then queue for a person or send. Every send passes the same gates.

Three promises hold the design together:
  1. A mail is saved together with its draft or not at all, so a crash or an outage can never leave a reply half-handled.
  2. A draft can only be sent after it has been claimed (approved -> sending) in one atomic step, so it can never go twice.
  3. Nothing is silent that a person might want to see: it is either answered, queued, or listed in the review.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import draft as drafting
from . import rules, triage, trust
from .config import Config
from .llm import LLM, LLMError
from .mailbox import DryRunSender, Sender, SendUncertain, build_reply
from .mailparse import parse
from .models import DRAFT_CATEGORIES, Decision, InboundMail
from .store import Store
from .trust import base_address
from .validate import check

MIN_CONFIDENCE_FOR_AUTO = 0.75
MAX_MODEL_FAILURES_PER_PASS = 3   # this many in a row: the model is probably down, so stop the pass and try again later
MAX_CRASHES_PER_MAIL = 3          # a mail that crashes the handler this many times is set aside for a person
MIN_CONFIDENCE_TO_SUPPRESS = 0.75  # a "no" the model is less sure of than this is shown to a person, not acted on
MAX_LISTED_PER_KIND_PER_DAY = 40  # so a flood of strangers cannot bury the review list, whatever kind of item it fills it with
MAX_LISTED_PER_KIND_PER_DAY_KNOWN = 200  # senders we know (an exact lead or a verified one) have their own, larger allowance
MAX_LISTED_PER_SENDER_PER_DAY = 10  # and one address, whatever kinds of item it manages to produce, gets this many a day
MAX_BATCHES_PER_PASS = 10         # a pass reads up to this many batches of mail, so a backlog is cleared in one go
MAX_BOUNCE_ADDRESSES_PER_NOTICE = 5     # one failure notice (anyone can forge one) may stop us writing to this many leads
MAX_BOUNCE_SUPPRESSIONS_PER_DAY = 200   # and all failure notices together, in a day
# Only mail that gets a draft needs its text kept. Anything a person must see keeps it too (that is decided by the attention note),
# so a flood of junk costs a few bytes each, not six thousand characters.
KEEP_BODY_FOR = DRAFT_CATEGORIES
QUIET_CATEGORIES = frozenset({"auto_reply", "out_of_office"})  # machine mail: never worth a person's time, however big or odd


@dataclass(frozen=True)
class Outcome:
    message_id: str
    category: str
    action: str  # skipped, logged, held, queued, scheduled, sent, uncertain, failed, retry
    note: str = ""
    draft_id: int | None = None


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat(timespec="seconds")


class Agent:
    def __init__(self, cfg: Config, store: Store, classify_llm: LLM, draft_llm: LLM | None = None,
                 sender: Sender | None = None, clock: Callable[[], datetime] | None = None,
                 rng: random.Random | None = None, known: rules.Known | None = None):
        self.cfg = cfg
        self.store = store
        self.classify_llm = classify_llm
        self.draft_llm = draft_llm or classify_llm
        self.sender = sender or DryRunSender()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.rng = rng or random.Random()
        self._base_known = known if known is not None else rules.load_known(cfg)
        self._model_off = False  # set when the model looks down, until the end of that pass

    def _need_model(self) -> None:
        if self._model_off:
            raise LLMError("the model looked unavailable earlier in this pass, so it is not asked again until the next one")

    def _known(self) -> rules.Known:
        return replace(self._base_known, suppressed=self.store.suppressed(), sent=self.store.sent_to())

    def _day_ago(self, now: datetime) -> str:
        return _iso(now - timedelta(hours=24))

    # --- reading ----------------------------------------------------------------------------
    def handle(self, mail: InboundMail) -> Outcome:
        """Sort one mail and queue, send or log it. Raises LLMError if the model is down: nothing is saved, so it is tried again."""
        if self.store.seen(mail.message_id):
            return Outcome(mail.message_id, "", "skipped", "already handled")
        now = self.clock()
        known = self._known()
        verified = trust.authenticated(mail, self.cfg.auth_host)
        level = rules.trust_level(mail, known)
        box = rules.our_mailbox(mail, self.cfg)

        decision, attention = rules.prefilter(mail, self.cfg, known, verified), None
        if decision is None:
            decision, attention = self._without_model(mail, level, verified, box, now)
        if decision is None:
            if mail.flags:  # we only have its headers: do not let the model guess from a placeholder
                decision = Decision("other", 0.0, "the message could not be read in full", "rule", box)
            else:
                self._need_model()
                decision = triage.ask_model(mail, self.cfg, self.classify_llm)
        suppress = self._suppress_targets(mail, decision, verified, level, known, now)
        trusted = verified or level == "exact"
        attention = attention or self._attention(mail, decision, known, now, trusted, applied=bool(suppress))

        written = None
        mode = self.cfg.mode_for(decision.category) if decision.category in DRAFT_CATEGORIES else "off"
        if mode != "off":
            self._need_model()
            written = drafting.write_reply(mail, decision, self.cfg, self.draft_llm)

        status, send_after = "pending", None
        if written is None:
            action = "logged"
            note = "mode is off for this category" if decision.category in DRAFT_CATEGORIES else decision.reason
        elif not written.body:
            status, action, note = "held", "held", "; ".join(written.problems)
        elif mode == "auto" and self._may_auto_send(mail, decision, verified, level, written.clean, now):
            delay = timedelta(minutes=self.rng.uniform(*self.cfg.delay_minutes))
            status, action, send_after = "approved", "scheduled", _iso(now + delay)
            note = f"sends after about {int(delay.total_seconds() // 60)} min"
        else:
            action = "queued"
            note = "; ".join(written.problems) if written.problems else "waiting for approval"
        if attention and action == "logged":
            note = f"{note} (shown in review: {attention[0]})"

        draft_id = self.store.record_outcome(
            mail, decision, verified=verified, trust=level, suppress=suppress,
            keep_body=attention is not None or decision.category in KEEP_BODY_FOR, draft=written, draft_status=status,
            send_after=send_after, attention=attention, at=_iso(now))
        return Outcome(mail.message_id, decision.category, action, note, draft_id)

    def _capped(self, kind: str, note: str, now: datetime, trusted: bool = False, sender: str = ""):
        """(kind, note) to list for a person, unless today's allowance of this kind is used up. Then a single notice that a
        flood is under way is listed instead (once a day), and the rest are logged quietly.

        Senders we know (an exact lead, or one our own server verified) have an allowance of their own, so a crowd of strangers
        can never use up what a real lead is allowed. And one address, however many ways it finds to be listed, gets only a few
        items a day.
        """
        since = self._day_ago(now)
        if kind in ("flood", "flood_known"):
            return (kind, note) if self.store.attention_count_since(kind, since) == 0 else None
        if sender and self.store.attention_count_for_sender_since(sender, since) >= MAX_LISTED_PER_SENDER_PER_DAY:
            return None
        limit = MAX_LISTED_PER_KIND_PER_DAY_KNOWN if trusted else MAX_LISTED_PER_KIND_PER_DAY
        if self.store.attention_count_since(kind, since, trusted=trusted) < limit:
            return kind, note
        return self._capped("flood_known" if trusted else "flood",
                            f"more than {limit} items of kind '{kind}' from {'known' if trusted else 'unknown'} senders arrived today, "
                            "so the rest are logged but not listed. Look through the tracking mailbox's inbox itself for a real reply among them",
                            now)

    def _listed_or_flood(self, kind: str, reason: str, box: str, now: datetime, trusted: bool = False, sender: str = ""):
        """Tell a person about this mail, unless too many like it came today: then say so once and log the rest quietly."""
        listed = self._capped(kind, reason, now, trusted, sender)
        if listed is not None and listed[0] == kind:
            return Decision("other", 0.0, reason, "rule", box), listed
        return Decision("ignore", 1.0, "too many messages of this kind today", "rule", box), listed

    def _without_model(self, mail: InboundMail, level: str, verified: bool, box: str, now: datetime):
        """Mail the model should not be paid to read.

        The model costs money and an attacker can send unlimited mail. Someone writing from a lead's company whom our own
        server could not verify never reaches it; each sender and the mailbox as a whole get a daily budget; unverified mail
        may use only half of that budget, so forged mail cannot starve the real replies. A real lead who is turned away
        always lands in the review list: this is never a silent drop.
        """
        if level == "domain" and not verified:
            return self._listed_or_flood("unverified", "writes from a lead's company, but our mail server could not verify who sent it, so a person decides",
                                         box, now, False, base_address(mail.from_addr))
        since = self._day_ago(now)
        budget = self.cfg.max_model_mails_per_day
        known_sender = verified or level == "exact"
        if self.store.model_mails_since(since, sender=mail.from_addr) >= self.cfg.max_model_mails_per_sender_per_day:
            reason = "this sender has used up today's limit of messages read by the model"
            return Decision("ignore", 1.0, reason, "rule", box), (
                self._capped("limit", reason, now, True, base_address(mail.from_addr)) if known_sender else None)
        if not verified and self.store.model_mails_since(since, verified=False) >= budget // 2:
            reason = "today's limit of messages read by the model for unverified senders is used up"
            return Decision("ignore", 1.0, reason, "rule", box), (
                self._capped("limit", reason, now, True, base_address(mail.from_addr)) if level == "exact" else None)
        if self.store.model_mails_since(since) >= budget:
            reason = "today's limit of messages read by the model is used up, so a person must read this"
            if known_sender:
                return self._listed_or_flood("limit", reason, box, now, True, base_address(mail.from_addr))
            return Decision("ignore", 1.0, reason, "rule", box), None
        return None, None

    def _attention(self, mail: InboundMail, decision: Decision, known: rules.Known, now: datetime, trusted: bool = False,
                   applied: bool = False):
        """Mail a person should see even though no draft is written for it. None means it is safe to leave alone.

        Every kind has a daily allowance (see `_capped`), so a stranger cannot fill the list with any kind of item.
        `applied` says whether this mail put someone on the do-not-write list.
        """
        found = self._attention_wanted(mail, decision, known, now, trusted, applied)
        return None if found is None else self._capped(found[0], found[1], now, trusted, base_address(mail.from_addr))

    def _attention_wanted(self, mail: InboundMail, decision: Decision, known: rules.Known, now: datetime, trusted: bool, applied: bool):
        category = decision.category
        if category == "bounce":
            lost = [a for a in mail.failed_recipients if a in set(known.sent.values())]
            if lost:
                return "bounced_reply", f"our reply to {lost[0]} could not be delivered"
            named = [a for a in mail.failed_recipients if a in known.emails]
            if len(named) > MAX_BOUNCE_ADDRESSES_PER_NOTICE:
                return "bulk_bounce", (f"one failure notice names {len(named)} addresses on the lead list; only the first "
                                       f"{MAX_BOUNCE_ADDRESSES_PER_NOTICE} were added to the do-not-write list. A forged notice looks like this")
            if named and self.store.suppressions_since("bounce", self._day_ago(now)) >= MAX_BOUNCE_SUPPRESSIONS_PER_DAY:
                return "flood", ("failure notices have named far more leads than usual today, so the rest were not added to the "
                                 "do-not-write list. Look at the bounces in the tracking mailbox's inbox")
            return None
        if category in QUIET_CATEGORIES:
            return None
        if category == "ignore":
            return ("suppressed_wrote", "someone on the do-not-write list wrote again") if base_address(mail.from_addr) in known.suppressed else None
        if category == "unknown_sender" and not rules.looks_like_reply(mail):
            return None
        if "unreadable" in mail.flags:
            return "unreadable", "the message could not be read automatically"
        if "oversized" in mail.flags:
            return "too_large", "the message is too large to read automatically"
        if category == "complaint":
            return "complaint", decision.reason
        if category == "other":
            return "other", decision.reason
        if category == "unsubscribe" and not applied:  # a legal request must never be invisible, even when nobody can confirm who sent it
            return "stop_unconfirmed", ("asked to stop, but nobody could confirm who sent it, so nobody was added to the do-not-write list. "
                                        "If it is genuine, add them: python -m reply_agent suppress ADDRESS")
        if category == "not_interested" and trusted and not applied:
            return "unsure_no", "the sorter thinks this was a no but is not sure, so nobody was added to the do-not-write list. A person decides"
        if category == "unknown_sender":
            return "unknown_reply", "an address with no lead on file replied to something"
        return None

    def _suppress_targets(self, mail: InboundMail, decision: Decision, verified: bool, level: str, known: rules.Known, now: datetime):
        """Whom to stop writing to, and why. A forged note from a stranger must not be able to silence a real lead."""
        category = decision.category
        if category in ("unsubscribe", "complaint", "not_interested"):
            if not mail.from_addr or not (verified or level == "exact"):
                return ()
            if category == "not_interested" and decision.confidence < MIN_CONFIDENCE_TO_SUPPRESS:
                return ()  # the model is not sure it was a real no: a person decides, nobody is silenced on a guess
            why = f"{category}: {decision.reason}" + ("" if verified else " (sender not verified)")
            return ((base_address(mail.from_addr), why[:300]),)
        if category == "bounce":  # the address that failed, never the mail server that reported it
            room = max(0, MAX_BOUNCE_SUPPRESSIONS_PER_DAY - self.store.suppressions_since("bounce", self._day_ago(now)))
            named = [addr for addr in mail.failed_recipients if addr in known.emails]
            return tuple((addr, "bounce") for addr in named[:min(MAX_BOUNCE_ADDRESSES_PER_NOTICE, room)])
        return ()

    def _may_auto_send(self, mail: InboundMail, decision: Decision, verified: bool, level: str, clean: bool, now: datetime) -> bool:
        if not (clean and decision.mailbox and decision.confidence >= MIN_CONFIDENCE_FOR_AUTO):
            return False
        if (self.cfg.require_verified_for_auto and not verified) or level != "exact" or mail.flags:
            return False  # a forged From, a colleague, or a half-read mail is for a person to answer
        if base_address(mail.from_addr) in self.store.suppressed():
            return False
        since = self._day_ago(now)
        if self.store.replied_to_sender_since(mail.from_addr, since, include_queued=True):
            return False  # a fast back-and-forth is for a person to handle
        return self._within_caps(decision.mailbox, since)

    def _within_caps(self, mailbox: str, since_iso: str) -> bool:
        return (self.store.sent_since(since_iso) < self.cfg.max_per_day
                and self.store.sent_since(since_iso, mailbox) < self.cfg.max_per_mailbox_per_day)

    # --- people deciding --------------------------------------------------------------------
    def approve(self, draft_id: int, body: str | None = None, force: bool = False) -> None:
        row = self.store.get_draft(draft_id)
        if row is None:
            raise KeyError(f"no draft {draft_id}")
        if row["status"] not in ("pending", "held"):
            raise ValueError(f"draft {draft_id} is {row['status']}, not waiting")
        text = (body if body is not None else row["body"]).strip()
        if not text:
            raise ValueError("the draft is empty, so there is nothing to send. Write the reply and pass it with --file")
        if (row["mailbox"] or "").lower() not in {m.lower() for m in self.cfg.campaign_mailboxes}:
            raise ValueError("the person did not write to one of our campaign mailboxes, so there is no valid sending mailbox. "
                             "Answer this one by hand")
        problems = check(text, row["category"], self.cfg, context=row["their_body"] or "")
        if problems and not force:
            raise ValueError("the checks object: " + "; ".join(problems))
        now = self.clock()
        if not force and self.store.replied_to_sender_since(row["from_addr"], self._day_ago(now), include_queued=True,
                                                            exclude_id=draft_id):
            raise ValueError("we already replied to this person in the last 24 hours, or a reply is lined up. "
                             "Use --force to send this one as well")
        self.store.update_draft(draft_id, body=text, status="approved", send_after=_iso(now), problems="",
                                forced=1 if force else 0, approved_at=_iso(now))

    def skip(self, draft_id: int, note: str = "") -> None:
        row = self.store.get_draft(draft_id)
        if row is None:
            raise KeyError(f"no draft {draft_id}")
        if row["status"] in ("sending", "sent"):
            raise ValueError(f"draft {draft_id} is {row['status']}: it cannot be skipped")
        self.store.update_draft(draft_id, status="skipped", note=note)

    def retry(self, draft_id: int) -> None:
        """Put a failed send back in the queue. Only a send that definitely did not go out is marked failed, so this is safe."""
        row = self.store.get_draft(draft_id)
        if row is None:
            raise KeyError(f"no draft {draft_id}")
        if row["status"] != "failed":
            raise ValueError(f"draft {draft_id} is {row['status']}, only a failed one can be retried")
        now = _iso(self.clock())
        self.store.update_draft(draft_id, status="approved", send_after=now, approved_at=now, note="retried by hand")

    def settle(self, draft_id: int, delivered: bool) -> None:
        """Close a send nobody could confirm (the connection broke while it was going out) once a person has found out which it was."""
        row = self.store.get_draft(draft_id)
        if row is None:
            raise KeyError(f"no draft {draft_id}")
        if row["status"] != "sending":
            raise ValueError(f"draft {draft_id} is {row['status']}: only one marked as sending, and so in doubt, can be settled")
        if delivered:
            self.store.update_draft(draft_id, status="sent", note="confirmed delivered, by hand")
        else:
            self.store.update_draft(draft_id, status="failed", note="confirmed not delivered, by hand")

    # --- sending ----------------------------------------------------------------------------
    def flush(self, live: bool) -> list[Outcome]:
        """Send approved drafts that are due, at most one per mailbox per pass. Without `live` nothing leaves the building."""
        outcomes: list[Outcome] = []
        if not live:
            return outcomes
        now = self.clock()
        used: set[str] = set()
        for row in self.store.drafts("approved"):
            if row["send_after"] and row["send_after"] > _iso(now):
                continue
            outcome = self._send_one(row, now, used)
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    def _hold(self, row, mid: str, note: str) -> Outcome:
        self.store.update_draft(row["id"], status="held", note=note)
        return Outcome(mid, row["category"], "held", note, row["id"])

    def _send_one(self, row, now: datetime, used: set[str]) -> Outcome | None:
        draft_id, mid, mailbox = row["id"], row["their_id"], row["mailbox"]
        stale_before = _iso(now - timedelta(hours=self.cfg.stale_after_hours))
        due = row["send_after"] or row["approved_at"] or row["created_at"]  # a draft from before due times were recorded still ages
        if due and due < stale_before:
            return self._hold(row, mid, "waited too long to be sent, so look at it again before approving it")
        if base_address(row["from_addr"]) in self.store.suppressed():
            self.store.update_draft(draft_id, status="skipped", note="sender asked to stop before this was sent")
            return Outcome(mid, row["category"], "skipped", "sender is now suppressed", draft_id)
        if not row["forced"]:
            problems = check(row["body"], row["category"], self.cfg, context=row["their_body"] or "")
            if problems:
                return self._hold(row, mid, "the checks object now: " + "; ".join(problems))
            if self.store.replied_to_sender_since(row["from_addr"], self._day_ago(now), include_queued=False, exclude_id=draft_id):
                return self._hold(row, mid, "we already replied to this person in the last 24 hours. Approve with --force to send anyway")
        if mailbox in used:
            return None  # one reply per mailbox per pass keeps the sending human-paced; this one goes next pass
        if not self._within_caps(mailbox, self._day_ago(now)):
            return Outcome(mid, row["category"], "held", "daily cap reached, will retry", draft_id)
        try:
            msg = build_reply(
                mailbox=mailbox, to_addr=row["from_addr"], to_name=row["from_name"],
                subject=row["subject"],  # build_reply echoes it back only when it is plainly harmless
                their_id=mid, their_refs=tuple((row["refs"] or "").split()), body=row["body"], cfg=self.cfg)
        except Exception as exc:  # noqa: BLE001  e.g. not one of our mailboxes: it can never be sent as it stands
            self.store.update_draft(draft_id, status="failed", note=f"{type(exc).__name__}: {str(exc)[:200]}")
            return Outcome(mid, row["category"], "failed", str(exc)[:200], draft_id)
        if not self.store.claim_draft(draft_id, _iso(now), msg["Message-ID"]):
            return Outcome(mid, row["category"], "skipped", "another run already took this draft", draft_id)
        used.add(mailbox)
        try:
            self.sender.send(msg)
        except SendUncertain as exc:  # the connection broke mid-send: it may have gone, so it must not be retried blindly
            note = f"may have been delivered ({str(exc)[:160]}). Find out, then settle it by hand"
            self.store.update_draft(draft_id, note=note)  # the status stays "sending", which keeps it in the review list
            return Outcome(mid, row["category"], "uncertain", note, draft_id)
        except Exception as exc:  # noqa: BLE001  a refusal or a login problem: it did not go, and it is recorded, never retried blindly
            self.store.update_draft(draft_id, status="failed", note=f"{type(exc).__name__}: {str(exc)[:200]}", sent_at=None)
            return Outcome(mid, row["category"], "failed", str(exc)[:200], draft_id)
        try:
            self.store.update_draft(draft_id, status="sent")
        except Exception as exc:  # noqa: BLE001  it IS sent; staying marked "sending" is what stops a second copy going out
            return Outcome(mid, row["category"], "sent",
                           f"sent from {mailbox}, but could not record it ({type(exc).__name__}). It stays marked as sending", draft_id)
        return Outcome(mid, row["category"], "sent", f"from {mailbox}", draft_id)

    # --- one pass over a mailbox ------------------------------------------------------------
    def run_once(self, source, live: bool = False) -> list[Outcome]:
        """Read every unhandled mail (in batches, so mail that cannot be flagged cannot hide newer mail), then send what is due."""
        outcomes: list[Outcome] = []
        seen: set[str] = set()
        failures = 0
        self._model_off = False
        for _ in range(MAX_BATCHES_PER_PASS):
            batch = [(uid, raw) for uid, raw in source.fetch_new(exclude=frozenset(seen)) if uid not in seen]
            if not batch:
                break
            seen.update(uid for uid, _ in batch)
            failures = self._work_through(batch, source, outcomes, failures)
        outcomes.extend(self.flush(live))
        return outcomes

    def _work_through(self, batch, source, outcomes: list[Outcome], failures: int) -> int:
        """Handle one batch. Mail the model has never failed on goes first, so one poisonous message cannot block the rest.

        After three model failures in a row the model is taken to be down: it is not asked again in this pass, but everything
        the rules can settle (a request to stop, a bounce, a complaint) is still handled, and the mail that needs the model
        is noted as waiting, so its 24 hours start now.
        """
        items: list[tuple[str, InboundMail]] = []
        for uid, raw in batch:
            try:
                items.append((uid, parse(raw, uid)))
            except Exception as exc:  # noqa: BLE001  parse() does not raise, but one bad message must never stop the rest
                outcomes.append(self._after_crash(source, uid, f"uid:{uid}", exc))
        waiting = {row["key"]: row for row in self.store.waiting_retries()}
        items.sort(key=lambda item: waiting[item[1].message_id]["attempts"] if item[1].message_id in waiting else 0)
        now = self.clock()
        park_before = _iso(now - timedelta(hours=self.cfg.park_after_hours))
        for uid, mail in items:
            key = mail.message_id
            if key in waiting and waiting[key]["first_at"] <= park_before:
                outcomes.append(self._park(source, uid, mail, key, now))  # waited long enough: no more model calls, a person reads it
                continue
            try:
                outcome = self.handle(mail)
            except LLMError as exc:
                if self._model_off:  # not tried at all: it waits, and the clock on it starts now
                    self.store.touch_retry(key, str(exc), at=_iso(now))
                    outcomes.append(Outcome(mail.message_id, "", "retry", "the model looks down, so this waits for the next pass"))
                    continue
                failures += 1
                outcomes.append(self._after_model_failure(mail, key, exc))
                self._model_off = failures >= MAX_MODEL_FAILURES_PER_PASS
                continue
            except Exception as exc:  # noqa: BLE001  one bad message must not stop the rest
                outcomes.append(self._after_crash(source, uid, key, exc))
                continue
            failures = 0
            self.store.clear_retry(key)
            outcomes.append(outcome)
            self._mark_done(source, uid, outcomes)
        return failures

    def _mark_done(self, source, uid: str, outcomes: list[Outcome]) -> None:
        try:
            source.mark_done(uid)
        except Exception as exc:  # noqa: BLE001  the outcome is already saved, so handling it again is harmless
            outcomes.append(Outcome("", "", "failed", f"could not mark message {uid} as handled: {str(exc)[:160]}"))

    def _after_model_failure(self, mail: InboundMail, key: str, exc: Exception) -> Outcome:
        attempts, _ = self.store.bump_retry(key, str(exc), at=_iso(self.clock()))
        return Outcome(mail.message_id, "", "retry", f"the model is unavailable (try {attempts}): {str(exc)[:120]}")

    def _park(self, source, uid: str, mail: InboundMail, key: str, now: datetime) -> Outcome:
        reason = f"the model could not be reached for over {self.cfg.park_after_hours} hours, so a person must read this"
        decision = Decision("other", 0.0, reason, "rule", rules.our_mailbox(mail, self.cfg))
        self.store.record_outcome(mail, decision, verified=trust.authenticated(mail, self.cfg.auth_host),
                                  trust=rules.trust_level(mail, self._known()), attention=("stuck", reason), at=_iso(now))
        self.store.clear_retry(key)
        self._mark_done(source, uid, [])
        return Outcome(mail.message_id, "other", "logged", reason)

    def _after_crash(self, source, uid: str, key: str, exc: Exception) -> Outcome:
        now = self.clock()
        what = f"{type(exc).__name__}: {str(exc)[:160]}"
        attempts, _ = self.store.bump_retry(key, what, at=_iso(now))
        if attempts >= MAX_CRASHES_PER_MAIL:
            self.store.add_attention(key, "stuck", f"failed {attempts} times and was set aside. {what}", at=_iso(now))
            try:
                source.quarantine(uid)
            except Exception:  # noqa: BLE001  the review entry still tells a person it exists
                pass
            self.store.clear_retry(key)
            return Outcome(key, "", "failed", f"set aside after {attempts} failed tries and shown in review ({what})")
        return Outcome(key, "", "failed", f"{what} (try {attempts} of {MAX_CRASHES_PER_MAIL})")
