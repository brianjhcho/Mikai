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
import math
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

# Echoes pass: traverse from this-week's entities back to older connected ones.
# Anchors come from the last `anchor_window_days` of episodes (we reuse `--days`).
# Echoes are entities reachable within ECHO_HOPS that are dormant for ≥
# DEFAULT_DORMANCY_DAYS with ≥ ECHO_MIN_EPISODES of substantive content.
DEFAULT_DORMANCY_DAYS = 30
DEFAULT_MAX_ECHOES = 5
ECHO_ANCHOR_LIMIT = 10        # top-N this-week entities by mention count
ECHO_HOPS = 3                 # RELATES_TO traversal depth
ECHO_MIN_EPISODES = 2         # echo must have ≥N mention episodes (substance gate)
ECHO_LAST_BEAT_CHARS = 500    # excerpt length per echo's last-mentioning episode
ECHO_MAX_ANCHOR_DEGREE = 80   # skip hub entities — they connect to everything,
                              # so they produce noisy echoes and OOM the traversal.
                              # Medium-degree anchors carry the structural insight.
ECHO_PER_HOP_CAP = 400        # max neighbor rows fetched in a single hop step
                              # (BFS is bounded — paths are not materialized)
ECHO_MAX_PER_ANCHOR = 2       # at most N echoes from any single anchor in the
                              # final slate — forces diversity across anchors

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


ECHOES_SYSTEM_PROMPT = """\
You are MIKAI's "Echoes" pass — the part of the dream that connects today's
threads back to older, dormant ones from the user's bitemporal graph.

The first dream pass has already written ## Who / ## Now / ## Tensions / ## Wants
from the last few days of activity. Your single job: write ONE additional section
called ## Echoes that surfaces older threads the user touched substantively and
then went quiet on.

You receive a ranked list of ECHO CANDIDATES. Each candidate is an entity from
the user's graph that (a) is reachable within a few RELATES_TO hops from an
entity active this week, (b) has been dormant for at least the configured
window, (c) has substantive episode content the user actually engaged with.

For each echo you decide to surface, write a single bullet of the form:

- **<echo name>** ← <bridge entities, in order, NOT repeating anchor/echo> ← **<anchor name>** · dormant <N> days
  · Last beat: "<terse one-line quote or paraphrase of what the user actually
    said about this echo — especially any stated next step that was never
    followed through>"
  · <one sentence on why the connection matters — name the bridge substrate
    explicitly and clarify whether they are distinct goals or aspects of one>

If the anchor and echo are directly connected with NO intermediate bridge
entity (a 1-hop echo), drop the bridge segment entirely:

- **<echo name>** ← **<anchor name>** · dormant <N> days · …

Do NOT include the anchor or echo name in the bridge segment. The bridge is
the SUBSTRATE that links them; it is empty for direct connections.

Rules:
1. DO NOT merge distinct goals just because they share a substrate. If two
   echoes connect via "food technology" but are otherwise different pursuits
   (e.g., ocean farming vs. building MIKAI), say that explicitly. The echo is
   the substrate connection, not a goal merge.
2. PRESERVE THE LAST STATED NEXT STEP. If the user said "I'll email <person>"
   or "I'll reach out to <X>" and never did, surface that exact unfinished move
   in the last-beat quote. This is the highest-value signal.
3. SKIP NOISE. Drop candidates whose name is a generic concept ("technology",
   "system", "things", "ideas"), or whose summary is empty/circular. Better to
   surface 2 strong echoes than 5 weak ones.
4. AT MOST 5 echoes. Aim for 3.
5. BE TERSE. Each bullet readable in under 10 seconds.

Output ONLY the ## Echoes section — start with the literal heading "## Echoes".
No preamble, no changelog, no other sections.
"""

# ── Echoes Cypher ──────────────────────────────────────────────────────
#
# Two queries because composing them in one statement makes the WITH chain
# hard to read and harder to debug. We accept the extra round-trip.

ANCHORS_CYPHER = """
MATCH (anchor:Entity)<-[:MENTIONS]-(ep:Episodic)
WHERE ep.valid_at >= datetime() - duration({days: $window_days})
WITH anchor, count(ep) AS recent_mentions
OPTIONAL MATCH (anchor)-[r:RELATES_TO]-()
WITH anchor, recent_mentions, count(r) AS degree
WHERE degree > 0 AND degree <= $max_degree
ORDER BY recent_mentions DESC
LIMIT $limit
RETURN anchor.uuid AS uuid, anchor.name AS name,
       recent_mentions, degree
"""

