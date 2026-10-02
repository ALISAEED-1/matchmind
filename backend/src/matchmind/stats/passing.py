"""Pass accuracy and pass difficulty.

Pass difficulty is an explainable, hand-calibrated model of how likely an
average player is to complete a pass, from observable features only:

    z = 3.1 - 0.05 * max(0, distance - 12m)
            - 0.025 * forward progression (m)
            - 0.9 if under pressure
            - 0.5 if it ends in the final third
            - 0.5 if it ends in the penalty box
    expected_completion = sigmoid(z)
    difficulty = 100 * (1 - expected_completion) / 0.75, clamped to 0..100

A 10 m sideways pass scores ~6; a 30 m pass under pressure into the box ~75.
For incomplete passes the end point is where the ball was cut out, so their
difficulty is a lower bound; aggregate stats use completed passes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from matchmind.geometry import X_M, dist_m, in_box, in_final_third
from matchmind.models import Event, EventType, Side
from matchmind.stats._common import clamp, end_att, of_type, sigmoid, start_att

HARD_PASS = 60  # difficulty threshold for "hard"
ELITE_PASS = 80  # threshold for "elite"


@dataclass(frozen=True)
class PassDifficulty:
    score: int  # 0..100
    expected_completion: float
    distance_m: float
    progression_m: float
    under_pressure: bool
    into_final_third: bool
    into_box: bool

    @property
    def label(self) -> str:
        return difficulty_label(self.score)


def difficulty_label(score: float) -> str:
    if score >= ELITE_PASS:
        return "elite"
    if score >= HARD_PASS:
        return "hard"
    if score >= 30:
        return "moderate"
    return "routine"


def pass_difficulty(e: Event) -> PassDifficulty:
    if e.type is not EventType.PASS:
        raise ValueError(f"{e.event_id} is a {e.type}, not a pass")
    ax, ay = start_att(e)
    ex, ey = end_att(e)
    distance = dist_m(ax, ay, ex, ey)
    progression = max(0.0, (ex - ax) * X_M)
    final_third = in_final_third(ex)
    box = in_box(ex, ey)

    z = (
        3.1
        - 0.05 * max(0.0, distance - 12)
        - 0.025 * progression
        - 0.9 * e.under_pressure
        - 0.5 * final_third
        - 0.5 * box
    )
    p = sigmoid(z)
    return PassDifficulty(
        score=round(clamp((1 - p) / 0.75) * 100),
        expected_completion=round(p, 3),
        distance_m=round(distance, 1),
        progression_m=round(progression, 1),
        under_pressure=e.under_pressure,
        into_final_third=final_third,
        into_box=box,
    )


@dataclass(frozen=True)
class PassingSummary:
    attempted: int
    completed: int
    accuracy: float  # 0..1
    avg_difficulty_completed: float
    hard_completed: int  # completed passes with difficulty >= HARD_PASS
    progressive: int  # completed passes moving the ball >= 10 m towards goal
    avg_speed_kmh: float


def passing_summary(
    events: Iterable[Event], side: Side | None = None, player_id: str | None = None
) -> PassingSummary:
    passes = [
        e
        for e in of_type(events, EventType.PASS, side=side)
        if player_id is None or e.player_id == player_id
    ]
    completed = [e for e in passes if e.outcome == "complete"]
    diffs = [pass_difficulty(e) for e in completed]
    speeds = [e.ball_speed_kmh for e in passes if e.ball_speed_kmh is not None]
    return PassingSummary(
        attempted=len(passes),
        completed=len(completed),
        accuracy=round(len(completed) / len(passes), 3) if passes else 0.0,
        avg_difficulty_completed=round(sum(d.score for d in diffs) / len(diffs), 1)
        if diffs
        else 0.0,
        hard_completed=sum(d.score >= HARD_PASS for d in diffs),
        progressive=sum(d.progression_m >= 10 for d in diffs),
        avg_speed_kmh=round(sum(speeds) / len(speeds), 1) if speeds else 0.0,
    )
