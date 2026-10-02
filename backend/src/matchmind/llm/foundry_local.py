"""Thin adapter: Microsoft Foundry Local SDK v2 -> OpenAI-compatible URL.

Agent Framework's own Foundry Local connector (agent-framework-foundry-local)
pins foundry-local-sdk 0.5.x, which drives the old `foundry service` CLI that no
longer exists in Foundry Local 0.10+. Instead we use SDK v2 directly:

1. initialise the SDK in-process (reusing the CLI's model cache),
2. pick the variant for the requested device, download if needed, load it,
3. start the SDK's built-in OpenAI-compatible web service,

and hand the URL to Agent Framework's standard `OpenAIChatCompletionClient`.
"""

from __future__ import annotations

import atexit
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".foundry" / "cache" / "models"


@dataclass(frozen=True)
class LocalEndpoint:
    base_url: str
    model_id: str


_lock = threading.Lock()
_endpoints: dict[tuple[str, str], LocalEndpoint] = {}


def ensure_local_model(alias: str, device: str = "cpu") -> LocalEndpoint:
    """Load `alias` on `device` and return its OpenAI-compatible endpoint.

    Idempotent and process-wide: the first call loads the model (can take a
    minute on CPU), later calls return the same endpoint.
    """
    key = (alias, device.upper())
    with _lock:
        if key in _endpoints:
            return _endpoints[key]

        from foundry_local_sdk import Configuration, FoundryLocalManager

        if FoundryLocalManager.instance is None:
            FoundryLocalManager.initialize(
                Configuration(app_name="MatchMind", model_cache_dir=str(DEFAULT_CACHE_DIR))
            )
        manager = FoundryLocalManager.instance

        model = manager.catalog.get_model(alias)
        if model is None:
            raise RuntimeError(f"Foundry Local has no model with alias {alias!r}.")

        variant = next(
            (v for v in model.variants if _device_of(v) == key[1]),
            None,
        )
        if variant is None:
            available = sorted({_device_of(v) for v in model.variants})
            raise RuntimeError(f"{alias!r} has no {key[1]} variant (available: {available}).")
        model.select_variant(variant)

        if not model.is_cached:
            log.info("Downloading %s ...", model.id)
            model.download()
        if not model.is_loaded:
            log.info("Loading %s on %s ...", model.id, key[1])
            model.load()

        if not manager.urls:
            manager.start_web_service()
            atexit.register(_shutdown)

        endpoint = LocalEndpoint(base_url=f"{manager.urls[0]}/v1", model_id=model.id)
        _endpoints[key] = endpoint
        return endpoint


def _device_of(variant) -> str:
    runtime = variant.info.runtime
    return str(runtime.device_type).upper() if runtime and runtime.device_type else ""


def _shutdown() -> None:
    from foundry_local_sdk import FoundryLocalManager

    manager = FoundryLocalManager.instance
    if manager is not None and manager.urls:
        manager.stop_web_service()
