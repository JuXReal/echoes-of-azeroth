#!/usr/bin/env bash
# ==============================================================================
# 🎙️ Echoes of Azeroth — Desktop One-Click Launcher
# Starts the Web Studio & Launchpad server (if not already running) and opens
# http://127.0.0.1:8765 in the default browser.
#
# Stale-server protection: if a serve.py process from an OLD version is still
# running (recognizable by the missing /api/version endpoint), it is stopped
# and replaced with the current version.
# ==============================================================================
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

URL="http://127.0.0.1:8765"

if ! curl -s "${URL}/api/version" >/dev/null 2>&1; then
    # No (or outdated) server running — stop leftovers and start the current version
    pkill -f "web/serve[.]py" 2>/dev/null || true
    sleep 0.5
    nohup "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/web/serve.py" --host 127.0.0.1 --port 8765 >/tmp/echoes-of-azeroth-web.log 2>&1 &
    sleep 1.2
fi

xdg-open "$URL" >/dev/null 2>&1 &
