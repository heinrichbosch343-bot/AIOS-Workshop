"""The warmup filter: the Sieve script, the ManageSieve conversation, and the Inbox tidy. No network."""
from __future__ import annotations

import base64
import io

import pytest

from reply_agent import warmup_filter as wf

TAGS = ("cedar-upstairs", "Forum-Capture", "cedar-upstairs", " thrill-mobile ")


# ---- the script ----------------------------------------------------------------------------------------------------

def test_clean_tags_lowercases_dedups_and_sorts():
    assert wf.clean_tags(TAGS) == ("cedar-upstairs", "forum-capture", "thrill-mobile")


@pytest.mark.parametrize("bad", ['evil"tag', "back\\slash", "two words", "tag]", "-lead", "trail-", "a--b", "x" * 61])
def test_clean_tags_refuses_anything_that_could_break_out_of_a_string(bad):
    with pytest.raises(ValueError):
        wf.clean_tags(["cedar-upstairs", bad])


def test_no_tags_is_an_error_not_an_empty_filter():
    with pytest.raises(ValueError):
        wf.clean_tags(["", "  ", None])


def test_script_files_tagged_mail_by_subject_or_body_and_stops():
    script = wf.warmup_script(TAGS)
    assert script.startswith('require ["body", "fileinto", "mailbox"];\r\n')
    tag_list = '["cedar-upstairs", "forum-capture", "thrill-mobile"]'
    assert f'header :contains "subject" {tag_list}' in script
    assert f"body :text :contains {tag_list}" in script
    assert "anyof (" in script
    assert '\tfileinto :create "Warmup";\r\n\tstop;' in script
    assert script.endswith("}\r\n")
    assert "\n" not in script.replace("\r\n", "")  # every line ends CRLF, as ManageSieve expects
    assert "keep" not in script and "discard" not in script and "redirect" not in script


@pytest.mark.parametrize("folder", ['Warm"up', "a/b", "", " lead", "x" * 41])
def test_script_refuses_an_odd_folder_name(folder):
    with pytest.raises(ValueError):
        wf.warmup_script(TAGS, folder)


# ---- reading server answers ------------------------------------------------------------------------------------------

def test_read_response_collects_lines_until_ok():
    r = wf.read_response(io.BytesIO(b'"one"\r\n"two" ACTIVE\r\nOK "done"\r\nleftover'))
    assert r.status == "OK" and r.lines == (b'"one"\r\n', b'"two" ACTIVE\r\n') and r.message == '"done"'


def test_read_response_reads_a_literal_exactly():
    body = b'require ["fileinto"];\r\nOK this is script text, not a status\r\n'
    r = wf.read_response(io.BytesIO(b"{%d}\r\n" % len(body) + body + b"\r\nOK\r\n"))
    assert r.status == "OK" and r.literal == body


def test_read_response_no_with_a_literal_message():
    r = wf.read_response(io.BytesIO(b"NO {11}\r\nbad syntax!\r\n"))
    assert r.status == "NO" and r.message == "bad syntax!"


def test_read_response_bye_and_lowercase_status():
    assert wf.read_response(io.BytesIO(b'bye "going away"\r\n')).status == "BYE"


@pytest.mark.parametrize("data", [b"", b'"one"\r\n', b"{50}\r\nshort"])
def test_read_response_raises_when_the_connection_ends_early(data):
    with pytest.raises(wf.SieveError):
        wf.read_response(io.BytesIO(data))


def test_read_response_refuses_a_huge_literal():
    with pytest.raises(wf.SieveError):
        wf.read_response(io.BytesIO(b"{99999999}\r\n"))


def test_parse_listing_reads_names_and_the_active_flag():
    lines = [b'"roundcube"\r\n', b'"reply-agent" ACTIVE\r\n', b'"with \\"quote\\""\r\n', b"\r\n", b"junk\r\n"]
    assert wf.parse_listing(lines) == [("roundcube", False), ("reply-agent", True), ('with "quote"', False)]


