import json
import os
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
API_SECRET_KEY = os.environ["API_SECRET_KEY"]

# Google Drive OAuth — set these after creating credentials in Google Cloud Console
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:7000/auth/google/callback")

# Firecrawl — powers the Deep Research tab (web search + website scraping)
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY")

# Voyage AI — embeddings for the Knowledge Pool (semantic search over docs + transcripts).
# voyage-law-2 is tuned for legal/governance text and its first 200M tokens are free.
# Both voyage-law-2 and voyage-3.5 output 1024-dim vectors, so EMBEDDING_DIM stays 1024
# if you switch between them. Changing the dimension means recreating the pgvector column.
VOYAGE_API_KEY = os.environ.get("VOYAGE_API_KEY")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "voyage-law-2")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))

# Knowledge Pool — which Drive folders to index.
# POOL_CLIENT_ROOTS: comma-separated company folder NAMES (or ids), each treated as one
# company in the dashboard dropdown. Leave empty to index every top-level Drive folder EXCEPT
# the system/admin ones the indexer skips by default. Subfolders inside each company are
# crawled automatically. Free-tier embedding is rate-limited, so the two knobs pace requests.
POOL_CLIENT_ROOTS = [s.strip() for s in os.environ.get("POOL_CLIENT_ROOTS", "").split(",") if s.strip()]
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "8"))
EMBED_REQUEST_INTERVAL = float(os.environ.get("EMBED_REQUEST_INTERVAL", "20"))

# === BoschAI: Follow-ups (lane B) — BEGIN ===
# Email auto-follow-up engine. Defaults to OFF + warmup (draft-only).
FOLLOWUP_ENABLED = os.environ.get("FOLLOWUP_ENABLED", "false").lower() in ("true", "1", "yes")
FOLLOWUP_ALLOWLIST = [s.strip() for s in os.environ.get("FOLLOWUP_ALLOWLIST", "").split(",") if s.strip()]
FOLLOWUP_DELAY_DAYS = int(os.environ.get("FOLLOWUP_DELAY_DAYS", "3"))
FOLLOWUP_DAILY_CAP = int(os.environ.get("FOLLOWUP_DAILY_CAP", "5"))
FOLLOWUP_KILL_SWITCH = os.environ.get("FOLLOWUP_KILL_SWITCH", "false").lower() in ("true", "1", "yes")
FOLLOWUP_WARMUP = os.environ.get("FOLLOWUP_WARMUP", "true").lower() in ("true", "1", "yes")
FOLLOWUP_MAX_ATTEMPTS = int(os.environ.get("FOLLOWUP_MAX_ATTEMPTS", "3"))

# Campaign auto-responder — monitors outreach email accounts and auto-replies
# to interested prospects. Accounts are configured as a JSON array in .env:
#   CAMPAIGN_ACCOUNTS=[{"email":"h@boschai.com","password":"...","imap_host":"imap.provider.com","smtp_host":"smtp.provider.com"}]
CAMPAIGN_ENABLED = os.environ.get("CAMPAIGN_ENABLED", "false").lower() in ("true", "1", "yes")
_raw_accounts = os.environ.get("CAMPAIGN_ACCOUNTS", "[]")
try:
    CAMPAIGN_ACCOUNTS = json.loads(_raw_accounts) if _raw_accounts.strip() else []
except Exception:
    CAMPAIGN_ACCOUNTS = []
CAMPAIGN_REPLY_DELAY_MINUTES = int(os.environ.get("CAMPAIGN_REPLY_DELAY_MINUTES", "10"))
CAMPAIGN_DAILY_CAP_PER_ACCOUNT = int(os.environ.get("CAMPAIGN_DAILY_CAP_PER_ACCOUNT", "50"))
CAMPAIGN_KILL_SWITCH = os.environ.get("CAMPAIGN_KILL_SWITCH", "false").lower() in ("true", "1", "yes")
# === BoschAI: Follow-ups (lane B) — END ===

# === BoschAI: LinkedIn (lane A) — BEGIN ===
# LinkedIn growth engine — uses ANTHROPIC_API_KEY (already configured above).
# LINKEDIN_DRAFTING_MODEL: override the Claude model used for LinkedIn drafts.
LINKEDIN_DRAFTING_MODEL = os.environ.get("LINKEDIN_DRAFTING_MODEL", "claude-sonnet-4-6")
# LINKEDIN_SCHEDULER_ENABLED: set to "1" to activate the daily morning draft.
# Off by default — no API calls until Heinrich flips this on.
LINKEDIN_SCHEDULER_ENABLED = os.environ.get("LINKEDIN_SCHEDULER_ENABLED", "0") == "1"
# === BoschAI: LinkedIn (lane A) — END ===
