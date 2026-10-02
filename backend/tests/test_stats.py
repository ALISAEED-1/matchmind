from functools import cache
from itertools import count
from statistics import mean

import pytest

from matchmind.generator import MATCHES_DIR, Story, generate
from matchmind.geometry import attacking, dist_m, goal_angle_rad, in_box
from matchmind.models import Event, EventType, Match, Side
from matchmind.stats import (
    MomentKind,
    carry_speed_kmh,
    compute_snapshot,
    control_chaos,
    detect_moments,
    momentum_series,
    pass_difficulty,
    passing_summary,
    possession_share,
    pressure_index,
    shot_xg,
)

H, A = Side.HOME, Side.AWAY
_ids = count(1)


def ev(etype: EventType, team: Side | None = H, x=50.0, y=50.0, t=0, **kw) -> Event:
    """Build an event; x/y/end_x/end_y are given in `team`'s attacking frame for readability."""
    if team is not None:
        x, y = attacking(team, x, y)
        if "end_x" in kw:
            kw["end_x"], kw["end_y"] = attacking(team, kw["end_x"], kw["end_y"])
    return Event(
        event_id=f"t{next(_ids):05d}",
        period=kw.pop("period", 1),
        minute=t // 60_000,
        second=(t // 1000) % 60,
        timestamp_ms=t,
        type=etype,
        team=team,
        player_id=kw.pop("player_id", f"{'RIV' if team is H else 'IRN'}-09" if team else None),
        x=x,
        y=y,
        **kw,
    )


def pass_(team=H, x=40, y=50, end_x=50, end_y=50, outcome="complete", t=0, **kw) -> Event:
    return ev(EventType.PASS, team, x, y, t, end_x=end_x, end_y=end_y, outcome=outcome, **kw)


def shot(team=H, x=90, y=50, t=0, **kw) -> Event:
    return ev(EventType.SHOT, team, x, y, t, end_x=100, end_y=50, outcome="saved", **kw)


@cache
def shipped(name: str) -> Match:
    return Match.load(MATCHES_DIR / f"{name}.json")


COMEBACK, RED_CARD, LATE_WINNER = "mm-0004-comeback", "mm-0003-red_card", "mm-0020-late_winner"


# ------------------------------------------------------------------ geometry


def test_geometry_basics():
    assert dist_m(0, 50, 100, 50) == pytest.approx(105)
    assert dist_m(50, 0, 50, 100) == pytest.approx(68)
    assert attacking(A, 10, 20) == (90, 80)
    assert goal_angle_rad(95, 50) > goal_angle_rad(80, 50) > goal_angle_rad(80, 10)
    assert in_box(90, 50) and not in_box(80, 50) and not in_box(90, 5)


# ------------------------------------------------------------------- passing


def test_pass_difficulty_ranks_easy_and_hard_passes():
    easy = pass_difficulty(pass_(x=30, y=50, end_x=30, end_y=60))
    hard = pass_difficulty(pass_(x=55, y=50, end_x=90, end_y=50, under_pressure=True))
    assert easy.score < 15 and easy.label == "routine"
    assert hard.score >= 80 and hard.label == "elite"
    assert hard.into_box and hard.into_final_third


@pytest.mark.parametrize(
    "change",
    [
        {"under_pressure": True},  # pressure makes it harder
        {"end_x": 75},  # longer, more progressive, into the final third
    ],
)
def test_pass_difficulty_is_monotonic(change):
    base = dict(x=40, y=50, end_x=55, end_y=50)
    harder = {**base, **change}
    assert pass_difficulty(pass_(**harder)).score > pass_difficulty(pass_(**base)).score


def test_pass_difficulty_is_side_symmetric():
    assert pass_difficulty(pass_(H, 40, 30, 70, 60)) == pass_difficulty(pass_(A, 40, 30, 70, 60))


def test_pass_difficulty_rejects_non_pass():
    with pytest.raises(ValueError):
        pass_difficulty(shot())


def test_passing_summary_counts():
    events = [pass_(), pass_(), pass_(outcome="incomplete"), pass_(A)]
    s = passing_summary(events, H)
    assert (s.attempted, s.completed, s.accuracy) == (3, 2, pytest.approx(0.667, abs=1e-3))


def test_pass_difficulty_is_calibrated_on_simulated_matches():
    passes = [e for seed in range(1, 6) for e in generate(seed).events if e.type is EventType.PASS]
    predicted = mean(pass_difficulty(e).expected_completion for e in passes)
    actual = mean(e.outcome == "complete" for e in passes)
    assert predicted == pytest.approx(actual, abs=0.03)


# ------------------------------------------------------------------ shooting


def test_xg_reference_values():
    assert shot_xg(shot(x=100 - 6 / 1.05)).xg == pytest.approx(0.28, abs=0.02)
    assert shot_xg(shot(x=100 - 20 / 1.05)).xg == pytest.approx(0.05, abs=0.01)


def test_xg_drops_with_distance_headers_and_pressure():
    close, far = shot_xg(shot(x=94)).xg, shot_xg(shot(x=80)).xg
    assert close > far
    assert shot_xg(shot(x=94, details={"body_part": "head"})).xg < close
    assert shot_xg(shot(x=94, under_pressure=True)).xg < close
    assert shot_xg(shot(H, 90, 40)) == shot_xg(shot(A, 90, 40))


def test_xg_is_calibrated_out_of_sample():
    """Fitted on seeds 100-299; check total xG against goals on unseen seeds 1-20."""
    xg = goals = 0.0
    for seed in range(1, 21):
        for e in generate(seed).events:
            if e.type is EventType.SHOT:
                xg += shot_xg(e).xg
                goals += e.outcome == "goal"
    assert 0.8 <= xg / goals <= 1.2


# ---------------------------------------------------------------- possession


def test_possession_is_time_on_ball():
    events = [
        pass_(H, t=0),
        pass_(H, t=6000),
        pass_(A, t=12_000),  # home had 0-12 s
        pass_(A, t=16_000),  # away had 12-20 s
        pass_(H, t=20_000),
    ]
    share = possession_share(events)
    assert share[H] == pytest.approx(0.6)
    assert share[H] + share[A] == pytest.approx(1)


def test_possession_ignores_dead_ball_gaps_and_handles_empty():
    events = [pass_(H, t=0), pass_(A, t=60_000), pass_(H, t=64_000)]
    assert possession_share(events)[A] == pytest.approx(1.0)
    assert possession_share([]) == {H: 0.5, A: 0.5}


# ------------------------------------------------------------------ pressure


def test_pressure_index_rewards_high_aggressive_pressing():
    opp_passes = [pass_(A, t=i * 1000) for i in range(20)]
    low = [ev(EventType.PRESSURE, H, x=20, t=i * 1000) for i in range(3)]
    high = [ev(EventType.PRESSURE, H, x=85, t=i * 1000) for i in range(10)]
    assert pressure_index(opp_passes + high, H, 0, 60_000) > pressure_index(
        opp_passes + low, H, 0, 60_000
    )
    assert 0 <= pressure_index(opp_passes + high, H, 0, 60_000) <= 1
    assert pressure_index(high, H, 0, 60_000) == 0.0  # no opponent actions to press


# ------------------------------------------------------------------ momentum


def test_momentum_follows_threat_and_is_bounded():
    events = [shot(H, x=92, t=i * 30_000) for i in range(6)]
    series = momentum_series(events)
    assert series[-1].value > 0.5
    away = [shot(A, x=92, t=i * 30_000) for i in range(6)]
    assert momentum_series(away)[-1].value < -0.5
    assert all(-1 <= p.value <= 1 for p in momentum_series(shipped(COMEBACK).events))


def test_momentum_is_causal():
    events = shipped(COMEBACK).events
    full = momentum_series(events)
    cut = 500
    prefix = momentum_series(events[:cut])
    complete = [p for p in prefix if (p.t_min + 1) * 60_000 <= events[cut - 1].timestamp_ms]
    assert complete == full[: len(complete)]


# --------------------------------------------------------------------- chaos


def test_chaos_separates_scrappy_from_patient_play():
    scrappy = []
    for i in range(30):
        side = H if i % 2 else A
        scrappy += [
            pass_(side, t=i * 4000, outcome="incomplete", under_pressure=True),
            ev(EventType.POSSESSION_CHANGE, side.other, t=i * 4000 + 1000),
        ]
        if i % 5 == 0:
            scrappy.append(ev(EventType.FOUL, side, t=i * 4000 + 2000))
    patient = [pass_(H, t=i * 2000) for i in range(60)] + [
        ev(EventType.POSSESSION_CHANGE, A, t=120_000)
    ]
    assert control_chaos(scrappy, 0, 120_000).label == "chaotic"
    assert control_chaos(patient, 0, 120_000).label == "controlled"


# ------------------------------------------------------------------ physical


def test_carry_speed():
    e = ev(
        EventType.CARRY,
        H,
        x=40,
        y=50,
        end_x=40 + 10 / 1.05,
        end_y=50,
        details={"duration_ms": 1000},
    )
    assert carry_speed_kmh(e) == pytest.approx(36.0)


# ------------------------------------------------------------------- moments


@pytest.mark.parametrize("name", [COMEBACK, RED_CARD, LATE_WINNER])
def test_moments_are_prefix_consistent(name):
    """Live detection on a partial match must agree with post-match detection."""
    events = shipped(name).events
    full = detect_moments(events)
    for cut in (250, 600, 900):
        while events[cut].timestamp_ms == events[cut - 1].timestamp_ms:
            cut += 1  # don't split events that share a timestamp
        last_ts = events[cut - 1].timestamp_ms
        expected = [m for m in full if m.timestamp_ms <= last_ts]
        assert detect_moments(events[:cut]) == expected


@pytest.mark.parametrize("name", [COMEBACK, RED_CARD, LATE_WINNER])
def test_every_goal_and_card_is_a_moment(name):
    m = shipped(name)
    moments = detect_moments(m.events)
    goals = [e.event_id for e in m.events if e.type is EventType.GOAL]
    assert [mo.event_id for mo in moments if mo.kind is MomentKind.GOAL] == goals
    reds = [e.event_id for e in m.events if e.type is EventType.CARD and e.outcome == "red"]
    assert [mo.event_id for mo in moments if mo.kind is MomentKind.RED_CARD] == reds
    assert moments[-1].kind is MomentKind.FULL_TIME
    assert len({mo.id for mo in moments}) == len(moments), "moment ids must be unique"


def test_red_card_story_shows_the_other_side_taking_over():
    m = shipped(RED_CARD)
    moments = detect_moments(m.events)
    red = next(mo for mo in moments if mo.kind is MomentKind.RED_CARD)
    after = [
        mo
        for mo in moments
        if red.timestamp_ms < mo.timestamp_ms <= red.timestamp_ms + 20 * 60_000
        and mo.kind in (MomentKind.PRESSURE_SURGE, MomentKind.MOMENTUM_SHIFT)
    ]
    assert any(mo.team is red.team.other for mo in after)


def test_late_winner_is_top_importance_in_stoppage_time():
    moments = detect_moments(shipped(LATE_WINNER).events)
    last_goal = [mo for mo in moments if mo.kind is MomentKind.GOAL][-1]
    assert last_goal.minute >= 90 and last_goal.importance == 1.0


# ------------------------------------------------------------------ snapshot


@pytest.mark.parametrize("name", [COMEBACK, RED_CARD, LATE_WINNER])
def test_snapshot_is_consistent_and_serialisable(name):
    m = shipped(name)
    snap = compute_snapshot(m.meta, m.events)
    assert (snap.score.home, snap.score.away) == (m.meta.final_score.home, m.meta.final_score.away)
    assert snap.home.possession + snap.away.possession == pytest.approx(1)
    passes = sum(e.type is EventType.PASS for e in m.events)
    assert snap.home.passing.attempted + snap.away.passing.attempted == passes
    assert snap.top_players and -1 <= snap.momentum <= 1
    assert type(snap).model_validate_json(snap.model_dump_json()) == snap


def test_snapshot_mid_match_reflects_only_events_so_far():
    m = shipped(COMEBACK)
    half = next(i for i, e in enumerate(m.events) if e.type is EventType.HALF_TIME) + 1
    snap = compute_snapshot(m.meta, m.events[:half])
    assert snap.period == 1
    assert (snap.score.home, snap.score.away) == (0, 2)  # Rovers trail at half time


def test_snapshot_rejects_empty_events():
    m = shipped(COMEBACK)
    with pytest.raises(ValueError):
        compute_snapshot(m.meta, [])


def test_natural_match_possession_is_believable():
    m = generate(2, Story.NONE)
    snap = compute_snapshot(m.meta, m.events)
    assert 0.3 <= snap.home.possession <= 0.7
