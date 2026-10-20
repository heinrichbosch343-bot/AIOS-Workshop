"""Keep PlusVibe warmup mail out of the tracking mailbox's Inbox.

Two parts, both run by `python -m reply_agent warmup-filter`:

- A Sieve filter on the tracking mailbox. Purelymail runs a mailbox's filter on every message that enters it, copies
  made by a routing rule included, so warmup mail goes straight into its own folder, even while the agent is not
  running. It is written over ManageSieve (RFC 5804, port 4190), the same store webmail's Filters page edits.
- A tidy that moves warmup mail already sitting in the Inbox into that folder. Moving is the only thing it does: nothing
  is flagged, deleted or expunged, and a person can move a message back.

Warmup mail carries a two-word tag (one per campaign mailbox, listed in the local config) and real replies never do.
The agent's own rule still ignores tagged mail, so anything the filter misses is still never answered.
"""
from __future__ import annotations

import base64
import re
import socket
from dataclasses import dataclass

from .tls import verifying_context

FOLDER = "Warmup"
SCRIPT_NAME = "reply-agent"
SIEVE_PORT = 4190
MAX_LITERAL = 1_000_000  # bytes; a filter script is a few hundred

_TAG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_FOLDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,39}")
_SCRIPT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")
_STATUS = re.compile(rb"^(OK|NO|BYE)\b", re.I)
_LITERAL = re.compile(rb"\{(\d+)\+?\}\r?\n$")
_LISTED = re.compile(r'^"((?:[^"\\]|\\.)*)"(\s+ACTIVE)?\s*$', re.I)


class SieveError(RuntimeError):
    """The filter server said no, or answered with something we do not understand."""


@dataclass(frozen=True)
class Response:
    status: str            # OK, NO or BYE
    lines: tuple[bytes, ...]
    literal: bytes         # data sent as {n} literals before the status line (GETSCRIPT's script)
    message: str           # the text after the status word


def clean_tags(tags) -> tuple[str, ...]:
    """The warmup tags, lowercased, de-duplicated and sorted. Anything that is not plain letters, digits and dashes is refused,
    because it is written into a Sieve string and an IMAP search."""
    out = sorted({str(t).strip().lower() for t in tags if t and str(t).strip()})
    if not out:
        raise ValueError("there are no warmup tags in the config, so there is nothing to filter on")
    bad = [t for t in out if len(t) > 60 or not _TAG.fullmatch(t)]
    if bad:
        raise ValueError(f"a warmup tag must be plain letters, digits and dashes, got {bad!r}")
    return tuple(out)


def _check_folder(folder: str) -> str:
    if not _FOLDER.fullmatch(folder or ""):
        raise ValueError(f"folder name must be plain letters, digits, spaces, dots and dashes, got {folder!r}")
    return folder


def warmup_script(tags, folder: str = FOLDER) -> str:
    """The Sieve script: mail whose subject or body holds any warmup tag is filed into `folder`, and kept nowhere else."""
    quoted = ", ".join(f'"{t}"' for t in clean_tags(tags))
    lines = (
        'require ["body", "fileinto", "mailbox"];',
        "# rule:[PlusVibe warmup]",
        f'if anyof (header :contains "subject" [{quoted}], body :text :contains [{quoted}])',
        "{",
        f'\tfileinto :create "{_check_folder(folder)}";',
        "\tstop;",
        "}",
    )
    return "\r\n".join(lines) + "\r\n"


def read_response(stream) -> Response:
    """Read one complete server response. `stream` needs readline(limit) and read(n), like a socket's makefile("rb")."""
    lines: list[bytes] = []
    literal = b""
    while True:
        line = stream.readline(65536)
        if not line:
            raise SieveError("the filter server closed the connection")
        status = _STATUS.match(line)
        found = _LITERAL.search(line)
        if found:
            size = int(found.group(1))
            if size > MAX_LITERAL:
                raise SieveError(f"the filter server sent {size} bytes at once, more than a filter can be")
            data = stream.read(size)
            if len(data) != size:
                raise SieveError("the filter server closed the connection")
            if status:  # NO {12}<CRLF>message: the message itself came as a literal
                return Response(status.group(1).decode().upper(), tuple(lines), literal,
                                data.decode("utf-8", "replace").strip())
            literal += data
            continue
        if status:
            message = line[status.end():].decode("utf-8", "replace").strip()
            return Response(status.group(1).decode().upper(), tuple(lines), literal, message)
        lines.append(line)


