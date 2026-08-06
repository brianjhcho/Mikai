# Graphiti freeze — rollback

The 2026-08-05 pivot made the Karpathy wiki (`~/.mikai/wiki/`) the primary
L3 substrate. Neo4j data was preserved untouched; ingestion just stopped
flowing in. To re-enable Graphiti:

1. In `~/.mikai/launchd.env`, set `MIKAI_L3_BACKEND=graphiti` (or delete
   the line — graphiti is the default).
2. Re-bootstrap the frozen writer plists:

   ```sh
   LD="$HOME/Library/Application Support/mikai/launchd"
   launchctl bootstrap "gui/$(id -u)" "$LD/com.mikai.ingestion.plist"
   launchctl bootstrap "gui/$(id -u)" "$LD/com.mikai.claude-threads.plist"
   launchctl bootstrap "gui/$(id -u)" "$LD/com.mikai.dream.plist"
   ```

3. Verify: `launchctl list | grep com.mikai.` shows all three; watch
   `~/.mikai/logs/` for successful Neo4j writes.
