"""Deterministic key-moment detection.

The orchestrator routes on these moments (importance decides which agents run)
and the LLM agents explain them; detection itself never uses an LLM.

Two kinds of detector:

* **Event moments** fire on a single event: goal, big chance, red/yellow card,
  elite pass, rocket shot, top-speed run, milestones, substitutions, half/full time.
* **Trend moments** are evaluated at each completed minute of play using only
  events before that minute's end: momentum shift, pressure surge, chaos spell.

Every moment depends only on events up to its own timestamp, so detecting on a
partial match gives exactly the full match's moments up to that point (tested).
Moment ids are stable, so live mode can de-duplicate across windows.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from matchmind.models import Event, EventType, Side
from matchmind.stats.chaos import control_chaos
from matchmind.stats.momentum import momentum_series
from matchmind.stats.passing import ELITE_PASS, pass_difficulty
from matchmind.stats.physical import TOP_SPEED_ALERT_KMH, carry_speed_kmh
from matchmind.stats.pressure import pressure_index
from matchmind.stats.shooting import BIG_CHANCE_XG, shot_xg

ROCKET_SHOT_KMH = 108.0  # ~2 per match in this league (about the 95th percentile)
PASS_MILESTONES = (50,)
TEAM_SHOT_MILESTONES = (10, 20)

MOMENTUM_SWING = 0.45  # change in momentum over SWING_LOOKBACK minutes
SWING_LOOKBACK = 5
MOMENTUM_COOLDOWN = 8
PRESSURE_SURGE_LEVEL = 0.60
PRESSURE_SURGE_RISE = 0.12
PRESSURE_COOLDOWN = 15
CHAOS_SPELL_LEVEL = 0.55
CHAOS_COOLDOWN = 15
WINDOW_MS = 10 * 60_000


class MomentKind(StrEnum):
    GOAL = "goal"
    BIG_CHANCE = "big_chance"
    RED_CARD = "red_card"
    YELLOW_CARD = "yellow_card"
    ELITE_PASS = "elite_pass"
    ROCKET_SHOT = "rocket_shot"
    TOP_SPEED = "top_speed"
    PASS_MILESTONE = "pass_milestone"
    SHOT_MILESTONE = "shot_milestone"
    SUBSTITUTION = "substitution"
    MOMENTUM_SHIFT = "momentum_shift"
    PRESSURE_SURGE = "pressure_surge"
    CHAOS_SPELL = "chaos_spell"
    HALF_TIME = "half_time"
    FULL_TIME = "full_time"


IMPORTANCE: dict[MomentKind, float] = {
    MomentKind.GOAL: 1.0,
    MomentKind.RED_CARD: 0.9,
    MomentKind.FULL_TIME: 0.85,
    MomentKind.HALF_TIME: 0.7,
    MomentKind.BIG_CHANCE: 0.6,  # +xG, see below
    MomentKind.MOMENTUM_SHIFT: 0.6,
    MomentKind.PRESSURE_SURGE: 0.5,
    MomentKind.CHAOS_SPELL: 0.45,
    MomentKind.ROCKET_SHOT: 0.4,
    MomentKind.ELITE_PASS: 0.35,
    MomentKind.TOP_SPEED: 0.35,
    MomentKind.YELLOW_CARD: 0.3,
    MomentKind.PASS_MILESTONE: 0.3,
    MomentKind.SHOT_MILESTONE: 0.25,
    MomentKind.SUBSTITUTION: 0.15,
}


@dataclass(frozen=True)
class Moment:
    id: str
    kind: MomentKind
    timestamp_ms: int
    period: int
    minute: int
    importance: float
    team: Side | None = None
    player_id: str | None = None
    event_id: str | None = None
    data: dict[str, float | int | str | bool] = field(default_factory=dict)


def _from_event(kind: MomentKind, e: Event, importance: float | None = None, **data) -> Moment:
    return Moment(
        id=f"{kind.value}:{e.event_id}",
        kind=kind,
        timestamp_ms=e.timestamp_ms,
        period=e.period,
        minute=e.minute,
        importance=round(IMPORTANCE[kind] if importance is None else importance, 3),
        team=e.team,
        player_id=e.player_id,
        event_id=e.event_id,
        data=data,
    )


def _event_moments(events: Sequence[Event]) -> list[Moment]:
    out: list[Moment] = []
    completed_passes: Counter[str] = Counter()
    team_shots: Counter[Side] = Counter()
    goals_by_player: Counter[str] = Counter()

    for i, e in enumerate(events):
        t = e.type
        if t is EventType.GOAL:
            goals_by_player[e.player_id] += 1
            shot = events[i - 1] if i and events[i - 1].type is EventType.SHOT else None
            out.append(
                _from_event(
                    MomentKind.GOAL,
                    e,
                    score_home=int(e.details["score_home"]),
                    score_away=int(e.details["score_away"]),
                    **({"assist_player_id": e.related_player_id} if e.related_player_id else {}),
                    player_goals=goals_by_player[e.player_id],
                    xg=shot_xg(shot).xg if shot else 0.0,
                    shot_speed_kmh=(shot.ball_speed_kmh or 0.0) if shot else 0.0,
                )
            )
        elif t is EventType.SHOT:
            team_shots[e.team] += 1
            value = shot_xg(e)
            if e.outcome != "goal" and value.xg >= BIG_CHANCE_XG:
                out.append(
                    _from_event(
                        MomentKind.BIG_CHANCE,
                        e,
                        IMPORTANCE[MomentKind.BIG_CHANCE] + value.xg / 2,
                        xg=value.xg,
                        outcome=e.outcome or "",
                        distance_m=value.distance_m,
                    )  # fmt: skip
                )
            if (e.ball_speed_kmh or 0) >= ROCKET_SHOT_KMH:
                out.append(
                    _from_event(
                        MomentKind.ROCKET_SHOT,
                        e,
                        speed_kmh=e.ball_speed_kmh,
                        outcome=e.outcome or "",
                    )
                )
            if team_shots[e.team] in TEAM_SHOT_MILESTONES:
                out.append(_from_event(MomentKind.SHOT_MILESTONE, e, team_shots=team_shots[e.team]))
        elif t is EventType.PASS and e.outcome == "complete":
            completed_passes[e.player_id] += 1
            d = pass_difficulty(e)
            if d.score >= ELITE_PASS:
                out.append(
                    _from_event(
                        MomentKind.ELITE_PASS,
                        e,
                        difficulty=d.score,
                        distance_m=d.distance_m,
                        under_pressure=d.under_pressure,
                        into_box=d.into_box,
                        recipient_id=e.related_player_id or "",
                    )  # fmt: skip
                )
            if completed_passes[e.player_id] in PASS_MILESTONES:
                out.append(
                    _from_event(
                        MomentKind.PASS_MILESTONE, e, completed_passes=completed_passes[e.player_id]
                    )
                )
        elif t is EventType.CARRY:
            speed = carry_speed_kmh(e)
            if speed >= TOP_SPEED_ALERT_KMH:
                out.append(_from_event(MomentKind.TOP_SPEED, e, speed_kmh=speed))
        elif t is EventType.CARD:
            kind = MomentKind.RED_CARD if e.outcome == "red" else MomentKind.YELLOW_CARD
            out.append(_from_event(kind, e))
        elif t is EventType.SUBSTITUTION:
            out.append(
                _from_event(MomentKind.SUBSTITUTION, e, on_player_id=e.related_player_id or "")
            )
        elif t in (EventType.HALF_TIME, EventType.FULL_TIME):
            kind = MomentKind.HALF_TIME if t is EventType.HALF_TIME else MomentKind.FULL_TIME
            out.append(
                _from_event(
                    kind,
                    e,
                    score_home=int(e.details["score_home"]),
                    score_away=int(e.details["score_away"]),
                )
            )
    return out


def _trend_moments(events: Sequence[Event]) -> list[Moment]:
    if not events:
        return []
    last_ts = events[-1].timestamp_ms
    series = momentum_series(events)
    complete = [p for p in series if (p.t_min + 1) * 60_000 <= last_ts]

    out: list[Moment] = []
    last_shift = -99
    last_surge = {Side.HOME: -99, Side.AWAY: -99}
    last_chaos = -99
    prev_chaos = 0.0
    # Events are time-ordered: binary-search each window instead of rescanning the prefix
    # (keeps detection linear per call; it runs every replay window in live mode).
    stamps = [e.timestamp_ms for e in events]

    def between(lo_ms: int, hi_ms: int) -> Sequence[Event]:
        """Events with lo_ms <= timestamp_ms < hi_ms."""
        return events[bisect_left(stamps, lo_ms) : bisect_left(stamps, hi_ms)]

    for p in complete:
        boundary = (p.t_min + 1) * 60_000
        meta = {"period": p.period, "minute": p.minute}

        # Momentum shift: a big swing towards one side.
        if p.t_min >= SWING_LOOKBACK and p.t_min - last_shift >= MOMENTUM_COOLDOWN:
            past = complete[p.t_min - SWING_LOOKBACK].value
            swing = p.value - past
            if abs(swing) >= MOMENTUM_SWING:
                last_shift = p.t_min
                side = Side.HOME if swing > 0 else Side.AWAY
                out.append(
                    Moment(
                        id=f"{MomentKind.MOMENTUM_SHIFT.value}:t{p.t_min}",
                        kind=MomentKind.MOMENTUM_SHIFT,
                        timestamp_ms=boundary,
                        importance=IMPORTANCE[MomentKind.MOMENTUM_SHIFT],
                        team=side,
                        data={"from": past, "to": p.value, "lookback_min": SWING_LOOKBACK},
                        **meta,
                    )
                )

        # Pressure surge and chaos spell are measured over the last 10 minutes.
        if boundary < WINDOW_MS:
            continue
        start = boundary - WINDOW_MS
        recent = between(start, boundary)
        earlier = between(max(0, start - WINDOW_MS), start)
        for side in Side:
            now = pressure_index(recent, side, start, boundary - 1)
            prior = pressure_index(earlier, side, max(0, start - WINDOW_MS), start - 1)
            if (
                now >= PRESSURE_SURGE_LEVEL
                and now - prior >= PRESSURE_SURGE_RISE
                and p.t_min - last_surge[side] >= PRESSURE_COOLDOWN
            ):
                last_surge[side] = p.t_min
                out.append(
                    Moment(
                        id=f"{MomentKind.PRESSURE_SURGE.value}:{side.value}:t{p.t_min}",
                        kind=MomentKind.PRESSURE_SURGE,
                        timestamp_ms=boundary,
                        importance=IMPORTANCE[MomentKind.PRESSURE_SURGE],
                        team=side,
                        data={"pressure_index": now, "previous": prior},
                        **meta,
                    )
                )

        chaos = control_chaos(recent, start, boundary - 1)
        if (
            chaos.index >= CHAOS_SPELL_LEVEL
            and prev_chaos < CHAOS_SPELL_LEVEL
            and p.t_min - last_chaos >= CHAOS_COOLDOWN
        ):
            last_chaos = p.t_min
            out.append(
                Moment(
                    id=f"{MomentKind.CHAOS_SPELL.value}:t{p.t_min}",
                    kind=MomentKind.CHAOS_SPELL,
                    timestamp_ms=boundary,
                    importance=IMPORTANCE[MomentKind.CHAOS_SPELL],
                    data={
                        "chaos_index": chaos.index,
                        "turnovers_per_min": chaos.turnovers_per_min,
                        "avg_sequence_passes": chaos.avg_sequence_passes,
                    },
                    **meta,
                )
            )
        prev_chaos = chaos.index
    return out


def detect_moments(events: Sequence[Event]) -> list[Moment]:
    """All key moments in time order (ties: higher importance first)."""
    moments = _event_moments(events) + _trend_moments(events)
    return sorted(moments, key=lambda m: (m.timestamp_ms, -m.importance, m.id))
