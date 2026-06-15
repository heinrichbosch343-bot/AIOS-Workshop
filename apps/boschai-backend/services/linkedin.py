"""
LinkedIn growth engine — assisted drafting for posts, replies, comments, and idea generation.

All LinkedIn logic lives here. The agent and bot import from this module only.
Claude drafts in Heinrich's voice; he copies to LinkedIn. No auto-posting.
"""
import json
from functools import lru_cache
from pathlib import Path

import anthropic

from config import ANTHROPIC_API_KEY, LINKEDIN_DRAFTING_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
_MODEL = LINKEDIN_DRAFTING_MODEL

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_CONTEXT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "context" / "linkedin"


@lru_cache(maxsize=1)
def _linkedin_voice() -> str:
    """Load the LinkedIn voice profile."""
    path = _PROMPTS_DIR / "linkedin_voice.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


@lru_cache(maxsize=1)
def _writing_rules() -> str:
    """Load the anti-AI-slop writing rules."""
    path = _PROMPTS_DIR / "writing_style.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _content_pillars() -> str:
    """Load content pillars (not cached — can be edited between calls)."""
    path = _CONTEXT_DIR / "content-pillars.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _idea_backlog() -> str:
    """Load the idea backlog."""
    path = _CONTEXT_DIR / "idea-backlog.md"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _base_system_prompt() -> str:
    """Assemble the system prompt for all LinkedIn drafting."""
    parts = [
        "You are a LinkedIn ghostwriter for Heinrich Bosch, founder of BoschAI.",
        "Your job is to draft LinkedIn content that sounds exactly like Heinrich wrote it himself.",
        "Follow the voice profile and writing rules precisely. Every draft must pass as human-written.",
    ]
    voice = _linkedin_voice()
    if voice:
        parts.append(f"\n=== LINKEDIN VOICE PROFILE ===\n{voice}\n=== END VOICE PROFILE ===")
    rules = _writing_rules()
    if rules:
        parts.append(
            f"\n=== WRITING RULES (apply to all output) ===\n{rules}\n=== END WRITING RULES ==="
        )
    pillars = _content_pillars()
    if pillars:
        parts.append(f"\n=== CONTENT PILLARS ===\n{pillars}\n=== END CONTENT PILLARS ===")
    return "\n\n".join(parts)


def _call_claude(system: str, user_msg: str, max_tokens: int = 1024) -> str:
    """Single Claude call, returns the text response."""
    response = _client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


# ---------------------------------------------------------------------------
# Public functions — called by agent tools and Telegram commands
# ---------------------------------------------------------------------------

def draft_post(topic_or_note: str) -> str:
    """Draft a LinkedIn post on the given topic or from a rough note.

    Returns the post text, ready to copy-paste into LinkedIn.
    """
    system = _base_system_prompt()
    user_msg = (
        f"Draft a LinkedIn post based on this topic or note:\n\n{topic_or_note}\n\n"
        "Output ONLY the post text. No preamble, no explanation, no quotation marks around it. "
        "150-300 words unless the topic genuinely needs more. "
        "Make it sound like Heinrich wrote it on his phone between meetings."
    )
    return _call_claude(system, user_msg)


def draft_reply(context_text: str) -> str:
    """Draft a LinkedIn reply to someone else's post or comment.

    `context_text` is the post/comment being replied to.
    Returns 1-3 sentences ready to paste.
    """
    system = _base_system_prompt()
    user_msg = (
        f"Someone posted this on LinkedIn:\n\n{context_text}\n\n"
        "Draft a reply from Heinrich. 1-3 sentences. Add a specific thought or question, "
        "not just agreement. Reference something concrete from the original. "
        "Output ONLY the reply text."
    )
    return _call_claude(system, user_msg, max_tokens=300)


