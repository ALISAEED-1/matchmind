"""Fault injection for demos and tests: a switch that makes every model "go down".

Live sessions wrap their providers in `FlakyProvider`. When the viewer flips
"simulate outage" in the debug drawer, every call fails with a simulated 503,
the cache is bypassed, and the recovery path (provider fallback -> template
fallback -> circuit breaker) runs for real, visible in the handoff log.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

from matchmind.llm.gateway import Provider, ResponseCache


@dataclass
class OutageSwitch:
    on: bool = False


class SimulatedOutage(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Error code: 503 - simulated outage (debug drawer switch)")


class FlakyProvider:
    def __init__(self, inner: Provider, switch: OutageSwitch):
        self.inner = inner
        self.switch = switch
        self.name = inner.name

    async def complete(self, agent_name, instructions, prompt, schema):
        if self.switch.on:
            raise SimulatedOutage()
        return await self.inner.complete(agent_name, instructions, prompt, schema)


class SwitchableCache(ResponseCache):
    """A cache view that misses while the outage switch is on (so failures are real)."""

    def __init__(self, inner: ResponseCache, switch: OutageSwitch):
        super().__init__(inner.root)
        self.switch = switch

    def get(self, agent_name: str, key: str, schema: type[BaseModel]):
        return None if self.switch.on else super().get(agent_name, key, schema)
