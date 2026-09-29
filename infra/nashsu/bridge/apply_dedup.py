"""Apply dedup MERGE verdicts from an R5 dedup report to a live wiki vault.

Two-phase, safety-first:

  --phase judge   Read-only. For every HIGH pair, ask `claude -p` to judge
                   MERGE / KEEP / HUB and write incremental verdicts to
                   --verdicts. Safe to re-run; never touches the vault.

  --phase apply   Destructive. Reads a --verdicts file (from judge phase),
                   backs up the vault, LLM-merges bodies for every MERGE
                   verdict, writes the canonical page + a retire stub for
                   the loser. HUB/KEEP verdicts are no-ops. Never deletes —
                   retired pages become stubs with `retired_to:` frontmatter.

After apply, inbound wikilinks still point at retired slugs — fix them with
rewrite-retire-stubs.ts (see --help / the printed command at the end of apply).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

_FRONTMATTER_RX = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)

JUDGE_PROMPT = """You are auditing a knowledge-base for duplicate concept pages.
Below are two candidate pages. Decide if they represent THE SAME concept
(should be merged) or DIFFERENT concepts (should be kept separate).

PAGE A: {slug_a}
{body_a}

PAGE B: {slug_b}
{body_b}

Output JSON with exactly these fields:
{{
  "verdict": "MERGE" | "KEEP" | "HUB",
  "reasoning": "<one sentence>",
  "canonical_slug": "<the slug to keep if MERGE, else null>",
  "confidence": <0.0-1.0>
}}

MERGE = same concept, different slugs. KEEP = related but genuinely distinct.
HUB = one is a specific example of the other; keep both but link.
"""

MERGE_PROMPT = """Combine these two knowledge-base page bodies into ONE canonical body.
Preserve every unique claim from both. Deduplicate redundant sentences.
Keep wikilinks intact. Output ONLY the merged body content (no frontmatter,
no explanation).

BODY A (canonical {winner}):
{body_a}