# ---- what to do ------------------------------------------------------------------------------------------------------

def test_plan_never_replaces_someone_elses_active_filter():
    with pytest.raises(wf.SieveError, match="roundcube"):
        wf.plan([("roundcube", True)], None, "x")


def test_plan_installs_when_nothing_is_there_or_ours_is_off_or_different():
    assert wf.plan([], None, "x") == "install"
    assert wf.plan([("reply-agent", False)], "x", "x") == "install"
    assert wf.plan([("reply-agent", True)], "old", "x") == "install"
    assert wf.plan([("roundcube", False), ("reply-agent", True)], "old", "x") == "install"


def test_plan_leaves_an_identical_active_filter_alone():
    assert wf.plan([("reply-agent", True)], "x", "x") == "unchanged"


# ---- the ManageSieve conversation --------------------------------------------------------------------------------------

class FakeSock:
    """A server: `initial` is readable at once, and each send releases the next of `replies`. With nothing left to read it
    stays quiet (a timeout), or, once `hung_up`, reports a closed connection."""

    def __init__(self, initial: bytes = b"", replies=(), hung_up=False):
        self.buffer = bytearray(initial)
        self.replies = list(replies)
        self.hung_up = hung_up
        self.sent = b""
        self.closed = False
        self.timeout = 30.0

    def recv(self, n):
        if not self.buffer:
            if self.hung_up:
                return b""
            raise wf.socket.timeout("quiet")
        chunk = bytes(self.buffer[:n])
        del self.buffer[:n]
        return chunk

    def sendall(self, data):
        self.sent += data
        if self.replies:
            self.buffer += self.replies.pop(0)

    def gettimeout(self):
        return self.timeout

    def settimeout(self, value):
        self.timeout = value

    def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, tls_sock):
        self.tls_sock = tls_sock
        self.hostname = None

    def wrap_socket(self, sock, server_hostname=None):
        # Bytes still waiting on the plain socket would be read as the start of the handshake and break it.
        assert not sock.buffer, "plain-text bytes were left in the socket before the TLS handshake"
        self.hostname = server_hostname
        return self.tls_sock


def _wire(monkeypatch, plain: FakeSock, tls: FakeSock):
    ctx = FakeContext(tls)
    monkeypatch.setattr(wf.socket, "create_connection", lambda addr, timeout=None: plain)
    monkeypatch.setattr(wf, "verifying_context", lambda: ctx)
    return ctx


GREETING = b'"IMPLEMENTATION" "Test"\r\n"STARTTLS"\r\nOK\r\n'
CAPS = b'"SIEVE" "body fileinto mailbox"\r\n"SASL" "PLAIN"\r\nOK\r\n'
TOKEN = base64.b64encode(b"%sinbox@example.com%ss3cret" % (bytes(1), bytes(1))).decode()


def test_connect_like_purelymail_capabilities_in_plain_text_after_starttls(monkeypatch):
    # Apache ManageSieve sends its capabilities unencrypted right after "OK" to STARTTLS, and nothing after the handshake.
    plain = FakeSock(GREETING, replies=[b"OK\r\n" + CAPS])
    tls = FakeSock(replies=[b"OK authentication successful\r\n"])
    ctx = _wire(monkeypatch, plain, tls)
    wf.ManageSieve("imap.example.com").connect("inbox@example.com", "s3cret")
    assert plain.sent == b"STARTTLS\r\n"  # nothing secret ever goes over the plain connection
    assert ctx.hostname == "imap.example.com"
    assert tls.sent == f'AUTHENTICATE "PLAIN" "{TOKEN}"\r\n'.encode()


