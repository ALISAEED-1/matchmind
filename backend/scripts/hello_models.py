"""Smoke test: one Agent Framework agent answering through each provider in the chain.

Run from backend/:  uv run python scripts/hello_models.py
One provider only:  LLM_CHAIN=foundry_local:qwen2.5-1.5b uv run python scripts/hello_models.py
"""

from __future__ import annotations

import asyncio
import sys
import time

from agent_framework import Agent

from matchmind.config import ConfigError, load_settings
from matchmind.llm import make_chat_client


async def main() -> int:
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"[setup] {exc}")
        return 1

    failures = 0
    for spec in settings.chain:
        started = time.perf_counter()
        try:
            agent = Agent(
                make_chat_client(spec, settings),
                instructions=(
                    "You are a football commentator for a fictional league. "
                    "Reply with one short, energetic sentence."
                ),
                name="hello_narrator",
            )
            response = await agent.run("Rivermouth Rovers just scored a late winner. Call it.")
        except Exception as exc:  # surface type + message only; never request headers
            failures += 1
            print(f"[error] {spec.name}: {type(exc).__name__}: {str(exc)[:160]}")
            continue
        print(f"[ok] {spec.name} {time.perf_counter() - started:.1f}s -> {response.text}")
    return 2 if failures == len(settings.chain) else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
