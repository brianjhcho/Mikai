"""Provider-swappable LLM shim.

One entry point. Two tiers. Every future Claude / DeepSeek call in the
MIKAI codebase routes through here so that when Anthropic re-meters
`claude -p` (announced then paused June 15 2026 — see the anthropic-
subscription-auth-policy memory) we flip provider policy in one file
instead of hunting down subprocess calls scattered across scenarios.

Tiers:
- interactive: routes to `claude -p` today. Bills to Max sub. Best model.
- background: routes to DeepSeek today. Cheap, unattended-safe. Use for
    bulk extraction, hourly loops, anything that would starve interactive
    quota if it went to Claude.

Callers ask for a tier by intent, never by provider. Provider mapping is
a policy decision that lives here.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Literal
from urllib import request as urlreq

Tier = Literal["interactive", "background"]


# ── Policy: tier → provider ────────────────────────────────────────────────

_POLICY: dict[Tier, str] = {
    "interactive": os.environ.get("MIKAI_LLM_INTERACTIVE", "claude"),
    "background": os.environ.get("MIKAI_LLM_BACKGROUND", "deepseek"),
}


# ── Provider: claude (via `claude -p`) ────────────────────────────────────


def _chat_claude(prompt: str, timeout: float = 300.0) -> str:
    """Route through the Claude Code CLI, billed to the Max subscription.

    Requires ANTHROPIC_API_KEY unset (otherwise the CLI prefers the key
    over the subscription auth). We unset it in the subprocess env only —
    the parent's env is untouched.
    """
    if shutil.which("claude") is None:
        raise RuntimeError("`claude` CLI not on PATH — install Claude Code first")
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    proc = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed (rc={proc.returncode}): {proc.stderr[:500]}")
    return proc.stdout.strip()


# ── Provider: deepseek ───────────────────────────────────────────────────

_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
_DEEPSEEK_MODEL = "deepseek-chat"


def _chat_deepseek(prompt: str, timeout: float = 90.0, json_mode: bool = False) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set — source ~/.mikai/launchd.env first"
        )
    body: dict = {
        "model": _DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 8000,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urlreq.Request(
        _DEEPSEEK_URL,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    with urlreq.urlopen(req, timeout=timeout) as resp:
        outer = json.loads(resp.read().decode())
    return outer["choices"][0]["message"]["content"].strip()


# ── Public API ───────────────────────────────────────────────────────────


def chat(
    prompt: str,
    tier: Tier = "interactive",
    json_mode: bool = False,
    timeout: float | None = None,
) -> str:
    """Send a single prompt to the configured provider for this tier.

    json_mode is honored for providers that support it (DeepSeek). Claude
    does not have a JSON-mode flag on the CLI — callers wanting JSON from
    the interactive tier should ask for it in the prompt.
    """
    provider = _POLICY[tier]
    if provider == "claude":
        if json_mode:
            prompt = prompt + "\n\nReturn ONLY valid JSON. No prose. No markdown fences."
        return _chat_claude(prompt, timeout=timeout or 300.0)
    if provider == "deepseek":
        return _chat_deepseek(prompt, timeout=timeout or 90.0, json_mode=json_mode)
    raise ValueError(f"Unknown provider {provider!r} for tier {tier!r}")


def which(tier: Tier) -> str:
    """Return the provider name currently mapped to this tier — for logs."""
    return _POLICY[tier]
