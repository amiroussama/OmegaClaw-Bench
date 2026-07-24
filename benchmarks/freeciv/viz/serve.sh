#!/usr/bin/env bash
# Serve the FreeCiv benchmark visualization page.
#
# Regenerates data, builds the React Decision Observatory UI, then serves dist/ with stdlib
# http.server. Use npm run dev from this directory for Vite hot reload.
#
# Usage: bash benchmarks/freeciv/viz/serve.sh [PORT]   (default 8009)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8009}"

python3 "$HERE/build_index.py"
python3 "$HERE/dump_atoms.py"

if [ ! -d "$HERE/node_modules" ]; then
  echo "Installing visualization frontend dependencies..."
  (cd "$HERE" && npm install)
fi
(cd "$HERE" && npm run build)

echo "Serving $HERE/dist at http://localhost:$PORT/  (Ctrl-C to stop)"
exec python3 -m http.server "$PORT" --directory "$HERE/dist"
