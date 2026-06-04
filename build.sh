#!/usr/bin/env bash
# Build the frontend, bundle it into the backend Python package, and install the
# `gitloco` CLI globally so it serves both the API and the UI from one process.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' is not installed or not on PATH." >&2
  echo "Install it from https://docs.astral.sh/uv/ (e.g. 'curl -LsSf https://astral.sh/uv/install.sh | sh' or 'brew install uv'), then re-run ./build.sh." >&2
  exit 1
fi

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

echo "==> Installing the gitloco CLI (uv tool install)"
( cd "$ROOT/backend" && uv tool install . --force )

echo
echo "Done. 'gitloco' is installed and on your PATH."
echo "Use it from any repo:"
echo "  cd /path/to/your/repo && gitloco"
