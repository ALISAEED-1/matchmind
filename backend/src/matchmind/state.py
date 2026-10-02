"""MatchState: the single shared state every agent reads and writes.

The orchestrator owns one MatchState per match. Agents never talk to each
other directly: they read what they need from here and write their results
back, and every hand-off between agents is recorded in `handoffs` so the
debug drawer can show who did what, how long it took, and what went wrong.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from matchmind.cards import OverlayCard
from matchmind.models import Event, MatchMeta
from matchmind.stats import MatchSnapshot, Moment


class HandoffStatus(StrEnum):
    OK = "ok"
    RETRY = "retry"  # output rejected (bad JSON, failed verification); trying again
    PROVIDER_FALLBACK = "provider_fallback"  # model unavailable; trying the next one
    FALLBACK = "fallback"  # all models failed; template used instead
    SKIPPED = "skipped"  # routing decided this step is not needed
    CACHED = "cached"  # answer served from the response cache


class Handoff(BaseModel):
    seq: int
    wall_ms: int  # milliseconds since the run started
    match_ms: int  # match clock (timestamp_ms) the work relates to
    source: str
    target: str
    moment_id: str | None = None
    status: HandoffStatus = HandoffStatus.OK
    detail: str = ""
    provider: str | None = None
    latency_ms: int | None = None


@dataclass
class MatchState:
    meta: MatchMeta
    events: list[Event] = field(default_factory=list)
    snapshot: MatchSnapshot | None = None
    moments: dict[str, Moment] = field(default_factory=dict)
    cards: list[OverlayCard] = field(default_factory=list)
    handoffs: list[Handoff] = field(default_factory=list)
    counters: Counter[str] = field(default_factory=Counter)
    recap: Any = None  # narrator's RecapOut at full time (None if it fell back to templates)
    listener: Callable[[Handoff], None] | None = field(default=None, repr=False)  # live log
    _started: float = field(default_factory=time.perf_counter, repr=False)

    @property
    def clock_ms(self) -> int:
        return self.events[-1].timestamp_ms if self.events else 0

    def ingest(self, batch: list[Event]) -> None:
        self.events.extend(batch)
        self.counters["events"] += len(batch)

    def add_moments(self, moments: list[Moment]) -> list[Moment]:
        """Store moments; return only the ones not seen before."""
        new = [m for m in moments if m.id not in self.moments]
        for m in new:
            self.moments[m.id] = m
        self.counters["moments"] += len(new)
        return new

    def add_cards(self, cards: list[OverlayCard]) -> None:
        self.cards.extend(cards)
        self.counters["cards"] += len(cards)

    def log(
        self,
        source: str,
        target: str,
        *,
        moment_id: str | None = None,
        status: HandoffStatus = HandoffStatus.OK,
        detail: str = "",
        provider: str | None = None,
        latency_ms: int | None = None,
        match_ms: int | None = None,
    ) -> Handoff:
        record = Handoff(
            seq=len(self.handoffs) + 1,
            wall_ms=int((time.perf_counter() - self._started) * 1000),
            match_ms=self.clock_ms if match_ms is None else match_ms,
            source=source,
            target=target,
            moment_id=moment_id,
            status=status,
            detail=detail,
            provider=provider,
            latency_ms=latency_ms,
        )
        self.handoffs.append(record)
        self.counters[f"handoff_{status.value}"] += 1
        if self.listener is not None:
            self.listener(record)
        return record
