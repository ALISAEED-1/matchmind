"""Pitch geometry shared by the generator and the stats engine.

Pitch units are 0-100 on both axes (see models.py). Helpers here convert to
metres and to a team's *attacking frame*, where x always grows towards the
opponent's goal (home: unchanged, away: mirrored).
"""

from __future__ import annotations

import math

from matchmind.models import PITCH_LENGTH_M, PITCH_WIDTH_M, Side

X_M = PITCH_LENGTH_M / 100
Y_M = PITCH_WIDTH_M / 100
GOAL_WIDTH_M = 7.32
FINAL_THIRD_X = 100 * 2 / 3
BOX_DEPTH_X = 16.5 / X_M  # penalty area depth in x-units (~15.7)
BOX_HALF_WIDTH_Y = 20.16 / Y_M  # half the penalty area width in y-units (~29.6)


def dist_m(x1: float, y1: float, x2: float, y2: float) -> float:
    """Distance in metres between two pitch points."""
    return math.hypot((x2 - x1) * X_M, (y2 - y1) * Y_M)


def attacking(side: Side, x: float, y: float) -> tuple[float, float]:
    """Convert absolute coordinates to `side`'s attacking frame (x towards the opponent goal)."""
    return (x, y) if side is Side.HOME else (100 - x, 100 - y)


def distance_to_goal_m(ax: float, ay: float) -> float:
    """Metres from an attacking-frame point to the centre of the opponent's goal."""
    return dist_m(ax, ay, 100, 50)


def goal_angle_rad(ax: float, ay: float) -> float:
    """Angle (radians) subtended by the goal mouth from an attacking-frame point."""
    dx = max((100 - ax) * X_M, 0.01)
    dy = (ay - 50) * Y_M
    half = GOAL_WIDTH_M / 2
    return abs(math.atan2(dy + half, dx) - math.atan2(dy - half, dx))


def in_final_third(ax: float) -> bool:
    return ax >= FINAL_THIRD_X


def in_box(ax: float, ay: float) -> bool:
    return ax >= 100 - BOX_DEPTH_X and abs(ay - 50) <= BOX_HALF_WIDTH_Y
