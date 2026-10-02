"""The orchestrator: a Microsoft Agent Framework workflow over a shared MatchState.

Workflow graph (one run per replay window):

    Window --> [stats_agent] --MomentTask--> [producer] --+--(full / insight)--> [insight_agent]
                                                         +--(recap)----------> [narrator_agent]
                                                         +--(template)-------> [template_writer]

    [insight_agent] --+--(full)----> [narrator_agent] --> [personalizer_agent] --> [publisher]
                      +--(insight)-------------------------^
    [template_writer] --------------------------------------------------------> [publisher]

* stats_agent    : ingests events, calls the stats MCP server, detects new moments, builds FACTS.
* producer       : routes each moment by importance; trips a circuit breaker when the
                   LLM chain keeps failing, so the broadcast degrades to templates
                   instead of stalling.
* insight_agent  : explains why the moment matters (LLM, verified).
* narrator_agent : live commentary line, and the full-time recap (LLM, verified).
* personalizer   : fan/analyst variants in each language (LLM, verified).
* template_writer: deterministic cards for low-importance moments.
* publisher      : writes cards to MatchState and emits them as workflow output.

Every hand-off, retry, provider fallback and template fallback is recorded in
MatchState.handoffs for the debug drawer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Never

from agent_framework import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler

from matchmind.agents.facts import FactBuilder, MomentFacts, display_minute
from matchmind.agents.llm_agents import (
    CommentaryOut,
    InsightAgent,
    InsightOut,
    NarratorAgent,
    PersonalizerAgent,
    RecapOut,
    ViewerProfile,
)
from matchmind.agents.stats_source import StatsSource
from matchmind.agents.templates import CARD_TYPE, render
from matchmind.agents.verifier import Verifier
from matchmind.cards import Audience, CardType, Language, OverlayCard
from matchmind.llm.gateway import AllProvidersFailed, Attempt, AttemptOutcome, LLMGateway
from matchmind.models import Event
from matchmind.state import HandoffStatus, MatchState
from matchmind.stats import MatchSnapshot, Moment, MomentKind

# ------------------------------------------------------------------ config


@dataclass(frozen=True)
class PipelineConfig:
    languages: tuple[Language, ...] = (Language.EN,)
    audiences: tuple[Audience, ...] = (Audience.FAN, Audience.ANALYST)
    profile: ViewerProfile | None = None  # live mode: personalize for this viewer
    full_threshold: float = 0.6  # insight + commentary + personalization
    insight_threshold: float = 0.45  # insight + personalization
    llm_enabled: bool = True
    breaker_failures: int = 3  # consecutive all-provider failures before degrading
    breaker_cooldown_moments: int = 6  # template-only moments before trying the LLM again

    @property
    def targets(self) -> list[tuple[Language, Audience]]:
        return [(lang, aud) for lang in self.languages for aud in self.audiences]


# ---------------------------------------------------------------- messages


@dataclass
class Window:
    events: list[Event]


class Route(StrEnum):
    FULL = "full"
    INSIGHT = "insight"
    TEMPLATE = "template"
    RECAP = "recap"


@dataclass
class MomentTask:
    moment: Moment
    facts: MomentFacts
    route: Route = Route.TEMPLATE
    reason: str = ""


@dataclass
class Draft:
    task: MomentTask
    insight: InsightOut | None = None
    commentary: CommentaryOut | None = None
    recap: RecapOut | None = None
    providers: dict[str, str] = field(default_factory=dict)  # agent -> provider used
    fallback: bool = False  # an LLM step failed and a template was used


@dataclass
class CardBatch:
    cards: list[OverlayCard]


# --------------------------------------------------------------- helpers

STATUS_FOR = {
    AttemptOutcome.OK: HandoffStatus.OK,
    AttemptOutcome.CACHED: HandoffStatus.CACHED,
    AttemptOutcome.INVALID_OUTPUT: HandoffStatus.RETRY,
    AttemptOutcome.REJECTED: HandoffStatus.RETRY,
    AttemptOutcome.TRANSIENT_ERROR: HandoffStatus.PROVIDER_FALLBACK,
    AttemptOutcome.PROVIDER_ERROR: HandoffStatus.PROVIDER_FALLBACK,
}


def attempt_logger(state: MatchState, agent: str, moment: Moment) -> Callable[[Attempt], None]:
    """Turn gateway attempts into handoff-log entries between the agent and the verifier/model."""

    def log(a: Attempt) -> None:
        verifying = a.outcome in (AttemptOutcome.OK, AttemptOutcome.REJECTED)
        state.log(
            agent,
            "verifier" if verifying else a.provider,
            moment_id=moment.id,
            status=STATUS_FOR[a.outcome],
            detail=a.outcome.value + (f": {a.detail}" if a.detail else ""),
            provider=a.provider,
            latency_ms=a.latency_ms,
            match_ms=moment.timestamp_ms,
        )
        state.counters[f"llm_{a.outcome.value}"] += 1

    return log


def _duration(importance: float) -> int:
    return int(6000 + 6000 * min(1.0, importance))


def _scalar_data(moment: Moment) -> dict[str, float | int | str | bool]:
    data = {k: v for k, v in moment.data.items() if isinstance(v, int | float | str | bool)}
    data["importance"] = moment.importance
    return data


# --------------------------------------------------------------- executors


class StatsAgentExecutor(Executor):
    """Ingest + interpret: no LLM. Talks to the stats engine through the MCP server."""

    def __init__(self, state: MatchState, source: StatsSource, builder: FactBuilder):
        super().__init__(id="stats_agent")
        self.state, self.source, self.builder = state, source, builder

    @handler
    async def on_window(self, window: Window, ctx: WorkflowContext[MomentTask]) -> None:
        state = self.state
        state.ingest(window.events)
        until = state.clock_ms
        state.log("replayer", "stats_agent", detail=f"{len(window.events)} events")

        snapshot: MatchSnapshot = await self.source.snapshot(until)
        state.snapshot = snapshot
        new = state.add_moments(await self.source.moments(until))
        state.log(
            "stats_agent",
            f"mcp:{self.source.name}",
            detail=f"snapshot + moments at {display_minute(snapshot.period, snapshot.minute)}",
        )
        for moment in new:
            facts = (
                self.builder.for_recap(snapshot, list(state.moments.values()))
                if moment.kind is MomentKind.FULL_TIME
                else self.builder.for_moment(moment, snapshot)
            )
            state.log(
                "stats_agent",
                "producer",
                moment_id=moment.id,
                detail=f"{moment.kind.value} (importance {moment.importance:.2f})",
                match_ms=moment.timestamp_ms,
            )
            await ctx.send_message(MomentTask(moment, facts))


class ProducerExecutor(Executor):
    """Decides how much of the agent team each moment deserves."""

    def __init__(self, state: MatchState, config: PipelineConfig):
        super().__init__(id="producer")
        self.state, self.config = state, config
        self.cooldown_left = 0

    def route(self, moment: Moment) -> tuple[Route, str]:
        cfg, counters = self.config, self.state.counters
        if not cfg.llm_enabled:
            return Route.TEMPLATE, "LLM disabled"
        if moment.kind is MomentKind.FULL_TIME:
            return Route.RECAP, "full time: recap"
        if moment.importance < cfg.insight_threshold:
            return Route.TEMPLATE, f"importance {moment.importance:.2f} < {cfg.insight_threshold}"

        if counters["consecutive_llm_failures"] >= cfg.breaker_failures and self.cooldown_left == 0:
            self.cooldown_left = cfg.breaker_cooldown_moments
            counters["consecutive_llm_failures"] = 0
            counters["breaker_trips"] += 1
        if self.cooldown_left > 0 and moment.importance < 0.9:
            self.cooldown_left -= 1
            return (
                Route.TEMPLATE,
                f"circuit breaker open ({self.cooldown_left} left): LLM chain failing",
            )

        if moment.importance >= cfg.full_threshold:
            return Route.FULL, f"importance {moment.importance:.2f} >= {cfg.full_threshold}"
        return Route.INSIGHT, f"importance {moment.importance:.2f} >= {cfg.insight_threshold}"

    @handler
    async def on_task(self, task: MomentTask, ctx: WorkflowContext[MomentTask]) -> None:
        task.route, task.reason = self.route(task.moment)
        target = {
            Route.FULL: "insight_agent",
            Route.INSIGHT: "insight_agent",
            Route.RECAP: "narrator_agent",
            Route.TEMPLATE: "template_writer",
        }[task.route]
        self.state.counters[f"route_{task.route.value}"] += 1
        self.state.log(
            "producer",
            target,
            moment_id=task.moment.id,
            detail=f"route={task.route.value}: {task.reason}",
            match_ms=task.moment.timestamp_ms,
            status=HandoffStatus.SKIPPED if task.route is Route.TEMPLATE else HandoffStatus.OK,
        )
        await ctx.send_message(task)


class InsightExecutor(Executor):
    def __init__(self, state: MatchState, agent: InsightAgent):
        super().__init__(id="insight_agent")
        self.state, self.agent = state, agent

    @handler
    async def on_task(self, task: MomentTask, ctx: WorkflowContext[Draft]) -> None:
        draft = Draft(task)
        log = attempt_logger(self.state, self.agent.name, task.moment)
        try:
            result = await self.agent.run(task.facts, on_attempt=log)
            draft.insight, draft.providers[self.agent.name] = result.value, result.provider
            self.state.counters["consecutive_llm_failures"] = 0
        except AllProvidersFailed as exc:
            draft.fallback = True
            self.state.counters["consecutive_llm_failures"] += 1
            self.state.log(
                self.agent.name,
                "template_writer",
                moment_id=task.moment.id,
                status=HandoffStatus.FALLBACK,
                detail=f"all providers failed ({len(exc.attempts)} attempts); using template",
                match_ms=task.moment.timestamp_ms,
            )
        next_agent = "narrator_agent" if task.route is Route.FULL else "personalizer_agent"
        self.state.log(
            self.agent.name, next_agent, moment_id=task.moment.id, match_ms=task.moment.timestamp_ms
        )
        await ctx.send_message(draft)


class NarratorExecutor(Executor):
    def __init__(self, state: MatchState, agent: NarratorAgent):
        super().__init__(id="narrator_agent")
        self.state, self.agent = state, agent

    @handler
    async def on_draft(self, draft: Draft, ctx: WorkflowContext[Draft]) -> None:
        moment = draft.task.moment
        if not draft.fallback:  # don't hammer a chain that just failed
            log = attempt_logger(self.state, self.agent.name, moment)
            try:
                result = await self.agent.commentate(
                    draft.task.facts, draft.insight, on_attempt=log
                )
                draft.commentary, draft.providers[self.agent.name] = result.value, result.provider
            except AllProvidersFailed:
                self.state.log(
                    self.agent.name, "personalizer_agent", moment_id=moment.id,
                    status=HandoffStatus.FALLBACK, detail="no commentary: all providers failed",
                    match_ms=moment.timestamp_ms,
                )  # fmt: skip
        self.state.log(
            self.agent.name, "personalizer_agent", moment_id=moment.id, match_ms=moment.timestamp_ms
        )
        await ctx.send_message(draft)

    @handler
    async def on_recap(self, task: MomentTask, ctx: WorkflowContext[Draft]) -> None:
        draft = Draft(task)
        log = attempt_logger(self.state, self.agent.name, task.moment)
        try:
            result = await self.agent.recap(task.facts, on_attempt=log)
            draft.recap, draft.providers[self.agent.name] = result.value, result.provider
        except AllProvidersFailed:
            draft.fallback = True
            self.state.log(
                self.agent.name, "template_writer", moment_id=task.moment.id,
                status=HandoffStatus.FALLBACK, detail="recap: all providers failed; using template",
                match_ms=task.moment.timestamp_ms,
            )  # fmt: skip
        self.state.recap = draft.recap
        self.state.log(
            self.agent.name,
            "personalizer_agent",
            moment_id=task.moment.id,
            match_ms=task.moment.timestamp_ms,
        )
        await ctx.send_message(draft)


class CardFactory:
    """Builds OverlayCards for a moment from LLM text or templates."""

    def __init__(self, config: PipelineConfig):
        self.config = config

    def card(
        self,
        moment: Moment,
        language: Language,
        audience: Audience,
        title: str,
        body: str,
        why: str | None,
        *,
        source_agent: str,
        provider: str | None,
        fallback: bool,
        card_type: CardType | None = None,
        offset_ms: int = 1500,
        suffix: str = "",
    ) -> OverlayCard:
        ctype = card_type or CARD_TYPE[moment.kind]
        group = moment.id + suffix
        return OverlayCard(
            id=f"{group}:{language.value}:{audience.value}",
            group_id=group,
            moment_id=moment.id,
            match_minute=moment.minute,
            period=moment.period,
            display_at_ms=moment.timestamp_ms + offset_ms,
            duration_ms=_duration(moment.importance),
            type=ctype,
            audience=audience,
            language=language,
            title=title,
            body=body,
            why_it_matters=why or None,
            data=_scalar_data(moment),
            team=moment.team,
            player_id=moment.player_id,
            importance=moment.importance,
            source_agent=source_agent,
            provider=provider,
            fallback_used=fallback,
        )

    def templates(
        self,
        task: MomentTask,
        targets: list[tuple[Language, Audience]],
        *,
        fallback: bool,
        source_agent: str = "template_writer",
    ) -> list[OverlayCard]:
        out = []
        for lang, aud in targets:
            title, body, why = render(task.moment.kind, lang, aud, task.facts.fields)
            out.append(
                self.card(
                    task.moment,
                    lang,
                    aud,
                    title,
                    body,
                    why,
                    source_agent=source_agent,
                    provider=None,
                    fallback=fallback,
                )  # fmt: skip
            )
        return out


class PersonalizerExecutor(Executor):
    def __init__(self, state: MatchState, agent: PersonalizerAgent, config: PipelineConfig):
        super().__init__(id="personalizer_agent")
        self.state, self.agent, self.config = state, agent, config
        self.factory = CardFactory(config)

    def _base(self, draft: Draft) -> tuple[str, str, str | None, str, str | None]:
        """(title, body, why, source_agent, provider) of the card to personalize."""
        if draft.recap is not None:
            r = draft.recap
            return (
                r.headline,
                r.summary,
                None,
                "narrator_agent",
                draft.providers.get("narrator_agent"),
            )
        if draft.insight is not None:
            i = draft.insight
            return (
                i.title,
                i.explanation,
                i.why_it_matters,
                "insight_agent",
                draft.providers.get("insight_agent"),
            )
        title, body, why = render(
            draft.task.moment.kind, Language.EN, Audience.ANALYST, draft.task.facts.fields
        )
        return title, body, why, "template_writer", None

    @handler
    async def on_draft(self, draft: Draft, ctx: WorkflowContext[CardBatch]) -> None:
        task, moment = draft.task, draft.task.moment
        targets = self.config.targets
        title, body, why, source, provider = self._base(draft)
        cards: list[OverlayCard] = []

        if draft.fallback:
            cards += self.factory.templates(task, targets, fallback=True)
        else:
            # One request per language: smaller answers are faster and more reliable, and a
            # failure in one language only costs that language (it falls back to templates).
            log = attempt_logger(self.state, self.agent.name, moment)
            for lang in self.config.languages:
                lang_targets = [t for t in targets if t[0] is lang]
                try:
                    result = await self.agent.run(
                        task.facts, title, body, why, lang_targets, self.config.profile,
                        on_attempt=log,
                    )  # fmt: skip
                except AllProvidersFailed:
                    self.state.counters["consecutive_llm_failures"] += 1
                    self.state.log(
                        self.agent.name, "template_writer", moment_id=moment.id,
                        status=HandoffStatus.FALLBACK,
                        detail=f"{lang.value}: all providers failed; using templates",
                        match_ms=moment.timestamp_ms,
                    )  # fmt: skip
                    cards += self.factory.templates(task, lang_targets, fallback=True)
                    continue
                self.state.counters["consecutive_llm_failures"] = 0
                wanted = set(lang_targets)
                for v in result.value.variants:
                    if (v.language, v.audience) in wanted:
                        wanted.discard((v.language, v.audience))
                        cards.append(
                            self.factory.card(
                                moment,
                                v.language,
                                v.audience,
                                v.title,
                                v.body,
                                v.why_it_matters,
                                source_agent=f"{source}+personalizer_agent",
                                provider=result.provider,
                                fallback=False,
                                card_type=CardType.RECAP if draft.recap else None,
                            )  # fmt: skip
                        )

        if draft.commentary is not None:
            cards.append(
                self.factory.card(
                    moment,
                    Language.EN,
                    Audience.FAN,
                    title,
                    draft.commentary.line,
                    None,
                    source_agent="narrator_agent",
                    provider=draft.providers.get("narrator_agent"),
                    fallback=False,
                    card_type=CardType.COMMENTARY,
                    offset_ms=4500,
                    suffix=":commentary",
                )  # fmt: skip
            )
        self.state.log(
            self.agent.name, "publisher", moment_id=moment.id,
            detail=f"{len(cards)} cards", match_ms=moment.timestamp_ms,
        )  # fmt: skip
        await ctx.send_message(CardBatch(cards))


class TemplateExecutor(Executor):
    def __init__(self, state: MatchState, config: PipelineConfig):
        super().__init__(id="template_writer")
        self.state, self.config = state, config
        self.factory = CardFactory(config)

    @handler
    async def on_task(self, task: MomentTask, ctx: WorkflowContext[CardBatch]) -> None:
        cards = self.factory.templates(task, self.config.targets, fallback=False)
        self.state.log(
            "template_writer", "publisher", moment_id=task.moment.id,
            detail=f"{len(cards)} cards", match_ms=task.moment.timestamp_ms,
        )  # fmt: skip
        await ctx.send_message(CardBatch(cards))


class PublisherExecutor(Executor):
    def __init__(self, state: MatchState):
        super().__init__(id="publisher")
        self.state = state

    @handler
    async def on_cards(self, batch: CardBatch, ctx: WorkflowContext[Never, CardBatch]) -> None:
        self.state.add_cards(batch.cards)
        await ctx.yield_output(batch)


# ------------------------------------------------------------ orchestrator


class MatchOrchestrator:
    """Owns the MatchState, the agents and the workflow for one match."""

    def __init__(
        self,
        state: MatchState,
        gateway: LLMGateway,
        source: StatsSource,
        config: PipelineConfig | None = None,
    ):
        self.state = state
        self.config = config or PipelineConfig()
        builder = FactBuilder(state.meta)
        players = [p.name for c in (state.meta.home, state.meta.away) for p in c.players]
        verifier = Verifier(players)

        stats = StatsAgentExecutor(state, source, builder)
        producer = ProducerExecutor(state, self.config)
        insight = InsightExecutor(state, InsightAgent(gateway, verifier))
        narrator = NarratorExecutor(state, NarratorAgent(gateway, verifier))
        personalizer = PersonalizerExecutor(
            state, PersonalizerAgent(gateway, verifier), self.config
        )
        template = TemplateExecutor(state, self.config)
        publisher = PublisherExecutor(state)

        self.workflow = (
            WorkflowBuilder(
                name="matchmind-broadcast", start_executor=stats, output_from=[publisher]
            )
            .add_edge(stats, producer)
            .add_switch_case_edge_group(
                producer,
                [
                    Case(lambda t: t.route in (Route.FULL, Route.INSIGHT), insight),
                    Case(lambda t: t.route is Route.RECAP, narrator),
                    Default(template),
                ],
            )
            .add_switch_case_edge_group(
                insight,
                [Case(lambda d: d.task.route is Route.FULL, narrator), Default(personalizer)],
            )
            .add_edge(narrator, personalizer)
            .add_edge(personalizer, publisher)
            .add_edge(template, publisher)
            .build()
        )

    async def process(self, window: list[Event]) -> list[OverlayCard]:
        """Run the workflow on one replay window; return the cards it published."""
        result = await self.workflow.run(Window(window))
        return [c for batch in result.get_outputs() for c in batch.cards]
