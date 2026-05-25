"""
DataOS — Gmail Email Collector

Fetches emails from Gmail via IMAP and stores to data.db.
Requires GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env.

To get an App Password:
  1. Go to myaccount.google.com/security
  2. Enable 2-Step Verification if not already on
  3. Search "App Passwords" → create one for "Mail"
  4. Paste the 16-character password as GMAIL_APP_PASSWORD in .env

Tables created: emails
"""

import email as email_lib
import email.header
import email.utils
import imaplib
import os
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def collect():
    """Fetch recent emails from Gmail via IMAP."""
    address = os.environ.get("GMAIL_ADDRESS", "").strip()
    app_password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

    if not address or not app_password:
        return {
            "source": "gmail",
            "status": "skipped",
            "reason": "GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set in .env",
        }

    since_date = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(address, app_password)
        mail.select("INBOX", readonly=True)

        _, data = mail.search(None, f'SINCE "{since_date}"')
        msg_ids = data[0].split() if data[0] else []

        emails = []
        for msg_id in msg_ids:
            try:
                _, msg_data = mail.fetch(msg_id, "(RFC822 FLAGS)")
                if not msg_data or not msg_data[0]:
                    continue

                flags_raw = msg_data[0][0]
                is_read = 1 if b"\\Seen" in flags_raw else 0
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                message_id = msg.get("Message-ID", "").strip()
                subject = _decode(msg.get("Subject", "(No Subject)"))
                from_raw = _decode(msg.get("From", ""))
                from_name, from_addr = email.utils.parseaddr(from_raw)

                try:
                    parsed_date = email.utils.parsedate_to_datetime(msg.get("Date", ""))
                    email_date = parsed_date.strftime("%Y-%m-%d")
                except Exception:
                    email_date = datetime.now().strftime("%Y-%m-%d")

                emails.append({
                    "message_id": message_id or f"no-id-{msg_id.decode()}",
                    "date": email_date,
                    "from_address": from_addr,
                    "from_name": from_name,
                    "subject": subject,
                    "snippet": _get_snippet(msg),
                    "has_attachment": _has_attachment(msg),
                    "is_read": is_read,
                })
            except Exception:
                continue

        mail.logout()
        return {"source": "gmail", "status": "success", "data": {"emails": emails}}

    except imaplib.IMAP4.error as e:
        return {
            "source": "gmail",
            "status": "error",
            "reason": f"IMAP login failed — check credentials ({e})",
        }
    except Exception as e:
        return {"source": "gmail", "status": "error", "reason": str(e)}


def write(conn, result, date):
    """Write emails to database. Returns records written."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS emails (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id  TEXT UNIQUE,
            date        TEXT,
            from_address TEXT,
            from_name   TEXT,
            subject     TEXT,
            snippet     TEXT,
            has_attachment INTEGER DEFAULT 0,
            is_read     INTEGER DEFAULT 0,
            collected_at TEXT
        )
    """)

    if result.get("status") != "success":
        conn.commit()
        return 0

    emails = result["data"].get("emails", [])
    collected_at = datetime.now(timezone.utc).isoformat()
    records = 0

    for e in emails:
        try:
            conn.execute("""
                INSERT OR IGNORE INTO emails
                (message_id, date, from_address, from_name, subject, snippet,
                 has_attachment, is_read, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                e["message_id"], e["date"], e["from_address"], e["from_name"],
                e["subject"], e["snippet"], e["has_attachment"], e["is_read"],
                collected_at,
            ))
            records += 1
        except Exception:
            pass

    conn.commit()
    return records


def _decode(val):
    if not val:
        return ""
    parts = email.header.decode_header(val)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def _get_snippet(msg, max_chars=250):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                try:
                    text = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                    return " ".join(text.split())[:max_chars]
                except Exception:
                    pass
    else:
        try:
            text = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
            return " ".join(text.split())[:max_chars]
        except Exception:
            pass
    return ""


def _has_attachment(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_filename():
                return 1
    return 0


if __name__ == "__main__":
    result = collect()
    print(f"Status: {result['status']}")
    if result["status"] == "success":
        emails = result["data"]["emails"]
        print(f"Fetched: {len(emails)} emails")
        for e in emails[:10]:
            read = "✓" if e["is_read"] else "●"
            print(f"  {read} [{e['date']}] {e['from_name'] or e['from_address']}: {e['subject'][:55]}")
    else:
        print(f"Reason: {result.get('reason')}")
