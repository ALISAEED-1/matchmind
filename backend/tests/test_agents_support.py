from functools import cache

import pytest

from matchmind.agents.facts import FactBuilder, display_minute, goal_effect
from matchmind.agents.templates import CARD_TYPE, TEMPLATES, render
from matchmind.agents.verifier import Verifier, allowed_numbers, numbers_in
from matchmind.cards import Audience, Language
from matchmind.generator import MATCHES_DIR
from matchmind.models import Match
from matchmind.stats import MomentKind, compute_snapshot, detect_moments

MATCHES = ["mm-0004-comeback", "mm-0003-red_card", "mm-0020-late_winner"]


@cache
def load(name: str) -> Match:
    return Match.load(MATCHES_DIR / f"{name}.json")


@cache
def moment_facts(name: str):
    """(moment, MomentFacts) for every moment, built from the snapshot at that moment."""
    m = load(name)
    fb = FactBuilder(m.meta)
    out = []
    for mo in detect_moments(m.events):
        events = [e for e in m.events if e.timestamp_ms <= mo.timestamp_ms]
        out.append((mo, fb.for_moment(mo, compute_snapshot(m.meta, events))))
    return out


def verifier_for(name: str) -> Verifier:
    m = load(name)
    return Verifier([p.name for c in (m.meta.home, m.meta.away) for p in c.players])


@pytest.mark.parametrize(
    "period, minute, shown",
    [
        (1, 0, "1'"),
        (1, 17, "18'"),
        (1, 44, "45'"),
        (1, 46, "45+2'"),
        (2, 45, "46'"),
        (2, 91, "90+2'"),
    ],
)
def test_display_minute(period, minute, shown):
    assert display_minute(period, minute) == shown


def test_goal_facts_carry_the_numbers_agents_may_quote():
    goal_mo, mf = next(
        (mo, mf) for mo, mf in moment_facts(MATCHES[0]) if mo.kind is MomentKind.GOAL
    )
    assert mf.facts["moment"] == "goal"
    assert mf.facts["score"] == mf.fields["score"]
    assert "xg" in mf.facts["details"]
    assert mf.fields["player"] and mf.fields["team"]
    assert "match_so_far" in mf.facts


@pytest.mark.parametrize("name", MATCHES)
def test_recap_facts_always_include_every_goal(name):
    m = load(name)
    moments = detect_moments(m.events)
    mf = FactBuilder(m.meta).for_recap(compute_snapshot(m.meta, m.events), moments)
    recap_goals = [x for x in mf.facts["key_moments"] if x["moment"] == "goal"]
    assert len(recap_goals) == m.meta.final_score.home + m.meta.final_score.away


def test_allowed_numbers_cover_common_spellings():
    allowed = allowed_numbers({"xg": 0.27, "score": "A 1-2 B", "minute": "90+2'", "poss": 57})
    for token in ["0.27", "27", "1", "2", "90", "57", "0.3"]:
        assert token in allowed
    assert "0.99" not in allowed
    assert numbers_in("xG ٠٫٢٧ و 57%") == ["0.27", "57"]


def test_verifier_flags_invented_numbers_players_script_and_length():
    v = verifier_for(MATCHES[0])
    facts = {"xg": 0.27, "score": "Rivermouth Rovers 1-2 Ironmere Athletic"}
    assert v.check_text({"body": "A 0.27 xG chance makes it 1-2."}, facts) == []
    assert any("0.81" in p for p in v.check_text({"body": "That was 0.81 xG."}, facts))

    league_outsider = next(iter(v.other_players))
    assert any(
        "not in this match" in p for p in v.check_text({"body": f"{league_outsider} scores"}, facts)
    )

    assert any("Urdu script" in p for p in v.check_text({"body": "This is English."}, facts, "ur"))
    assert v.check_text({"body": "Rivermouth Rovers نے گول کر دیا۔"}, facts, "ur") == []
    assert any("English only" in p for p in v.check_text({"body": "گول"}, facts, "en"))
    assert any("characters" in p for p in v.check_text({"title": "x" * 200}, facts))
    assert any("empty" in p for p in v.check_text({"title": ""}, facts))


