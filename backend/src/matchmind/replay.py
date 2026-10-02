"""Event replayer: turns a stored match into a stream of event batches.

Batches are cut at minute-of-play boundaries (timestamp_ms // 60 000), which
lines up with the stats engine's per-minute trend detection.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence

from matchmind.models import Event

WINDOW_MS = 60_000


def batches(events: Sequence[Event], window_ms: int = WINDOW_MS) -> Iterator[list[Event]]:
    """Split events into consecutive windows of match time (instant, for baking and tests)."""
    batch: list[Event] = []
    current = None
    for e in events:
        w = e.timestamp_ms // window_ms
        if current is not None and w != current and batch:
            yield batch
            batch = []
        current = w
        batch.append(e)
    if batch:
        yield batch


async def live_batches(
    events: Sequence[Event], speed: float = 10.0, window_ms: int = WINDOW_MS
) -> AsyncIterator[list[Event]]:
    """Yield windows in (sped-up) real time: one window of match time takes window_ms / speed."""
    if speed <= 0:
        raise ValueError("speed must be positive")
    for batch in batches(events, window_ms):
        yield batch
        await asyncio.sleep(window_ms / 1000 / speed)
