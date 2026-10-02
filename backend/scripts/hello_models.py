"""Phase 0 smoke test: one Agent Framework agent answering through the configured LLM provider.

Run from backend/:  uv run python scripts/hello_models.py
Override the provider for one run:  LLM_PROVIDER=gemini uv run python scripts/hello_models.py
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

    print(f"[config] provider={settings.provider} model={settings.model}")

    started = time.perf_counter()
    try:
        agent = Agent(
            make_chat_client(settings),
            instructions=(
                "You are a football commentator for a fictional league. "
                "Reply with one short, energetic sentence."
            ),
            name="hello_narrator",
        )
        print(f"[ready] client up in {time.perf_counter() - started:.1f}s")

        started = time.perf_counter()
        response = await agent.run("Rivermouth Rovers just scored a late winner. Call it.")
    except Exception as exc:  # surface type + message only; never request headers
        print(f"[error] {type(exc).__name__}: {exc}")
        return 2

    print(f"[ok] {time.perf_counter() - started:.1f}s -> {response.text}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
