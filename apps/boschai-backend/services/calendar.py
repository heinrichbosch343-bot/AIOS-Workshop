"""
Google Calendar (read-only) for the connected account — Heinrich's meetings account.

Feeds the daily brief ("you have a meeting at 10:00 with …") and powers the
list_calendar_events agent tool. Fails soft to an empty list if the calendar
scope hasn't been granted yet (re-auth pending) or the API errors.
"""
import datetime
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from services.drive import get_credentials

TZ = ZoneInfo("Africa/Johannesburg")


def _service():
    return build("calendar", "v3", credentials=get_credentials())


def _format(event: dict) -> dict:
    start = event.get("start", {})
    dt = start.get("dateTime")
    if dt:
        when = datetime.datetime.fromisoformat(dt).astimezone(TZ)
        time_str = when.strftime("%H:%M")
        date_str = when.strftime("%a %d %b")
    else:  # all-day event
        time_str = "all day"
        date_str = start.get("date", "")
    attendees = [
        a.get("displayName") or a.get("email", "")
        for a in event.get("attendees", []) if not a.get("self")
    ]
    return {
        "time": time_str,
        "date": date_str,
        "title": event.get("summary", "(no title)"),
        "with": [a for a in attendees if a][:6],
        "location": event.get("location", ""),
    }


def _list(time_min: datetime.datetime, time_max: datetime.datetime, limit: int = 20) -> list[dict]:
    try:
        res = _service().events().list(
            calendarId="primary",
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=limit,
        ).execute()
        return [_format(e) for e in res.get("items", [])]
    except Exception:
        return []  # scope not granted yet / API error -> treat as no calendar


def today_events() -> list[dict]:
    """Meetings for the rest of today (from now to midnight, SAST)."""
    now = datetime.datetime.now(TZ)
    end = now.replace(hour=23, minute=59, second=59, microsecond=0)
    return _list(now, end)


def upcoming_events(days: int = 7) -> list[dict]:
    """Meetings from now through the next `days` days."""
    now = datetime.datetime.now(TZ)
    return _list(now, now + datetime.timedelta(days=max(1, days)))
