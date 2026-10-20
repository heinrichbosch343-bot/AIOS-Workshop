"""One place that builds the TLS context for every mail connection.

Python's imaplib and smtplib, given no context, use one that does NOT check the server's certificate or hostname
(verify_mode CERT_NONE). Anyone on the network path could then pose as the mail server and read the password. This
context checks both. truststore uses the operating system's certificate store, which is what keeps it working behind
Windows antivirus that re-signs web traffic.
"""
from __future__ import annotations

import ssl


def verifying_context() -> ssl.SSLContext:
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()
