"""
Extract a lead list from a Google Takeout Sent.mbox file.

Parses every sent email, pulls out each recipient (To + Cc), deduplicates by
email address, and writes a clean CSV ready for outreach tools (Instantly,
Apollo, etc.).

Usage:
    python scripts/extract_leads_from_mbox.py <path-to-mbox> <output-csv>
"""

import sys
import csv
import re
import mailbox
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime
from collections import OrderedDict


# Addresses we never want in an outreach list (automated / noise senders).
JUNK_PATTERNS = re.compile(
    r"(no[-_.]?reply|do[-_.]?not[-_.]?reply|notifications?@|mailer-daemon|"
    r"postmaster@|bounce|@.*\.(calendar|mail-noreply)|googlegroups\.com|"
    r"automated|support@|billing@|receipts?@|@email\.|@e\.|@mailer\.|"
    r"@bounces?\.|@reply\.|unsubscribe|@sentry\.|@github\.com|@slack\.com|"
    r"@stripe\.com|@paypal\.|@amazon|@google\.com|@accounts\.google|"
    r"intercom-mail|@mail\.|@support\.|@snov\.io|hostinger|team@|"
    r"welcome@|hello@mail\.|@.*\.intercom)",
    re.IGNORECASE,
)

# Subjects that signal a throwaway / test email rather than real outreach.
TEST_SUBJECTS = re.compile(r"^\s*(wad|asd|qwe|test|aaa+|xxx+|\.+)\s*\w*\s*$", re.IGNORECASE)


def clean_header(raw):
    """Decode a MIME-encoded header into a plain unicode string."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except Exception:
        return str(raw).strip()


def clean_name(name, email_addr):
    """Tidy a display name; fall back to the email's local part if empty."""
    name = clean_header(name).strip().strip('"').strip("'").strip()
    # Drop names that are just the email address repeated.
    if name.lower() == email_addr.lower():
        name = ""
    if not name:
        local = email_addr.split("@")[0]
        # Turn "john.smith" / "john_smith" into "John Smith".
        name = re.sub(r"[._-]+", " ", local).title()
    return name


def is_valid_lead(email_addr, own_domains=()):
    """Filter out blanks, malformed addresses, own domains, and automated senders."""
    if not email_addr or "@" not in email_addr:
        return False
    if JUNK_PATTERNS.search(email_addr):
        return False
    if email_addr.split("@")[1] in own_domains:
        return False
    # Basic shape check.
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_addr):
        return False
    return True


def main():
    if len(sys.argv) < 3:
        print("Usage: python extract_leads_from_mbox.py <mbox> <output.csv>")
        sys.exit(1)

    mbox_path = sys.argv[1]
    out_path = sys.argv[2]
    # Optional 3rd arg: comma-separated exclusions. Entries with "@" are treated
    # as exact addresses; entries without "@" are treated as whole domains.
    own_addrs = set()
    own_domains = set()
    if len(sys.argv) > 3:
        for entry in sys.argv[3].split(","):
            entry = entry.strip().lower()
            if not entry:
                continue
            (own_addrs if "@" in entry else own_domains).add(entry)

    print(f"Opening mailbox: {mbox_path}")
    mbox = mailbox.mbox(mbox_path)

    leads = OrderedDict()  # email -> aggregated record
    total_msgs = 0
    total_recipients = 0
    skipped_junk = 0

    for message in mbox:
        total_msgs += 1

        subject = re.sub(r"\s+", " ", clean_header(message.get("Subject", ""))).strip()

        # Skip obvious test/throwaway emails.
        if TEST_SUBJECTS.match(subject):
            continue

        # Parse the send date.
        date_raw = message.get("Date", "")
        try:
            dt = parsedate_to_datetime(date_raw)
            date_str = dt.strftime("%Y-%m-%d") if dt else ""
            sort_key = dt.timestamp() if dt else 0
        except Exception:
            date_str = ""
            sort_key = 0

        # Collect recipients from To and Cc.
        recipients = []
        for hdr in ("To", "Cc"):
            recipients.extend(getaddresses(message.get_all(hdr, [])))

        for raw_name, raw_email in recipients:
            email_addr = raw_email.strip().lower()
            total_recipients += 1

            if email_addr in own_addrs:
                continue
            if not is_valid_lead(email_addr, own_domains):
                skipped_junk += 1
                continue

            name = clean_name(raw_name, email_addr)

            if email_addr not in leads:
                leads[email_addr] = {
                    "name": name,
                    "email": email_addr,
                    "company_domain": email_addr.split("@")[1],
                    "times_emailed": 0,
                    "first_contacted": date_str,
                    "last_contacted": date_str,
                    "last_subject": subject,
                    "_first_sort": sort_key,
                    "_last_sort": sort_key,
                }

            rec = leads[email_addr]
            rec["times_emailed"] += 1

            # Prefer a real display name if we later find one.
            if (not rec["name"] or rec["name"] == email_addr.split("@")[0].title()) and name:
                rec["name"] = name

            # Track earliest and latest contact.
            if sort_key and sort_key < rec["_first_sort"]:
                rec["_first_sort"] = sort_key
                rec["first_contacted"] = date_str
            if sort_key and sort_key >= rec["_last_sort"]:
                rec["_last_sort"] = sort_key
                rec["last_contacted"] = date_str
                rec["last_subject"] = subject

    # Sort: most-emailed first (warmest leads at the top).
    ordered = sorted(
        leads.values(),
        key=lambda r: (r["times_emailed"], r["_last_sort"]),
        reverse=True,
    )

    fields = [
        "name",
        "email",
        "company_domain",
        "times_emailed",
        "first_contacted",
        "last_contacted",
        "last_subject",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for rec in ordered:
            writer.writerow(rec)

    print("-" * 50)
    print(f"Messages scanned:      {total_msgs:,}")
    print(f"Recipients seen:       {total_recipients:,}")
    print(f"Junk/automated skipped:{skipped_junk:,}")
    print(f"Unique leads exported: {len(ordered):,}")
    print(f"CSV written to:        {out_path}")


if __name__ == "__main__":
    main()
