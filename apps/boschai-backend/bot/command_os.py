import asyncio
import os

import anthropic
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from core.prime import build_system_prompt
from services.agent import build_agent_prompt, run_agent_loop
from services.compiler import compile_sources
from services.design_brief import generate_brief
from services.scaffolder import scaffold_report
from services.signoff import create_signoff, get_open_signoffs, resolve_signoff

ai_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_bot_app: Application = None


def _allowed_chats() -> set[int]:
    """Telegram chats allowed to use the bot. Defaults to TELEGRAM_CHAT_ID; override
    with ALLOWED_TELEGRAM_CHATS (comma-separated chat ids). Anyone else is ignored,
    so a stranger who finds the bot can't reach Heinrich's email/Drive."""
    raw = os.environ.get("ALLOWED_TELEGRAM_CHATS", "") or str(TELEGRAM_CHAT_ID or "")
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part:
            try:
                ids.add(int(part))
            except ValueError:
                pass
    return ids


ALLOWED_CHATS = _allowed_chats()

# Per-chat conversation memory (in-memory; resets if the server restarts).
_histories: dict[int, list] = {}
_MAX_HISTORY = 30
_TG_LIMIT = 4000  # Telegram hard-caps messages at 4096 chars

# Telegram replies are sent as plain text (no parse mode), so any Markdown the agent
# emits — bold stars, hash headers, and especially pipe/dash tables — shows up as ugly
# literal symbols. This addendum is appended to the SHARED agent prompt for the Telegram
# channel only; the dashboard keeps its Markdown (it renders fine in a web UI).
TELEGRAM_FORMAT = (
    "\n\nTELEGRAM CHANNEL — you are replying inside a Telegram chat on a phone. "
    "Write CLEAN PLAIN TEXT ONLY. Do NOT use Markdown or HTML: no asterisks, underscores, "
    "hash headers, backticks, angle brackets, and NEVER a pipe/dash table — they all render as "
    "ugly literal characters here. Keep replies short and scannable, with a blank line between "
    "sections.\n"
    "When you list emails (or any set of items), give each its own block, numbered, like:\n"
    "1. Sender name\n"
    "   Short subject\n"
    "   2h ago, unread\n"
    "Leave a blank line between items and open with a one-line summary (e.g. 'You have 3 new "
    "emails:'). Never dump raw fields, ids, or JSON."
)


async def _reply_long(update: Update, text: str):
    """Send a reply, splitting into chunks if it exceeds Telegram's length limit."""
    text = text or "(no response)"
    for i in range(0, len(text), _TG_LIMIT):
        await update.message.reply_text(text[i:i + _TG_LIMIT])


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi Heinrich. I'm ready. Ask me anything or give me a task."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Full agentic chat over Telegram — same brain as the dashboard (email, sign-offs,
    projects, Drive), with per-chat memory so follow-ups keep context."""
    chat_id = update.effective_chat.id
    user_message = update.message.text
    await update.message.reply_chat_action("typing")

    system_prompt = await build_agent_prompt() + TELEGRAM_FORMAT
    history = _histories.get(chat_id, [])
    history.append({"role": "user", "content": user_message})

    try:
        # run_agent_loop is blocking (network + tools); keep the event loop free.
        reply = await asyncio.to_thread(run_agent_loop, system_prompt, history, source="telegram")
    except Exception as e:
        await update.message.reply_text(f"Sorry, something went wrong: {e}")
        return

    _histories[chat_id] = history[-_MAX_HISTORY:]
    await _reply_long(update, reply)


async def handle_waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /waiting [person] [item] [project (optional)]
    Example: /waiting "Thabo Nkosi" "Signed ToR" "Motsepe"
    """
    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text(
            "Usage: /waiting [person] [item]\nExample: /waiting Thabo \"Signed ToR\""
        )
        return

    waiting_on = args[0]
    item = " ".join(args[1:])
    signoff = create_signoff(waiting_on=waiting_on, item=item)
    await update.message.reply_text(
        f"Logged. Waiting on {waiting_on} for: {item}\nID: {signoff['id'][:8]}"
    )


