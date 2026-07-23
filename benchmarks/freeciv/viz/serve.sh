#!/usr/bin/env bash
# Serve the FreeCiv PLN benchmark dashboard (React + Vite).
#
# Data comes from the Python generators (no live game needed): build_index.py writes the run
# catalog + per-run detail + batch aggregates into public/data/, and dump_atoms.py writes the
# offline atom reconstruction. Two modes:
#   dev  (default) — vite dev server with HMR at http://localhost:8009/
#   prod           — vite build, then serve the static dist/ with python http.server
#
# Usage: bash benchmarks/freeciv/viz/serve.sh [dev|prod] [PORT]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-dev}"
PORT="${2:-8009}"
cd "$HERE"

# 1. deps
if [ ! -d node_modules ]; then
  echo "[viz] installing npm deps (first run)…"
  npm install
fi

# 2. regenerate data into public/data (served at /data/*)
echo "[viz] generating data…"
python3 build_index.py
python3 dump_atoms.py

# 3. serve
if [ "$MODE" = "prod" ]; then
  echo "[viz] building…"
  npm run build
  cp -r public/data dist/ 2>/dev/null || true   # ensure freshest data is in the served tree
  echo "[viz] serving dist/ at http://localhost:$PORT/  (Ctrl-C to stop)"
  exec python3 -m http.server "$PORT" --bind 0.0.0.0 --directory dist
else
  # --host binds all interfaces so the page is reachable over LAN/Tailscale, not just localhost.
  echo "[viz] dev server at http://localhost:$PORT/  (also on this host's LAN IP; Ctrl-C to stop)"
  exec npm run dev -- --host --port "$PORT"
fi
