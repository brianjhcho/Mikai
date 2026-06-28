"""
MIKAI dream — minimal prototype (the thesis, simplest form).

The dream is a synthesis pass: read the user's recent activity (Graphiti
episodes) + the current wiki, and rewrite the wiki to reflect what the user
currently WANTS, VALUES, is DOING, and is CONFLICTED about. The wiki is the
LLM-native projection an assistant reads whole; the graph is the immutable
substrate the dream reads from and never edits.

Lineage (see docs/MEMORY_ARCHITECTURE.md, navy-windshield):
  - Karpathy's LLM Wiki   → the wiki is LLM-owned markdown, read whole, compiled
                            by the dream (its maintenance routine). log.md = the
                            append-only timeline.
  - Generative Agents     → the dream is "reflection": periodic synthesis over a
                            recent memory stream. (Numeric importance + importance-
                            triggered cadence deferred; recency window + in-prompt
                            salience for now.)
  - MIKAI epistemic thesis → tensions are priority-0: surface them, never resolve
                            them to make the wiki tidy.

This file is deliberately the SIMPLEST version: one LLM call, no numeric
confidence/importance/decay. Those are deferred "as the system develops."

Usage:
    python dream.py --dry-run            # print proposed wiki.md, write nothing
    python dream.py --dry-run --days 14
    python dream.py                      # write ~/.mikai/wiki/wiki.md + append log.md
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase
from openai import OpenAI

MIKAI_DIR = Path.home() / ".mikai"
WIKI_DIR = MIKAI_DIR / "wiki"
WIKI_PATH = WIKI_DIR / "wiki.md"
LOG_PATH = WIKI_DIR / "log.md"
ENV_FILE = MIKAI_DIR / "launchd.env"

DEFAULT_GROUPS = ["claude-thread"]
MAX_CHARS_PER_EPISODE = 1500
MAX_EPISODES = 150
CHANGELOG_DELIM = "===CHANGELOG==="

SYSTEM_PROMPT = """\
You are MIKAI's "dream": a synthesis pass that runs over a user's recent activity.
You read the user's recent conversations/notes and the CURRENT WIKI, and you
rewrite the wiki to reflect what the user currently WANTS, VALUES, is DOING, and
is CONFLICTED about. An assistant reads this wiki whole to understand the user,
so it must be high-signal and honest.

Rules:
1. SURFACE TENSIONS, DO NOT RESOLVE THEM. If the user holds two incompatible
   goals or beliefs at once, record BOTH under ## Tensions. Never pick a winner
   just to make the wiki tidy — unresolved thinking is the highest-value signal.
2. WEIGHT BY DEPTH, NOT VOLUME. Processed reflections, explicit decisions, and
   stated wants matter far more than passing fragments. Recurring themes (across
   multiple conversations) outweigh one-off mentions — EXCEPT a single pivotal
   life event, which matters regardless of how often it appears.
3. MARK MOVEMENT. If something changed state (exploring → decided → acting →
   stalled) or a belief was revised, say so explicitly.
4. GROUND EVERYTHING. Use only the provided material; do not invent. If recent
   activity is thin, keep the prior wiki and change little.

Output the new wiki.md as markdown with EXACTLY these four sections, in order:

## Who
The user's current self-model: values, working style, identity-level facts.

## Now
Active threads/projects and their state (exploring/decided/acting/stalled).

## Tensions
Unresolved contradictions the user is actively holding. Never empty this to look
clean; if there are none in the material, write "(none surfaced this pass)".

## Wants
Goals/desires the recent activity points toward. Express certainty in words
("clearly", "tentatively"), never numbers.

Write in the third person about the user ("Brian is..."). Be concise.