def draft_comment(post_text: str) -> str:
    """Draft a thoughtful comment on a LinkedIn post.

    Similar to draft_reply but framed as a first comment, not a reply to a reply.
    """
    system = _base_system_prompt()
    user_msg = (
        f"Here's a LinkedIn post:\n\n{post_text}\n\n"
        "Draft a comment from Heinrich. 1-3 sentences that add value. "
        "Show he actually read and thought about it. No hollow praise. "
        "Output ONLY the comment text."
    )
    return _call_claude(system, user_msg, max_tokens=300)


def suggest_ideas(n: int = 5, pillar: str | None = None) -> list[dict]:
    """Generate post ideas, optionally filtered to a content pillar.

    Returns a list of dicts: [{"title": "...", "hook": "...", "pillar": "..."}]
    """
    system = _base_system_prompt()
    backlog = _idea_backlog()

    constraint = ""
    if pillar:
        constraint = f"Focus on this content pillar: {pillar}\n"

    existing = ""
    if backlog:
        existing = f"Avoid duplicating these existing ideas:\n{backlog}\n\n"

    user_msg = (
        f"Suggest {n} LinkedIn post ideas for Heinrich.\n\n"
        f"{constraint}{existing}"
        "For each idea, return a JSON array where each element has:\n"
        '- "title": a short working title (5-10 words)\n'
        '- "hook": the opening line of the post (one sentence)\n'
        '- "pillar": which content pillar it falls under\n\n'
        "Output ONLY the JSON array, no other text."
    )
    raw = _call_claude(system, user_msg, max_tokens=800)

    # Parse the JSON response, handling markdown code fences
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines (code fence markers)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        ideas = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: return the raw text as a single idea
        return [{"title": "Raw suggestions", "hook": raw, "pillar": "mixed"}]

    return ideas if isinstance(ideas, list) else [ideas]


# ---------------------------------------------------------------------------
# Tool definitions for agent.py registration
# ---------------------------------------------------------------------------

LINKEDIN_TOOLS = [
    {
        "name": "draft_linkedin_post",
        "description": (
            "Draft a LinkedIn post in Heinrich's voice on the given topic or from a rough note. "
            "Returns the post text ready to copy-paste into LinkedIn. Use when he says 'write a "
            "post about X', 'draft something for LinkedIn', or sends a rough idea to turn into a post."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "The topic, rough note, or idea for the post",
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "draft_linkedin_reply",
        "description": (
            "Draft a LinkedIn reply or comment in Heinrich's voice. Use when he pastes someone "
            "else's post or comment and asks for a reply or comment to post."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "context_text": {
                    "type": "string",
                    "description": "The post or comment being replied to",
                },
            },
            "required": ["context_text"],
        },
    },
    {
        "name": "suggest_linkedin_ideas",
        "description": (
            "Generate LinkedIn post ideas for Heinrich. Returns a list of ideas with titles, "
            "opening hooks, and which content pillar each falls under. Use when he asks for "
            "post ideas, content suggestions, or 'what should I write about'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "How many ideas to generate (default 5)",
                },
                "pillar": {
                    "type": "string",
                    "description": "Optional content pillar to focus on",
                },
            },
        },
    },
]


def handle_linkedin_tool(name: str, tool_input: dict) -> dict:
    """Execute a LinkedIn tool and return the result. Called from agent.py's run_tool."""
    if name == "draft_linkedin_post":
        text = draft_post(tool_input["topic"])
        return {"draft": text, "note": "Copy-paste this into LinkedIn. Edit anything that doesn't feel right."}
    if name == "draft_linkedin_reply":
        text = draft_reply(tool_input["context_text"])
        return {"reply": text}
    if name == "suggest_linkedin_ideas":
        count = tool_input.get("count", 5)
        pillar = tool_input.get("pillar")
        ideas = suggest_ideas(n=count, pillar=pillar)
        return {"ideas": ideas, "count": len(ideas)}
    return {"error": f"Unknown LinkedIn tool: {name}"}
