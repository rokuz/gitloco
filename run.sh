#!/usr/bin/env bash
# Start the GitLoco backend and frontend together for development.
#
# Usage:
#   ./dev.sh              # serve the current directory (the GitLoco repo itself)
#   ./dev.sh /path/to/repo
#
# Backend listens on 127.0.0.1:7777; Vite (with /api proxy) on 0.0.0.0:5173.
# Ctrl-C tears both down.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
REPO="${1:-$ROOT}"
BACKEND_HOST="127.0.0.1"
BACKEND_PORT="7777"
FRONTEND_URL="http://localhost:5173"

if [ ! -d "$REPO/.git" ] && ! git -C "$REPO" rev-parse --git-dir >/dev/null 2>&1; then
  echo "error: $REPO is not a git repository" >&2
  exit 2
fi

cleanup() {
  trap - INT TERM EXIT
  echo
  echo "Stopping GitLoco…"
  kill 0 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "GitLoco dev"
echo "  repo:     $REPO"
echo "  backend:  http://$BACKEND_HOST:$BACKEND_PORT"
echo "  frontend: $FRONTEND_URL"
echo

( cd "$ROOT/backend" && uv run gitloco "$REPO" \
    --host "$BACKEND_HOST" --port "$BACKEND_PORT" --no-browser ) &
( cd "$ROOT/frontend" && npm run dev -- --host ) &

# Open the UI once Vite is up. Best-effort — Vite usually binds in <1s.
( sleep 1.8 && command -v open >/dev/null && open "$FRONTEND_URL" ) &

wait
