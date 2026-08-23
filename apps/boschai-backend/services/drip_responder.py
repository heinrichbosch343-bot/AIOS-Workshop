"""
Drip responder — watches the threads the email drip has sent and answers
prospect replies in Heinrich's voice, within minutes.

Every 10 minutes (scheduler):
  1. One Gmail search over recent inbox mail; anything sitting in a
     drip-sent thread that we haven't already handled is a prospect reply.
  2. Claude classifies it: interested / question / not_interested /
     unsubscribe / out_of_office / bounce / other.
  3. Interested or question -> compose a short reply (booking link when a call
     makes sense). With DRIP_AUTOREPLY_ENABLED=1 it SENDS — once per thread,
     then the conversation is Heinrich's. With the flag off it saves the reply
     as a Gmail draft instead, so Heinrich just reviews and hits send.
  4. Everything else is logged and flagged, never auto-answered.
  5. Every action lands in drip_replies (mirrored to the local CRM by
     crm_cloud_sync.py) and pings Heinrich on Telegram.

Safety rails: env gate (default drafts-only), runtime kill switch
(/autoreply off), daily cap, ONE auto-reply per thread, dedupe on the
inbound Gmail message id so a reply is never handled twice.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

import config
from config import ANTHROPIC_API_KEY, CALENDAR_BOOKING_LINK, DRIP_AUTOREPLY_DAILY_CAP
from core.writing_style import writing_style_block
from db.client import supabase
from services import email as email_service
from services.notify import send_telegram

_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_MODEL = "claude-sonnet-4-6"
TZ = ZoneInfo("Africa/Johannesburg")

_SCAN_QUERY = "in:inbox newer_than:3d"
_SCAN_MAX = 30


def set_kill_switch(on: bool) -> bool:
    """Runtime toggle. Set DRIP_AUTOREPLY_KILL_SWITCH=true in env to persist."""
    config.DRIP_AUTOREPLY_KILL_SWITCH = on
    return on


def get_status() -> dict:
    today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    sent = (supabase.table("drip_replies")
            .select("id", count="exact")
            .eq("action", "replied")
            .gte("created_at", today.isoformat())
            .execute()).count or 0
    return {
        "enabled": config.DRIP_AUTOREPLY_ENABLED,
        "kill_switch": config.DRIP_AUTOREPLY_KILL_SWITCH,
        "daily_cap": DRIP_AUTOREPLY_DAILY_CAP,
        "today_replies": sent,
    }


# ---------------------------------------------------------------------------
# Classification + composition
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = """Classify one reply to a warm re-engagement email Heinrich Bosch sent to a past prospect. Heinrich runs BoschAI, which builds custom AI systems for businesses.

Categories:
- "interested" — positive, open to talking, suggests or accepts a call, wants to hear more
- "question" — asks something real (pricing, what Heinrich offers, how it works) without committing
- "not_interested" — declines, not relevant, bad timing, "we're covered"
- "unsubscribe" — asks to stop emailing / be removed
- "out_of_office" — auto-reply, vacation notice
- "bounce" — delivery failure, address not found
- "other" — anything that doesn't fit (forwarded to a colleague, ambiguous one-liner)

Respond with ONLY a JSON object:
{"category": "<category>", "reason": "<one short line>"}"""


def _classify(subject: str, body: str) -> dict:
    try:
        resp = _ai.messages.create(
            model=_MODEL,
            max_tokens=256,
            system=_CLASSIFY_PROMPT,
            messages=[{"role": "user",
                       "content": f"Subject: {subject}\n\nReply:\n{body[:2000]}"}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end + 1])
    except Exception as e:
        print(f"[responder] classify failed: {e}", flush=True)
    # Unknown = flag for Heinrich rather than guess-reply.
    return {"category": "other", "reason": "classification failed"}


_COMPOSE_PROMPT = f"""You are Heinrich Bosch (BoschAI — builds custom AI systems for businesses). A past prospect just replied to your warm re-engagement email. Write your reply.

Rules:
- Answer what they actually said. Reference their specifics, never invent any about their business, pricing, or commitments.
- If they're open to talking, propose a call and put this booking link on its OWN line: {CALENDAR_BOOKING_LINK}
- If they asked a question you can't answer without inventing facts, acknowledge it and move it to the call.
- 2 to 6 sentences. Warm, direct, zero sales fluff. Sign off with just "Heinrich".
- Plain text only, no subject line.

