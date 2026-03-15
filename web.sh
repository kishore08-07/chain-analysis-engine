#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# web.sh — Web visualizer
#
# Starts the web visualizer server.
#
# Behavior:
#   - Reads PORT env var (default: 3000)
#   - Prints the URL (e.g., http://127.0.0.1:3000) to stdout
#   - Keeps running until terminated (CTRL+C / SIGTERM)
#   - Must serve GET /api/health -> 200 { "ok": true }
###############################################################################

export PORT="${PORT:-3000}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Start the Python web server
exec python3 "$SCRIPT_DIR/src/web/server.py"

