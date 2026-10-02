"""Story presets: scripted drama layered on top of the free simulation.

A story fixes *when* goals and red cards happen and nudges momentum so the
surrounding play looks like it earned them. Minutes get a small seeded jitter
so two seeds of the same story are not identical.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum

from matchmind.models import Side


class Story(StrEnum):
    NONE = "none"
    COMEBACK = "comeback"
    RED_CARD = "red_card"
    LATE_WINNER = "late_winner"


@dataclass(frozen=True)
class ScriptedGoal:
    minute: int  # 0-based match minute (>= 90 means second-half stoppage time)
    side: Side


@dataclass(frozen=True)
class ScriptedRedCard:
    minute: int
    side: Side


@dataclass(frozen=True)
class MomentumBias:
    """Adds `amount` to momentum in favour of `side` from `start` to `end` minute."""

    start: int
    end: int
    side: Side
    amount: float


@dataclass(frozen=True)
class StoryPlan:
    story: Story
    goals: tuple[ScriptedGoal, ...] = ()
    red_cards: tuple[ScriptedRedCard, ...] = ()
    biases: tuple[MomentumBias, ...] = ()
    min_stoppage_p2: int = 0
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def scripted_goals(self) -> bool:
        return self.story is not Story.NONE

    def bias_for_home(self, minute: int) -> float:
        total = 0.0
        for b in self.biases:
            if b.start <= minute < b.end:
                total += b.amount if b.side is Side.HOME else -b.amount
        return total


def plan_story(story: Story, rng: random.Random) -> StoryPlan:
    def j(minute: int, spread: int = 3) -> int:
        return minute + rng.randint(-spread, spread)

    if story is Story.NONE:
        return StoryPlan(story)

    if story is Story.COMEBACK:
        winner = rng.choice([Side.HOME, Side.AWAY])
        loser = winner.other
        return StoryPlan(
            story,
            goals=(
                ScriptedGoal(j(18), loser),
                ScriptedGoal(j(37), loser),
                ScriptedGoal(j(57), winner),
                ScriptedGoal(j(71), winner),
                ScriptedGoal(j(86, 2), winner),
            ),
            biases=(
                MomentumBias(0, 45, loser, 0.15),
                MomentumBias(50, 95, winner, 0.20),
            ),
            tags={"winner": winner.value, "trailed_by": "2"},
        )

    if story is Story.RED_CARD:
        punished = rng.choice([Side.HOME, Side.AWAY])
        other = punished.other
        return StoryPlan(
            story,
            goals=(
                ScriptedGoal(j(22), punished),
                ScriptedGoal(j(56), other),
                ScriptedGoal(j(79), other),
            ),
            red_cards=(ScriptedRedCard(j(31), punished),),
            tags={"sent_off_side": punished.value, "winner": other.value},
        )

    if story is Story.LATE_WINNER:
        winner = rng.choice([Side.HOME, Side.AWAY])
        first = rng.choice([Side.HOME, Side.AWAY])
        return StoryPlan(
            story,
            goals=(
                ScriptedGoal(j(34), first),
                ScriptedGoal(j(63), first.other),
                ScriptedGoal(92, winner),
            ),
            biases=(MomentumBias(80, 99, winner, 0.30),),
            min_stoppage_p2=5,
            tags={"winner": winner.value},
        )

    raise ValueError(f"Unknown story: {story}")