Respond with ONLY a JSON object:
{{"reply_body": "<the reply text>"}}"""


def _compose(prospect_name: str, thread_context: str) -> str | None:
    try:
        resp = _ai.messages.create(
            model=_MODEL,
            max_tokens=700,
            system=_COMPOSE_PROMPT + "\n" + writing_style_block(),
            messages=[{"role": "user", "content": (
                f"Prospect: {prospect_name}\n\n"
                f"The thread so far (oldest first):\n{thread_context[:6000]}"
            )}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            data = json.loads(text[start:end + 1])
            return (data.get("reply_body") or "").strip() or None
    except Exception as e:
        print(f"[responder] compose failed: {e}", flush=True)
    return None


# ---------------------------------------------------------------------------
# Thread bookkeeping
# ---------------------------------------------------------------------------

def _watched_threads() -> dict[str, dict]:
    """thread_id -> send info for every drip email that went out."""
    watched: dict[str, dict] = {}
    for table, source in (("draft_queue", "draft"), ("email_queue", "queue")):
        rows = (supabase.table(table)
                .select("sent_thread_id,to_email,subject")
                .eq("status", "sent")
                .neq("sent_thread_id", "")
                .execute()).data
        for r in rows:
            watched[r["sent_thread_id"]] = {
                "source": source,
                "to_email": r.get("to_email", ""),
                "subject": r.get("subject", ""),
            }
    return watched


def _already_handled(message_ids: list[str]) -> set[str]:
    if not message_ids:
        return set()
    rows = (supabase.table("drip_replies")
            .select("inbound_message_id")
            .in_("inbound_message_id", message_ids)
            .execute()).data
    return {r["inbound_message_id"] for r in rows}


def _thread_already_answered(thread_id: str) -> bool:
    rows = (supabase.table("drip_replies")
            .select("id")
            .eq("thread_id", thread_id)
            .eq("action", "replied")
            .limit(1)
            .execute()).data
    return bool(rows)


def _log(row: dict) -> None:
    try:
        supabase.table("drip_replies").insert(row).execute()
    except Exception as e:
        # Unique-violation on inbound_message_id = a concurrent run got there
        # first; anything else is worth seeing in the logs.
        print(f"[responder] log skipped ({row.get('prospect_email')}): {e}", flush=True)


def _notify(text: str) -> None:
    try:
        send_telegram(text)
    except Exception:
        pass


def _thread_context(msgs: list[dict]) -> str:
    parts = []
    for m in msgs[-6:]:
        who = m["from"] or "(unknown)"
        parts.append(f"From: {who}\n{(m['body'] or m['snippet'] or '')[:1500]}")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run() -> dict:
    """One responder pass. Called by the scheduler every 10 minutes."""
    watched = _watched_threads()
    if not watched:
        return {"handled": 0, "reason": "no drip sends to watch"}

    try:
        recent = email_service.list_inbox(max_results=_SCAN_MAX, q=_SCAN_QUERY)
    except RuntimeError as e:  # Google not connected
        print(f"[responder] skipped: {e}", flush=True)
        return {"handled": 0, "reason": str(e)}

    candidates = [m for m in recent if m.get("thread_id") in watched]
    if not candidates:
        return {"handled": 0}

    handled_ids = _already_handled([m["id"] for m in candidates])
    fresh = [m for m in candidates if m["id"] not in handled_ids]

    results = []
    for msg in fresh:
        thread_id = msg["thread_id"]
        info = watched[thread_id]
        full = email_service.get_message(msg["id"])
        body = full.get("body") or msg.get("snippet") or ""
        prospect_name = (msg.get("from") or "").split("<")[0].strip().strip('"') \
            or msg.get("email", "")

        classification = _classify(full.get("subject", ""), body)
        category = classification.get("category", "other")

        base_row = {
            "source": info["source"],
            "thread_id": thread_id,
            "prospect_email": msg.get("email", ""),
            "prospect_name": prospect_name,
            "inbound_message_id": msg["id"],
            "subject": full.get("subject", ""),
            "category": category,
            "inbound_preview": body[:500],
        }

        if category not in ("interested", "question"):
            _log({**base_row, "action": "logged", "reply_body": ""})
            if category in ("not_interested", "unsubscribe"):
                _notify(f"Drip: {prospect_name} ({msg.get('email','')}) — {category}.\n"
                        f"\"{body[:200]}\"\nLogged; no auto-reply. CRM syncs the flag down.")
            elif category == "other":
                _notify(f"Drip: reply from {prospect_name} needs your eyes "
                        f"(couldn't classify it):\n\"{body[:300]}\"")
            results.append({"email": msg.get("email"), "category": category,
                            "action": "logged"})
            continue

        # Interested or asking questions. One auto-touch per thread, capped daily.
        status = get_status()
        already_answered = _thread_already_answered(thread_id)
        can_send = (status["enabled"] and not status["kill_switch"]
                    and not already_answered
                    and status["today_replies"] < status["daily_cap"])

        reply = _compose(prospect_name, _thread_context(
            email_service.get_thread(thread_id)))
        if not reply:
            _log({**base_row, "action": "flagged", "reply_body": ""})
            _notify(f"Drip: {prospect_name} ({msg.get('email','')}) is {category} "
                    f"but I couldn't compose a reply — over to you.\n\"{body[:300]}\"")
            results.append({"email": msg.get("email"), "category": category,
                            "action": "flagged"})
            continue

        if can_send:
            try:
                email_service.send_reply(msg["id"], reply)
                _log({**base_row, "action": "replied", "reply_body": reply})
                _notify(f"Drip auto-reply sent to {prospect_name} "
                        f"({msg.get('email','')}) — {category}.\n\n"
                        f"They said: \"{body[:200]}\"\n\nI sent:\n{reply}\n\n"
                        f"The thread is yours from here.")
                results.append({"email": msg.get("email"), "category": category,
                                "action": "replied"})
            except Exception as e:
                _log({**base_row, "action": "flagged", "reply_body": reply})
                _notify(f"Drip: reply to {prospect_name} failed to send ({e}). "
                        f"Flagged for you.")
                results.append({"email": msg.get("email"), "category": category,
                                "action": "flagged"})
        else:
            reason = ("already auto-replied once" if already_answered
                      else "auto-reply off" if not status["enabled"]
                      else "kill switch on" if status["kill_switch"]
                      else "daily cap reached")
            try:
                email_service.create_draft_reply(msg["id"], reply)
                action = "drafted"
                note = f"Reply DRAFTED in Gmail ({reason}) — review and send."
            except Exception as e:
                action = "flagged"
                note = f"Couldn't draft a reply ({e}) — over to you."
            _log({**base_row, "action": action, "reply_body": reply})
            _notify(f"Drip: {prospect_name} ({msg.get('email','')}) is {category}.\n"
                    f"They said: \"{body[:200]}\"\n\n{note}")
            results.append({"email": msg.get("email"), "category": category,
                            "action": action})

    if results:
        print(f"[responder] handled {len(results)}: {results}", flush=True)
    return {"handled": len(results), "results": results}