def test_connect_like_the_standard_capabilities_resent_over_tls(monkeypatch):
    plain = FakeSock(GREETING, replies=[b"OK begin TLS\r\n"])
    tls = FakeSock(CAPS, replies=[b"OK logged in\r\n", b'"reply-agent" ACTIVE\r\nOK\r\n'])
    _wire(monkeypatch, plain, tls)
    client = wf.ManageSieve("imap.example.com")
    client.connect("inbox@example.com", "s3cret")
    assert tls.sent == f'AUTHENTICATE "PLAIN" "{TOKEN}"\r\n'.encode()
    # The capability block was read on its own, so every later answer lines up with its own command.
    assert client.list_scripts() == [("reply-agent", True)]


def test_plain_text_after_starttls_never_counts_as_the_login_answer(monkeypatch):
    # A forged "OK" slipped in before encryption must be thrown away, so the refusal that comes over TLS is what counts.
    plain = FakeSock(GREETING, replies=[b"OK\r\nOK authentication successful\r\n"])
    tls = FakeSock(replies=[b'NO "authentication failed"\r\n'])
    _wire(monkeypatch, plain, tls)
    with pytest.raises(wf.SieveError, match="login"):
        wf.ManageSieve("imap.example.com").connect("inbox@example.com", "s3cret")


def test_a_server_that_never_stops_talking_before_tls_is_refused(monkeypatch):
    plain = FakeSock(GREETING, replies=[b"OK\r\n" + b"x" * 70_000])
    tls = FakeSock()
    _wire(monkeypatch, plain, tls)
    with pytest.raises(wf.SieveError, match="will not stop"):
        wf.ManageSieve("imap.example.com").connect("u", "s3cret")
    assert tls.sent == b""


def test_a_refused_starttls_never_sends_the_password(monkeypatch):
    plain = FakeSock(GREETING, replies=[b"NO no TLS today\r\n"])
    tls = FakeSock()
    _wire(monkeypatch, plain, tls)
    with pytest.raises(wf.SieveError, match="STARTTLS"):
        wf.ManageSieve("imap.example.com").connect("u", "s3cret")
    assert b"s3cret" not in plain.sent and tls.sent == b""


def test_a_refused_login_does_not_echo_the_token(monkeypatch):
    plain = FakeSock(GREETING, replies=[b"OK\r\n"])
    tls = FakeSock(replies=[b'NO "authentication failed"\r\n'])
    _wire(monkeypatch, plain, tls)
    with pytest.raises(wf.SieveError) as err:
        wf.ManageSieve("imap.example.com").connect("inbox@example.com", "s3cret")
    assert TOKEN not in str(err.value) and "s3cret" not in str(err.value)


def test_a_hang_up_while_waiting_for_tls_is_an_error(monkeypatch):
    plain = FakeSock(GREETING, replies=[b"OK\r\n"], hung_up=True)
    _wire(monkeypatch, plain, FakeSock())
    with pytest.raises(wf.SieveError, match="closed"):
        wf.ManageSieve("imap.example.com").connect("u", "s3cret")


def _logged_in(server_says: bytes) -> tuple[wf.ManageSieve, FakeSock]:
    sock = FakeSock(server_says, hung_up=True)
    client = wf.ManageSieve("imap.example.com")
    client._attach(sock)
    return client, sock


def test_install_on_an_empty_mailbox_checks_saves_and_switches_on():
    client, sock = _logged_in(b"OK\r\n" + b"OK\r\n" + b"OK\r\n" + b"OK\r\n")
    assert wf.install(client, TAGS) == "installed"
    script = wf.warmup_script(TAGS).encode()
    assert sock.sent == (b"LISTSCRIPTS\r\n"
                         + b"CHECKSCRIPT {%d+}\r\n" % len(script) + script + b"\r\n"
                         + b'PUTSCRIPT "reply-agent" {%d+}\r\n' % len(script) + script + b"\r\n"
                         + b'SETACTIVE "reply-agent"\r\n')


