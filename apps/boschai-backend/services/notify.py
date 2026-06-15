"""Telegram notifications — used to ping Heinrich instantly when something changes."""
import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_telegram(text: str, chat_id: str = None) -> dict:
    """Send a Telegram message to Heinrich. Returns Telegram's API response."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id or TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = httpx.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()
