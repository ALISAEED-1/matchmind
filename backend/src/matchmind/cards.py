"""Overlay cards: the timed, machine-readable output of the pipeline.

A card is one piece of on-screen content for one audience in one language.
All variants produced for the same moment share a `group_id`, so a client can
switch audience or language and show the matching card.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from matchmind.models import Side


class CardType(StrEnum):
    INSIGHT = "insight"
    STAT = "stat"
    COMMENTARY = "commentary"
    MILESTONE = "milestone"
    RECAP = "recap"


class Audience(StrEnum):
    FAN = "fan"
    ANALYST = "analyst"
    PLAYER_FOCUS = "player_focus"


class Language(StrEnum):
    EN = "en"
    UR = "ur"
    AR = "ar"


class OverlayCard(BaseModel):
    id: str
    group_id: str = Field(description="Shared by all audience/language variants of one card.")
    moment_id: str | None = None
    match_minute: int
    period: int
    display_at_ms: int = Field(description="Show at this timestamp_ms of match play.")
    duration_ms: int = 8000
    type: CardType
    audience: Audience
    language: Language
    title: str
    body: str
    why_it_matters: str | None = None
    data: dict[str, float | int | str | bool] = Field(default_factory=dict)
    team: Side | None = None
    player_id: str | None = None
    importance: float = 0.0
    source_agent: str
    provider: str | None = Field(default=None, description="Model that wrote the text, if any.")
    fallback_used: bool = False
    verified: bool = True
