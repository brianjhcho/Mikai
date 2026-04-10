"""
import_sequential.py

Imports episodes one at a time using add_episode() (singular).
This is Graphiti's intended pattern — scales to any graph size.

Supports:
  - Apple Notes (from dump file)
  - Claude threads (turn-by-turn with saga)
  - Perplexity threads (query + answer with saga)

Usage:
    # Apple Notes (remaining)
    python scripts/import_sequential.py --source notes --dump /tmp/mikai_notes_all.txt --skip-existing

    # Claude threads
    python scripts/import_sequential.py --source claude --db-path ~/.mikai/mikai.db

    # Perplexity threads
    python scripts/import_sequential.py --source perplexity --db-path ~/.mikai/mikai.db --limit 50
"""

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from graphiti_core import Graphiti
from graphiti_core.llm_client.config import LLMConfig, ModelSize
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.embedder.voyage import VoyageAIEmbedder, VoyageAIEmbedderConfig
from graphiti_core.cross_encoder.client import CrossEncoderClient
from graphiti_core.nodes import EpisodeType

SKIP_PATTERNS = ["api key", "password", "secret", "credential", "token"]


# ── Clients ──────────────────────────────────────────────────────────────────

class DeepSeekClient(OpenAIGenericClient):
    async def _generate_response(self, messages, response_model=None, max_tokens=8192, model_size=ModelSize.medium):
        from openai.types.chat import ChatCompletionMessageParam
        openai_messages = []
        for m in messages:
            m.content = self._clean_input(m.content)
            if m.role == 'user': openai_messages.append({'role': 'user', 'content': m.content})
            elif m.role == 'system': openai_messages.append({'role': 'system', 'content': m.content})
        if response_model is not None:
            schema = response_model.model_json_schema()
            for i, msg in enumerate(openai_messages):
                if msg['role'] == 'system':
                    openai_messages[i] = {'role': 'system', 'content': str(msg['content']) + f"\n\nRespond with valid JSON matching this schema:\n```json\n{json.dumps(schema, indent=2)}\n```\nRespond ONLY with the JSON object."}
                    break
            else:
                openai_messages.insert(0, {'role': 'system', 'content': f"Respond with valid JSON:\n```json\n{json.dumps(schema, indent=2)}\n```"})
        response = await self.client.chat.completions.create(model=self.model, messages=openai_messages, temperature=self.temperature, max_tokens=self.max_tokens, response_format={'type': 'json_object'})
        return json.loads(response.choices[0].message.content or '{}')


class PassthroughReranker(CrossEncoderClient):
    async def rank(self, query, passages):
        return [(p, 1.0 - i * 0.01) for i, p in enumerate(passages)]


# ── Parsers ──────────────────────────────────────────────────────────────────

def parse_notes_dump(path):
    """Parse Apple Notes dump into episodes."""
    notes = []
    current = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line == "===NOTE_START===":
                current = {"name": "", "date": "", "body_lines": []}
            elif line == "===NOTE_END===" and current:
                body = "\n".join(current["body_lines"]).strip()
                name = current["name"]
                is_sensitive = any(p in name.lower() for p in SKIP_PATTERNS)
                if len(body) > 50 and not is_sensitive:
                    notes.append({"name": name, "date": current["date"], "body": body[:5000]})
                current = None
            elif current is not None:
                if line.startswith("NAME:") and not current["name"]:
                    current["name"] = line[5:]
                elif line.startswith("DATE:") and not current["date"]:
                    current["date"] = line[5:]
                else:
                    current["body_lines"].append(line)
    return notes


