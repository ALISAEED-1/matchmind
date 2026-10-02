"""Chat client factory: one Agent Framework chat client per provider in the chain.

Both providers return Agent Framework's `OpenAIChatCompletionClient`, so agents
never know which one is behind them:

- Foundry Local: our adapter loads the model in-process and exposes the SDK's
  OpenAI-compatible web service on localhost (see `foundry_local.py`).
- Gemini: Google's OpenAI-compatible Chat Completions endpoint.
"""

from __future__ import annotations

from agent_framework.openai import OpenAIChatCompletionClient

from matchmind.config import ProviderSpec, Settings
from matchmind.llm.foundry_local import ensure_local_model

# Foundry Local's local web service does not check keys, but the OpenAI client requires one.
_LOCAL_API_KEY = "foundry-local"


def make_chat_client(spec: ProviderSpec, settings: Settings) -> OpenAIChatCompletionClient:
    if spec.kind == "foundry_local":
        endpoint = ensure_local_model(spec.model, settings.foundry_device)
        return OpenAIChatCompletionClient(
            model=endpoint.model_id,
            api_key=_LOCAL_API_KEY,
            base_url=endpoint.base_url,
        )
    return OpenAIChatCompletionClient(
        model=spec.model,
        api_key=settings.gemini_api_key,
        base_url=settings.gemini_endpoint,
    )
