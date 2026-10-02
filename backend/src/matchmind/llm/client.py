"""Chat client for GitHub Models, used by every LLM agent.

GitHub Models exposes an OpenAI-compatible *Chat Completions* endpoint.
Agent Framework's `OpenAIChatClient` targets the newer Responses API, so we
use `OpenAIChatCompletionClient` and point its `base_url` at GitHub Models.
No custom adapter is needed.
"""

from __future__ import annotations

from agent_framework.openai import OpenAIChatCompletionClient

from matchmind.config import Settings, load_settings


def make_chat_client(settings: Settings | None = None) -> OpenAIChatCompletionClient:
    settings = settings or load_settings()
    return OpenAIChatCompletionClient(
        model=settings.model,
        api_key=settings.github_token,
        base_url=settings.endpoint,
    )