async def handle_signoffs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all open sign-off items with days waiting."""
    items = get_open_signoffs()
    if not items:
        await update.message.reply_text("No pending sign-offs.")
        return

    lines = [f"Pending sign-offs ({len(items)}):"]
    for item in items:
        days = item["days_waiting"]
        age = f"{days}d" if days > 0 else "today"
        short_id = item["id"][:8]
        lines.append(f"[{short_id}] {item['waiting_on']} — {item['item']} ({age})")

    lines.append("\nResolve with /done [id]")
    await update.message.reply_text("\n".join(lines))


async def handle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /done [signoff_id]  — marks a sign-off as resolved."""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /done [id]\nGet IDs from /signoffs")
        return

    short_id = args[0]

    # Find the matching full UUID from open sign-offs
    open_items = get_open_signoffs()
    match = next((s for s in open_items if s["id"].startswith(short_id) or s["id"] == short_id), None)

    if not match:
        await update.message.reply_text(f"No open sign-off found with id starting '{short_id}'.")
        return

    resolved = resolve_signoff(match["id"])
    await update.message.reply_text(
        f"Done. Resolved: {resolved['waiting_on']} — {resolved['item']}"
    )


async def handle_compile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /compile [project_id]
    Compiles approved source documents into a structured report package.
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /compile [project_id]\nGet project IDs from the dashboard Reports tab."
        )
        return

    project_id = args[0]
    await update.message.reply_text("Compiling sources… this may take 30–60 seconds.")

    try:
        result = compile_sources(project_id=project_id)
        sections = result["section_counts"]
        found = result["sections_found"]
        total = result["sections_total"]
        lines = [f"Source package ready. {found}/{total} sections have content.\n"]
        for section, has_content in sections.items():
            icon = "✓" if has_content else "⚠"
            lines.append(f"{icon} {section}")
        lines.append(f"\nDocument ID: {result['document_id'][:8]}")
        lines.append("Review and approve in the dashboard before scaffolding.")
        await update.message.reply_text("\n".join(lines))
    except ValueError as e:
        await update.message.reply_text(f"Could not compile: {e}")
    except Exception as e:
        await update.message.reply_text(f"Compilation failed: {e}")


async def handle_scaffold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /scaffold [project_id] — generate a report scaffold from the approved source package."""
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /scaffold [project_id]\nGet project IDs from the dashboard Reports tab."
        )
        return

    project_id = args[0]
    await update.message.reply_text("Generating report scaffold… this may take 60–90 seconds.")

    try:
        result = scaffold_report(project_id=project_id)
        gap_count = result["gap_count"]
        lines = ["Scaffold ready."]
        if gap_count:
            lines.append(f"⚠️ {gap_count} gap{'s' if gap_count != 1 else ''} need source material.")
        else:
            lines.append("All sections sourced — no gaps.")
        lines.append(f"Document ID: {result['document_id'][:8]}")
        lines.append("Review in the dashboard and approve before generating a design brief.")
        await update.message.reply_text("\n".join(lines))
    except ValueError as e:
        await update.message.reply_text(f"Could not scaffold: {e}")
    except Exception as e:
        await update.message.reply_text(f"Scaffolding failed: {e}")


async def handle_brief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /brief [project_id] — generate a design brief from the approved scaffold."""
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /brief [project_id]\nGet project IDs from the dashboard Reports tab."
        )
        return

    project_id = args[0]
    await update.message.reply_text("Generating design brief…")

    try:
        result = generate_brief(project_id=project_id)
        lines = [
            "Design brief ready.",
            f"Estimated pages: {result['page_estimate']}",
            f"Sections: {result['section_count']}",
            f"Document ID: {result['document_id'][:8]}",
            "Review in the dashboard and mark as sent when dispatched to the design agency.",
        ]
        await update.message.reply_text("\n".join(lines))
    except ValueError as e:
        await update.message.reply_text(f"Could not generate brief: {e}")
    except Exception as e:
        await update.message.reply_text(f"Brief generation failed: {e}")


