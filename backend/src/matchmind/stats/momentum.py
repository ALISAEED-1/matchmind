"""Momentum: which team is creating more danger right now.

Each attacking action gets a threat value:

    shot                         xG + 0.05
    completed pass into the box  0.04
    completed pass into the
      final third (from outside) 0.02
    carry into the box           0.04
    tackle/interception won in
      the opponent's half        0.01

Threat is binned per minute of play (timestamp_ms // 60 000) and smoothed
with an exponential decay (half-life HALF_LIFE_MIN). Momentum is

    value = tanh(SCALE * (home - away) / (home + away + FLOOR))

in -1..+1: positive favours home. It is causal: the value at minute t only
uses events up to t, so live and post-match numbers agree.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from matchmind.geometry import in_box, in_final_third
from matchmind.models import Event, EventType, Side
from matchmind.stats._common import end_att, start_att
from matchmind.stats.shooting import shot_xg

HALF_LIFE_MIN = 4.0
SCALE = 1.2
FLOOR = 0.25


def threat(e: Event) -> float:
    """Danger created by one event for e.team (0 if none)."""
    if e.team is None:
        return 0.0
    if e.type is EventType.SHOT:
        return shot_xg(e).xg + 0.05
    if e.type is EventType.PASS and e.outcome == "complete":
        ax, _ = start_att(e)
        ex, ey = end_att(e)
        if in_box(ex, ey) and not in_box(*start_att(e)):
            return 0.04
        if in_final_third(ex) and not in_final_third(ax):
            return 0.02
        return 0.0
    if e.type is EventType.CARRY:
        if in_box(*end_att(e)) and not in_box(*start_att(e)):
            return 0.04
        return 0.0
    if e.type in (EventType.TACKLE, EventType.INTERCEPTION) and e.outcome == "won":
        ax, _ = start_att(e)
        return 0.01 if ax > 50 else 0.0
    return 0.0


@dataclass(frozen=True)
class MomentumPoint:
    t_min: int  # minute of play since kickoff (timestamp_ms // 60000)
    minute: int  # match-clock minute shown to viewers
    period: int
    home: float  # smoothed threat
    away: float
    value: float  # -1..+1, positive = home on top


def momentum_series(events: Sequence[Event]) -> list[MomentumPoint]:
    """One point per minute of play up to the last event."""
    if not events:
        return []
    decay = 0.5 ** (1 / HALF_LIFE_MIN)
    last_t = events[-1].timestamp_ms // 60_000
    bins: dict[int, dict[Side, float]] = {}
    clock: dict[int, tuple[int, int]] = {}
    for e in events:
        t = e.timestamp_ms // 60_000
        clock[t] = (e.minute, e.period)
        v = threat(e)
        if v:
            bins.setdefault(t, {Side.HOME: 0.0, Side.AWAY: 0.0})[e.team] += v

    series, h, a = [], 0.0, 0.0
    minute, period = 0, 1
    for t in range(last_t + 1):
        b = bins.get(t, {})
        h = h * decay + b.get(Side.HOME, 0.0)
        a = a * decay + b.get(Side.AWAY, 0.0)
        minute, period = clock.get(t, (minute + 1 if t else 0, period))
        value = math.tanh(SCALE * (h - a) / (h + a + FLOOR))
        series.append(MomentumPoint(t, minute, period, round(h, 3), round(a, 3), round(value, 3)))
    return series


def current_momentum(events: Sequence[Event]) -> float:
    series = momentum_series(events)
    return series[-1].value if series else 0.0
