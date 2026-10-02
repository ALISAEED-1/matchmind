"""Deterministic stats engine: pure functions over a list of events.

Every function takes the events seen so far, so the same code serves live
replay (a prefix of the match) and post-match analysis (all events).
"""

from matchmind.stats.chaos import ChaosReading, control_chaos, recent_chaos
from matchmind.stats.moments import Moment, MomentKind, detect_moments
from matchmind.stats.momentum import MomentumPoint, current_momentum, momentum_series, threat
from matchmind.stats.passing import (
    PassDifficulty,
    difficulty_label,
    pass_difficulty,
    passing_summary,
)
from matchmind.stats.physical import carry_speed_kmh, physical_summary
from matchmind.stats.possession import possession_share
from matchmind.stats.pressure import pressure_index, recent_pressure, under_pressure_share
from matchmind.stats.shooting import ShotValue, shooting_summary, shot_xg
from matchmind.stats.snapshot import (
    MatchSnapshot,
    PlayerSnapshot,
    TeamSnapshot,
    compute_snapshot,
    player_snapshot,
)

__all__ = [
    "ChaosReading",
    "MatchSnapshot",
    "Moment",
    "MomentKind",
    "MomentumPoint",
    "PassDifficulty",
    "PlayerSnapshot",
    "ShotValue",
    "TeamSnapshot",
    "carry_speed_kmh",
    "compute_snapshot",
    "control_chaos",
    "current_momentum",
    "detect_moments",
    "difficulty_label",
    "momentum_series",
    "pass_difficulty",
    "passing_summary",
    "physical_summary",
    "player_snapshot",
    "possession_share",
    "pressure_index",
    "recent_chaos",
    "recent_pressure",
    "shooting_summary",
    "shot_xg",
    "threat",
    "under_pressure_share",
]