def parse_listing(lines) -> list[tuple[str, bool]]:
    """LISTSCRIPTS lines into (name, active) pairs."""
    out = []
    for raw in lines:
        found = _LISTED.match(raw.decode("utf-8", "replace").strip())
        if found:
            out.append((re.sub(r"\\(.)", r"\1", found.group(1)), bool(found.group(2))))
    return out


def plan(listing, current: str | None, wanted: str, name: str = SCRIPT_NAME) -> str:
    """'unchanged' or 'install'. Only one filter set can be active, so someone else's active set is never replaced."""
    others = [n for n, active in listing if active and n != name]
    if others:
        raise SieveError(f"another filter set, {others[0]!r}, is already active on this mailbox. Only one can be active, "
                         "so add the warmup rule to it by hand (webmail, Settings, Filters) rather than replacing it.")
    ours_active = any(n == name and active for n, active in listing)
    return "unchanged" if ours_active and current == wanted else "install"


class _Reader:
    """readline and read over a socket with our own buffer, plus the two timed peeks STARTTLS needs."""

    MAX_DRAIN = 65_536

    def __init__(self, sock):
        self.sock, self.buf = sock, bytearray()

    def _fill(self) -> bool:
        chunk = self.sock.recv(4096)
        if chunk:
            self.buf += chunk
        return bool(chunk)

    def readline(self, limit: int = 65536) -> bytes:
        while b"\n" not in self.buf and len(self.buf) < limit and self._fill():
            pass
        end = self.buf.find(b"\n")
        end = min(len(self.buf) if end < 0 else end + 1, limit)
        line = bytes(self.buf[:end])
        del self.buf[:end]
        return line

    def read(self, n: int) -> bytes:
        while len(self.buf) < n and self._fill():
            pass
        data = bytes(self.buf[:n])
        del self.buf[:n]
        return data

    def _recv_within(self, wait: float) -> bytes | None:
        """What arrives within `wait` seconds: bytes, b"" when the server hung up, None when it stayed quiet."""
        old = self.sock.gettimeout()
        self.sock.settimeout(wait)
        try:
            return self.sock.recv(4096)
        except socket.timeout:
            return None
        finally:
            self.sock.settimeout(old)

    def drain(self, quiet: float) -> None:
        """Throw away what the server sends until it has been quiet for `quiet` seconds."""
        thrown = len(self.buf)
        self.buf.clear()
        while (chunk := self._recv_within(quiet)) is not None:
            thrown += len(chunk)
            if not chunk:
                raise SieveError("the filter server closed the connection")
            if thrown > self.MAX_DRAIN:
                raise SieveError("the filter server will not stop talking before encryption starts")

    def has_data(self, wait: float) -> bool:
        if self.buf:
            return True
        chunk = self._recv_within(wait)
        if chunk == b"":
            raise SieveError("the filter server closed the connection")
        if chunk:
            self.buf += chunk
        return bool(chunk)


