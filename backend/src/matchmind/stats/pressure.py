"""Pressing: how hard a team is squeezing the opponent.

Pressure index (0..1) for a team over a time window, PPDA-inspired:

    defensive work = sum over the team's pressures (x1), tackles (x1.5),
                     interceptions (x1.5) and fouls (x0.5),
                     each weighted by how high up the pitch it happened
                     (0.5 in its own box .. 1.5 at the opponent's box)
    intensity      = defensive work / opponent on-ball actions (passes + carries)
    index          = intensity / (intensity + K)

K is set so a typical match averages about 0.5. Higher = more aggressive press.
"""

from __future__ import annotations

from collections.abc import Sequence

from matchmind.models import Event, EventType, Side
from matchmind.stats._common import in_window, start_att

K = 0.30
WINDOW_MS = 10 * 60_000

_ACTION_WEIGHT = {
    EventType.PRESSURE: 1.0,
    EventType.TACKLE: 1.5,
    EventType.INTERCEPTION: 1.5,
    EventType.FOUL: 0.5,
}


def pressure_index(events: Sequence[Event], side: Side, start_ms: int, end_ms: int) -> float:
    window = in_window(events, start_ms, end_ms)
    work = 0.0
    for e in window:
        if e.team is side and e.type in _ACTION_WEIGHT and e.x is not None:
            ax, _ = start_att(e)
            work += _ACTION_WEIGHT[e.type] * (0.5 + ax / 100)
    opp_actions = sum(
        1 for e in window if e.team is side.other and e.type in (EventType.PASS, EventType.CARRY)
    )
    if opp_actions == 0:
        return 0.0
    intensity = work / opp_actions
    return round(intensity / (intensity + K), 3)


def recent_pressure(events: Sequence[Event], side: Side, window_ms: int = WINDOW_MS) -> float:
    """Pressure index over the last `window_ms` of the given events."""
    if not events:
        return 0.0
    end = events[-1].timestamp_ms
    return pressure_index(events, side, max(0, end - window_ms), end)


def under_pressure_share(events: Sequence[Event], side: Side) -> float:
    """Share of a team's passes, carries and shots made under pressure."""
    actions = [
        e
        for e in events
        if e.team is side and e.type in (EventType.PASS, EventType.CARRY, EventType.SHOT)
    ]
    if not actions:
        return 0.0
    return round(sum(e.under_pressure for e in actions) / len(actions), 3)
