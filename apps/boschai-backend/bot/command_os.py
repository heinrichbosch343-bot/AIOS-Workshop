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
    "ugly literal characters here.\n"
    "BE BRIEF. This is a phone chat, not an essay. Default to 1-3 short sentences. Give the answer "
    "directly, no preamble, no recap, no sign-off. Only go longer when he explicitly asks for "
    "detail, a draft, or a plan.\n"
    "When you list emails (or any set of items), give each its own block, numbered, like:\n"
    "1. Sender name (their@email.com)\n"
    "   One-line summary of what it's about.\n"
    "Leave a blank line between items and open with a one-line count (e.g. 'You have 3 unanswered "
    "emails from the last 24h:'). Never dump raw fields, ids, dates, or JSON."
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

    try:
        system_prompt = await build_agent_prompt() + TELEGRAM_FORMAT
        history = _histories.get(chat_id, [])
        history.append({"role": "user", "content": user_message})
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
    """Open command to discover the chat id (for the allowlist) and, when run inside a
    group topic, that topic's id — so the daily brief can target a specific tab.
    Run it inside the Daily Brief tab to get both values ready to paste into Railway."""
    chat_id = update.effective_chat.id
    thread_id = update.message.message_thread_id  # None outside a topic / in General
    lines = [f"Chat id: {chat_id}"]
    if thread_id is not None:
        lines.append(f"Topic (tab) id: {thread_id}")
        lines.append("")
        lines.append("To send the daily brief into THIS tab, set these on Railway:")
        lines.append(f"TELEGRAM_BRIEF_CHAT_ID={chat_id}")
        lines.append(f"TELEGRAM_BRIEF_TOPIC_ID={thread_id}")
    await update.message.reply_text("\n".join(lines))


