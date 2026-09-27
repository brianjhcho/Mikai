#!/usr/bin/env bash
# session-start-branch-context.sh
#
# Fired at session start. Injects a <system-reminder> naming the current
# branch, its manifest, and any stale docs router entries. Cheap: a few
# git/grep calls, no LLM.
#
# Emits JSON on stdout per Claude Code hook schema:
#   { "hookSpecificOutput": { "hookEventName": "SessionStart",
#                              "additionalContext": "<text>" } }
set -euo pipefail

# Resolve worktree root (the dir Claude Code was launched from)
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT" || exit 0  # if git fails, fail-open (empty context)

BRANCH="$(git branch --show-current 2>/dev/null || echo unknown)"
MANIFEST=""
CONSTITUTION_LINE=""
UNROUTED=""

# Escape branch name for filesystem: `feat/pure-file-brain` → `feat-pure-file-brain`
BRANCH_FS="$(echo "$BRANCH" | tr '/' '-')"
CANDIDATE="docs/branches/${BRANCH_FS}.md"
if [ -f "$CANDIDATE" ]; then
  MANIFEST="$CANDIDATE"
  CONSTITUTION_LINE="$(grep -m1 '^\*\*Constitution:\*\*' "$CANDIDATE" 2>/dev/null || true)"
fi

# Router-freshness: docs/*.md files (excluding session-dated) not referenced in CLAUDE.md
if [ -f CLAUDE.md ]; then
  # Collect all docs/*.md paths, excluding date-stamped session artifacts + docs/branches + docs/research
  DOCS=$(ls docs/*.md 2>/dev/null \
    | grep -Ev 'docs/(DAY_LOG|BACKFILL|INGESTION_NOTES|LINT_PASS|GRAPHITI_FREEZE)' \
    || true)
  # For each doc, check if referenced anywhere in CLAUDE.md
  MISSING=""
  for doc in $DOCS; do
    if ! grep -qF "$(basename "$doc")" CLAUDE.md; then
      MISSING="${MISSING}${doc}, "
    fi
  done
  if [ -n "$MISSING" ]; then
    UNROUTED="${MISSING%, }"
  fi
fi

# Compose the additional-context block
CONTEXT_BODY=""
CONTEXT_BODY+="Session on branch \`${BRANCH}\`."
if [ -n "$MANIFEST" ]; then
  CONTEXT_BODY+="\n\nBranch manifest: \`${MANIFEST}\`. Read before making architectural decisions."
  if [ -n "$CONSTITUTION_LINE" ]; then
    CONTEXT_BODY+="\n${CONSTITUTION_LINE}"
  fi
else
  CONTEXT_BODY+="\n\nNo branch manifest at \`${CANDIDATE}\`. Consider creating one if this branch has a constitution."
fi
if [ -n "$UNROUTED" ]; then
  CONTEXT_BODY+="\n\n**Docs router freshness alert:** the following docs exist but are NOT referenced in CLAUDE.md's router table — discoverability decayed:\n${UNROUTED}\nAdd them to CLAUDE.md's docs router (\`## Where to look for what\` section) or move them under \`docs/research/\` if archived."
fi

# Emit JSON per schema
python3 -c "
import json, sys
context = '''${CONTEXT_BODY}'''.replace(chr(92) + 'n', chr(10))
print(json.dumps({
  'hookSpecificOutput': {
    'hookEventName': 'SessionStart',
    'additionalContext': context
  }
}))
"
