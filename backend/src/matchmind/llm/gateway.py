"""LLM gateway: structured output with retries, provider fallback and caching.

Every LLM agent calls `LLMGateway.generate(...)`, which:

1. returns a cached answer if this exact request succeeded before;
2. calls the first provider in the chain through an Agent Framework `Agent`
   with `response_format=<Pydantic model>` (structured output);
3. on malformed or schema-invalid JSON, or when the caller's `check` finds
   problems (the Verifier), retries the same provider with that feedback;
4. on rate limits (429), overload (503), timeouts or connection errors,
   backs off and retries, then falls through to the next provider;
5. raises `AllProvidersFailed` when the chain is exhausted, so the caller can
   use its deterministic template instead.

Every attempt is reported through `on_attempt`, which the orchestrator turns
into handoff-log entries for the debug drawer.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from matchmind.config import ProviderSpec, Settings

T = TypeVar("T", bound=BaseModel)


class AttemptOutcome(StrEnum):
    OK = "ok"
    CACHED = "cached"
    INVALID_OUTPUT = "invalid_output"  # bad JSON / schema mismatch -> retry same provider
    REJECTED = "rejected"  # verifier found problems -> retry same provider with feedback
    TRANSIENT_ERROR = "transient_error"  # 429/503/timeout -> back off, retry, then next provider
    PROVIDER_ERROR = "provider_error"  # anything else -> next provider


@dataclass(frozen=True)
class Attempt:
    provider: str
    outcome: AttemptOutcome
    detail: str = ""
    latency_ms: int = 0


@dataclass
class LLMResult[T: BaseModel]:
    value: T
    provider: str
    attempts: list[Attempt] = field(default_factory=list)
    cached: bool = False


class AllProvidersFailed(RuntimeError):
    def __init__(self, attempts: list[Attempt]):
        self.attempts = attempts
        last = attempts[-1] if attempts else None
        super().__init__(
            f"All LLM providers failed after {len(attempts)} attempts"
            + (f"; last: {last.provider} {last.outcome.value} {last.detail}" if last else "")
        )


class InvalidOutput(ValueError):
    """The model answered, but not with usable JSON for the schema."""


class Provider(Protocol):
    name: str

    async def complete(
        self, agent_name: str, instructions: str, prompt: str, schema: type[T]
    ) -> T: ...


# ---------------------------------------------------------------- providers


class AgentFrameworkProvider:
    """A provider backed by an Agent Framework chat client, created lazily.

    Lazy creation matters for Foundry Local: loading the model takes ~20 s, so
    we only pay it if the chain actually falls through to the local model.
    """

    def __init__(self, spec: ProviderSpec, settings: Settings):
        self.spec = spec
        self.name = spec.name
        self.settings = settings
        self._client = None
        self._agents: dict[tuple[str, str], object] = {}

    def _agent(self, agent_name: str, instructions: str):
        from agent_framework import Agent

        from matchmind.llm.client import make_chat_client

        if self._client is None:
            self._client = make_chat_client(self.spec, self.settings)
        key = (agent_name, instructions)
        if key not in self._agents:
            self._agents[key] = Agent(self._client, instructions=instructions, name=agent_name)
        return self._agents[key]

    async def complete(self, agent_name: str, instructions: str, prompt: str, schema: type[T]) -> T:
        agent = self._agent(agent_name, instructions)
        response = await asyncio.wait_for(
            agent.run(prompt, options={"response_format": schema, "temperature": 0.6}),
            timeout=self.settings.llm_timeout_s,
        )
        try:
            value = response.value
        except (ValidationError, ValueError) as exc:
            raise InvalidOutput(f"schema mismatch: {_short(exc)}") from exc
        if value is None:
            value = parse_json_output(response.text or "", schema)
        return value


def parse_json_output[T: BaseModel](text: str, schema: type[T]) -> T:
    """Parse model text into `schema`, tolerating ```json fences and surrounding prose."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise InvalidOutput("no JSON object in the answer")
    try:
        return schema.model_validate_json(cleaned[start : end + 1])
    except ValidationError as exc:
        raise InvalidOutput(f"schema mismatch: {_short(exc)}") from exc


def _short(exc: BaseException, limit: int = 160) -> str:
    text = " ".join(str(exc).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


_TRANSIENT_MARKERS = (
    "429",
    "rate limit",
    "ratelimit",
    "resource_exhausted",
    "quota",
    "503",
    "unavailable",
    "overloaded",
    "high demand",
    "timeout",
    "timed out",
    "connection",
    "502",
    "504",
)


def classify(exc: BaseException) -> AttemptOutcome:
    if isinstance(exc, InvalidOutput):
        return AttemptOutcome.INVALID_OUTPUT
    if isinstance(exc, asyncio.TimeoutError | TimeoutError | ConnectionError):
        return AttemptOutcome.TRANSIENT_ERROR
    chain, cur = [], exc
    while cur is not None and len(chain) < 6:
        chain.append(cur)
        cur = cur.__cause__ or cur.__context__
    text = " ".join(f"{type(e).__name__} {e}" for e in chain).lower()
    if any(m in text for m in _TRANSIENT_MARKERS):
        return AttemptOutcome.TRANSIENT_ERROR
    return AttemptOutcome.PROVIDER_ERROR


# -------------------------------------------------------------------- cache


class ResponseCache:
    """On-disk cache of validated answers, keyed by agent + instructions + prompt + schema."""

    def __init__(self, root: Path):
        self.root = root

    @staticmethod
    def key(agent_name: str, instructions: str, prompt: str, schema: type[BaseModel]) -> str:
        blob = json.dumps([agent_name, instructions, prompt, schema.__name__], ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:32]

    def _path(self, agent_name: str, key: str) -> Path:
        return self.root / agent_name / f"{key}.json"

    def get(self, agent_name: str, key: str, schema: type[T]) -> tuple[T, str] | None:
        path = self._path(agent_name, key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return schema.model_validate(data["value"]), data["provider"]

    def put(self, agent_name: str, key: str, value: BaseModel, provider: str) -> None:
        path = self._path(agent_name, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"provider": provider, "value": value.model_dump(mode="json")}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ gateway

Check = Callable[[BaseModel], list[str]]
OnAttempt = Callable[[Attempt], None]


class LLMGateway:
    def __init__(
        self,
        providers: list[Provider],
        cache: ResponseCache | None = None,
        *,
        max_invalid_retries: int = 1,
        max_transient_retries: int = 1,
        backoff_s: float = 10.0,
        min_interval_s: dict[str, float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if not providers:
            raise ValueError("at least one provider is required")
        self.providers = providers
        self.cache = cache
        self.max_invalid_retries = max_invalid_retries
        self.max_transient_retries = max_transient_retries
        self.backoff_s = backoff_s
        self._sleep = sleep
        # A provider that just failed transiently is skipped for a cool-down period,
        # so one overloaded model doesn't cost a timeout on every call.
        self._cooldown_until: dict[str, float] = {}
        self.cooldown_s = 60.0
        # Client-side pacing (requests-per-minute quotas): minimum gap between calls.
        self.min_interval_s = min_interval_s or {}
        self._next_slot: dict[str, float] = {}
        self._pace_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Settings, cache: ResponseCache | None = None) -> LLMGateway:
        pacing = {
            s.name: 60.0 / settings.gemini_rpm
            for s in settings.chain
            if s.kind == "gemini" and settings.gemini_rpm > 0
        }
        return cls(
            [AgentFrameworkProvider(s, settings) for s in settings.chain],
            cache,
            min_interval_s=pacing,
        )

    async def _pace(self, name: str) -> None:
        gap = self.min_interval_s.get(name, 0.0)
        if gap <= 0:
            return
        async with self._pace_lock:
            now = time.monotonic()
            slot = max(now, self._next_slot.get(name, 0.0))
            self._next_slot[name] = slot + gap
        if slot > now:
            await self._sleep(slot - now)

    async def generate(
        self,
        *,
        agent_name: str,
        instructions: str,
        prompt: str,
        schema: type[T],
        check: Check | None = None,
        on_attempt: OnAttempt | None = None,
        skip_provider: Callable[[str], bool] | None = None,
        invalid_retries: int | None = None,
    ) -> LLMResult[T]:
        """`skip_provider(name)` excludes providers unsuited to this request (e.g. a small
        local model for Urdu); `invalid_retries` overrides the corrective-retry budget."""
        attempts: list[Attempt] = []

        def record(a: Attempt) -> None:
            attempts.append(a)
            if on_attempt:
                on_attempt(a)

        key = ResponseCache.key(agent_name, instructions, prompt, schema)
        if self.cache and (hit := self.cache.get(agent_name, key, schema)):
            value, provider = hit
            if not check or not check(value):
                record(Attempt(provider, AttemptOutcome.CACHED))
                return LLMResult(value, provider, attempts, cached=True)

        now = time.monotonic()
        usable = [p for p in self.providers if not (skip_provider and skip_provider(p.name))]
        ordered = [p for p in usable if self._cooldown_until.get(p.name, 0) <= now]
        ordered += [p for p in usable if p not in ordered]  # cooling ones last, not never

        for provider in ordered:
            feedback: list[str] = []
            invalid_left = self.max_invalid_retries if invalid_retries is None else invalid_retries
            transient_left = self.max_transient_retries
            while True:
                full_prompt = prompt if not feedback else _with_feedback(prompt, feedback)
                await self._pace(provider.name)
                started = time.perf_counter()
                try:
                    value = await provider.complete(agent_name, instructions, full_prompt, schema)
                except Exception as exc:  # noqa: BLE001 - classified below
                    outcome = classify(exc)
                    record(Attempt(provider.name, outcome, _short(exc), _ms(started)))
                    if outcome is AttemptOutcome.INVALID_OUTPUT and invalid_left > 0:
                        invalid_left -= 1
                        feedback = ["Your answer was not valid JSON for the required schema."]
                        continue
                    if outcome is AttemptOutcome.TRANSIENT_ERROR and transient_left > 0:
                        transient_left -= 1
                        await self._sleep(self.backoff_s)
                        continue
                    if outcome is AttemptOutcome.TRANSIENT_ERROR:
                        self._cooldown_until[provider.name] = time.monotonic() + self.cooldown_s
                    break  # next provider

                problems = check(value) if check else []
                if problems:
                    record(
                        Attempt(
                            provider.name,
                            AttemptOutcome.REJECTED,
                            "; ".join(problems),
                            _ms(started),
                        )
                    )
                    if invalid_left > 0:
                        invalid_left -= 1
                        feedback = problems
                        continue
                    break  # this provider can't get it right; try the next one

                record(Attempt(provider.name, AttemptOutcome.OK, "", _ms(started)))
                if self.cache:
                    self.cache.put(agent_name, key, value, provider.name)
                return LLMResult(value, provider.name, attempts)

        raise AllProvidersFailed(attempts)


def _with_feedback(prompt: str, problems: list[str]) -> str:
    bullet = "\n".join(f"- {p}" for p in problems)
    return (
        f"{prompt}\n\nYour previous answer was rejected:\n{bullet}\n"
        "Fix every problem. Use only facts and numbers given above. Reply with JSON only."
    )


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
