"""Running speeds and distances from carries (the only movement the event data records)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from matchmind.geometry import dist_m
from matchmind.models import Event, EventType
from matchmind.stats._common import of_type

SPRINT_KMH = 25.2  # common high-intensity sprint threshold (7 m/s)
TOP_SPEED_ALERT_KMH = 30.0


def carry_distance_m(e: Event) -> float:
    assert e.type is EventType.CARRY and e.end_x is not None and e.end_y is not None
    return dist_m(e.x, e.y, e.end_x, e.end_y)


def carry_speed_kmh(e: Event) -> float:
    duration_s = int(e.details["duration_ms"]) / 1000
    return round(carry_distance_m(e) / duration_s * 3.6, 1)


@dataclass(frozen=True)
class PhysicalSummary:
    carries: int
    carry_distance_m: float
    top_speed_kmh: float
    sprints: int


def physical_summary(
    events: Iterable[Event], player_id: str | None = None, side=None
) -> PhysicalSummary:
    carries = [
        e
        for e in of_type(events, EventType.CARRY, side=side)
        if player_id is None or e.player_id == player_id
    ]
    speeds = [carry_speed_kmh(e) for e in carries]
    return PhysicalSummary(
        carries=len(carries),
        carry_distance_m=round(sum(carry_distance_m(e) for e in carries), 1),
        top_speed_kmh=max(speeds, default=0.0),
        sprints=sum(s >= SPRINT_KMH for s in speeds),
    )
