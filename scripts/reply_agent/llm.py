"""The model, behind one small interface so tests can swap in a fake.

ClaudeCli runs `claude -p` on Heinrich's subscription (no API key, no per-call bill).
AnthropicApi is for running on a server where the CLI is not logged in.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Protocol


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    def complete(self, system: str, prompt: str, *, model: str) -> str: ...


def _claude_exe() -> str:
    found = shutil.which("claude")
    if found:
        return found
    for candidate in (Path.home() / ".local/bin/claude.exe", Path.home() / ".local/bin/claude"):
        if candidate.exists():
            return str(candidate)
    raise LLMError("claude CLI not found on PATH")


class ClaudeCli:
    """One tool-free, connector-free `claude -p` call per request.

    It runs from an empty temp folder so this workspace's CLAUDE.md is not loaded into every call,
    and with an empty MCP list so no connector opens a login page in the browser.
    """

    def __init__(self, timeout: int = 240, runner: Callable = subprocess.run, base_env: dict | None = None):
        self.timeout = timeout
        self.runner = runner
        # The environment the child process gets. The caller passes the environment as it was BEFORE the workspace secrets
        # file was loaded, so the model's process (and any hook or plugin it starts) never sees those keys.
        self.base_env = base_env

    def complete(self, system: str, prompt: str, *, model: str) -> str:
        cmd = [
            _claude_exe(), "-p", "--model", model, "--tools", "", "--strict-mcp-config",
            "--mcp-config", '{"mcpServers":{}}', "--disable-slash-commands", "--no-session-persistence",
            "--output-format", "json", "--system-prompt", system,
        ]
        source_env = self.base_env if self.base_env is not None else os.environ
        env = {k: v for k, v in source_env.items() if k != "ANTHROPIC_API_KEY"}  # use the login, not a stale key
        try:
            with tempfile.TemporaryDirectory(prefix="reply-agent-") as cwd:
                done = self.runner(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                   timeout=self.timeout, cwd=cwd, env=env)
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"claude did not answer within {self.timeout} seconds") from exc
        except OSError as exc:
            raise LLMError(f"claude could not be started: {str(exc)[:200]}") from exc
        if done.returncode != 0:
            raise LLMError(f"claude exited {done.returncode}: {done.stderr.strip()[:300]}")
        try:
            data = json.loads(done.stdout)
        except json.JSONDecodeError as exc:
            raise LLMError(f"claude returned non-JSON output: {done.stdout[:200]!r}") from exc
        if not isinstance(data, dict):  # valid JSON, but not the answer envelope: null, a list, a bare string
            raise LLMError(f"claude returned something unexpected: {done.stdout[:200]!r}")
        if data.get("is_error"):
            raise LLMError(f"claude reported an error: {str(data.get('result'))[:300]}")
        return str(data.get("result", "")).strip()


class AnthropicApi:
    """Direct API call. Needs ANTHROPIC_API_KEY and credit on the account."""

    MODELS = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}

    def __init__(self, api_key: str):
        import anthropic  # imported here so the CLI path needs no extra package

        self.client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=1)

    def complete(self, system: str, prompt: str, *, model: str) -> str:
        try:
            reply = self.client.messages.create(
                model=self.MODELS.get(model, model), max_tokens=900, system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001  any SDK failure (network, quota, overload) is a model outage to the caller
            raise LLMError(f"{type(exc).__name__}: {str(exc)[:200]}") from exc
        return "".join(block.text for block in reply.content if getattr(block, "text", None)).strip()


class FakeLLM:
    """Scripted answers for tests. `answers` is a list of strings or a function(system, prompt, model)."""

    def __init__(self, answers):
        self.answers = answers
        self.calls: list[tuple[str, str, str]] = []

    def complete(self, system: str, prompt: str, *, model: str) -> str:
        self.calls.append((system, prompt, model))
        if callable(self.answers):
            return self.answers(system, prompt, model)
        if not self.answers:
            raise LLMError("FakeLLM ran out of answers")
        return self.answers.pop(0)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply, even if it is wrapped in prose or a code fence."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in the reply")
        candidate = text[start:end + 1]
    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("JSON was not an object")
    return data
