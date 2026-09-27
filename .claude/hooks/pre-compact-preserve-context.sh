#!/usr/bin/env bash
# pre-compact-preserve-context.sh
#
# Fired just before context compaction. Injects a short reminder into the
# compact summary so the constitution reference survives context erasure.
# The most drift-prone moment in long sessions.
#
# Emits JSON on stdout per Claude Code hook schema.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT" || exit 0

BRANCH="$(git branch --show-current 2>/dev/null || echo unknown)"
BRANCH_FS="$(echo "$BRANCH" | tr '/' '-')"
MANIFEST="docs/branches/${BRANCH_FS}.md"

CONTEXT_BODY="Post-compact reminder. Branch: \`${BRANCH}\`."
if [ -f "$MANIFEST" ]; then
  CONTEXT_BODY+=" Manifest: \`${MANIFEST}\`. Re-read it before architectural decisions on this branch — the constitution reference and do-not list live there. The docs router in CLAUDE.md is also load-bearing."
else
  CONTEXT_BODY+=" No branch manifest exists; consult docs/VISION.md §0 + docs/STATUS.md as the fallback constitution."
fi

python3 -c "
import json
context = '''${CONTEXT_BODY}'''
print(json.dumps({
  'hookSpecificOutput': {
    'hookEventName': 'PreCompact',
    'additionalContext': context
  }
}))
"
