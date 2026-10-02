"""Core data models shared by the generator, stats engine, agents and API.

Coordinates: pitch is 0-100 on both axes. The HOME team always attacks towards
x = 100, the AWAY team towards x = 0 (no side switch at half time, to keep the
data simple to render). y = 0 is the home team's right touchline.
1 unit on x = 1.05 m, 1 unit on y = 0.68 m (105 x 68 m pitch).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


class Side(StrEnum):
    HOME = "home"
    AWAY = "away"

    @property
    def other(self) -> Side:
        return Side.AWAY if self is Side.HOME else Side.HOME


class Position(StrEnum):
    GK = "GK"
    RB = "RB"
    CB = "CB"
    LB = "LB"
    DM = "DM"
    CM = "CM"
    AM = "AM"
    RW = "RW"
    LW = "LW"
    ST = "ST"


class EventType(StrEnum):
    KICKOFF = "kickoff"
    PASS = "pass"
    CARRY = "carry"
    PRESSURE = "pressure"
    TACKLE = "tackle"
    INTERCEPTION = "interception"
    POSSESSION_CHANGE = "possession_change"
    FOUL = "foul"
    CARD = "card"
    SHOT = "shot"
    GOAL = "goal"
    SUBSTITUTION = "substitution"
    HALF_TIME = "half_time"
    FULL_TIME = "full_time"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Player(_Strict):
    id: str = Field(description="Stable id, e.g. 'RIV-09'.")
    name: str
    shirt: int
    position: Position
    rating: int = Field(ge=40, le=99)
    pace: int = Field(ge=40, le=99)
    passing: int = Field(ge=40, le=99)
    finishing: int = Field(ge=40, le=99)
    defending: int = Field(ge=40, le=99)


class Club(_Strict):
    id: str = Field(description="Three-letter code, e.g. 'RIV'.")
    name: str
    short_name: str
    venue: str
    primary_color: str
    secondary_color: str
    formation: str = "4-3-3"
    players: list[Player] = Field(description="First 11 are the starters, in formation order.")

    @property
    def starters(self) -> list[Player]:
        return self.players[:11]

    @property
    def bench(self) -> list[Player]:
        return self.players[11:]


class Event(_Strict):
    event_id: str
    period: int = Field(ge=1, le=2)
    minute: int = Field(ge=0, description="Match minute, 0-based; >45 in period 1 means stoppage.")
    second: int = Field(ge=0, le=59)
    timestamp_ms: int = Field(ge=0, description="Milliseconds of play since kickoff (monotonic).")
    type: EventType
    team: Side | None = None
    player_id: str | None = None
    related_player_id: str | None = Field(
        default=None,
        description="Pass recipient, pressured/fouled player, player coming on, or assister.",
    )
    x: float | None = Field(default=None, ge=0, le=100)
    y: float | None = Field(default=None, ge=0, le=100)
    end_x: float | None = Field(default=None, ge=0, le=100)
    end_y: float | None = Field(default=None, ge=0, le=100)
    outcome: str | None = None
    ball_speed_kmh: float | None = Field(default=None, ge=0)
    under_pressure: bool = False
    details: dict[str, str | int | float | bool] = Field(default_factory=dict)


class Score(_Strict):
    home: int = 0
    away: int = 0


class MatchMeta(_Strict):
    match_id: str
    seed: int
    story: str
    generator_version: str
    competition: str
    venue: str
    home: Club
    away: Club
    final_score: Score
    stoppage_minutes: list[int] = Field(description="Added time for [period 1, period 2].")


class Match(_Strict):
    schema_version: str = SCHEMA_VERSION
    meta: MatchMeta
    events: list[Event]

    def club(self, side: Side) -> Club:
        return self.meta.home if side is Side.HOME else self.meta.away

    def player(self, player_id: str) -> Player:
        for club in (self.meta.home, self.meta.away):
            for p in club.players:
                if p.id == player_id:
                    return p
        raise KeyError(player_id)

    @classmethod
    def load(cls, path: str | Path) -> Match:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