class ManageSieve:
    """Just enough of a ManageSieve client: STARTTLS with a checked certificate, PLAIN login, list, get, check, put, activate."""

    QUIET = 1.0  # seconds of silence that end what the server says around STARTTLS

    def __init__(self, host: str, port: int = SIEVE_PORT, timeout: float = 30.0):
        self.host, self.port, self.timeout = host, port, timeout
        self._sock = None
        self._file: _Reader | None = None

    def _attach(self, sock) -> None:
        self._sock = sock
        self._file = _Reader(sock)

    def _send(self, data: bytes) -> None:
        self._sock.sendall(data)

    def _expect(self, what: str) -> Response:
        response = read_response(self._file)
        if response.status != "OK":
            raise SieveError(f"{what} refused: {response.status} {response.message[:200]}")
        return response

    def connect(self, user: str, password: str) -> None:
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._attach(sock)
        self._expect("greeting")
        self._send(b"STARTTLS\r\n")
        self._expect("STARTTLS")
        # Purelymail's server (Apache ManageSieve) sends its capability list here, unencrypted, BEFORE the handshake.
        # Left in the socket it would be read as the start of the handshake, so it is thrown away unread: nothing said
        # before encryption is trusted.
        self._file.drain(self.QUIET)
        self._attach(verifying_context().wrap_socket(sock, server_hostname=self.host))
        # The standard (RFC 5804) has the server re-send its capabilities over TLS on its own; Purelymail's does not.
        # Read them only if they come, so either kind of server stays in step.
        if self._file.has_data(self.QUIET):
            self._expect("capabilities after STARTTLS")
        token = base64.b64encode(b"%s%s%s%s" % (bytes(1), user.encode(), bytes(1), password.encode())).decode()
        self._send(f'AUTHENTICATE "PLAIN" "{token}"\r\n'.encode())
        self._expect("login")  # the error never carries the token: it is built from the server's answer only

    def list_scripts(self) -> list[tuple[str, bool]]:
        self._send(b"LISTSCRIPTS\r\n")
        return parse_listing(self._expect("listing filters").lines)

    def get_script(self, name: str) -> str:
        self._send(f'GETSCRIPT "{_safe_name(name)}"\r\n'.encode())
        return self._expect(f"reading filter {name!r}").literal.decode("utf-8", "replace")

    def _with_literal(self, command: str, text: str) -> bytes:
        data = text.encode("utf-8")
        return f"{command} {{{len(data)}+}}\r\n".encode() + data + b"\r\n"

    def check_script(self, text: str) -> None:
        self._send(self._with_literal("CHECKSCRIPT", text))
        self._expect("checking the filter")

    def put_script(self, name: str, text: str) -> None:
        self._send(self._with_literal(f'PUTSCRIPT "{_safe_name(name)}"', text))
        self._expect(f"saving filter {name!r}")

    def set_active(self, name: str) -> None:
        self._send(f'SETACTIVE "{_safe_name(name)}"\r\n'.encode())
        self._expect(f"switching on filter {name!r}")

    def logout(self) -> None:
        if self._sock is None:
            return
        try:
            self._send(b"LOGOUT\r\n")
            read_response(self._file)
        except (OSError, SieveError):
            pass
        finally:
            try:
                self._sock.close()
            finally:
                self._sock = self._file = None


def _safe_name(name: str) -> str:
    if not _SCRIPT_NAME.fullmatch(name or ""):
        raise ValueError(f"filter name must be plain letters, digits, dots and dashes, got {name!r}")
    return name


def install(client: ManageSieve, tags, folder: str = FOLDER, name: str = SCRIPT_NAME, dry: bool = False) -> str:
    """Put the warmup filter on a logged-in client and switch it on. Returns 'unchanged', 'installed' or 'would install'."""
    wanted = warmup_script(tags, folder)
    listing = client.list_scripts()
    current = client.get_script(name) if any(n == name for n, _ in listing) else None
    if plan(listing, current, wanted, name) == "unchanged":
        return "unchanged"
    if dry:
        return "would install"
    client.check_script(wanted)
    client.put_script(name, wanted)
    client.set_active(name)
    return "installed"


def tidy_inbox(conn, tags, folder: str = FOLDER, dry: bool = False) -> int:
    """Move warmup mail already in the Inbox into `folder`; returns how many messages that is (or would be, when dry).

    `conn` is a logged-in imaplib connection. The server does the searching, on the subject and the body.
    """
    clean = clean_tags(tags)
    target = f'"{_check_folder(folder)}"'
    if not dry:
        conn.create(target)      # answers NO when the folder is already there, which is fine
        conn.subscribe(target)   # so webmail and mail apps show it
    status, _ = conn.select('"INBOX"', readonly=dry)
    if status != "OK":
        raise RuntimeError("could not open the Inbox")
    found: set[bytes] = set()
    for tag in clean:
        for key in ("SUBJECT", "BODY"):
            status, data = conn.uid("search", None, key, f'"{tag}"')
            if status == "OK" and data and data[0]:
                found.update(data[0].split())
    if not found or dry:
        return len(found)
    uids = b",".join(sorted(found, key=int)).decode()
    status, detail = conn.uid("move", uids, target)
    if status != "OK":
        raise RuntimeError(f"could not move the warmup mail: {status} {detail!r}"[:300])
    return len(found)