async def handle_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open command so an authorised person can discover their chat id for the allowlist."""
    await update.message.reply_text(f"This chat's id is: {update.effective_chat.id}")


# === BoschAI: Follow-ups (lane B) — BEGIN ===

async def handle_followups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List pending follow-ups and today's activity."""
    from services.followup import get_status_summary

    summary = get_status_summary()
    mode = "WARMUP (drafts only)" if summary["warmup"] else "LIVE"
    enabled = "ON" if summary["enabled"] else "OFF"
    kill = "ENGAGED" if summary["kill_switch"] else "off"

    lines = [
        f"Follow-up engine: {enabled} | Mode: {mode}",
        f"Kill switch: {kill}",
        f"Today: {summary['today_sent']}/{summary['daily_cap']} sent/drafted",
        "",
    ]

    if summary["pending"]:
        lines.append(f"Pending follow-ups ({summary['pending_count']}):")
        for item in summary["pending"][:10]:
            days = ""
            if item.get("original_sent_at"):
                try:
                    from datetime import datetime, timezone
                    sent = datetime.fromisoformat(item["original_sent_at"])
                    if sent.tzinfo is None:
                        sent = sent.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - sent).days
                    days = f" ({age}d ago)"
                except Exception:
                    pass
            attempts = item.get("attempt_count", 0)
            lines.append(f"  {item.get('contact_name', item.get('contact_email', '?'))}")
            lines.append(f"    {item.get('subject', '?')}{days} | {attempts} attempt(s)")
    else:
        lines.append("No pending follow-ups.")

    await _reply_long(update, "\n".join(lines))


async def handle_killswitch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /killswitch on|off — toggle the follow-up kill switch."""
    from services.followup import set_kill_switch

    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Usage: /killswitch on|off")
        return

    on = args[0].lower() == "on"
    set_kill_switch(on)
    if on:
        state = "ENGAGED — all follow-ups paused.\nNote: restarting the server resets this. Set FOLLOWUP_KILL_SWITCH=true in env vars for persistence."
    else:
        state = "OFF — follow-ups active"
    await update.message.reply_text(f"Kill switch: {state}")


async def handle_campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show campaign auto-responder status."""
    from services.campaign_responder import get_status
    s = get_status()
    enabled = "ON" if s["enabled"] else "OFF"
    kill = "ENGAGED" if s["kill_switch"] else "off"
    lines = [
        f"Campaign responder: {enabled} | Kill switch: {kill}",
        f"Accounts: {s['account_count']} | Cap: {s['daily_cap']}/account/day",
        "",
    ]
    for acct, count in s.get("today_replies", {}).items():
        lines.append(f"  {acct}: {count} replies today")
    if not s.get("today_replies"):
        lines.append("  No activity today.")
    await _reply_long(update, "\n".join(lines))


async def handle_campaign_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /campaignkill on|off — toggle campaign responder kill switch."""
    from services.campaign_responder import set_kill_switch
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await update.message.reply_text("Usage: /campaignkill on|off")
        return
    on = args[0].lower() == "on"
    set_kill_switch(on)
    state = "ENGAGED — campaign replies paused" if on else "OFF — campaign replies active"
    await update.message.reply_text(f"Campaign kill switch: {state}")

# === BoschAI: Follow-ups (lane B) — END ===


async def start_bot():
    global _bot_app
    _bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Only these chats can use the bot. Everyone else is silently ignored.
    chat_filter = filters.Chat(chat_id=ALLOWED_CHATS)
    print(f"[bot] access locked to chats: {sorted(ALLOWED_CHATS) or 'NONE (misconfigured!)'}", flush=True)

    _bot_app.add_handler(CommandHandler("myid", handle_myid))  # open: lets you find your id
    _bot_app.add_handler(CommandHandler("start", handle_start, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("waiting", handle_waiting, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("signoffs", handle_signoffs, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("done", handle_done, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("compile", handle_compile, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("scaffold", handle_scaffold, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("brief", handle_brief, filters=chat_filter))
    # === BoschAI: Follow-ups (lane B) — BEGIN ===
    _bot_app.add_handler(CommandHandler("followups", handle_followups, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("killswitch", handle_killswitch, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("campaigns", handle_campaigns, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("campaignkill", handle_campaign_kill, filters=chat_filter))
    # === BoschAI: Follow-ups (lane B) — END ===
    _bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & chat_filter, handle_message))

    await _bot_app.initialize()
    await _bot_app.start()
    await _bot_app.updater.start_polling(drop_pending_updates=True)


async def stop_bot():
    if _bot_app:
        await _bot_app.updater.stop()
        await _bot_app.stop()
        await _bot_app.shutdown()
