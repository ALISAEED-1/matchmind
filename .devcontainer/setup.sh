#!/usr/bin/env bash
# One-time Codespace setup: Python deps + the prebuilt web app (no Flutter needed).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Installing uv and backend dependencies"
pip install --quiet --user uv
export PATH="$HOME/.local/bin:$PATH"
(cd backend && uv sync)

echo "==> Downloading the prebuilt web app"
repo="$(git config --get remote.origin.url | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')"
repo="${repo:-ALISAEED-1/matchmind}"
mkdir -p frontend/build/web
if curl -fsSL "https://github.com/${repo}/releases/download/web-latest/web.zip" -o /tmp/web.zip; then
  unzip -o -q /tmp/web.zip -d frontend/build/web
  echo "    web app ready"
else
  echo "    no prebuilt web app found; use https://alisaeed-1.github.io/matchmind/ instead"
fi
