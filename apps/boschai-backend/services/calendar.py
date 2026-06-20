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
    guests = [a for a in event.get("attendees", []) if not a.get("self")]
    attendees = [a.get("displayName") or a.get("email", "") for a in guests]
    emails = [a.get("email", "") for a in guests if a.get("email")]
    return {
        "time": time_str,
        "date": date_str,
        "title": event.get("summary", "(no title)"),
        "with": [a for a in attendees if a][:6],
        "emails": emails[:6],
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


def _parse_dt(value: str) -> datetime.datetime:
    """ISO 8601 string -> tz-aware datetime in SAST. A naive value (no offset) is
    assumed to already be SAST."""
    s = (value or "").strip().replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def create_event(title: str, start: str, end: str = None, duration_minutes: int = 30,
                 attendees: list = None, location: str = None,
                 description: str = None) -> dict:
    """Create an event on the primary calendar. `start`/`end` are ISO 8601 strings
    (naive values treated as SAST). With no `end`, the event runs `duration_minutes`.
    Invites `attendees` (emails) if given. Returns a short confirmation dict."""
    try:
        start_dt = _parse_dt(start)
    except Exception:
        return {"created": False, "error": f"Couldn't read the start time '{start}'. Use a date and time."}
    end_dt = None
    if end:
        try:
            end_dt = _parse_dt(end)
        except Exception:
            end_dt = None
    if end_dt is None or end_dt <= start_dt:
        end_dt = start_dt + datetime.timedelta(minutes=max(5, duration_minutes))

    body = {
        "summary": title,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Africa/Johannesburg"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Africa/Johannesburg"},
    }
    guests = [a for a in (attendees or []) if a]
    if guests:
        body["attendees"] = [{"email": a} for a in guests]
    if location:
        body["location"] = location
    if description:
        body["description"] = description

    try:
        created = _service().events().insert(
            calendarId="primary", body=body,
            sendUpdates="all" if guests else "none",
        ).execute()
    except Exception as e:
        msg = str(e)
        if any(t in msg.lower() for t in ("insufficient", "forbidden", "403", "scope")):
            msg = ("Calendar write access isn't granted yet — reconnect Google at "
                   "/auth/google (it now asks for permission to create events).")
        return {"created": False, "error": msg}

    when = start_dt.strftime("%a %d %b %H:%M") + end_dt.strftime("–%H:%M")
    return {
        "created": True,
        "title": title,
        "when": when,
        "attendees": guests,
        "link": created.get("htmlLink", ""),
        "id": created.get("id", ""),
    }
