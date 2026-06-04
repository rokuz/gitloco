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

# uv caches the built wheel by version — without a clean, a reinstall after a
# rebuild can keep serving the old UI even though the source has new files.
echo "==> Clearing uv build cache for gitloco"
uv cache clean gitloco >/dev/null 2>&1 || true

echo
echo "Frontend bundled into $STATIC"
echo "Next:"
echo "  cd backend && uv tool install ."
echo "  cd /path/to/your/repo && gitloco"
