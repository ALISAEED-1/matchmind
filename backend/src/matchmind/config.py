"""Runtime settings loaded from the repo-root `.env` file.

The GitHub token is only ever read here and handed to the HTTP client.
It is never logged or included in error messages.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_ENDPOINT = "https://models.github.ai/inference"
DEFAULT_MODEL = "openai/gpt-4.1-mini"


class MissingTokenError(RuntimeError):
    """Raised when GITHUB_TOKEN is not configured."""


@dataclass(frozen=True)
class Settings:
    github_token: str
    endpoint: str
    model: str

    def __repr__(self) -> str:  # keep the token out of logs and tracebacks
        return f"Settings(endpoint={self.endpoint!r}, model={self.model!r}, github_token=***)"


def load_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise MissingTokenError(
            "GITHUB_TOKEN is not set. Copy .env.example to .env and add a token "
            "with the 'Models: read' permission."
        )
    return Settings(
        github_token=token,
        endpoint=os.getenv("GITHUB_MODELS_ENDPOINT", DEFAULT_ENDPOINT).strip(),
        model=os.getenv("GITHUB_MODELS_MODEL", DEFAULT_MODEL).strip(),
    )
