"""A live session: replay a match in sped-up real time and run the agent team on it.

One session per WebSocket connection. Server -> client messages (JSON):

    {"type": "hello",    "match": {...meta...}, "config": {...}}
    {"type": "events",   "events": [...]}                 one replay window
    {"type": "stats",    "point": {...}}                  scoreboard / momentum point
    {"type": "cards",    "cards": [...]}                  overlay cards published this window
    {"type": "handoffs", "handoffs": [...]}               new handoff-log entries
    {"type": "status",   "paused": .., "speed": .., "outage": ..}
    {"type": "done",     "recap": {...} | null, "counters": {...}}
    {"type": "error",    "message": "..."}

Client -> server controls:

    {"action": "pause"} | {"action": "resume"}
    {"action": "speed", "value": 20}
    {"action": "outage", "value": true}
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

from matchmind.agents.facts import display_minute
from matchmind.agents.llm_agents import ViewerProfile
from matchmind.agents.orchestrator import MatchOrchestrator, PipelineConfig
from matchmind.agents.stats_source import LocalStatsSource, MCPStatsSource
from matchmind.llm.faults import FlakyProvider, OutageSwitch, SwitchableCache
from matchmind.llm.gateway import LLMGateway
from matchmind.models import Match
from matchmind.replay import WINDOW_MS, batches
from matchmind.state import MatchState
from matchmind.stats import MatchSnapshot

Send = Callable[[dict[str, Any]], Awaitable[None]]

MIN_SPEED, MAX_SPEED = 1.0, 6000.0


def stats_point(snap: MatchSnapshot) -> dict[str, Any]:
    chaos = snap.control_chaos_10min
    return {
        "t_min": snap.timestamp_ms // 60_000,
        "minute": display_minute(snap.period, snap.minute),
        "period": snap.period,
        "score_home": snap.score.home,
        "score_away": snap.score.away,
        "momentum": snap.momentum,
        "possession_home": snap.home.possession,
        "pressure_home": snap.home.pressure_index_10min,
        "pressure_away": snap.away.pressure_index_10min,
        "chaos_index": chaos.index,
        "chaos_label": chaos.label,
        "xg_home": snap.home.shooting.xg,
        "xg_away": snap.away.shooting.xg,
    }


@dataclass
class SessionOptions:
    speed: float = 10.0
    profile: ViewerProfile = field(default_factory=ViewerProfile)
    llm_enabled: bool = True
    use_mcp: bool = True
    outage: bool = False  # start with the simulated outage on (demo)


class LiveSession:
    def __init__(
        self,
        match: Match,
        base_gateway: LLMGateway | None,
        options: SessionOptions,
        send: Send,
    ):
        self.match = match
        self.options = options
        self.send = send
        self.speed = min(MAX_SPEED, max(MIN_SPEED, options.speed))
        self.switch = OutageSwitch(on=options.outage)
        self.running = asyncio.Event()
        self.running.set()
        self.state = MatchState(meta=match.meta)
        self._sent_handoffs = 0

        profile = options.profile
        self.config = PipelineConfig(
            languages=(profile.language,),
            audiences=(profile.audience,),
            profile=profile,
            commentary_language=profile.language,
            llm_enabled=options.llm_enabled and base_gateway is not None,
        )
        self.gateway = None
        if base_gateway is not None:
            self.gateway = LLMGateway(
                [FlakyProvider(p, self.switch) for p in base_gateway.providers],
                SwitchableCache(base_gateway.cache, self.switch) if base_gateway.cache else None,
                min_interval_s=base_gateway.min_interval_s,
                backoff_s=base_gateway.backoff_s,
                sleep=base_gateway._sleep,
            )

    # ----------------------------------------------------------- controls

    async def control(self, msg: dict[str, Any]) -> None:
        action = msg.get("action")
        if action == "pause":
            self.running.clear()
        elif action == "resume":
            self.running.set()
        elif action == "speed":
            self.speed = min(MAX_SPEED, max(MIN_SPEED, float(msg.get("value", self.speed))))
        elif action == "outage":
            self.switch.on = bool(msg.get("value"))
            self.state.log(
                "viewer",
                "orchestrator",
                detail=f"simulated outage {'ON' if self.switch.on else 'OFF'}",
            )
        else:
            await self.send({"type": "error", "message": f"unknown action {action!r}"})
            return
        await self.send(self.status())

    def status(self) -> dict[str, Any]:
        return {
            "type": "status",
            "paused": not self.running.is_set(),
            "speed": self.speed,
            "outage": self.switch.on,
        }

    # ---------------------------------------------------------------- run

    async def _flush_handoffs(self) -> None:
        new = self.state.handoffs[self._sent_handoffs :]
        self._sent_handoffs = len(self.state.handoffs)
        if new:
            await self.send(
                {
                    "type": "handoffs",
                    "handoffs": [h.model_dump(mode="json", exclude_none=True) for h in new],
                }
            )

    async def run(self) -> None:
        meta = self.match.meta
        await self.send(
            {
                "type": "hello",
                "match": meta.model_dump(mode="json"),
                "config": {
                    "speed": self.speed,
                    "profile": self.options.profile.model_dump(mode="json"),
                    "llm_enabled": self.config.llm_enabled,
                    "stats_source": "mcp" if self.options.use_mcp else "local",
                },
            }
        )
        async with AsyncExitStack() as stack:
            if self.options.use_mcp:
                source = await stack.enter_async_context(MCPStatsSource(meta.match_id))
            else:
                source = LocalStatsSource(meta, self.state.events)
            orchestrator = MatchOrchestrator(
                self.state, self.gateway or _NullGateway(), source, self.config
            )

            for window in batches(self.match.events):
                await self.running.wait()
                started = time.perf_counter()
                await self.send(
                    {
                        "type": "events",
                        "events": [
                            e.model_dump(mode="json", exclude_defaults=True) for e in window
                        ],
                    }
                )
                cards = await orchestrator.process(window)
                if self.state.snapshot is not None:
                    await self.send({"type": "stats", "point": stats_point(self.state.snapshot)})
                if cards:
                    await self.send(
                        {
                            "type": "cards",
                            "cards": [c.model_dump(mode="json", exclude_none=True) for c in cards],
                        }
                    )
                await self._flush_handoffs()
                # Keep the replay at the requested speed; slow LLM work simply delays it.
                budget = WINDOW_MS / 1000 / self.speed
                await asyncio.sleep(max(0.0, budget - (time.perf_counter() - started)))

        recap = self.state.recap.model_dump() if self.state.recap else None
        await self.send({"type": "done", "recap": recap, "counters": dict(self.state.counters)})


class _NullGateway(LLMGateway):
    """Placeholder when no LLM is configured (the producer routes everything to templates)."""

    def __init__(self) -> None:
        self.providers = []
        self.cache = None
        self.min_interval_s = {}