def test_install_again_with_the_same_tags_changes_nothing():
    script = wf.warmup_script(TAGS).encode()
    client, sock = _logged_in(b'"reply-agent" ACTIVE\r\nOK\r\n' + b"{%d}\r\n" % len(script) + script + b"\r\nOK\r\n")
    assert wf.install(client, TAGS) == "unchanged"
    assert b"PUTSCRIPT" not in sock.sent and b"SETACTIVE" not in sock.sent


def test_install_dry_reads_but_writes_nothing():
    client, sock = _logged_in(b"OK\r\n")
    assert wf.install(client, TAGS, dry=True) == "would install"
    assert sock.sent == b"LISTSCRIPTS\r\n"


def test_install_stops_when_another_filter_set_is_active():
    client, sock = _logged_in(b'"roundcube" ACTIVE\r\nOK\r\n')
    with pytest.raises(wf.SieveError):
        wf.install(client, TAGS)
    assert b"PUTSCRIPT" not in sock.sent and b"SETACTIVE" not in sock.sent


def test_a_script_the_server_rejects_is_never_saved_or_switched_on():
    client, sock = _logged_in(b"OK\r\n" + b'NO "line 3: unknown test"\r\n')
    with pytest.raises(wf.SieveError, match="unknown test"):
        wf.install(client, TAGS)
    assert b"PUTSCRIPT" not in sock.sent


def test_logout_closes_even_when_the_server_has_gone():
    client, sock = _logged_in(b"")
    client.logout()
    assert sock.closed and client._sock is None
    client.logout()  # a second call is harmless


# ---- tidying the Inbox ------------------------------------------------------------------------------------------------

class FakeConn:
    """A logged-in imaplib connection. Anything but create, subscribe, select, search and one MOVE is a failure."""

    def __init__(self, hits: dict[tuple[str, str], list[int]], move_status="OK"):
        self.hits, self.move_status = hits, move_status
        self.calls = []

    def create(self, name):
        self.calls.append(("create", name))
        return "NO", [b"exists"]

    def subscribe(self, name):
        self.calls.append(("subscribe", name))
        return "OK", [b""]

    def select(self, name, readonly=False):
        self.calls.append(("select", name, readonly))
        return "OK", [b"3"]

    def uid(self, command, *args):
        command = command.lower()
        if command == "search":
            _, key, value = args
            ids = self.hits.get((key, value.strip('"')), [])
            return "OK", [" ".join(map(str, ids)).encode()]
        if command == "move":
            self.calls.append(("move",) + args)
            return self.move_status, [b"moved"]
        raise AssertionError(f"the tidy must never call uid {command}")

    def __getattr__(self, name):
        raise AssertionError(f"the tidy must never call {name}")


def test_tidy_moves_every_tagged_message_in_one_move():
    conn = FakeConn({("BODY", "cedar-upstairs"): [5, 12], ("BODY", "forum-capture"): [12, 7], ("SUBJECT", "thrill-mobile"): [30]})
    assert wf.tidy_inbox(conn, TAGS) == 4
    assert ("create", '"Warmup"') in conn.calls and ("subscribe", '"Warmup"') in conn.calls
    assert ("select", '"INBOX"', False) in conn.calls
    assert [c for c in conn.calls if c[0] == "move"] == [("move", "5,7,12,30", '"Warmup"')]


def test_tidy_dry_only_counts():
    conn = FakeConn({("BODY", "cedar-upstairs"): [5]})
    assert wf.tidy_inbox(conn, TAGS, dry=True) == 1
    assert conn.calls == [("select", '"INBOX"', True)]


def test_tidy_with_nothing_to_move_moves_nothing():
    conn = FakeConn({})
    assert wf.tidy_inbox(conn, TAGS) == 0
    assert not [c for c in conn.calls if c[0] == "move"]


def test_tidy_reports_a_refused_move():
    with pytest.raises(RuntimeError, match="could not move"):
        wf.tidy_inbox(FakeConn({("BODY", "cedar-upstairs"): [5]}, move_status="NO"), TAGS)
