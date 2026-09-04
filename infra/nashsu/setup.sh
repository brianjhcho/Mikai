#!/bin/bash
# infra/nashsu/setup.sh — bootstrap the MIKAI ↔ nashsu integration.
#
# One-time (or after an upstream `git pull` in the vendor dir):
#   1. Clone nashsu into $MIKAI_NASHSU_PATH if missing
#   2. Run `npm install` inside the vendor dir
#   3. Apply MIKAI deviation patches
#   4. Copy the Node-native LLM transport shim into place
#
# Idempotent: safe to re-run. Won't overwrite an existing clone; won't
# reapply an already-applied patch (uses `patch --dry-run` probe first).

set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────

# Resolve the MIKAI glue dir (this script's location); default vendor
# is a sibling `vendor/` under the same dir.
GLUE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIKAI_NASHSU_PATH="${MIKAI_NASHSU_PATH:-$GLUE_DIR/vendor}"
UPSTREAM_URL="https://github.com/nashsu/llm_wiki.git"
UPSTREAM_TAG="v0.6.9"  # pinned version; update deliberately

echo "[nashsu-setup] MIKAI_NASHSU_PATH = $MIKAI_NASHSU_PATH"
echo "[nashsu-setup] GLUE_DIR          = $GLUE_DIR"

# ── Phase 1: clone if missing ──────────────────────────────────────────

if [ ! -f "$MIKAI_NASHSU_PATH/package.json" ]; then
    echo "[nashsu-setup] cloning $UPSTREAM_URL @ $UPSTREAM_TAG …"
    mkdir -p "$(dirname "$MIKAI_NASHSU_PATH")"
    git clone --depth 1 --branch "$UPSTREAM_TAG" "$UPSTREAM_URL" "$MIKAI_NASHSU_PATH"
    # Discard upstream .git — vendored under MIKAI's git, not tracking upstream history
    rm -rf "$MIKAI_NASHSU_PATH/.git"
    echo "[nashsu-setup]   pinned at $UPSTREAM_TAG (upstream .git discarded)"
else
    VENDOR_VERSION=$(node -p "require('$MIKAI_NASHSU_PATH/package.json').version" 2>/dev/null || echo "?")
    echo "[nashsu-setup] vendor exists at version $VENDOR_VERSION — skipping clone"
fi

# ── Phase 2: npm install ───────────────────────────────────────────────

if [ ! -d "$MIKAI_NASHSU_PATH/node_modules" ] || [ ! -f "$MIKAI_NASHSU_PATH/node_modules/.package-lock.json" ]; then
    echo "[nashsu-setup] running npm install …"
    (cd "$MIKAI_NASHSU_PATH" && npm install)
else
    echo "[nashsu-setup] node_modules present — skipping npm install"
fi

# ── Phase 3: apply deviation patches ───────────────────────────────────

apply_patch() {
    local patch_file="$1"
    local target_file="$2"
    local marker="$3"  # unique string that appears ONLY after patch is applied
    local patch_name
    patch_name=$(basename "$patch_file")

    # Probe by marker (BSD patch's -R detection is interactive/unreliable).
    if grep -q -F "$marker" "$MIKAI_NASHSU_PATH/$target_file" 2>/dev/null; then
        echo "[nashsu-setup] patch already applied — skipping: $patch_name"
        return 0
    fi

    # Forward apply, non-interactive (--forward rejects reverse-detection)
    if patch --forward -p1 -d "$MIKAI_NASHSU_PATH" < "$patch_file"; then
        echo "[nashsu-setup] applied: $patch_name"
    else
        echo "[nashsu-setup] ERROR: patch failed: $patch_name" >&2
        echo "[nashsu-setup]   (upstream file may have changed since patch was authored)" >&2
        return 1
    fi
}

apply_patch "$GLUE_DIR/patches/ingest-queue-worker-clamp.patch" \
    "src/lib/ingest-queue.ts" \
    "DEVIATION from upstream nashsu (MIKAI-specific): bump max workers"

# ── Phase 4: install Node-native LLM transport shim ────────────────────

