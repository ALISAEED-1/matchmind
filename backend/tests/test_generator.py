from collections import Counter
from functools import cache
from statistics import mean

import pytest

from matchmind.generator import (
    MATCHES_DIR,
    SCHEMA_PATH,
    SHIPPED_MATCHES,
    Story,
    build_league,
    generate,
    match_json_schema,
)
from matchmind.generator.simulator import dist_m
from matchmind.models import EventType, Match, Side

NATURAL_SEEDS = range(1, 9)


@cache
def natural(seed: int) -> Match:
    return generate(seed)


@cache
def story_match(story: Story, seed: int) -> Match:
    return generate(seed, story)


def passes(match: Match):
    return [e for e in match.events if e.type is EventType.PASS]


# --------------------------------------------------------------------- league


def test_league_is_stable_and_well_formed():
    a, b = build_league(), build_league()
    assert a == b
    assert len(a) == 4
    names = [p.name for club in a.values() for p in club.players]
    assert len(names) == len(set(names)), "player names must be unique across the league"
    for club in a.values():
        assert len(club.players) == 16
        assert len({p.shirt for p in club.players}) == 16
        assert len({p.id for p in club.players}) == 16


# ---------------------------------------------------------------- determinism


def test_same_seed_same_match():
    assert generate(5) == generate(5)


def test_different_seed_different_match():
    assert generate(5).events != generate(6).events


# ------------------------------------------------------------------- realism


@pytest.mark.parametrize("seed", NATURAL_SEEDS)
def test_event_count_and_pass_completion_in_range(seed):
    m = natural(seed)
    ps = passes(m)
    completion = sum(e.outcome == "complete" for e in ps) / len(ps)
    assert 900 <= len(m.events) <= 1150
    assert 0.75 <= completion <= 0.92


def test_average_shots_in_range():
    shots = [sum(e.type is EventType.SHOT for e in natural(s).events) for s in NATURAL_SEEDS]
    assert 20 <= mean(shots) <= 30


def test_momentum_creates_possession_swings():
    """Pass share per 15-minute block should not be flat: some blocks favour each side."""
    m = natural(3)
    blocks: dict[int, Counter] = {}
    for e in passes(m):
        blocks.setdefault(min(e.minute // 15, 5), Counter())[e.team] += 1
    shares = [c[Side.HOME] / (c[Side.HOME] + c[Side.AWAY]) for c in blocks.values()]
    assert max(shares) - min(shares) > 0.10


# ----------------------------------------------------------------- integrity


@pytest.mark.parametrize("seed", NATURAL_SEEDS)
def test_clock_and_ids_are_consistent(seed):
    m = natural(seed)
    ev = m.events
    assert ev[0].type is EventType.KICKOFF
    assert ev[-1].type is EventType.FULL_TIME
    assert [e.event_id for e in ev] == [f"e{i:05d}" for i in range(1, len(ev) + 1)]
    assert all(a.timestamp_ms <= b.timestamp_ms for a, b in zip(ev, ev[1:], strict=False))
    assert sum(e.type is EventType.HALF_TIME for e in ev) == 1
    assert all(e.minute >= 45 for e in ev if e.period == 2)


@pytest.mark.parametrize("seed", NATURAL_SEEDS)
def test_score_matches_goal_events(seed):
    m = natural(seed)
    goals = Counter(e.team for e in m.events if e.type is EventType.GOAL)
    assert goals[Side.HOME] == m.meta.final_score.home
    assert goals[Side.AWAY] == m.meta.final_score.away
    for i, e in enumerate(m.events):
        if e.type is EventType.GOAL:
            shot = m.events[i - 1]
            assert shot.type is EventType.SHOT and shot.outcome == "goal"
            assert shot.player_id == e.player_id


def _assert_players_on_pitch(m: Match) -> None:
    on_pitch = {
        Side.HOME: {p.id for p in m.meta.home.starters},
        Side.AWAY: {p.id for p in m.meta.away.starters},
    }
    for e in m.events:
        if e.team is None or e.player_id is None:
            continue
        assert e.player_id in on_pitch[e.team], f"{e.event_id}: {e.player_id} not on pitch"
        if e.type is EventType.SUBSTITUTION:
            on_pitch[e.team].remove(e.player_id)
            on_pitch[e.team].add(e.related_player_id)
        elif e.type is EventType.CARD and e.outcome == "red":
            on_pitch[e.team].remove(e.player_id)


@pytest.mark.parametrize("seed", NATURAL_SEEDS)
def test_only_players_on_pitch_act(seed):
    _assert_players_on_pitch(natural(seed))


def test_carries_have_plausible_speeds():
    for e in natural(1).events:
        if e.type is EventType.CARRY:
            mps = dist_m(e.x, e.y, e.end_x, e.end_y) / (e.details["duration_ms"] / 1000)
            assert mps < 10.0, "faster than a top sprinter"


# -------------------------------------------------------------------- stories


def _score_timeline(m: Match) -> list[tuple[int, int]]:
    return [
        (e.details["score_home"], e.details["score_away"])
        for e in m.events
        if e.type is EventType.GOAL
    ]


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_comeback_winner_trailed_by_two(seed):
    m = story_match(Story.COMEBACK, seed)
    fs = m.meta.final_score
    assert abs(fs.home - fs.away) == 1
    winner = Side.HOME if fs.home > fs.away else Side.AWAY
    deficits = [(a - h) if winner is Side.HOME else (h - a) for h, a in _score_timeline(m)]
    assert max(deficits) == 2
    _assert_players_on_pitch(m)


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_red_card_story(seed):
    m = story_match(Story.RED_CARD, seed)
    reds = [e for e in m.events if e.type is EventType.CARD and e.outcome == "red"]
    assert len(reds) == 1
    punished = reds[0].team
    fs = m.meta.final_score
    winner = Side.HOME if fs.home > fs.away else Side.AWAY
    assert winner is punished.other
    _assert_players_on_pitch(m)


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_late_winner_story(seed):
    m = story_match(Story.LATE_WINNER, seed)
    goals = [e for e in m.events if e.type is EventType.GOAL]
    last = goals[-1]
    assert last.period == 2 and last.minute >= 90
    h, a = last.details["score_home"], last.details["score_away"]
    assert abs(h - a) == 1, "the late goal decides the match"
    _assert_players_on_pitch(m)


# ------------------------------------------------------------- shipped files


@pytest.mark.parametrize("spec", SHIPPED_MATCHES, ids=lambda s: f"{s.seed}-{s.story.value}")
def test_shipped_match_is_valid_and_up_to_date(spec):
    path = MATCHES_DIR / f"mm-{spec.seed:04d}-{spec.story.value}.json"
    on_disk = Match.load(path)
    assert on_disk == generate(spec.seed, spec.story, spec.home, spec.away), (
        "data/matches is stale: run `uv run python -m matchmind.generator --shipped`"
    )
    shots = sum(e.type is EventType.SHOT for e in on_disk.events)
    assert 900 <= len(on_disk.events) <= 1150
    assert 20 <= shots <= 30


def test_json_schema_is_up_to_date():
    assert SCHEMA_PATH.read_text(encoding="utf-8") == match_json_schema(), (
        "docs/schema is stale: run `uv run python -m matchmind.generator --schema`"
    )
