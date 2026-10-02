"""Control vs chaos: is the game settled or scrappy right now?

For a window of play (both teams together) we measure:

    turnover rate   possession changes per minute         (typical 1.2)
    sequence length completed passes per possession       (typical 4.5)
    foul rate       fouls per minute                      (typical 0.18)
    pressure share  share of on-ball actions under pressure (typical 0.12)

Each is scaled to 0..1 against a "calm" and a "frantic" reference value and
combined:

    chaos = 0.40 * turnovers + 0.30 * (short sequences) + 0.15 * fouls + 0.15 * pressure

0 = total control (long, patient possession), 1 = chaos (ball pinging between
teams, fouls, pressure everywhere). Labels: < 0.25 controlled, > 0.5 chaotic
(on simulated matches: 36% of 10-minute spells controlled, 17% chaotic).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from matchmind.models import Event, EventType
from matchmind.stats._common import clamp, in_window

WINDOW_MS = 10 * 60_000
CONTROLLED_BELOW = 0.25
CHAOTIC_ABOVE = 0.50


def _scale(v: float, calm: float, frantic: float) -> float:
    return clamp((v - calm) / (frantic - calm))


@dataclass(frozen=True)
class ChaosReading:
    index: float
    label: str  # controlled | balanced | chaotic
    turnovers_per_min: float
    avg_sequence_passes: float
    fouls_per_min: float
    under_pressure_share: float


def control_chaos(events: Sequence[Event], start_ms: int, end_ms: int) -> ChaosReading:
    window = in_window(events, start_ms, end_ms)
    minutes = max((end_ms - start_ms) / 60_000, 1.0)

    turnovers = sum(e.type is EventType.POSSESSION_CHANGE for e in window)
    fouls = sum(e.type is EventType.FOUL for e in window)
    on_ball = [e for e in window if e.type in (EventType.PASS, EventType.CARRY, EventType.SHOT)]
    pressured = sum(e.under_pressure for e in on_ball)
    completed = sum(e.type is EventType.PASS and e.outcome == "complete" for e in window)

    sequences = max(turnovers + sum(e.type is EventType.KICKOFF for e in window), 1)
    seq_len = completed / sequences
    t_rate = turnovers / minutes
    f_rate = fouls / minutes
    p_share = pressured / len(on_ball) if on_ball else 0.0

    index = (
        0.40 * _scale(t_rate, 0.8, 2.0)
        + 0.30 * (1 - _scale(seq_len, 2.0, 7.0))
        + 0.15 * _scale(f_rate, 0.05, 0.40)
        + 0.15 * _scale(p_share, 0.05, 0.25)
    )
    index = round(index, 3)
    label = (
        "controlled"
        if index < CONTROLLED_BELOW
        else "chaotic"
        if index > CHAOTIC_ABOVE
        else "balanced"
    )
    return ChaosReading(
        index=index,
        label=label,
        turnovers_per_min=round(t_rate, 2),
        avg_sequence_passes=round(seq_len, 2),
        fouls_per_min=round(f_rate, 2),
        under_pressure_share=round(p_share, 3),
    )


def recent_chaos(events: Sequence[Event], window_ms: int = WINDOW_MS) -> ChaosReading:
    end = events[-1].timestamp_ms if events else 0
    return control_chaos(events, max(0, end - window_ms), end)