# One BFS step: from a frontier set of entity uuids, fetch any RELATES_TO
# neighbors not yet visited. Hard-capped to avoid heap pressure on hub paths.
BFS_HOP_CYPHER = """
MATCH (src:Entity)
WHERE src.uuid IN $src_uuids
MATCH (src)-[:RELATES_TO]-(dst:Entity)
WHERE NOT dst.uuid IN $visited
RETURN DISTINCT src.uuid AS src_uuid, dst.uuid AS dst_uuid, dst.name AS dst_name
LIMIT $cap
"""

# For a batch of candidate uuids, return those whose most-recent mention is
# older than `dormancy_days` and which have at least `min_episodes` total
# mentions (substance gate).
DORMANCY_FILTER_CYPHER = """
MATCH (e:Entity) WHERE e.uuid IN $uuids
MATCH (e)<-[:MENTIONS]-(ep:Episodic)
WITH e,
     max(ep.valid_at) AS most_recent_valid,
     min(ep.valid_at) AS earliest_valid,
     count(ep) AS ep_count
WHERE most_recent_valid < datetime() - duration({days: $dormancy_days})
  AND ep_count >= $min_episodes
RETURN e.uuid AS uuid, e.name AS name, e.summary AS summary,
       toString(most_recent_valid) AS most_recent_valid,
       toString(earliest_valid) AS earliest_valid,
       ep_count
"""

LAST_BEAT_CYPHER = """
MATCH (echo:Entity {uuid: $uuid})<-[:MENTIONS]-(ep:Episodic)
RETURN ep.content AS content, toString(ep.valid_at) AS valid_at
ORDER BY ep.valid_at DESC
LIMIT 1
"""


# Generic terms whose name alone is too low-signal to be an echo regardless of
# graph score. We still let them appear in `path_names` (bridge substrate is
# useful) but block them from being the echo itself.
ECHO_NAME_BLOCKLIST = {
    "technology", "system", "things", "ideas", "concept", "thing",
    "tool", "tools", "stuff", "the user", "user", "brian",
}


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


