#!/usr/bin/env bash
# Build the frontend and bundle it into the backend Python package so that
# `gitloco` (after `uv tool install`) serves both the API and the UI from
# one process.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "==> Installing frontend dependencies"
( cd "$ROOT/frontend" && npm install --no-fund --no-audit )

echo "==> Building frontend"
( cd "$ROOT/frontend" && npm run build )

echo "==> Bundling frontend dist into backend package"
STATIC="$ROOT/backend/src/gitloco/static"
rm -rf "$STATIC"
cp -r "$ROOT/frontend/dist" "$STATIC"

echo
echo "Frontend bundled into $STATIC"
echo "Next:"
echo "  cd backend && uv tool install ."
echo "  cd /path/to/your/repo && gitloco"