BODY B (retiring {loser}):
{body_b}
"""


def ensure_user_path() -> None:
    extra = (
        Path.home() / ".local" / "bin",
        Path.home() / ".superset" / "bin",
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
    )
    parts = os.environ.get("PATH", "").split(os.pathsep)
    for p in extra:
        if p.is_dir() and str(p) not in parts:
            parts.append(str(p))
    os.environ["PATH"] = os.pathsep.join(parts)


def claude_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}


def call_claude(prompt: str, model: str = "claude-sonnet-4-5", timeout: float = 180.0) -> str:
    """Blocking `claude -p --output-format json` call. Returns the assistant's
    text result (the `result` field of the CLI's JSON envelope)."""
    ensure_user_path()
    argv = ["claude", "-p", "--model", model, "--output-format", "json", "--tools", ""]
    proc = subprocess.run(
        argv,
        input=prompt,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=claude_env(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed (rc={proc.returncode}): {proc.stderr[:500]}")
    envelope = json.loads(proc.stdout)
    result = envelope.get("result")
    if not isinstance(result, str):
        raise RuntimeError(f"claude -p json envelope missing 'result': {proc.stdout[:500]}")
    return result


def extract_json_object(text: str) -> dict:
    """Model output is usually a bare JSON object but may be fenced in
    ```json ... ``` — strip fences, then parse the first {...} block."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object found in: {text[:300]}")
    return json.loads(text[start:end + 1])


def read_page(vault: Path, slug: str) -> tuple[str, str, str]:
    """Returns (full_text, frontmatter_block, body)."""
    path = vault / "concepts" / f"{slug}.md"
    text = path.read_text(encoding="utf-8", errors="replace")
    m = _FRONTMATTER_RX.match(text)
    if m:
        return text, m.group(0), text[m.end():]
    return text, "", text


def parse_frontmatter(fm_block: str) -> dict[str, str]:
    """Very small line-oriented frontmatter parser — good enough for the
    flat `key: value` / `key: [a, b]` shape nashsu emits."""
    inner = _FRONTMATTER_RX.match(fm_block)
    body = inner.group(1) if inner else fm_block.strip("- \n")
    out: dict[str, str] = {}
    for line in body.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def parse_list_field(raw: str) -> list[str]:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    items = [x.strip().strip('"').strip("'") for x in raw.split(",")]
    return [x for x in items if x]


def render_list_field(items: list[str]) -> str:
    seen: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.append(it)
    return "[" + ", ".join(seen) + "]"


def union_frontmatter(fm_a: dict[str, str], fm_b: dict[str, str], keep_from: dict[str, str]) -> str:
    """Build the merged frontmatter block: keep_from's scalar fields, but
    union the list-shaped fields (`related`, `sources`, `tags`) across a+b."""
    lines = ["---"]
    list_fields = {"related", "sources", "tags"}
    handled: set[str] = set()
    for k, v in keep_from.items():
        if k in list_fields:
            merged = parse_list_field(fm_a.get(k, "")) + parse_list_field(fm_b.get(k, ""))
            lines.append(f"{k}: {render_list_field(merged)}")
        else:
            lines.append(f"{k}: {v}")
        handled.add(k)
    for k in list_fields - handled:
        if k in fm_a or k in fm_b:
            merged = parse_list_field(fm_a.get(k, "")) + parse_list_field(fm_b.get(k, ""))
            lines.append(f"{k}: {render_list_field(merged)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def load_pairs(report_path: Path) -> list[dict]:
    data = json.loads(report_path.read_text())
    return data["pairs"]["HIGH"]


def load_verdicts(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def save_verdicts(path: Path, verdicts: list[dict]) -> None:
    path.write_text(json.dumps(verdicts, indent=2))


def phase_judge(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser()
    report_path = Path(args.report)
    verdicts_path = Path(args.verdicts)

    pairs = load_pairs(report_path)
    if args.limit:
        pairs = pairs[:args.limit]

    verdicts = load_verdicts(verdicts_path)
    done = {(v["retire"], v["retire_to"]) for v in verdicts}

    total = len(pairs)
    for i, pair in enumerate(pairs, 1):
        slug_a, slug_b = pair["retire"], pair["retire_to"]
        if (slug_a, slug_b) in done:
            print(f"[{i}/{total}] {slug_a} <-> {slug_b} (cos {pair['cosine']}) -> already judged, skip")
            continue

        path_a = vault / "concepts" / f"{slug_a}.md"
        path_b = vault / "concepts" / f"{slug_b}.md"
        if not path_a.exists() or not path_b.exists():
            print(f"[{i}/{total}] {slug_a} <-> {slug_b} -> SKIP (missing page: "
                  f"{slug_a if not path_a.exists() else slug_b})")
            continue

        _, _, body_a = read_page(vault, slug_a)
        _, _, body_b = read_page(vault, slug_b)

        prompt = JUDGE_PROMPT.format(slug_a=slug_a, body_a=body_a.strip(),
                                      slug_b=slug_b, body_b=body_b.strip())
        try:
            raw = call_claude(prompt, model=args.model)
            parsed = extract_json_object(raw)
            verdict = parsed.get("verdict")
            canonical = parsed.get("canonical_slug")
            reasoning = parsed.get("reasoning")
            confidence = parsed.get("confidence")
            error = None
        except Exception as exc:  # noqa: BLE001
            verdict = None
            canonical = None
            reasoning = None
            confidence = None
            error = str(exc)[:500]

        record = {
            "retire": slug_a,
            "retire_to": slug_b,
            "cosine": pair.get("cosine"),
            "verdict": verdict,
            "canonical_slug": canonical,
            "reasoning": reasoning,
            "confidence": confidence,
            "error": error,
            "judged_at": datetime.now(timezone.utc).isoformat(),
        }
        verdicts.append(record)
        save_verdicts(verdicts_path, verdicts)

        if error:
            print(f"[{i}/{total}] {slug_a} <-> {slug_b} (cos {pair['cosine']}) -> ERROR: {error}")
        else:
            print(f"[{i}/{total}] {slug_a} <-> {slug_b} (cos {pair['cosine']}) "
                  f"-> {verdict} canonical={canonical}")

    print(f"\nwrote {verdicts_path} ({len(verdicts)} verdicts)")
    return 0


def make_backup(vault: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(f"/tmp/vault-backup-{ts}.tar.gz")
    dirs = ["concepts", "entities", "wisdom"]
    with tarfile.open(out, "w:gz") as tar:
        for d in dirs:
            full = vault / d
            if full.exists():
                tar.add(full, arcname=d)
    return out


def resolve_winner_loser(verdict: dict) -> tuple[str, str]:
    """Returns (winner, loser). The LLM's canonical_slug may pick either
    side of the pair — it can disagree with the report's default retire_to
    (which was only a body-length heuristic)."""
    r, rt = verdict["retire"], verdict["retire_to"]
    canonical = verdict.get("canonical_slug")
    if canonical == r:
        return r, rt
    if canonical == rt:
        return rt, r
    # canonical_slug from the LLM didn't match either input slug (e.g.
    # null, or malformed) — fall back to the report's retire_to.
    return rt, r


def apply_merge(vault: Path, verdict: dict, model: str, dry_run: bool, log: list[dict]) -> None:
    winner, loser = resolve_winner_loser(verdict)

    path_loser = vault / "concepts" / f"{loser}.md"
    path_winner = vault / "concepts" / f"{winner}.md"
    if not path_loser.exists() or not path_winner.exists():
        log.append({"loser": loser, "winner": winner, "status": "SKIP-missing-page"})
        print(f"  SKIP {loser} -> {winner}: missing page on disk")
        return

    full_winner, fm_winner, body_winner = read_page(vault, winner)
    full_loser, fm_loser, body_loser = read_page(vault, loser)
    fm_winner_fields = parse_frontmatter(fm_winner)
    fm_loser_fields = parse_frontmatter(fm_loser)

    if dry_run:
        print(f"  [dry-run] would merge {loser} -> {winner}")
        log.append({"loser": loser, "winner": winner, "status": "dry-run"})
        return

    prompt = MERGE_PROMPT.format(winner=winner, body_a=body_winner.strip(),
                                  loser=loser, body_b=body_loser.strip())
    merged_body = call_claude(prompt, model=model, timeout=240.0).strip()

    new_fm = union_frontmatter(fm_winner_fields, fm_loser_fields, keep_from=fm_winner_fields)
    path_winner.write_text(new_fm + "\n" + merged_body + "\n", encoding="utf-8")

    stub_fm = (
        "---\n"
        f"type: concept\n"
        f"title: \"{fm_loser_fields.get('title', loser)}\"\n"
        f"retired_to: {winner}\n"
        "---\n"
    )
    stub_body = f"\nThis page has been merged into [[concepts/{winner}]].\n"
    path_loser.write_text(stub_fm + stub_body, encoding="utf-8")

    log.append({"loser": loser, "winner": winner, "status": "merged"})
    print(f"  merged {loser} -> {winner}")


def phase_apply(args: argparse.Namespace) -> int:
    vault = Path(args.vault).expanduser()
    verdicts_path = Path(args.verdicts)
    if not verdicts_path.exists():
        print(f"ERROR: --verdicts file not found: {verdicts_path}", file=sys.stderr)
        return 1

    verdicts = load_verdicts(verdicts_path)
    merges = [v for v in verdicts if v.get("verdict") == "MERGE" and v.get("canonical_slug")]
    others = [v for v in verdicts if v.get("verdict") in ("HUB", "KEEP")]
    unresolved = [v for v in verdicts if v.get("verdict") not in ("MERGE", "HUB", "KEEP")]

    if args.limit:
        merges = merges[:args.limit]

    print("=== PLAN ===")
    print(f"vault:            {vault}")
    print(f"verdicts file:    {verdicts_path}")
    print(f"MERGE pairs:      {len(merges)} (pages to retire: {len(merges)}, pages to update: {len(merges)})")
    print(f"HUB/KEEP no-ops:  {len(others)}")
    print(f"unresolved/error: {len(unresolved)}")
    print("")
    for v in merges:
        winner, loser = resolve_winner_loser(v)
        print(f"  retire {loser!r} -> canonical {winner!r}")
    print("")

    if args.dry_run:
        print("--dry-run: no writes performed.")
        for v in merges:
            winner, loser = resolve_winner_loser(v)
            print(f"  [dry-run] would merge {loser} -> {winner}")
        return 0

    if not merges:
        print("Nothing to apply (no MERGE verdicts).")
        return 0

    backup_path = make_backup(vault)
    print(f"backup written: {backup_path}")

    log: list[dict] = []
    for i, v in enumerate(merges, 1):
        print(f"[{i}/{len(merges)}] {v['retire']} <-> {v['retire_to']}")
        try:
            apply_merge(vault, v, model=args.model, dry_run=False, log=log)
        except Exception as exc:  # noqa: BLE001
            print(f"  ERROR: {exc}")
            log.append({"loser": v["retire"], "winner": v.get("canonical_slug") or v["retire_to"],
                        "status": "error", "error": str(exc)[:500]})
        time.sleep(0.2)

    merged_count = sum(1 for r in log if r["status"] == "merged")
    print(f"\nApplied {merged_count}/{len(merges)} merges.")
    print("\nNext: fix inbound wikilinks to retired slugs by running:")
    print(f"  cd {Path(__file__).resolve().parents[1] / 'vendor'} && \\")
    print(f"    npx tsx --tsconfig src/mikai-cli/tsconfig.json src/mikai-cli/rewrite-retire-stubs.ts \\")
    print(f"      --project {vault.parent}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True, help="dedup report JSON (R5 shape, pairs.HIGH)")
    ap.add_argument("--vault", required=True, help="path to wiki/ (contains concepts/, entities/, ...)")
    ap.add_argument("--phase", required=True, choices=["judge", "apply"])
    ap.add_argument("--verdicts", required=True, help="verdicts JSON: output for judge, input for apply")
    ap.add_argument("--limit", type=int, default=0, help="cap pairs/merges processed (0 = no cap)")
    ap.add_argument("--dry-run", action="store_true", help="apply phase: print planned actions, don't write")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    args = ap.parse_args()

    if args.phase == "judge":
        return phase_judge(args)
    return phase_apply(args)


if __name__ == "__main__":
    raise SystemExit(main())
