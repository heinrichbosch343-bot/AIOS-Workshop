"""
Sign-off watcher: for each open sign-off, look in Gmail for a reply from the
person/company Heinrich is waiting on. The moment one is found, ping him on Telegram
and flag the sign-off (he confirms and closes it himself — never auto-resolved).

Matching: by contact_email if he gave one (exact), otherwise by waiting_on name
(fuzzy — Gmail matches the sender's name/address).

Run on a 30-minute schedule (on the always-on server) and once immediately when a
sign-off is logged.
"""
from datetime import datetime, timezone
from html import escape

from db.client import supabase
from services import email as email_service
from services.notify import send_telegram


def _gmail_after(iso_ts: str) -> str:
    """Gmail 'after:' date (YYYY/MM/DD) for the day the sign-off was logged."""
    dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    return dt.strftime("%Y/%m/%d")


def _find_reply(contact: str, since_iso: str) -> dict | None:
    """Search Gmail for a message from `contact` since the sign-off was logged."""
    q = f'in:inbox from:{contact} after:{_gmail_after(since_iso)}'
    try:
        hits = email_service.list_inbox(max_results=3, q=q)
    except Exception:
        return None
    return hits[0] if hits else None


def check_signoffs() -> dict:
    """Check every open, not-yet-notified sign-off for a reply. Returns a summary."""
    rows = (
        supabase.table("signoffs")
        .select("*")
        .is_("resolved_at", "null")
        .is_("reply_detected_at", "null")
        .execute()
    ).data

    notified = []
    for s in rows:
        contact = (s.get("contact_email") or s.get("waiting_on") or "").strip()
        if not contact:
            continue

        since = s.get("sent_at") or s.get("created_at")
        hit = _find_reply(contact, since)
        if not hit:
            continue

        supabase.table("signoffs").update({
            "reply_detected_at": datetime.now(timezone.utc).isoformat(),
            "reply_from": hit["from"],
            "reply_subject": hit["subject"],
        }).eq("id", s["id"]).execute()

        try:
            send_telegram(
                f"📬 <b>{escape(s['waiting_on'])}</b> replied about <b>{escape(s['item'])}</b>\n\n"
                f"<i>{escape(hit['subject'])}</i>\n\n"
                f"Open your dashboard to review and close this sign-off."
            )
        except Exception:
            pass  # detection is recorded even if the ping fails

        notified.append({"waiting_on": s["waiting_on"], "item": s["item"], "subject": hit["subject"]})

    return {"checked": len(rows), "notified": len(notified), "details": notified}