def fetch_echo_candidates(
    *,
    anchor_window_days: int,
    dormancy_days: int,
    max_echoes: int,
) -> list[dict]:
    """Run the Echoes pass over the graph.

    Returns up to `max_echoes` deduplicated candidates, each with:
        echo_uuid, echo_name, echo_summary, anchor_name, hops, path_names,
        most_recent_valid (ISO date), earliest_valid (ISO date), ep_count,
        last_beat (string excerpt from the most recent mentioning episode).

    The anchor set is the top `ECHO_ANCHOR_LIMIT` entities by mention count in
    the last `anchor_window_days`. From each anchor we walk RELATES_TO up to
    `ECHO_HOPS` and look for connected entities whose own most-recent mention
    is older than `dormancy_days`. We dedup across anchors (an echo reachable
    from multiple anchors keeps its strongest/shortest path) and trim to the
    top `max_echoes` by recency-of-last-mention then by path length.
    """
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ["NEO4J_PASSWORD"]
    driver = GraphDatabase.driver(uri, auth=(user, pw))

    by_echo: dict[str, dict] = {}
    top: list[dict] = []
    try:
        with driver.session() as session:
            anchors = session.run(
                ANCHORS_CYPHER,
                window_days=anchor_window_days,
                max_degree=ECHO_MAX_ANCHOR_DEGREE,
                limit=ECHO_ANCHOR_LIMIT,
            ).data()
            print(
                f"Echoes pass: {len(anchors)} anchor entities "
                f"(last {anchor_window_days}d, degree ≤ {ECHO_MAX_ANCHOR_DEGREE}, "
                f"top {ECHO_ANCHOR_LIMIT} by mentions)",
                file=sys.stderr,
            )

            for a in anchors:
                # BFS from this anchor up to ECHO_HOPS, accumulating the
                # shortest-known path per visited entity. No Cypher path-
                # variables: paths are tracked in Python so the database
                # never materializes them.
                visited: set[str] = {a["uuid"]}
                paths: dict[str, list[str]] = {a["uuid"]: [a["name"]]}
                frontier: list[str] = [a["uuid"]]

                for hop in range(1, ECHO_HOPS + 1):
                    if not frontier:
                        break
                    rows = session.run(
                        BFS_HOP_CYPHER,
                        src_uuids=frontier,
                        visited=list(visited),
                        cap=ECHO_PER_HOP_CAP,
                    ).data()
                    new_frontier: list[str] = []
                    for r in rows:
                        dst = r["dst_uuid"]
                        if dst in visited:
                            continue
                        visited.add(dst)
                        src_path = paths[r["src_uuid"]]
                        paths[dst] = src_path + [r["dst_name"]]
                        new_frontier.append(dst)

                    if not new_frontier:
                        frontier = []
                        continue

                    # Check dormancy on entities newly reached at this hop.
                    dormant = session.run(
                        DORMANCY_FILTER_CYPHER,
                        uuids=new_frontier,
                        dormancy_days=dormancy_days,
                        min_episodes=ECHO_MIN_EPISODES,
                    ).data()
                    for d in dormant:
                        name = (d.get("name") or "").strip()
                        if not name or name.lower() in ECHO_NAME_BLOCKLIST:
                            continue
                        uuid = d["uuid"]
                        existing = by_echo.get(uuid)
                        if existing is None or hop < existing["hops"]:
                            by_echo[uuid] = {
                                "echo_uuid": uuid,
                                "echo_name": name,
                                "echo_summary": d.get("summary") or "",
                                "anchor_name": a["name"],
                                "hops": hop,
                                "path_names": paths[uuid],
                                "most_recent_valid": d["most_recent_valid"],
                                "earliest_valid": d["earliest_valid"],
                                "ep_count": d["ep_count"],
                            }

                    frontier = new_frontier

            # Rank by substance × dormancy depth, lightly penalized by hops.
            # log1p so neither factor dominates; high-substance long-dormant
            # items at hop 2-3 still beat thin-substance just-dormant items.
            now_utc = datetime.now(tz=timezone.utc)
            for c in by_echo.values():
                c["days_dormant"] = _days_since(c["most_recent_valid"], now_utc)
                c["score"] = (
                    math.log1p(max(c["ep_count"], 1))
                    * math.log1p(max(c["days_dormant"], 1))
                    / max(c["hops"], 1)
                )
            ranked = sorted(by_echo.values(), key=lambda r: r["score"], reverse=True)

            # Per-anchor diversity: at most ECHO_MAX_PER_ANCHOR echoes per anchor
            # so we don't return 5 items all reached via the same this-week
            # entity (defeats the connection-across-life-areas insight).
            top = []
            per_anchor: dict[str, int] = {}
            for c in ranked:
                a = c["anchor_name"]
                if per_anchor.get(a, 0) >= ECHO_MAX_PER_ANCHOR:
                    continue
                top.append(c)
                per_anchor[a] = per_anchor.get(a, 0) + 1
                if len(top) >= max_echoes:
                    break

            # Fetch last-beat quote for each surviving candidate.
            for c in top:
                qr = session.run(LAST_BEAT_CYPHER, uuid=c["echo_uuid"]).data()
                content = (qr[0]["content"] if qr else "") or ""
                c["last_beat"] = content.strip()[:ECHO_LAST_BEAT_CHARS]
    finally:
        driver.close()

    print(
        f"Echoes pass: {len(by_echo)} unique candidates after BFS; "
        f"top {len(top)} after diversity cap (≤{ECHO_MAX_PER_ANCHOR}/anchor).",
        file=sys.stderr,
    )
    if top:
        print("Echoes pass: selected candidates —", file=sys.stderr)
        for c in top:
            print(
                f"  · score={c['score']:.2f}  hops={c['hops']}  "
                f"ep_count={c['ep_count']}  dormant={c['days_dormant']}d  "
                f"[{c['anchor_name']}] → {c['echo_name']}",
                file=sys.stderr,
            )
    return top


def _days_since(iso_str: str, now: datetime) -> int:
    """Days between an ISO-formatted timestamp string and `now`. Returns 0
    on parse failure (the echo will sort low rather than crash the pass)."""
    if not iso_str:
        return 0
    try:
        # Normalize Neo4j's `[UTC]` suffix and zoneless localdatetime values.
        s = iso_str.split("[", 1)[0]
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (now - dt).days)
    except (ValueError, TypeError):
        return 0


