#!/usr/bin/env bash
# Start the MatchMind server (web app + live API + Ask MatchMind) on port 8000.
set -euo pipefail
cd "$(dirname "$0")/../backend"
export PATH="$HOME/.local/bin:$PATH"
nohup uv run uvicorn matchmind.api.app:app --host 0.0.0.0 --port 8000 > /tmp/matchmind.log 2>&1 &
echo "MatchMind is starting on port 8000 (log: /tmp/matchmind.log)"
