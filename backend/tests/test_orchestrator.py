import asyncio
import json
from functools import cache

from matchmind.agents.llm_agents import (
    CommentaryOut,
    InsightOut,
    PersonalizedOut,
    RecapOut,
    Variant,
)
from matchmind.agents.orchestrator import MatchOrchestrator, PipelineConfig
from matchmind.agents.stats_source import LocalStatsSource, MCPStatsSource
from matchmind.cards import Audience, CardType, Language
from matchmind.generator import MATCHES_DIR
from matchmind.llm.gateway import LLMGateway
from matchmind.models import Match
from matchmind.replay import batches
from matchmind.state import HandoffStatus, MatchState
from matchmind.stats import MomentKind

MATCH_ID = "mm-0004-comeback"
TEXT = {
    Language.EN: ("Big moment", "Something important just happened."),
    Language.UR: ("اہم لمحہ", "میچ کا ایک اہم لمحہ۔"),
    Language.AR: ("لحظة مهمة", "لحظة مهمة في المباراة."),
}


class FakeLLM:
    """Schema-aware fake model. Can be told to fail or to slip a bad number in first."""

    name = "fake:model"

    def __init__(self, outage: bool = False, bad_number_first: bool = False):
        self.outage = outage
        self.bad_number_first = bad_number_first
        self.calls: list[str] = []

    async def complete(self, agent_name, instructions, prompt, schema):
        self.calls.append(agent_name)
        if self.outage:
            raise RuntimeError("Error code: 503 - high demand")
        if schema is InsightOut:
            if self.bad_number_first and self.calls.count(agent_name) == 1:
                return InsightOut(
                    title="Huge", explanation="That chance was 0.99 xG.", why_it_matters="Big."
                )
            return InsightOut(
                title="Key moment",
                explanation="A big moment.",
                why_it_matters="It shifts the game.",
            )
        if schema is CommentaryOut:
            return CommentaryOut(line="What a moment in this match!", tone="excited")
        if schema is RecapOut:
            return RecapOut(
                headline="What a match",
                summary="A thrilling game.",
                turning_points=["1' a", "2' b", "3' c"],
            )
        if schema is PersonalizedOut:
            request = json.loads(prompt.split("REQUEST:\n", 1)[1])
            variants = []
            for want in request["produce_exactly"]:
                lang, aud = Language(want["language"]), Audience(want["audience"])
                title, body = TEXT[lang]
                variants.append(Variant(language=lang, audience=aud, title=title, body=body))
            return PersonalizedOut(variants=variants)
        raise AssertionError(schema)


async def _no_sleep(_s: float) -> None:
    return None


@cache
def load() -> Match:
    return Match.load(MATCHES_DIR / f"{MATCH_ID}.json")


def run_pipeline(
    llm: FakeLLM, minutes: int | None = 25, config: PipelineConfig | None = None, mcp=False
):
    match = load()
    events = [e for e in match.events if minutes is None or e.timestamp_ms < minutes * 60_000]
    state = MatchState(meta=match.meta)
    gateway = LLMGateway([llm], sleep=_no_sleep)

    async def go():
        if mcp:
            async with MCPStatsSource(MATCH_ID) as source:
                orch = MatchOrchestrator(state, gateway, source, config)
                for b in batches(events):
                    await orch.process(b)
        else:
            orch = MatchOrchestrator(
                state, gateway, LocalStatsSource(match.meta, state.events), config
            )
            for b in batches(events):
                await orch.process(b)

    asyncio.run(go())
    return state


def pairs(state: MatchState) -> set[tuple[str, str]]:
    return {(h.source, h.target) for h in state.handoffs}


BILINGUAL = PipelineConfig(languages=(Language.EN, Language.UR))


def test_every_moment_gets_cards_for_every_target_and_routing_is_visible():
    state = run_pipeline(FakeLLM(), config=BILINGUAL)
    targets = set(BILINGUAL.targets)
    assert state.moments
    for moment in state.moments.values():
        cards = [c for c in state.cards if c.group_id == moment.id]
        assert {(c.language, c.audience) for c in cards} == targets, moment.id
        assert all(c.display_at_ms >= moment.timestamp_ms for c in cards)
        llm_routed = moment.importance >= BILINGUAL.insight_threshold
        assert all(("personalizer_agent" in c.source_agent) == llm_routed for c in cards), moment.id

    assert {
        ("replayer", "stats_agent"),
        ("stats_agent", "producer"),
        ("producer", "insight_agent"),
        ("insight_agent", "verifier"),
        ("insight_agent", "narrator_agent"),
        ("narrator_agent", "personalizer_agent"),
        ("personalizer_agent", "publisher"),
        ("producer", "template_writer"),
        ("template_writer", "publisher"),
    } <= pairs(state)

    commentary = [c for c in state.cards if c.type is CardType.COMMENTARY]
    full = [m for m in state.moments.values() if m.importance >= BILINGUAL.full_threshold]
    assert len(commentary) == len(full) > 0
    assert not any(c.fallback_used for c in state.cards)


def test_verifier_rejection_is_retried_and_logged():
    state = run_pipeline(FakeLLM(bad_number_first=True), minutes=20)
    retries = [h for h in state.handoffs if h.status is HandoffStatus.RETRY]
    assert retries and "0.99" in retries[0].detail
    assert not any("0.99" in (c.body + (c.why_it_matters or "")) for c in state.cards)


def test_total_outage_degrades_to_templates_and_trips_the_breaker():
    llm = FakeLLM(outage=True)
    state = run_pipeline(llm)
    assert state.cards and all(c.source_agent == "template_writer" for c in state.cards)
    llm_routed = [m for m in state.moments.values() if m.importance >= 0.45]
    fell_back = {c.group_id for c in state.cards if c.fallback_used}
    assert fell_back and fell_back <= {m.id for m in llm_routed}
    assert state.counters["breaker_trips"] >= 1
    assert any("circuit breaker" in h.detail for h in state.handoffs)
    assert any(h.status is HandoffStatus.FALLBACK for h in state.handoffs)
    # the breaker saves calls: fewer LLM attempts than LLM-routed moments x 2 retries
    assert len(llm.calls) < 2 * len(llm_routed)


def test_full_match_ends_with_a_recap():
    state = run_pipeline(FakeLLM(), minutes=None, config=PipelineConfig(audiences=(Audience.FAN,)))
    recap = [c for c in state.cards if c.type is CardType.RECAP]
    assert recap and recap[0].title == "Big moment"
    assert state.recap is not None and state.recap.headline == "What a match"
    goals = [m for m in state.moments.values() if m.kind is MomentKind.GOAL]
    assert len(goals) == 5


def test_stats_agent_works_through_the_mcp_server():
    state = run_pipeline(FakeLLM(), minutes=8, mcp=True)
    assert ("stats_agent", "mcp:mcp") in pairs(state)
    assert state.cards
