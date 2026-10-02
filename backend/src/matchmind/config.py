"""Runtime settings loaded from the repo-root `.env` file.

Two LLM providers are supported, selected with LLM_PROVIDER:

- ``foundry_local`` (default): Microsoft Foundry Local, models run on this machine.
  No account, no key, no rate limits.
- ``gemini``: Google Gemini through its OpenAI-compatible endpoint (free API key).

API keys are only read here and handed to the HTTP client. They are never
logged or included in error messages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]

Provider = Literal["foundry_local", "gemini"]
PROVIDERS: tuple[Provider, ...] = ("foundry_local", "gemini")

DEFAULT_FOUNDRY_MODEL = "qwen2.5-1.5b"
DEFAULT_FOUNDRY_DEVICE = "cpu"
DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"


class ConfigError(RuntimeError):
    """Raised when required settings are missing or invalid."""


@dataclass(frozen=True)
class Settings:
    provider: Provider
    model: str
    foundry_device: str = DEFAULT_FOUNDRY_DEVICE
    gemini_endpoint: str = DEFAULT_GEMINI_ENDPOINT
    gemini_api_key: str = field(default="", repr=False)  # keep the key out of logs and tracebacks


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")

    provider = _env("LLM_PROVIDER", "foundry_local").lower()
    if provider not in PROVIDERS:
        raise ConfigError(f"LLM_PROVIDER must be one of {PROVIDERS}, got {provider!r}.")

    if provider == "foundry_local":
        return Settings(
            provider="foundry_local",
            model=_env("FOUNDRY_LOCAL_MODEL", DEFAULT_FOUNDRY_MODEL),
            foundry_device=_env("FOUNDRY_LOCAL_DEVICE", DEFAULT_FOUNDRY_DEVICE).lower(),
        )

    api_key = _env("GEMINI_API_KEY")
    if not api_key:
        raise ConfigError(
            "LLM_PROVIDER=gemini but GEMINI_API_KEY is not set. "
            "Create a free key at https://aistudio.google.com/apikey and add it to .env."
        )
    return Settings(
        provider="gemini",
        model=_env("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
        gemini_endpoint=_env("GEMINI_ENDPOINT", DEFAULT_GEMINI_ENDPOINT),
        gemini_api_key=api_key,
    )