def test_verifier_flags_invented_names():
    v = verifier_for(MATCHES[0])
    facts = {"score": "Rivermouth Rovers 1-2 Ironmere Athletic", "player": {"name": "Femi Okarie"}}
    assert (
        v.check_text({"body": "What a finish from Femi Okarie for Ironmere Athletic!"}, facts) == []
    )
    assert v.check_text({"body": "Unbelievable scenes! The Rovers keep pushing."}, facts) == []
    flagged = v.check_text({"body": "He's done it! A late winner from Smith."}, facts)
    assert any("Smith" in p for p in flagged)
    assert any("Smith" in p for p in v.check_text({"body": "Smith نے گول کیا"}, facts, "ur"))
    assert v.check_text({"body": "Femi Okarie نے گول کیا"}, facts, "ur") == []
    assert v.check_text({"title": "Missed Chance For Rivermouth Rovers"}, facts) == []
    assert (
        v.check_text({"body": "It lifts the Rovers' spirits and Ironmere's nerves."}, facts) == []
    )
    assert any(
        "Urdu script" in p for p in v.check_text({"title": "Rovers ka pehla hamla"}, facts, "ur")
    )


@pytest.mark.parametrize(
    "before, effect",
    [((0, 0), "opens the scoring"), ((1, 2), "equaliser"), ((1, 1), "takes the lead"),
     ((2, 0), "extends the lead"), ((0, 2), "pulls one back")],
)  # fmt: skip
def test_goal_effect(before, effect):
    assert goal_effect(*before)[0] == effect


def test_verifier_rejects_misreading_the_scoreline():
    v = verifier_for(MATCHES[0])
    _, equaliser_rules = goal_effect(1, 2)
    _, lead_rules = goal_effect(1, 1)
    facts = {"score": "Rivermouth Rovers 2-2 Ironmere Athletic"}
    bad = v.check_text(
        {"line": "Orbeza restores the Rovers lead!"}, facts, forbidden=equaliser_rules
    )
    assert any("equaliser" in p for p in bad)
    good = "Orbeza levels it at 2-2 and wipes out Ironmere's lead!"
    assert v.check_text({"line": good}, facts, forbidden=equaliser_rules) == []
    assert v.check_text({"line": "A late equaliser!"}, facts, forbidden=lead_rules)
    # Urdu/Arabic text is not pattern-checked (the rules are English phrases)
    assert v.check_text({"line": "گول"}, facts, "ur", forbidden=equaliser_rules) == []


def test_goal_facts_state_the_effect_in_words():
    for mo, mf in moment_facts(MATCHES[0]):
        if mo.kind is MomentKind.GOAL:
            effects = {"opens the scoring", "equaliser", "takes the lead", "extends the lead"}
            effects.add("pulls one back")
            assert mf.facts["details"]["goal_effect"].split(" (")[0] in effects
            assert "goal of the match" in mf.facts["details"]["scorer_goal_of_match"]


def test_every_moment_kind_has_a_template_and_card_type():
    for kind in MomentKind:
        assert kind.value in TEMPLATES, kind
        assert kind in CARD_TYPE, kind
        for lang in Language:
            assert Audience.FAN in TEMPLATES[kind.value][lang]
            assert Audience.ANALYST in TEMPLATES[kind.value][lang]


@pytest.mark.parametrize("name", MATCHES)
def test_templates_render_cleanly_and_pass_the_verifier(name):
    """Template cards are the last line of defence, so they must always be valid."""
    v = verifier_for(name)
    for mo, mf in moment_facts(name):
        for lang in Language:
            for aud in (Audience.FAN, Audience.ANALYST):
                title, body, why = render(mo.kind, lang, aud, mf.fields)
                text = f"{title} {body} {why or ''}"
                assert "{" not in text and "}" not in text, (mo.kind, lang, aud, text)
                problems = v.check_text(
                    {"title": title, "body": body, "why_it_matters": why}, mf.facts, lang.value
                )
                assert problems == [], (mo.kind, lang, aud, text, problems)
