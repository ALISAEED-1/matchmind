"""Expected goals (xG) and shot summaries.

xG is a logistic model fitted by maximum likelihood on 4,797 shots from 200
natural (non-story) synthetic matches (seeds 100-299, 11.5% conversion):

    z  = -0.07 - 0.147 * distance_to_goal_m
         - 0.51 for headers - 0.26 under pressure
    xg = sigmoid(z), clamped to 0.01..0.95

A lateral-offset term was tested and came out ~0 (distance already captures
wide shots), so it was dropped to keep the model explainable. Reference
values: 6 m central 0.28, penalty spot 0.16, 20 m 0.05, 25 m 0.02.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from matchmind.geometry import distance_to_goal_m, goal_angle_rad
from matchmind.models import Event, EventType, Side
from matchmind.stats._common import clamp, of_type, sigmoid, start_att

BIG_CHANCE_XG = 0.25
ON_TARGET = frozenset({"goal", "saved"})


@dataclass(frozen=True)
class ShotValue:
    xg: float
    distance_m: float
    angle_deg: float
    header: bool
    under_pressure: bool


def shot_xg(e: Event) -> ShotValue:
    if e.type is not EventType.SHOT:
        raise ValueError(f"{e.event_id} is a {e.type}, not a shot")
    ax, ay = start_att(e)
    distance = distance_to_goal_m(ax, ay)
    angle = goal_angle_rad(ax, ay)
    header = e.details.get("body_part") == "head"
    z = -0.07 - 0.147 * distance - 0.51 * header - 0.26 * e.under_pressure
    return ShotValue(
        xg=round(clamp(sigmoid(z), 0.01, 0.95), 3),
        distance_m=round(distance, 1),
        angle_deg=round(angle * 57.2958, 1),
        header=header,
        under_pressure=e.under_pressure,
    )


@dataclass(frozen=True)
class ShootingSummary:
    shots: int
    on_target: int
    goals: int
    xg: float
    big_chances: int
    max_shot_speed_kmh: float
    avg_shot_speed_kmh: float


def shooting_summary(
    events: Iterable[Event], side: Side | None = None, player_id: str | None = None
) -> ShootingSummary:
    shots = [
        e
        for e in of_type(events, EventType.SHOT, side=side)
        if player_id is None or e.player_id == player_id
    ]
    values = [shot_xg(e) for e in shots]
    speeds = [e.ball_speed_kmh for e in shots if e.ball_speed_kmh is not None]
    return ShootingSummary(
        shots=len(shots),
        on_target=sum(e.outcome in ON_TARGET for e in shots),
        goals=sum(e.outcome == "goal" for e in shots),
        xg=round(sum(v.xg for v in values), 2),
        big_chances=sum(v.xg >= BIG_CHANCE_XG for v in values),
        max_shot_speed_kmh=max(speeds, default=0.0),
        avg_shot_speed_kmh=round(sum(speeds) / len(speeds), 1) if speeds else 0.0,
    )
