# System: LinkedIn Growth Engine

> Assisted LinkedIn drafting: posts, replies, comments, and idea generation in Heinrich's voice.

## Architecture

```
Heinrich (Telegram /post, /reply, /ideas)
    |
    v
bot/command_os.py  -->  services/linkedin.py  -->  Claude API
    |                         |
    v                         v
Agent tools             prompts/linkedin_voice.md
(draft_linkedin_post,    + prompts/writing_style.md
 draft_linkedin_reply,   + context/linkedin/content-pillars.md
 suggest_linkedin_ideas)
    |
    v
Plain text draft --> Heinrich copy-pastes to LinkedIn
```

## Key Files

| File | Purpose |
|------|---------|
| `apps/boschai-backend/services/linkedin.py` | Core service: draft_post, draft_reply, draft_comment, suggest_ideas |
| `apps/boschai-backend/prompts/linkedin_voice.md` | Heinrich's LinkedIn voice profile |
| `context/linkedin/content-pillars.md` | 5 content pillars the agent drafts around |
| `context/linkedin/idea-backlog.md` | Running list of post ideas |
| `context/linkedin/accounts-to-engage.md` | People/accounts to engage with for growth |
| `context/linkedin/cadence.md` | Weekly posting schedule |

## How It Works

1. Heinrich sends `/post <topic>` or `/ideas` via Telegram (or asks the agent in free text)
2. The service loads linkedin_voice.md + writing_style.md + content-pillars.md
3. Claude drafts content matching Heinrich's voice and the anti-AI-slop rules
4. The draft is returned as plain text, ready to copy-paste into LinkedIn

## Configuration

| Variable | Purpose | Required |
|----------|---------|----------|
| `ANTHROPIC_API_KEY` | Claude API for drafting | Yes (shared) |
| `LINKEDIN_DRAFTING_MODEL` | Override Claude model (default: claude-sonnet-4-6) | No |

## Common Operations

**Draft a post:** `/post why I built my own AIOS`
**Draft a reply:** `/reply <paste the post text>`
**Get ideas:** `/ideas` or `/ideas Building in Public`
**Free-text:** "Draft a LinkedIn post about automating follow-ups"

## Dependencies

- **Depends on:** Claude API, boschai-backend running
- **Used by:** Telegram bot, agent chat

## History

| Date | Change |
|------|--------|
| 2026-06-15 | Initial build (lane A of parallel build) |
