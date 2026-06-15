"""
Auto-draft: scan Heinrich's recent real emails, and for the routine ones he could
quickly reply to, write a reply in his voice and save it as a Gmail DRAFT.

Nothing is ever sent. Heinrich opens Gmail -> Drafts and reviews/sends himself.
Designed to be run on a morning schedule or on-demand from the dashboard.
"""
import json

import anthropic

from config import ANTHROPIC_API_KEY
from core.prime import build_system_prompt
from core.writing_style import writing_style_block
from services import email as email_service

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = "claude-sonnet-4-6"

DECIDE_INSTRUCTIONS = """You are triaging one email for Heinrich Bosch (BoschAI).

Decide whether to pre-write a reply draft for him.

DRAFT a reply ONLY if ALL of these hold:
- It is from a real person or a real company representative (not a no-reply address).
- It is a routine message he can quickly answer: a question, a scheduling request,
  an acknowledgement, a simple request, a follow-up, an introduction.
- A short, polite reply genuinely moves it forward.

DO NOT draft if it is: promotional/marketing, a newsletter, an automated notification,
a receipt, a delivery/bounce notice, spam, or anything sensitive, legal, or requiring
Heinrich's personal judgement or information he hasn't given you.

If you draft, write it in Heinrich's voice: sharp, direct, concise, signed "Heinrich Bosch".
Keep it short. Do not invent facts, dates, figures, or commitments — if a detail is needed,
leave a clearly marked [bracketed placeholder] for Heinrich to fill.

Respond with ONLY a JSON object, no other text:
{"should_draft": true/false, "reason": "<one short line>", "draft": "<reply text, or empty string>"}"""


def _decide_and_draft(system_prompt: str, full_email: dict) -> dict:
    user_block = (
        f"From: {full_email.get('from','')}\n"
        f"Subject: {full_email.get('subject','')}\n"
        f"Date: {full_email.get('date','')}\n\n"
        f"Body:\n{(full_email.get('body','') or '')[:4000]}"
    )
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt + "\n\n" + DECIDE_INSTRUCTIONS,
            messages=[{"role": "user", "content": user_block}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        # Be tolerant of stray formatting around the JSON.
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
        data = json.loads(text)
        return {
            "should_draft": bool(data.get("should_draft")),
            "reason": str(data.get("reason", "")),
            "draft": str(data.get("draft", "")),
        }
    except Exception as e:
        return {"should_draft": False, "reason": f"skipped (could not assess: {e})", "draft": ""}


async def auto_draft_replies(max_emails: int = 10) -> dict:
    """Scan recent unread Primary emails; create Gmail drafts for the routine ones."""
    emails = email_service.list_inbox(
        max_results=max_emails, q="in:inbox category:primary is:unread", people_only=True
    )

    system_prompt = await build_system_prompt() + writing_style_block()
    created, skipped = [], []

    for e in emails:
        full = email_service.get_message(e["id"])
        decision = _decide_and_draft(system_prompt, full)

        if decision["should_draft"] and decision["draft"].strip():
            try:
                email_service.create_draft_reply(e["id"], decision["draft"])
                created.append({"from": e["from"], "subject": e["subject"], "reason": decision["reason"]})
            except Exception as ex:
                skipped.append({"from": e["from"], "subject": e["subject"], "reason": f"draft failed: {ex}"})
        else:
            skipped.append({"from": e["from"], "subject": e["subject"], "reason": decision["reason"]})

    return {
        "scanned": len(emails),
        "drafted": len(created),
        "created": created,
        "skipped": skipped,
    }
