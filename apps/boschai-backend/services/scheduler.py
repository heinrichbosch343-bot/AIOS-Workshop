"""
Background scheduler for the always-on backend.

Runs Heinrich's recurring jobs in-process (no extra Railway service needed):
  - Knowledge Pool reindex -> incremental Drive re-crawl at 04:00 SAST (only new/changed files)
  - Daily brief  -> sent to Telegram every morning at 06:00 SAST
  - Sign-off watcher -> scans Gmail for replies every 30 minutes

Only started when the Telegram bot is enabled (i.e. on the hosted server), so the
local dev backend never fires duplicate briefs or notifications.
"""
import asyncio
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from services import daily_brief, signoff_watcher, autodraft, indexer

TZ = ZoneInfo("Africa/Johannesburg")
_scheduler: BackgroundScheduler | None = None


def _safe(fn):
    def wrapper():
        try:
            fn()
        except Exception as e:  # never let a job crash the scheduler thread
            print(f"[scheduler] {getattr(fn, '__name__', 'job')} failed: {e}", flush=True)
    return wrapper


def _run_reindex():
    """Incremental Knowledge Pool refresh: only new/changed Drive files get re-embedded."""
    print("[scheduler] knowledge reindex starting", flush=True)
    totals = indexer.reindex_all(log=lambda *_: None)
    print(f"[scheduler] knowledge reindex done: {totals}", flush=True)


def start_scheduler():
    global _scheduler
    if _scheduler:
        return
    sch = BackgroundScheduler(timezone=TZ)
    # Keep the Knowledge Pool fresh: incremental Drive reindex before the morning jobs, so
    # anything dropped in Drive overnight is answerable by the time Heinrich's up. Idempotent +
    # max_instances=1, so a slow run never overlaps itself.
    sch.add_job(_safe(_run_reindex),
                CronTrigger(hour=4, minute=0, timezone=TZ),
                id="knowledge_reindex", replace_existing=True, misfire_grace_time=3600)
    # Auto-draft replies to routine emails (drafts only, never sends) — runs before the
    # brief so the 06:00 brief reflects the freshly created drafts.
    sch.add_job(_safe(lambda: asyncio.run(autodraft.auto_draft_replies())),
                CronTrigger(hour=5, minute=50, timezone=TZ),
                id="auto_draft", replace_existing=True, misfire_grace_time=1800)
    sch.add_job(_safe(daily_brief.send_daily_brief),
                CronTrigger(hour=6, minute=0, timezone=TZ),
                id="daily_brief", replace_existing=True, misfire_grace_time=3600)
    sch.add_job(_safe(signoff_watcher.check_signoffs),
                IntervalTrigger(minutes=30),
                id="signoff_watcher", replace_existing=True, misfire_grace_time=600)
    # === BoschAI: LinkedIn (lane A) — BEGIN ===
    from config import LINKEDIN_SCHEDULER_ENABLED
    if LINKEDIN_SCHEDULER_ENABLED:
        from datetime import datetime
        from services.linkedin import generate_morning_content

        def _linkedin_morning():
            weekday = datetime.now().weekday()  # 0=Mon .. 4=Fri
            include_videos = weekday in (0, 2, 4)  # Mon, Wed, Fri
            generate_morning_content(include_video_ideas=include_videos)

        sch.add_job(_safe(_linkedin_morning),
                    CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone=TZ),
                    id="linkedin_morning", replace_existing=True, misfire_grace_time=3600)
        print("[scheduler] linkedin morning draft: 09:00 SAST Mon-Fri (video ideas Mon/Wed/Fri)", flush=True)
    # === BoschAI: LinkedIn (lane A) — END ===

    sch.start()
    _scheduler = sch
    print("[scheduler] started: knowledge reindex 04:00, auto-draft 05:50, daily brief 06:00 SAST, sign-off watcher every 30 min", flush=True)


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
