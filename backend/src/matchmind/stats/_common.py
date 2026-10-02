"""Small helpers shared by the stat modules."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator

from matchmind.geometry import attacking
from matchmind.models import Event, EventType, Side

ON_BALL = frozenset({EventType.PASS, EventType.CARRY, EventType.SHOT, EventType.KICKOFF})


def sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z))


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def of_type(
    events: Iterable[Event], *types: EventType, side: Side | None = None
) -> Iterator[Event]:
    wanted = set(types)
    for e in events:
        if e.type in wanted and (side is None or e.team is side):
            yield e


def in_window(events: Iterable[Event], start_ms: int, end_ms: int) -> list[Event]:
    """Events with start_ms <= timestamp_ms <= end_ms."""
    return [e for e in events if start_ms <= e.timestamp_ms <= end_ms]


def start_att(e: Event) -> tuple[float, float]:
    """Event start position in the acting team's attacking frame."""
    assert e.team is not None and e.x is not None and e.y is not None
    return attacking(e.team, e.x, e.y)


def end_att(e: Event) -> tuple[float, float]:
    """Event end position in the acting team's attacking frame."""
    assert e.team is not None and e.end_x is not None and e.end_y is not None
    return attacking(e.team, e.end_x, e.end_y)
