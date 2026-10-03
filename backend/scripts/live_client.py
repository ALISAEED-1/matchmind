"""Minimal live-mode client: connect to the API and print what the agent team publishes.

uv run python scripts/live_client.py mm-0004-comeback --speed 120 --llm 0
uv run python scripts/live_client.py mm-0020-late_winner --language ur --club "Duncairn Harbour"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from urllib.parse import urlencode

import websockets


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("match")
    p.add_argument("--host", default="ws://127.0.0.1:8765")
    p.add_argument("--speed", type=float, default=60)
    p.add_argument("--audience", default="fan")
    p.add_argument("--language", default="en")
    p.add_argument("--club", default="")
    p.add_argument("--llm", default="1")
    p.add_argument("--outage", default="0")
    p.add_argument("--quiet", action="store_true", help="only print the summary")
    a = p.parse_args()

    query = urlencode(
        {"speed": a.speed, "audience": a.audience, "language": a.language, "club": a.club,
         "llm": a.llm, "outage": a.outage}
    )  # fmt: skip
    kinds: Counter[str] = Counter()
    async with websockets.connect(f"{a.host}/ws/live/{a.match}?{query}", max_size=None) as ws:
        async for raw in ws:
            msg = json.loads(raw)
            kinds[msg["type"]] += 1
            if msg["type"] == "hello":
                m = msg["match"]
                print(f"{m['home']['name']} v {m['away']['name']} | config {msg['config']}")
            elif msg["type"] == "cards" and not a.quiet:
                for c in msg["cards"]:
                    print(f"  [{c['type']:<10}] {c['title']} - {c['body'][:90]}")
            elif msg["type"] == "error":
                print("ERROR", msg["message"])
                break
            elif msg["type"] == "done":
                print("done; counters:", {k: v for k, v in msg["counters"].items() if "route" in k})
                break
    print("messages:", dict(kinds))


if __name__ == "__main__":
    asyncio.run(main())
