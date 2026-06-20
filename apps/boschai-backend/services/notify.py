"""Telegram notifications — used to ping Heinrich instantly when something changes."""
import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram(text: str, chat_id: str = None, message_thread_id: int = None) -> dict:
    """Send a Telegram message to Heinrich. Returns Telegram's API response.

    `message_thread_id` targets a specific topic (tab) inside a group with Topics
    enabled — e.g. the BoschAI group's "Daily Brief" tab. Leave it None to post to a
    DM or a group's General tab.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id or TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if message_thread_id is not None:
        payload["message_thread_id"] = message_thread_id
    resp = httpx.post(url, json=payload, timeout=15)
    if resp.status_code != 200:
        # Surface Telegram's actual reason WITHOUT leaking the bot token, which is baked
        # into the request URL (httpx's own error string would include it).
        try:
            reason = resp.json().get("description", resp.text)
        except Exception:
            reason = resp.text
        raise RuntimeError(f"Telegram error {resp.status_code}: {reason}")
    return resp.json()