def parse_claude_threads(db_path):
    """Parse Claude threads into turn-by-turn episodes grouped by saga."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT label, raw_content, created_at FROM sources WHERE source = 'claude-thread' "
        "AND label NOT IN ('users','memories','projects','conversations') "
        "AND LENGTH(raw_content) > 100 ORDER BY created_at"
    ).fetchall()
    db.close()

    all_episodes = []
    for row in rows:
        label = row["label"]
        if any(p in label.lower() for p in SKIP_PATTERNS):
            continue

        raw = row["raw_content"]
        created = row["created_at"] or "2026-01-01T00:00:00Z"
        saga_name = f"claude: {label[:80]}"

        # Parse turns
        turns = []
        current_role = None
        current_lines = []
        for line in raw.split('\n'):
            if line.startswith('[User]:'):
                if current_role:
                    turns.append({'role': current_role, 'content': '\n'.join(current_lines).strip()})
                current_role = 'user'
                current_lines = [line[7:].strip()]
            elif line.startswith('[Assistant]:'):
                if current_role:
                    turns.append({'role': current_role, 'content': '\n'.join(current_lines).strip()})
                current_role = 'assistant'
                current_lines = [line[12:].strip()]
            else:
                current_lines.append(line)
        if current_role:
            turns.append({'role': current_role, 'content': '\n'.join(current_lines).strip()})

        # Only keep first 20 turns per thread (most substance is early)
        for i, turn in enumerate(turns[:20]):
            if len(turn['content']) < 20:
                continue
            all_episodes.append({
                'saga': saga_name,
                'name': f"Turn {i+1} ({turn['role']})",
                'body': f"{turn['role']}: {turn['content'][:3000]}",
                'date': created,
                'turn_index': i,
                'source_type': 'claude-thread',
            })

    return all_episodes


def parse_perplexity_threads(db_path, limit=None):
    """Parse Perplexity threads into query + answer episodes grouped by saga."""
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    query = (
        "SELECT label, raw_content, created_at FROM sources WHERE source = 'perplexity' "
        "AND LENGTH(raw_content) > 200 ORDER BY created_at"
    )
    if limit:
        query += f" LIMIT {limit}"
    rows = db.execute(query).fetchall()
    db.close()

    all_episodes = []
    for row in rows:
        label = row["label"]
        if any(p in label.lower() for p in SKIP_PATTERNS):
            continue

        raw = row["raw_content"]
        created = row["created_at"] or "2026-01-01T00:00:00Z"
        saga_name = f"perplexity: {label[:80]}"

        # Extract user query and final answer from JSON structure
        try:
            if raw.startswith('[Assistant]:'):
                raw = raw[len('[Assistant]:'):].strip()

            # Handle concatenated JSON arrays by parsing only the first array
            bracket_depth = 0
            end_pos = 0
            for ci, c in enumerate(raw):
                if c == '[': bracket_depth += 1
                elif c == ']': bracket_depth -= 1
                if bracket_depth == 0 and ci > 0:
                    end_pos = ci + 1
                    break
            if end_pos > 0:
                raw = raw[:end_pos]

            steps = json.loads(raw) if raw.startswith('[') else [json.loads(raw)]

            user_query = None
            answer = None
            for step in steps:
                if isinstance(step, dict):
                    step_type = step.get('step_type', '')
                    content = step.get('content', {})
                    if step_type == 'INITIAL_QUERY' and isinstance(content, dict):
                        user_query = content.get('query', '')
                    elif step_type == 'FINAL' and isinstance(content, dict):
                        answer_raw = content.get('answer', '')
                        try:
                            answer_obj = json.loads(answer_raw)
                            answer = answer_obj.get('answer', answer_raw) if isinstance(answer_obj, dict) else answer_raw
                        except (json.JSONDecodeError, TypeError):
                            answer = answer_raw

            if user_query and len(user_query) > 10:
                all_episodes.append({
                    'saga': saga_name,
                    'name': f"Query",
                    'body': f"user: {user_query[:2000]}",
                    'date': created,
                    'turn_index': 0,
                    'source_type': 'perplexity',
                })
            if answer and len(answer) > 50:
                all_episodes.append({
                    'saga': saga_name,
                    'name': f"Answer",
                    'body': f"assistant: {answer[:3000]}",
                    'date': created,
                    'turn_index': 1,
                    'source_type': 'perplexity',
                })
        except (json.JSONDecodeError, TypeError):
            # Fallback: treat as plain text
            if len(raw) > 100:
                all_episodes.append({
                    'saga': saga_name,
                    'name': label[:60],
                    'body': raw[:3000],
                    'date': created,
                    'turn_index': 0,
                    'source_type': 'perplexity',
                })

    return all_episodes


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Sequential Graphiti import")
    parser.add_argument("--source", required=True, choices=["notes", "claude", "perplexity"])
    parser.add_argument("--dump", default="/tmp/mikai_notes_all.txt", help="Notes dump file")
    parser.add_argument("--db-path", default=str(Path.home() / ".mikai" / "mikai.db"))
    parser.add_argument("--skip-existing", action="store_true", help="Skip notes already in graph")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between episodes")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--group-id", default="mikai-default")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Parse episodes based on source
    if args.source == "notes":
        raw_notes = parse_notes_dump(args.dump)
        if args.skip_existing:
            # Get existing episode names from Neo4j
            from neo4j import AsyncGraphDatabase
            driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "mikai-local-dev"))
            async with driver.session() as session:
                result = await session.run(
                    "MATCH (e:Episodic) WHERE e.group_id = $gid RETURN e.source_description AS desc",
                    gid=args.group_id,
                )
                existing = set()
                async for r in result:
                    existing.add(r["desc"])
            await driver.close()
            print(f"Existing episodes: {len(existing)}", flush=True)
            episodes = []
            for n in raw_notes:
                desc = f"apple-notes: {n['name']}"
                if desc not in existing:
                    episodes.append({
                        'saga': None,
                        'name': n['name'],
                        'body': n['body'],
                        'date': n['date'],
                        'turn_index': 0,
                        'source_type': 'apple-notes',
                    })
        else:
            episodes = [{'saga': None, 'name': n['name'], 'body': n['body'], 'date': n['date'], 'turn_index': 0, 'source_type': 'apple-notes'} for n in raw_notes]
    elif args.source == "claude":
        episodes = parse_claude_threads(args.db_path)
    elif args.source == "perplexity":
        episodes = parse_perplexity_threads(args.db_path, args.limit)

    if args.limit and args.source != "perplexity":
        episodes = episodes[:args.limit]

    print(f"Source: {args.source}", flush=True)
    print(f"Episodes to import: {len(episodes)}", flush=True)
    if args.source in ("claude", "perplexity"):
        sagas = set(e['saga'] for e in episodes if e.get('saga'))
        print(f"Sagas (conversations): {len(sagas)}", flush=True)

    if args.dry_run:
        for ep in episodes[:10]:
            saga = f" [saga: {ep['saga'][:40]}]" if ep.get('saga') else ""
            print(f"  {ep['name'][:50]} ({len(ep['body'])} chars){saga}", flush=True)
        if len(episodes) > 10:
            print(f"  ... and {len(episodes) - 10} more", flush=True)
        return

    # Connect to Graphiti
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    voyage_key = os.environ.get("VOYAGE_API_KEY")
    if not deepseek_key or not voyage_key:
        print("Need DEEPSEEK_API_KEY and VOYAGE_API_KEY", file=sys.stderr)
        sys.exit(1)

    llm = DeepSeekClient(
        config=LLMConfig(api_key=deepseek_key, model="deepseek-chat", small_model="deepseek-chat", base_url="https://api.deepseek.com"),
        max_tokens=8192,
    )
    embedder = VoyageAIEmbedder(config=VoyageAIEmbedderConfig(api_key=voyage_key, model="voyage-3"))
    graphiti = Graphiti("bolt://localhost:7687", "neo4j", "mikai-local-dev",
                        llm_client=llm, embedder=embedder, cross_encoder=PassthroughReranker())
    await graphiti.build_indices_and_constraints()

    # Import sequentially
    success = 0
    failed = 0
    start = time.time()
    current_saga = None

    for i, ep in enumerate(episodes):
        name = ep['name'][:50]
        chars = len(ep['body'])
        saga_info = f" [{ep['saga'][:30]}...]" if ep.get('saga') else ""
        print(f"[{i+1}/{len(episodes)}] {name} ({chars} chars){saga_info}", flush=True)

        try:
            ref_time = datetime.fromisoformat(ep['date'].replace('Z', '+00:00')) if ep['date'] else datetime.now(timezone.utc)
        except ValueError:
            ref_time = datetime.now(timezone.utc)

        try:
            result = await graphiti.add_episode(
                name=ep['name'][:100],
                episode_body=ep['body'],
                source=EpisodeType.message if ep['source_type'] in ('claude-thread', 'perplexity') else EpisodeType.text,
                source_description=f"{ep['source_type']}: {ep['name'][:80]}",
                reference_time=ref_time,
                group_id=args.group_id,
                saga=ep.get('saga'),
            )
            nodes = len(result.nodes) if result and result.nodes else 0
            edges = len(result.edges) if result and result.edges else 0
            print(f"  OK: +{nodes} nodes, +{edges} edges", flush=True)
            success += 1
        except Exception as e:
            err = str(e)[:120]
            print(f"  FAIL: {err}", flush=True)
            failed += 1

        # Progress
        if (i + 1) % 20 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(episodes) - i - 1) / rate / 60 if rate > 0 else 0
            print(f"  --- {i+1}/{len(episodes)} | {success} ok, {failed} fail | ~{remaining:.0f}m left ---", flush=True)

        await asyncio.sleep(args.delay)

    elapsed = time.time() - start
    await graphiti.close()

    print(f"\nDone in {elapsed/60:.1f} min", flush=True)
    print(f"  Success: {success}/{len(episodes)}", flush=True)
    print(f"  Failed: {failed}", flush=True)


if __name__ == "__main__":
    # Load env
    env_path = Path(__file__).parent.parent.parent.parent / '.env.local'
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            key, _, val = line.partition('=')
            if key and val and key not in os.environ: os.environ[key] = val
    asyncio.run(main())
