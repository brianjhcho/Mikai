#!/usr/bin/env python3
"""Semi-manual MIKAI eval harness.

Auto-runs the MIKAI arm for each test question via the Anthropic Messages
API with MIKAI wired in as a remote MCP connector. Writes a markdown
report with blank slots for the Claude.ai baseline responses — those are
filled in manually by running each question on Claude.ai with the MIKAI
connector toggled OFF.

Usage:
    python scripts/eval_mikai.py

Config:
- ANTHROPIC_API_KEY env var, or ~/.mikai/config.json `anthropicKey`.
- MIKAI_URL at the top — change if the tunnel URL rotates.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

MIKAI_URL = os.environ.get("MIKAI_EVAL_URL", "http://localhost:8100/mcp")
MODEL = os.environ.get("MIKAI_EVAL_MODEL", "claude-opus-4-7")
MCP_BETA_HEADER = "mcp-client-2025-04-04"

QUESTIONS = [
    {
        "id": "A1",
        "dimension": "A — Does the graph understand the user?",
        "text": "What's my working theory about why certain coffee-origin countries stay trapped in commodity markets?",
        "what_it_tests": "Cross-note argumentative synthesis — can MIKAI reconstruct Brian's through-line, not just list facts?",
    },
    {
        "id": "A2",
        "dimension": "A — Does the graph understand the user?",
        "text": "Based on what I've written, what's a position I hold about coffee trading or coffee origins that most of my notes support, and what's a position where I've written competing or contradictory views?",
        "what_it_tests": "Belief confidence + contradicts/unresolved_tension edge surfacing",
    },
    {
        "id": "B1",
        "dimension": "B — Does it fit the cognitive model of idea progression?",
        "text": "Between January and April 2026, how has my thinking about coffee supply chains or the intermediary trade structure evolved?",
        "what_it_tests": "Bitemporal get_history + temporal ordering of belief change",
    },
    {
        "id": "B2",
        "dimension": "B — Does it fit the cognitive model of idea progression?",
        "text": "What's a research thread about East Africa or coffee that I opened earlier this year but haven't come back to in 6+ weeks?",
        "what_it_tests": "Stall detection — requires composing search + timestamps",
    },
    {
        "id": "C1",
        "dimension": "C — Does it return richer answers than Claude?",
        "text": "What have I written about Martin and the Ngacha farm?",
        "what_it_tests": "Source retrieval — exposes the edges-only tool gap",
    },
    {
        "id": "C2",
        "dimension": "C — Does it return richer answers than Claude?",
        "text": "What connects my thinking about colonial economic structures and my thinking about specialty coffee? Are there specific notes that bridge the two?",
        "what_it_tests": "Cross-topic bridge traversal — the clearest graph advantage",
    },
]


def get_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    cfg = Path.home() / ".mikai" / "config.json"
    if cfg.exists():
        data = json.loads(cfg.read_text())
        if data.get("anthropicKey"):
            return data["anthropicKey"]
    raise RuntimeError(
        "Set ANTHROPIC_API_KEY env var or add `anthropicKey` to ~/.mikai/config.json"
    )


def call_with_mikai(question: str, key: str) -> dict:
    body = {
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": question}],
        "mcp_servers": [
            {
                "type": "url",
                "url": MIKAI_URL,
                "name": "mikai",
            }
        ],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": MCP_BETA_HEADER,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return {"_error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


def extract_text_and_tools(resp: dict) -> tuple[str, list[dict]]:
    if "_error" in resp:
        return f"[API ERROR: {resp['_error']}]", []
    text_parts: list[str] = []
    tool_trace: list[dict] = []
    for block in resp.get("content", []):
        btype = block.get("type", "")
        if btype == "text":
            text_parts.append(block.get("text", ""))
        elif btype in ("mcp_tool_use", "tool_use"):
            tool_trace.append(
                {
                    "tool": block.get("name", ""),
                    "input": block.get("input", {}),
                }
            )
    return "\n".join(text_parts).strip() or "(no text response)", tool_trace


def main() -> int:
    try:
        key = get_api_key()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    out_dir = Path(__file__).resolve().parent.parent / "docs" / "evals"
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = out_dir / f"run-{timestamp}.md"

    lines: list[str] = [
        f"# MIKAI eval — {timestamp}",
        "",
        f"**MIKAI endpoint:** `{MIKAI_URL}`",
        f"**Model:** `{MODEL}`",
        "",
        "## Protocol",
        "",
        "1. MIKAI-arm responses below are auto-generated by `scripts/eval_mikai.py`.",
        "2. For each question, open a **fresh Claude.ai chat with the MIKAI",
        "   connector toggled OFF**, paste the question verbatim, and copy the",
        "   response into the **Claude.ai baseline** block.",
        "3. Score both arms on the rubric. Fill in winner + notes.",
        "4. Save the file as-is; it becomes a regression test.",
        "",
        "---",
        "",
    ]

    for q in QUESTIONS:
        print(f"[{q['id']}] {q['text'][:80]}...")
        resp = call_with_mikai(q["text"], key)
        text, tools = extract_text_and_tools(resp)

        lines.extend(
            [
                f"## {q['id']} — {q['dimension']}",
                "",
                f"**Question:** {q['text']}",
                "",
                f"*Tests:* {q['what_it_tests']}",
                "",
                "### Claude.ai baseline (PASTE MANUALLY — MIKAI OFF)",
                "",
                "```",
                "(paste the Claude.ai response here, with MIKAI connector disabled)",
                "```",
                "",
                "### Claude + MIKAI (auto-generated)",
                "",
                text,
                "",
                "**Tool trace:**",
                "",
            ]
        )
        if tools:
            for t in tools:
                lines.append(
                    f"- `{t['tool']}(" + json.dumps(t["input"]) + ")`"
                )
        else:
            lines.append("_(no MCP tool calls — model answered from training knowledge)_")

        lines.extend(
            [
                "",
                "### Scoring",
                "",
                "| Axis | Baseline | MIKAI |",
                "|---|---|---|",
                "| Specificity (1-5) |  |  |",
                "| Depth (1-5) |  |  |",
                "| Non-obvious insight (0-3+) |  |  |",
                "| Confidence calibration (1-5) |  |  |",
                "",
                "**Winner:** _",
                "",
                "**Notes:** _",
                "",
                "---",
                "",
            ]
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
