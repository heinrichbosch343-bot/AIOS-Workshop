"""Command line. Run from the scripts folder:

    uv run --no-project --system-certs --python 3.12 --with python-dotenv --with truststore python -m reply_agent demo
    ... python -m reply_agent once            # read the tracking mailbox once, queue drafts, send nothing
    ... python -m reply_agent watch --live    # keep running; sends only if the config says live AND --live is given
    ... python -m reply_agent review          # drafts waiting, mail needing a person, anything that may have gone wrong
    ... python -m reply_agent approve ID [--file reply.txt] [--force] | skip ID | retry ID | resolve ID
    ... python -m reply_agent settle ID --sent | --not-sent    # close a send nobody could confirm, once you know which it was
    ... python -m reply_agent resolve-kind KIND                # clear every open review item of one kind (a flood)
    ... python -m reply_agent suppressed | suppress ADDRESS | unsuppress ADDRESS | stats
    ... python -m reply_agent warmup-filter [--dry]   # server filter: PlusVibe warmup mail goes into a Warmup folder
    ... python -m reply_agent railway-setup --url https://x.up.railway.app --key KEY   # push settings to the hosted copy
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from . import config as config_mod
from . import review
from .agent import Agent, Outcome
from .llm import ClaudeCli
from .mailbox import FilingSender, ImapSource, SmtpSender
from .rules import Known, load_known
from .samples import SAMPLES, sample_mails
from .store import Store
from .textnorm import strip_controls

_CLEAN_ENV: dict[str, str] | None = None  # the environment before the workspace secrets file was loaded


def _setup_environment() -> None:
    """Fix the Windows TLS quirks, then load the secrets file. The model process is later given the environment from BEFORE this."""
    global _CLEAN_ENV
    try:
        import truststore
        truststore.inject_into_ssl()
    except ImportError:
        pass
    os.environ.pop("SSLKEYLOGFILE", None)  # Norton's device path aborts OpenSSL on Windows
    _CLEAN_ENV = dict(os.environ)
    try:
        from dotenv import load_dotenv
        load_dotenv(config_mod.REPO / ".env")
    except ImportError:
        pass


def _llm() -> ClaudeCli:
    return ClaudeCli(base_env=_CLEAN_ENV)


def resolve_live(flag, cfg: config_mod.Config) -> bool:
    """Sending needs the --live flag AND `live: true` in the config. Anything that is not exactly True does not count."""
    return flag is True and cfg.live is True


def _print(outcome: Outcome) -> None:
    print(f"  {outcome.action:<9} {outcome.category or '-':<15} {strip_controls(outcome.note)}")


def cmd_demo(cfg: config_mod.Config) -> None:
    box = cfg.campaign_mailboxes[0] if cfg.campaign_mailboxes else "heinrich1@boschly.com"
    mails = sample_mails(box)
    known = Known(emails=frozenset(m.from_addr for m in mails))
    demo_cfg = cfg.with_overrides(campaign_mailboxes=cfg.campaign_mailboxes or (box,), tracking_mailbox=cfg.tracking_mailbox or "track@invalid.example")
    agent = Agent(demo_cfg, Store(":memory:"), _llm(), known=known)
    print("DEMO: made-up replies, real model, nothing is sent.\n")
    for (label, *_), mail in zip(SAMPLES, mails):
        print(f"--- {label.upper()}  ({mail.from_name})\n{mail.body}\n")
        outcome = agent.handle(mail)
        _print(outcome)
        if outcome.draft_id:
            row = agent.store.get_draft(outcome.draft_id)
            print("\n" + (row["body"] or "  (no draft: a person handles this one)") + "\n")
        print()


def _connect(cfg: config_mod.Config):
    password = os.environ.get("TRACKING_MAILBOX_PASSWORD", "")
    if not cfg.tracking_mailbox or not password:
        sys.exit("Set tracking_mailbox in outputs/outreach/reply-agent.json and TRACKING_MAILBOX_PASSWORD in the workspace env file.")
    return ImapSource(cfg.imap_host, cfg.tracking_mailbox, password), password


def _agent(cfg: config_mod.Config, live: bool):
    source, password = _connect(cfg)
    sender = FilingSender(SmtpSender(cfg.smtp_host, cfg.tracking_mailbox, password), source) if live else None
    try:
        return Agent(cfg, Store(cfg.db_path), _llm(), sender=sender), source
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(f"Cannot start: {exc}")


def cmd_once(cfg: config_mod.Config, live: bool) -> None:
    agent, source = _agent(cfg, live)
    try:
        outcomes = agent.run_once(source, live=live)
    finally:
        source.close()
    print(f"{len(outcomes)} item(s), live={live}")
    for outcome in outcomes:
        _print(outcome)


def cmd_watch(cfg: config_mod.Config, live: bool, every: int) -> None:
    print(f"watching {cfg.tracking_mailbox} every {every}s, live={live}. Ctrl+C to stop.")
    try:
        while True:
            try:
                cmd_once(cfg, live)
            except Exception as exc:  # noqa: BLE001  a network blip must not end a watcher
                print(f"pass failed: {type(exc).__name__}: {strip_controls(str(exc))[:200]}")
            time.sleep(every)
    except KeyboardInterrupt:
        print("stopped.")


def cmd_review(cfg: config_mod.Config) -> None:
    print(review.review_text(Store(cfg.db_path), cfg))


def cmd_stats(cfg: config_mod.Config, days: int) -> None:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    store = Store(cfg.db_path)
    counts = store.counts_by_category(since)
    print(f"Last {days} days: " + (", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "nothing yet"))
    print(f"Needing a person now: {len(store.drafts('pending')) + len(store.drafts('held'))} draft(s), {len(store.open_attention())} other item(s)")


def cmd_suppressed(cfg: config_mod.Config) -> None:
    rows = Store(cfg.db_path).suppression_rows()
    if not rows:
        print("Nobody is on the do-not-write list.")
        return
    for row in rows:
        print(f"{strip_controls(row['addr']):<45} {strip_controls(row['at'])[:10]}  {strip_controls(row['reason'])}")
    print("\nAdd these to PlusVibe's block list too, so the campaigns stop writing to them as well.")


def cmd_warmup_filter(cfg: config_mod.Config, dry: bool) -> None:
    """Put the warmup filter on the tracking mailbox, then move warmup mail already in its Inbox into the Warmup folder."""
    import imaplib

    from . import warmup_filter as wf
    from .tls import verifying_context

    _, password = _connect(cfg)
    try:
        tags = wf.clean_tags(cfg.warmup_tags)
    except ValueError as exc:
        sys.exit(f"Cannot build the filter: {exc}")
    client = wf.ManageSieve(cfg.imap_host)
    try:
        client.connect(cfg.tracking_mailbox, password)
        result = wf.install(client, tags, dry=dry)
    except (OSError, wf.SieveError) as exc:
        sys.exit(f"Could not set the filter: {strip_controls(str(exc))[:300]}")
    finally:
        client.logout()
    print({"installed": f"Filter is on: warmup mail ({len(tags)} tags) now goes straight into the '{wf.FOLDER}' folder of {cfg.tracking_mailbox}.",
           "unchanged": f"Filter was already on with these {len(tags)} tags. Nothing changed.",
           "would install": f"Would put the filter on {cfg.tracking_mailbox} (dry run, nothing changed):"}[result])
    if dry:
        print(wf.warmup_script(tags))
    conn = imaplib.IMAP4_SSL(cfg.imap_host, 993, ssl_context=verifying_context(), timeout=60)
    try:
        conn.login(cfg.tracking_mailbox, password)
        moved = wf.tidy_inbox(conn, tags, dry=dry)
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
    print(f"{moved} warmup message(s) already in the Inbox " + ("would be moved." if dry else f"moved to '{wf.FOLDER}'."))


def cmd_railway_setup(cfg: config_mod.Config, url: str, key: str) -> None:
    """Push the shareable settings, the private settings, the lead list, the mailbox password and the do-not-write
    list up to the hosted copy, over one authenticated call. Never prints the password."""
    url = url or os.environ.get("REPLY_AGENT_RAILWAY_URL", "")
    key = key or os.environ.get("REPLY_AGENT_KEY", "")
    if not url or not key:
        sys.exit("Need --url and --key (or REPLY_AGENT_RAILWAY_URL and REPLY_AGENT_KEY in the workspace env file).")
    password = os.environ.get("TRACKING_MAILBOX_PASSWORD", "")
    if not password:
        sys.exit("Set TRACKING_MAILBOX_PASSWORD in the workspace env file first.")
    shared = json.loads(config_mod.CONFIG_PATH.read_text(encoding="utf-8")) if config_mod.CONFIG_PATH.exists() else {}
    local = json.loads(config_mod.LOCAL_PATH.read_text(encoding="utf-8")) if config_mod.LOCAL_PATH.exists() else {}
    local = {k: v for k, v in local.items() if k not in ("lead_files", "db_path")}
    if not cfg.lead_files:
        sys.exit("lead_files is empty in the config; there is nothing to send as the lead list.")
    leads = sorted(load_known(cfg).emails)
    suppressed = []
    if os.path.exists(cfg.db_path):
        store = Store(cfg.db_path)
        try:
            suppressed = [{"addr": r["addr"], "reason": r["reason"], "at": r["at"]} for r in store.suppression_rows()]
        finally:
            store.close()
    payload = json.dumps({"shared": shared, "local": local, "leads": leads, "password": password,
                          "suppressed": suppressed}).encode("utf-8")
    request = urllib.request.Request(f"{url.rstrip('/')}/setup?key={key}", data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        sys.exit(f"The host said no ({exc.code}): {strip_controls(detail)}")
    except urllib.error.URLError as exc:
        sys.exit(f"Could not reach {url}: {strip_controls(str(exc.reason))[:200]}")
    print(f"Sent {result['leads']} lead address(es), {result['mailboxes']} mailbox(es), "
         f"{result['suppressed_added']} new do-not-write address(es). "
         f"Replies-are-waiting emails: {'on' if result['notify'] else 'off (set notify_to in the local config)'}.")
    remember_hosted(url, key)
    print(f"Check it worked: {url.rstrip('/')}/ready")


def remember_hosted(url: str, key: str, path=None) -> None:
    """Save where the hosted copy lives (and its key) beside the private config, so the Replies and Systems pages in
    Twenty can read it. Gitignored, like the private config."""
    path = path or config_mod.HOSTED_PATH
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"url": url.rstrip("/"), "key": key}, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="reply_agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    for name in ("once", "watch"):
        p = sub.add_parser(name)
        p.add_argument("--live", action="store_true", help="allow sending (the config must also say live: true)")
        if name == "watch":
            p.add_argument("--every", type=int, default=60)
    sub.add_parser("review")
    sub.add_parser("suppressed")
    p = sub.add_parser("resolve-kind", help="clear every open review item of one kind, for example a flood of 'unverified' ones")
    p.add_argument("kind")
    for name in ("approve", "skip", "retry", "resolve", "settle"):
        p = sub.add_parser(name)
        p.add_argument("id", type=int)
        if name == "approve":
            p.add_argument("--file", help="a text file with an edited reply")
            p.add_argument("--force", action="store_true", help="send even if the checks object or we already replied today")
        if name == "settle":
            outcome = p.add_mutually_exclusive_group(required=True)
            outcome.add_argument("--sent", action="store_true", help="you found out it was delivered")
            outcome.add_argument("--not-sent", action="store_true", help="you found out it was not delivered")
    for name in ("suppress", "unsuppress"):
        p = sub.add_parser(name)
        p.add_argument("address")
        if name == "suppress":
            p.add_argument("--reason", default="by hand")
    p = sub.add_parser("stats")
    p.add_argument("--days", type=int, default=30)
    p = sub.add_parser("warmup-filter", help="file PlusVibe warmup mail into its own folder on the server")
    p.add_argument("--dry", action="store_true", help="show what would change, change nothing")
    p = sub.add_parser("railway-setup", help="push the current settings, leads and do-not-write list to the hosted copy")
    p.add_argument("--url", default="", help="the hosted service's address, or set REPLY_AGENT_RAILWAY_URL")
    p.add_argument("--key", default="", help="the shared key it checks ?key= against, or set REPLY_AGENT_KEY")
    args = parser.parse_args(argv)

    # Mail holds emoji and other characters a Windows console, or a pipe, may not encode: print them as "?" rather than crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    _setup_environment()
    try:
        cfg = config_mod.load()
    except ValueError as exc:
        sys.exit(f"Config problem in outputs/outreach/reply-agent.json: {exc}")
    asked = getattr(args, "live", False)
    live = resolve_live(asked, cfg)
    if asked and not live:
        print("--live given but the config says live: false, so nothing will be sent.")

    if args.cmd == "demo":
        cmd_demo(cfg)
    elif args.cmd == "once":
        cmd_once(cfg, live)
    elif args.cmd == "watch":
        cmd_watch(cfg, live, args.every)
    elif args.cmd == "review":
        cmd_review(cfg)
    elif args.cmd == "stats":
        cmd_stats(cfg, args.days)
    elif args.cmd == "suppressed":
        cmd_suppressed(cfg)
    elif args.cmd == "warmup-filter":
        cmd_warmup_filter(cfg, args.dry)
    elif args.cmd == "railway-setup":
        cmd_railway_setup(cfg, args.url, args.key)
    elif args.cmd in ("suppress", "unsuppress"):
        store = Store(cfg.db_path)
        if args.cmd == "suppress":
            store.suppress(args.address, args.reason)
            print(f"{args.address} will not be written to again.")
        else:
            print("Removed." if store.unsuppress(args.address) else "That address was not on the list.")
    elif args.cmd == "resolve":
        print("Cleared." if Store(cfg.db_path).resolve_attention(args.id) else "No open item with that number.")
    elif args.cmd == "resolve-kind":
        print(f"Cleared {Store(cfg.db_path).resolve_attention_kind(args.kind)} open item(s) of kind '{strip_controls(args.kind)}'.")
    else:
        store = Store(cfg.db_path)
        agent = Agent(cfg, store, _llm(), known=Known())  # these commands need no lead list
        try:
            if args.cmd == "approve":
                body = open(args.file, encoding="utf-8").read() if args.file else None
                agent.approve(args.id, body, force=args.force)
                print(f"Draft {args.id} approved. It goes out on the next pass of `once --live` or `watch --live`.")
                if not store.get_draft(args.id)["verified"]:
                    print("Note: our mail server could not verify who sent the message this answers, so its From line could be forged. "
                          "The reply goes to that address.")
            elif args.cmd == "retry":
                agent.retry(args.id)
                print(f"Draft {args.id} is back in the queue. (Only a send that certainly did not go out is marked failed, so this is safe.)")
            elif args.cmd == "settle":
                agent.settle(args.id, delivered=args.sent)
                print(f"Draft {args.id} is closed as " + ("sent." if args.sent else "not sent. It is marked failed, so `retry` can queue it again."))
            else:
                agent.skip(args.id)
                print(f"Draft {args.id} skipped.")
        except (KeyError, ValueError) as exc:
            sys.exit(str(exc).strip("'\""))


if __name__ == "__main__":
    main()
