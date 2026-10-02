"""Possession share, measured as time on the ball.

Between two consecutive on-ball events (pass, carry, shot, kickoff), the
interval is credited to the team that made the earlier one. Gaps longer than
MAX_LIVE_GAP_MS are treated as dead ball and ignored.
"""

from __future__ import annotations

from collections.abc import Sequence

from matchmind.models import Event, Side
from matchmind.stats._common import ON_BALL

MAX_LIVE_GAP_MS = 15_000


def possession_ms(events: Sequence[Event]) -> dict[Side, int]:
    totals = {Side.HOME: 0, Side.AWAY: 0}
    prev: Event | None = None
    for e in events:
        if e.type not in ON_BALL or e.team is None:
            continue
        if prev is not None and prev.period == e.period:
            gap = e.timestamp_ms - prev.timestamp_ms
            if 0 < gap <= MAX_LIVE_GAP_MS:
                totals[prev.team] += gap
        prev = e
    return totals


def possession_share(events: Sequence[Event]) -> dict[Side, float]:
    """Share of time on the ball, 0..1 per team (sums to 1; 0.5 each if no data)."""
    ms = possession_ms(events)
    total = ms[Side.HOME] + ms[Side.AWAY]
    if total == 0:
        return {Side.HOME: 0.5, Side.AWAY: 0.5}
    home = round(ms[Side.HOME] / total, 3)
    return {Side.HOME: home, Side.AWAY: round(1 - home, 3)}