def format_echoes_for_prompt(candidates: list[dict]) -> str:
    chunks = []
    for c in candidates:
        last_seen = (c.get("most_recent_valid") or "")[:10]
        first_seen = (c.get("earliest_valid") or "")[:10]
        # path_names is [anchor, intermediate1, ..., intermediateN, echo]. The
        # bridge is JUST the intermediates — anchor and echo are passed
        # separately. Don't repeat them or the model duplicates them in output.
        path = c.get("path_names") or []
        bridge_only = path[1:-1] if len(path) >= 2 else []
        bridge = (
            " ← ".join(bridge_only)
            if bridge_only
            else f"(direct, {c['hops']} hop)"
        )
        summary = (c.get("echo_summary") or "").strip()
        if len(summary) > 400:
            summary = summary[:400] + " […]"
        last_beat = (c.get("last_beat") or "").strip()
        chunks.append(
            f"ECHO: {c['echo_name']}\n"
            f"  anchor (this week): {c['anchor_name']}\n"
            f"  hops: {c['hops']}\n"
            f"  bridge entities (between anchor and echo, NOT including either): {bridge}\n"
            f"  first mentioned: {first_seen}\n"
            f"  last mentioned:  {last_seen} (dormant {c.get('days_dormant', '?')} days)\n"
            f"  total episodes:  {c['ep_count']}\n"
            f"  entity summary:  {summary}\n"
            f"  last beat (from most recent mention episode):\n"
            f"    {last_beat}"
        )
    return "\n\n---\n\n".join(chunks)


def compose_echoes_section(
    candidates: list[dict],
    *,
    model: str,
    client: OpenAI,
) -> str:
    if not candidates:
        return ""
    user_prompt = (
        "=== ECHO CANDIDATES (ranked, most recent dormancy first) ===\n\n"
        + format_echoes_for_prompt(candidates)
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": ECHOES_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text.lstrip().startswith("## Echoes"):
        text = "## Echoes\n" + text.lstrip()
    return text


def inject_echoes(wiki_text: str, echoes_text: str) -> str:
    if not echoes_text:
        return wiki_text
    return wiki_text.rstrip() + "\n\n" + echoes_text.strip() + "\n"


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


def run_dream(
    *,
    days: int,
    groups: list[str],
    model: str,
    dry_run: bool,
    do_echoes: bool = True,
    dormancy_days: int = DEFAULT_DORMANCY_DAYS,
    max_echoes: int = DEFAULT_MAX_ECHOES,
) -> int:
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

    # Pass 2: Echoes. Graph traversal back to dormant connected entities.
    # Best-effort: a failure here must not break the standard dream output.
    if do_echoes:
        try:
            candidates = fetch_echo_candidates(
                anchor_window_days=days,
                dormancy_days=dormancy_days,
                max_echoes=max_echoes,
            )
            if candidates:
                print(
                    f"Composing ## Echoes section from {len(candidates)} candidates "
                    f"(dormancy ≥ {dormancy_days}d)...",
                    file=sys.stderr,
                )
                echoes_text = compose_echoes_section(
                    candidates, model=model, client=client,
                )
                new_wiki = inject_echoes(new_wiki, echoes_text)
            else:
                print(
                    f"Echoes pass: no candidates passed the dormancy/substance gate "
                    f"(dormancy_days={dormancy_days})",
                    file=sys.stderr,
                )
        except Exception as e:
            print(f"WARN: Echoes pass failed (non-fatal): {e}", file=sys.stderr)

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
    parser.add_argument("--no-echoes", action="store_true",
                        help="Skip the Echoes pass (just the standard 4-section synthesis).")
    parser.add_argument("--dormancy-days", type=int, default=DEFAULT_DORMANCY_DAYS,
                        help=f"Echo candidates must be dormant ≥N days "
                             f"(default {DEFAULT_DORMANCY_DAYS}).")
    parser.add_argument("--max-echoes", type=int, default=DEFAULT_MAX_ECHOES,
                        help=f"Max number of echoes to surface "
                             f"(default {DEFAULT_MAX_ECHOES}).")
    args = parser.parse_args()

    load_env()
    groups = args.groups or DEFAULT_GROUPS
    sys.exit(run_dream(
        days=args.days, groups=groups, model=args.model, dry_run=args.dry_run,
        do_echoes=not args.no_echoes,
        dormancy_days=args.dormancy_days,
        max_echoes=args.max_echoes,
    ))


if __name__ == "__main__":
    main()
