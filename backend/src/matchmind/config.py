"""Runtime settings loaded from the repo-root `.env` file.

LLM access is an ordered *provider chain* (LLM_CHAIN): the agents try the first
provider and fall back to the next one when it is rate-limited, overloaded,
times out or returns unusable output. Each entry is `kind:model`:

- ``gemini:<model>``: Google Gemini via its OpenAI-compatible endpoint (free API key).
- ``foundry_local:<alias>``: Microsoft Foundry Local, on this machine. No account or key.

Default chain: two Gemini models then Foundry Local when GEMINI_API_KEY is set,
otherwise Foundry Local only. API keys are only read here and never logged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]

ProviderKind = Literal["foundry_local", "gemini"]
PROVIDER_KINDS: tuple[ProviderKind, ...] = ("foundry_local", "gemini")

DEFAULT_FOUNDRY_MODEL = "qwen2.5-1.5b"
DEFAULT_FOUNDRY_DEVICE = "cpu"
DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"
# flash-lite first: ~2 s per call. gemini-3.5-flash "thinks" before answering (45 s measured
# for one sentence), so it is the backup, not the default.
DEFAULT_GEMINI_CHAIN = "gemini:gemini-flash-lite-latest,gemini:gemini-3.5-flash"


class ConfigError(RuntimeError):
    """Raised when required settings are missing or invalid."""


@dataclass(frozen=True)
class ProviderSpec:
    kind: ProviderKind
    model: str

    @property
    def name(self) -> str:
        return f"{self.kind}:{self.model}"


@dataclass(frozen=True)
class Settings:
    chain: tuple[ProviderSpec, ...]
    foundry_device: str = DEFAULT_FOUNDRY_DEVICE
    gemini_endpoint: str = DEFAULT_GEMINI_ENDPOINT
    gemini_api_key: str = field(default="", repr=False)  # keep the key out of logs and tracebacks
    llm_timeout_s: float = 60.0


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def parse_chain(text: str) -> tuple[ProviderSpec, ...]:
    specs = []
    for item in filter(None, (part.strip() for part in text.split(","))):
        kind, sep, model = item.partition(":")
        if not sep or not model or kind not in PROVIDER_KINDS:
            raise ConfigError(
                f"Bad LLM_CHAIN entry {item!r}: expected kind:model with kind in {PROVIDER_KINDS}."
            )
        specs.append(ProviderSpec(kind, model))  # type: ignore[arg-type]
    if not specs:
        raise ConfigError("LLM_CHAIN is empty.")
    return tuple(specs)


def load_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")
    api_key = _env("GEMINI_API_KEY")
    local = f"foundry_local:{_env('FOUNDRY_LOCAL_MODEL', DEFAULT_FOUNDRY_MODEL)}"
    default_chain = f"{DEFAULT_GEMINI_CHAIN},{local}" if api_key else local
    chain = parse_chain(_env("LLM_CHAIN") or default_chain)

    if any(s.kind == "gemini" for s in chain) and not api_key:
        raise ConfigError(
            "LLM_CHAIN uses gemini but GEMINI_API_KEY is not set. "
            "Create a free key at https://aistudio.google.com/apikey and add it to .env."
        )
    return Settings(
        chain=chain,
        foundry_device=_env("FOUNDRY_LOCAL_DEVICE", DEFAULT_FOUNDRY_DEVICE).lower(),
        gemini_endpoint=_env("GEMINI_ENDPOINT", DEFAULT_GEMINI_ENDPOINT),
        gemini_api_key=api_key,
        llm_timeout_s=float(_env("LLM_TIMEOUT_S", "60")),
    )
