#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# setup.sh — Install project dependencies
#
# Add your install commands below (e.g., npm install, pip install, cargo build).
# This script is run once before grading to set up the environment.
###############################################################################

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Decompress block fixtures if not already present
for gz in fixtures/*.dat.gz; do
  dat="${gz%.gz}"
  if [[ ! -f "$dat" ]]; then
    echo "Decompressing $(basename "$gz")..."
    gunzip -k "$gz"
  fi
done

# Build React web visualizer
if command -v node &>/dev/null; then
  echo "Building web visualizer..."
  cd "$SCRIPT_DIR/src/web/frontend"
  npm install --no-audit --no-fund 2>&1
  npx vite build 2>&1
  cd "$SCRIPT_DIR"
  echo "Web visualizer built successfully"
else
  echo "Warning: Node.js not found, skipping web UI build"
fi

echo "Setup complete"