After the wiki, output a line containing EXACTLY:
===CHANGELOG===
then 2-5 bullet points describing what changed versus the prior wiki (the
revision record). If this is the first dream, summarize what you established.
"""


def load_env() -> None:
    """Populate os.environ from ~/.mikai/launchd.env for manual runs (the launchd
    runner already sources it). Does not overwrite already-set vars."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def fetch_recent_episodes(*, groups: list[str], days: int) -> list[dict]:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ["NEO4J_PASSWORD"]
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    query = """
    MATCH (e:Episodic)
    WHERE e.group_id IN $groups
      AND e.valid_at >= datetime() - duration({days: $days})
    RETURN e.content AS content, e.group_id AS group_id,
           toString(e.valid_at) AS valid_at, e.name AS name
    ORDER BY e.valid_at ASC
    LIMIT $limit
    """
    try:
        with driver.session() as session:
            rows = session.run(
                query, groups=groups, days=days, limit=MAX_EPISODES
            ).data()
    finally:
        driver.close()
    return rows


def format_episodes(rows: list[dict]) -> str:
    chunks = []
    for r in rows:
        content = (r.get("content") or "").strip()
        if not content:
            continue
        if len(content) > MAX_CHARS_PER_EPISODE:
            content = content[:MAX_CHARS_PER_EPISODE] + " […]"
        ts = (r.get("valid_at") or "")[:10]
        name = r.get("name") or r.get("group_id") or ""
        chunks.append(f"[{ts}] ({name})\n{content}")
    return "\n\n---\n\n".join(chunks)


def run_dream(*, days: int, groups: list[str], model: str, dry_run: bool) -> int:
    rows = fetch_recent_episodes(groups=groups, days=days)
    if not rows:
        print(f"No episodes in groups {groups} within the last {days} days. "
              "Nothing to dream over.", file=sys.stderr)
        return 1
    episodes_text = format_episodes(rows)
    current_wiki = WIKI_PATH.read_text() if WIKI_PATH.exists() else "(empty — first dream)"

    user_prompt = (
        f"=== CURRENT WIKI ===\n{current_wiki}\n\n"
        f"=== RECENT ACTIVITY (last {days} days, {len(rows)} episodes, chronological) ===\n"
        f"{episodes_text}"
    )

    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )
    print(f"Dreaming over {len(rows)} episodes from {groups} "
          f"(last {days}d) with {model}...", file=sys.stderr)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )
    output = resp.choices[0].message.content or ""

    if CHANGELOG_DELIM in output:
        new_wiki, changelog = output.split(CHANGELOG_DELIM, 1)
    else:
        new_wiki, changelog = output, "(model did not emit a changelog)"
    new_wiki = new_wiki.strip() + "\n"
    changelog = changelog.strip()

    if dry_run:
        print("\n" + "=" * 72)
        print("PROPOSED wiki.md (DRY RUN — nothing written)")
        print("=" * 72 + "\n")
        print(new_wiki)
        print("=" * 72)
        print("CHANGELOG (would append to log.md)")
        print("=" * 72)
        print(changelog)
        return 0

    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    WIKI_PATH.write_text(new_wiki)
    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M")
    with LOG_PATH.open("a") as f:
        f.write(f"\n## Dream {stamp}  ·  {len(rows)} episodes, last {days}d\n{changelog}\n")
    print(f"Wrote {WIKI_PATH} and appended to {LOG_PATH}.", file=sys.stderr)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="MIKAI dream — synthesize the wiki.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print proposed wiki.md; write nothing.")
    parser.add_argument("--days", type=int, default=7,
                        help="Recency window for the memory stream (default 7).")
    parser.add_argument("--group", action="append", dest="groups", default=None,
                        help="Episode group_id to include (repeatable). Default: claude-thread.")
    parser.add_argument("--model", default="deepseek-chat",
                        help="Synthesis model (default deepseek-chat).")
    args = parser.parse_args()

    load_env()
    groups = args.groups or DEFAULT_GROUPS
    sys.exit(run_dream(
        days=args.days, groups=groups, model=args.model, dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
