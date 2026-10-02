"""Match snapshot: every number an agent may cite, computed in code.

`compute_snapshot(meta, events_so_far)` is what the Stats agent hands to the
LLM agents. They explain and narrate these values; they never compute numbers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel

from matchmind.models import Event, EventType, MatchMeta, Score, Side
from matchmind.stats.chaos import ChaosReading, recent_chaos
from matchmind.stats.momentum import MomentumPoint, momentum_series
from matchmind.stats.passing import PassingSummary, passing_summary
from matchmind.stats.physical import PhysicalSummary, physical_summary
from matchmind.stats.possession import possession_share
from matchmind.stats.pressure import recent_pressure, under_pressure_share
from matchmind.stats.shooting import ShootingSummary, shooting_summary

MOMENTUM_TAIL = 15  # minutes of momentum history included in a snapshot


class TeamSnapshot(BaseModel):
    side: Side
    club_id: str
    name: str
    goals: int
    possession: float
    passing: PassingSummary
    shooting: ShootingSummary
    physical: PhysicalSummary
    pressure_index_10min: float
    under_pressure_share: float
    tackles_won: int
    interceptions: int
    fouls: int
    yellow_cards: int
    red_cards: int


class PlayerSnapshot(BaseModel):
    player_id: str
    name: str
    team: Side
    position: str
    on_pitch: bool
    passing: PassingSummary
    shooting: ShootingSummary
    physical: PhysicalSummary
    goals: int
    assists: int
    tackles_won: int
    interceptions: int
    involvement: int  # on-ball + defensive actions


class MatchSnapshot(BaseModel):
    match_id: str
    period: int
    minute: int
    timestamp_ms: int
    score: Score
    home: TeamSnapshot
    away: TeamSnapshot
    momentum: float
    momentum_recent: list[MomentumPoint]
    control_chaos_10min: ChaosReading
    top_players: list[PlayerSnapshot]

    def team(self, side: Side) -> TeamSnapshot:
        return self.home if side is Side.HOME else self.away


def _count(
    events: Sequence[Event], etype: EventType, side=None, player_id=None, outcome=None
) -> int:
    return sum(
        1
        for e in events
        if e.type is etype
        and (side is None or e.team is side)
        and (player_id is None or e.player_id == player_id)
        and (outcome is None or e.outcome == outcome)
    )


def _team(meta: MatchMeta, events: Sequence[Event], side: Side, possession: float) -> TeamSnapshot:
    club = meta.home if side is Side.HOME else meta.away
    return TeamSnapshot(
        side=side,
        club_id=club.id,
        name=club.name,
        goals=_count(events, EventType.GOAL, side),
        possession=possession,
        passing=passing_summary(events, side),
        shooting=shooting_summary(events, side),
        physical=physical_summary(events, side=side),
        pressure_index_10min=recent_pressure(events, side),
        under_pressure_share=under_pressure_share(events, side),
        tackles_won=_count(events, EventType.TACKLE, side, outcome="won"),
        interceptions=_count(events, EventType.INTERCEPTION, side),
        fouls=_count(events, EventType.FOUL, side),
        yellow_cards=_count(events, EventType.CARD, side, outcome="yellow"),
        red_cards=_count(events, EventType.CARD, side, outcome="red"),
    )


def players_on_pitch(meta: MatchMeta, events: Sequence[Event]) -> set[str]:
    on = {p.id for p in meta.home.starters} | {p.id for p in meta.away.starters}
    for e in events:
        if e.type is EventType.SUBSTITUTION:
            on.discard(e.player_id)
            on.add(e.related_player_id)
        elif e.type is EventType.CARD and e.outcome == "red":
            on.discard(e.player_id)
    return on


def player_snapshot(meta: MatchMeta, events: Sequence[Event], player_id: str) -> PlayerSnapshot:
    side = Side.HOME if any(p.id == player_id for p in meta.home.players) else Side.AWAY
    club = meta.home if side is Side.HOME else meta.away
    player = next(p for p in club.players if p.id == player_id)
    involvement = sum(
        1
        for e in events
        if e.player_id == player_id
        and e.type
        in (
            EventType.PASS,
            EventType.CARRY,
            EventType.SHOT,
            EventType.TACKLE,
            EventType.INTERCEPTION,
            EventType.PRESSURE,
        )
    )
    return PlayerSnapshot(
        player_id=player_id,
        name=player.name,
        team=side,
        position=player.position.value,
        on_pitch=player_id in players_on_pitch(meta, events),
        passing=passing_summary(events, player_id=player_id),
        shooting=shooting_summary(events, player_id=player_id),
        physical=physical_summary(events, player_id=player_id),
        goals=_count(events, EventType.GOAL, player_id=player_id),
        assists=sum(
            1 for e in events if e.type is EventType.GOAL and e.related_player_id == player_id
        ),
        tackles_won=_count(events, EventType.TACKLE, player_id=player_id, outcome="won"),
        interceptions=_count(events, EventType.INTERCEPTION, player_id=player_id),
        involvement=involvement,
    )


def top_players(meta: MatchMeta, events: Sequence[Event], n: int = 5) -> list[PlayerSnapshot]:
    """Most influential players so far: goals and assists first, then involvement."""
    goals = Counter(e.player_id for e in events if e.type is EventType.GOAL)
    assists = Counter(e.related_player_id for e in events if e.type is EventType.GOAL)
    involvement = Counter(
        e.player_id
        for e in events
        if e.player_id and e.type not in (EventType.SUBSTITUTION, EventType.POSSESSION_CHANGE)
    )
    ranked = sorted(
        involvement,
        key=lambda pid: (goals[pid] * 3 + assists[pid] * 2, involvement[pid]),
        reverse=True,
    )
    return [player_snapshot(meta, events, pid) for pid in ranked[:n]]


def compute_snapshot(meta: MatchMeta, events: Sequence[Event]) -> MatchSnapshot:
    if not events:
        raise ValueError("cannot snapshot a match with no events")
    last = events[-1]
    share = possession_share(events)
    home = _team(meta, events, Side.HOME, share[Side.HOME])
    away = _team(meta, events, Side.AWAY, share[Side.AWAY])
    series = momentum_series(events)
    return MatchSnapshot(
        match_id=meta.match_id,
        period=last.period,
        minute=last.minute,
        timestamp_ms=last.timestamp_ms,
        score=Score(home=home.goals, away=away.goals),
        home=home,
        away=away,
        momentum=series[-1].value if series else 0.0,
        momentum_recent=series[-MOMENTUM_TAIL:],
        control_chaos_10min=recent_chaos(events),
        top_players=top_players(meta, events),
    )