async def handle_dailybrief(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate and send today's daily brief on demand — it posts into the configured
    Daily Brief tab (TELEGRAM_BRIEF_CHAT_ID / TELEGRAM_BRIEF_TOPIC_ID), wherever you run
    this from. Handy for testing the routing and for an on-demand brief any time of day."""
    await update.message.reply_chat_action("typing")
    await update.message.reply_text("Building today's brief… (about 20–30 seconds)")
    try:
        from services.daily_brief import send_daily_brief
        await asyncio.to_thread(send_daily_brief)
    except Exception as e:
        await update.message.reply_text(f"Couldn't send the brief: {e}")
        return
    await update.message.reply_text("Done — posted to the Daily Brief tab. ✅")


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

# === BoschAI: LinkedIn (lane A) — BEGIN ===
from services.linkedin import draft_post, draft_reply, draft_comment, suggest_ideas


async def handle_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /post <topic or rough note>
    Drafts a LinkedIn post in Heinrich's voice, ready to copy-paste."""
    if not context.args:
        await update.message.reply_text("Usage: /post <topic or rough note>\nExample: /post why I built my own AIOS")
        return
    topic = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    try:
        text = await asyncio.to_thread(draft_post, topic)
        await _reply_long(update, f"LinkedIn draft:\n\n{text}")
    except Exception as e:
        await update.message.reply_text(f"Drafting failed: {e}")


async def handle_linkedin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /reply <paste the post or comment you're replying to>
    Drafts a LinkedIn reply or comment in Heinrich's voice."""
    if not context.args:
        await update.message.reply_text("Usage: /reply <paste the post or comment>\nPaste the text you want to reply to.")
        return
    context_text = " ".join(context.args)
    await update.message.reply_chat_action("typing")
    try:
        text = await asyncio.to_thread(draft_reply, context_text)
        await _reply_long(update, f"Reply draft:\n\n{text}")
    except Exception as e:
        await update.message.reply_text(f"Drafting failed: {e}")


async def handle_ideas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /ideas [pillar]
    Suggests LinkedIn post ideas, optionally filtered to a content pillar."""
    pillar = " ".join(context.args) if context.args else None
    await update.message.reply_chat_action("typing")
    try:
        ideas = await asyncio.to_thread(suggest_ideas, 5, pillar)
        lines = [f"Post ideas ({len(ideas)}):"]
        for i, idea in enumerate(ideas, 1):
            title = idea.get("title", "Untitled")
            hook = idea.get("hook", "")
            p = idea.get("pillar", "")
            lines.append(f"\n{i}. {title}")
            if p:
                lines.append(f"   Pillar: {p}")
            if hook:
                lines.append(f"   Hook: {hook}")
        lines.append("\nPick one and run /post to draft it.")
        await _reply_long(update, "\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Idea generation failed: {e}")
# === BoschAI: LinkedIn (lane A) — END ===

# === BoschAI: CRM Pipeline — BEGIN ===


async def handle_pipeline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the full sales pipeline grouped by stage."""
    from services.pipeline import format_pipeline_telegram, check_nudges, format_nudges_telegram
    await update.message.reply_chat_action("typing")
    text = format_pipeline_telegram()
    nudges = check_nudges()
    if nudges:
        text += "\n\n" + format_nudges_telegram(nudges)
    await _reply_long(update, text)


async def handle_addlead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /addlead [name] [email (optional)]
    Example: /addlead "John Smith" john@acme.com
    """
    from services.pipeline import add_lead
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /addlead [name] [email]\n"
            "Example: /addlead John john@acme.com\n"
            "Example: /addlead \"John Smith\" john@acme.com"
        )
        return

    # Last arg is email if it contains @
    email = None
    name_parts = list(args)
    if name_parts and "@" in name_parts[-1]:
        email = name_parts.pop()
    name = " ".join(name_parts)

    if not name:
        await update.message.reply_text("Please provide a name: /addlead [name] [email]")
        return

    try:
        lead = add_lead(name, email=email, origin="telegram")
        lines = [f"Added {lead['name']} as interested."]
        if email:
            lines.append(f"Email: {email}")
        lines.append("I'll remind you in 2 days to book a meeting.")
        lines.append("\nAdd notes? Just type them and I'll attach them.")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"Could not add lead: {e}")


async def handle_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /move [name] [stage]
    Stages: interested, no_reply, meeting_booked, follow_up_meeting, proposal, won, lost
    """
    from services.pipeline import move_stage, STAGES, STAGE_LABELS
    args = context.args
    if not args or len(args) < 2:
        stage_list = ", ".join(STAGES)
        await update.message.reply_text(
            f"Usage: /move [name] [stage]\nStages: {stage_list}\n"
            "Example: /move John meeting_booked"
        )
        return

    # Last arg is the stage, everything before is the name
    stage = args[-1].lower()
    name = " ".join(args[:-1])

    if stage not in STAGES:
        # Try fuzzy match
        matches = [s for s in STAGES if s.startswith(stage)]
        if len(matches) == 1:
            stage = matches[0]
        else:
            stage_list = ", ".join(STAGES)
            await update.message.reply_text(f"Unknown stage '{stage}'.\nValid: {stage_list}")
            return

    try:
        lead = move_stage(name, stage, source="telegram")
        await update.message.reply_text(
            f"Moved {lead['name']} to {STAGE_LABELS.get(stage, stage)}."
        )
    except ValueError as e:
        await update.message.reply_text(str(e))
    except Exception as e:
        await update.message.reply_text(f"Could not move lead: {e}")


async def handle_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /note [name] | [text]
    Example: /note John | Great discovery call, wants proposal by Friday
    Example: /note John Great call (single-word name, rest is note)
    """
    from services.pipeline import add_note
    raw = " ".join(context.args) if context.args else ""
    if not raw:
        await update.message.reply_text(
            "Usage: /note [name] | [your note]\n"
            "Example: /note John | Great call, wants proposal by Friday\n"
            "Example: /note John Great call"
        )
        return

    # If user used a pipe separator, split cleanly on it (supports multi-word names)
    if "|" in raw:
        parts = raw.split("|", 1)
        name = parts[0].strip()
        note_text = parts[1].strip()
    else:
        # Fallback: first word is name, rest is note
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /note [name] | [your note]\n"
                "Use | to separate multi-word names from the note."
            )
            return
        name = args[0]
        note_text = " ".join(args[1:])

    try:
        add_note(name, note_text, source="telegram")
        await update.message.reply_text(f"Note added to {name}.")
    except ValueError as e:
        await update.message.reply_text(str(e))
    except Exception as e:
        await update.message.reply_text(f"Could not add note: {e}")


async def handle_lead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /lead [name] — show details for a specific lead."""
    from services.pipeline import format_lead_telegram
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /lead [name]\nExample: /lead John")
        return

    name = " ".join(args)
    await update.message.reply_chat_action("typing")
    text = format_lead_telegram(name)
    await _reply_long(update, text)


async def handle_removelead(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /removelead [name] — mark a lead as lost."""
    from services.pipeline import remove_lead
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /removelead [name]")
        return

    name = " ".join(args)
    try:
        lead = remove_lead(name, source="telegram")
        await update.message.reply_text(f"Moved {lead['name']} to Lost. Use /move to restore if needed.")
    except ValueError as e:
        await update.message.reply_text(str(e))
    except Exception as e:
        await update.message.reply_text(f"Could not remove lead: {e}")

# === BoschAI: CRM Pipeline — END ===

# === BoschAI: Client memory (transcripts) — BEGIN ===

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A meeting transcript was uploaded. Read it, summarise it, and save it to the
    client's living memory. Tip: add the client's name as the file caption; otherwise
    I'll infer it from the transcript."""
    doc = update.message.document
    if not doc:
        return
    caption = (update.message.caption or "").strip() or None

    await update.message.reply_chat_action("typing")
    await update.message.reply_text("Got the file — reading the transcript…")

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        raw = bytes(await tg_file.download_as_bytearray())
        from services.transcripts import ingest_transcript
        result = await asyncio.to_thread(
            ingest_transcript, raw, doc.file_name or "", caption, "telegram"
        )
    except ValueError as e:
        await update.message.reply_text(str(e))
        return
    except Exception as e:
        await update.message.reply_text(f"Couldn't process that file: {e}")
        return

    tag = " (new client added)" if result.get("client_created") else ""
    lines = [f"Saved to {result['client_name']}'s memory{tag}."]
    if result.get("summary"):
        lines.append("")
        lines.append(result["summary"])
    if result.get("brief"):
        lines.append("")
        lines.append("Updated brief:")
        lines.append(result["brief"])
    lines.append("")
    lines.append(f"Ask me anytime: \"what are we building for {result['client_name']}?\"")
    await _reply_long(update, "\n".join(lines))

# === BoschAI: Client memory (transcripts) — END ===


async def start_bot():
    global _bot_app
    _bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Only these chats can use the bot. Everyone else is silently ignored.
    chat_filter = filters.Chat(chat_id=ALLOWED_CHATS)
    print(f"[bot] access locked to chats: {sorted(ALLOWED_CHATS) or 'NONE (misconfigured!)'}", flush=True)

    _bot_app.add_handler(CommandHandler("myid", handle_myid))  # open: lets you find your id
    _bot_app.add_handler(CommandHandler("start", handle_start, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("dailybrief", handle_dailybrief, filters=chat_filter))
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
    # === BoschAI: LinkedIn (lane A) — BEGIN ===
    _bot_app.add_handler(CommandHandler("post", handle_post, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("reply", handle_linkedin_reply, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("ideas", handle_ideas, filters=chat_filter))
    # === BoschAI: LinkedIn (lane A) — END ===
    # === BoschAI: CRM Pipeline — BEGIN ===
    _bot_app.add_handler(CommandHandler("pipeline", handle_pipeline, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("addlead", handle_addlead, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("move", handle_move, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("note", handle_note, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("lead", handle_lead, filters=chat_filter))
    _bot_app.add_handler(CommandHandler("removelead", handle_removelead, filters=chat_filter))
    # === BoschAI: CRM Pipeline — END ===
    # === BoschAI: Client memory (transcripts) — BEGIN ===
    _bot_app.add_handler(MessageHandler(filters.Document.ALL & chat_filter, handle_document))
    # === BoschAI: Client memory (transcripts) — END ===
    _bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & chat_filter, handle_message))

    await _bot_app.initialize()
    await _bot_app.start()
    await _bot_app.updater.start_polling(drop_pending_updates=True)


async def stop_bot():
    if _bot_app:
        await _bot_app.updater.stop()
        await _bot_app.stop()
        await _bot_app.shutdown()