TRANSPORT_SRC="$GLUE_DIR/transport/claude-cli-transport.ts"
TRANSPORT_DST="$MIKAI_NASHSU_PATH/src/lib/claude-cli-transport.ts"

if [ -f "$TRANSPORT_DST" ]; then
    # Compare — only overwrite if different (so we don't churn mtimes)
    if ! cmp -s "$TRANSPORT_SRC" "$TRANSPORT_DST"; then
        echo "[nashsu-setup] backing up upstream transport → claude-cli-transport.ts.upstream-backup"
        cp "$TRANSPORT_DST" "$TRANSPORT_DST.upstream-backup"
        echo "[nashsu-setup] installing MIKAI Node-native transport shim"
        cp "$TRANSPORT_SRC" "$TRANSPORT_DST"
    else
        echo "[nashsu-setup] transport shim already installed — skipping"
    fi
else
    echo "[nashsu-setup] ERROR: expected transport target not found: $TRANSPORT_DST" >&2
    exit 1
fi

# ── Phase 5: install MIKAI CLI wrapper into vendor tree ────────────────
# CLI wrapper lives inside vendor so it can use nashsu's tsconfig
# (@/ alias resolution) + inherit tsx from vendor's node_modules.
# Source of truth is infra/nashsu/cli/ingest.ts; copied into vendor.

CLI_DST_DIR="$MIKAI_NASHSU_PATH/src/mikai-cli"
SHIM_DST_DIR="$CLI_DST_DIR/shims"
mkdir -p "$CLI_DST_DIR" "$SHIM_DST_DIR"

install_copy() {
    local src="$1"
    local dst="$2"
    local label="$3"
    if [ ! -f "$src" ]; then
        return
    fi
    if [ -f "$dst" ] && cmp -s "$src" "$dst"; then
        echo "[nashsu-setup] $label already installed — skipping"
    else
        echo "[nashsu-setup] installing → $label"
        cp "$src" "$dst"
    fi
}

# CLI wrappers
for cli_name in ingest init-project; do
    install_copy \
        "$GLUE_DIR/cli/${cli_name}.ts" \
        "$CLI_DST_DIR/${cli_name}.ts" \
        "src/mikai-cli/${cli_name}.ts"
done

# fs + tauri shims (path-alias targets for tsconfig-node.json)
for shim_name in fs-shim tauri-core; do
    install_copy \
        "$GLUE_DIR/shims/${shim_name}.ts" \
        "$SHIM_DST_DIR/${shim_name}.ts" \
        "src/mikai-cli/shims/${shim_name}.ts"
done

# tsconfig with path overrides
install_copy \
    "$GLUE_DIR/tsconfig-node.json" \
    "$CLI_DST_DIR/tsconfig.json" \
    "src/mikai-cli/tsconfig.json"

# ── Phase 6: ensure tsx runtime is available ───────────────────────────
# tsx handles TS type-stripping + tsconfig @/ path resolution. Native
# Node --experimental-strip-types doesn't do path resolution.

if [ ! -f "$MIKAI_NASHSU_PATH/node_modules/.bin/tsx" ]; then
    echo "[nashsu-setup] installing tsx …"
    (cd "$MIKAI_NASHSU_PATH" && npm install --save-dev tsx)
else
    echo "[nashsu-setup] tsx already installed — skipping"
fi

# ── Done ───────────────────────────────────────────────────────────────

echo ""
echo "[nashsu-setup] complete."
echo "  vendor path:  $MIKAI_NASHSU_PATH"
echo "  patches:      1 applied (ingest-queue-worker-clamp)"
echo "  transport:    Node-native shim installed"
echo "  CLI wrapper:  src/mikai-cli/ingest.ts"
echo "  tsx runtime:  present"
echo ""
echo "  invoke:"
echo "    cd \"\$MIKAI_NASHSU_PATH\" && \\"
echo "      npx tsx --tsconfig src/mikai-cli/tsconfig.json src/mikai-cli/ingest.ts --project <PATH> --workers <N>"
echo "      (the --tsconfig flag is REQUIRED — without it, tsx uses vendor's root tsconfig and skips the fs-shim / tauri-core path aliases, causing every write to fail with 'window is not defined')"
