import asyncio

import pytest
from pydantic import BaseModel

from matchmind.llm.gateway import (
    AllProvidersFailed,
    AttemptOutcome,
    InvalidOutput,
    LLMGateway,
    ResponseCache,
    classify,
    parse_json_output,
)


class Out(BaseModel):
    text: str


class FakeProvider:
    """Plays back a script: each item is an Out to return or an exception to raise."""

    def __init__(self, name: str, script: list):
        self.name = name
        self.script = list(script)
        self.prompts: list[str] = []

    async def complete(self, agent_name, instructions, prompt, schema):
        self.prompts.append(prompt)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class Sleeps:
    def __init__(self):
        self.calls: list[float] = []

    async def __call__(self, s: float) -> None:
        self.calls.append(s)


def run(gateway: LLMGateway, **kw):
    kw.setdefault("agent_name", "insight_agent")
    kw.setdefault("instructions", "be brief")
    kw.setdefault("prompt", "facts")
    kw.setdefault("schema", Out)
    return asyncio.run(gateway.generate(**kw))


def outcomes(result_or_exc) -> list[tuple[str, AttemptOutcome]]:
    return [(a.provider, a.outcome) for a in result_or_exc.attempts]


def test_first_provider_success():
    gw = LLMGateway([FakeProvider("a", [Out(text="hi")]), FakeProvider("b", [])])
    res = run(gw)
    assert res.value.text == "hi" and res.provider == "a" and not res.cached
    assert outcomes(res) == [("a", AttemptOutcome.OK)]


def test_invalid_output_is_retried_on_same_provider():
    a = FakeProvider("a", [InvalidOutput("no JSON"), Out(text="fixed")])
    res = run(LLMGateway([a]))
    assert res.value.text == "fixed"
    assert outcomes(res) == [("a", AttemptOutcome.INVALID_OUTPUT), ("a", AttemptOutcome.OK)]
    assert "not valid JSON" in a.prompts[1]


def test_verifier_rejection_feeds_back_into_prompt():
    a = FakeProvider("a", [Out(text="xG was 0.99"), Out(text="xG was 0.27")])

    def check(v: Out) -> list[str]:
        return ["number 0.99 is not in the facts"] if "0.99" in v.text else []

    res = run(LLMGateway([a]), check=check)
    assert res.value.text == "xG was 0.27"
    assert outcomes(res) == [("a", AttemptOutcome.REJECTED), ("a", AttemptOutcome.OK)]
    assert "number 0.99 is not in the facts" in a.prompts[1]


def test_transient_errors_back_off_then_fall_through_and_cool_down():
    a = FakeProvider("a", [RuntimeError("Error code: 503 high demand")] * 2)
    b = FakeProvider("b", [Out(text="from b"), Out(text="again b")])
    sleeps = Sleeps()
    gw = LLMGateway([a, b], sleep=sleeps, backoff_s=2.0)

    res = run(gw)
    assert res.provider == "b"
    assert outcomes(res) == [
        ("a", AttemptOutcome.TRANSIENT_ERROR),
        ("a", AttemptOutcome.TRANSIENT_ERROR),
        ("b", AttemptOutcome.OK),
    ]
    assert sleeps.calls == [2.0]

    # "a" is cooling down, so the next call goes straight to "b".
    res2 = run(gw, prompt="other facts")
    assert outcomes(res2) == [("b", AttemptOutcome.OK)]


def test_all_providers_failing_raises_with_full_history():
    a = FakeProvider("a", [ValueError("bad request")])
    b = FakeProvider("b", [InvalidOutput("x"), InvalidOutput("y")])
    with pytest.raises(AllProvidersFailed) as info:
        run(LLMGateway([a, b], sleep=Sleeps()))
    assert outcomes(info.value) == [
        ("a", AttemptOutcome.PROVIDER_ERROR),
        ("b", AttemptOutcome.INVALID_OUTPUT),
        ("b", AttemptOutcome.INVALID_OUTPUT),
    ]


def test_skip_provider_and_extra_retries():
    local = FakeProvider("foundry_local:tiny", [Out(text="never used")])
    remote = FakeProvider("gemini:x", [Out(text="bad 1"), Out(text="bad 2"), Out(text="good")])
    gw = LLMGateway([remote, local])
    res = run(
        gw,
        check=lambda v: ["bad"] if "bad" in v.text else [],
        skip_provider=lambda name: name.startswith("foundry_local:"),
        invalid_retries=2,
    )
    assert res.value.text == "good" and local.prompts == []
    assert [a.outcome for a in res.attempts].count(AttemptOutcome.REJECTED) == 2


def test_pacing_spaces_calls_to_the_same_provider():
    sleeps = Sleeps()
    a = FakeProvider("gemini:x", [Out(text="1"), Out(text="2")])
    gw = LLMGateway([a], sleep=sleeps, min_interval_s={"gemini:x": 6.0})
    run(gw, prompt="one")
    run(gw, prompt="two")
    assert len(sleeps.calls) == 1 and sleeps.calls[0] == pytest.approx(6.0, abs=0.5)


def test_cache_serves_repeat_requests(tmp_path):
    a = FakeProvider("a", [Out(text="once")])
    gw = LLMGateway([a], ResponseCache(tmp_path))
    first, second = run(gw), run(gw)
    assert first.value == second.value
    assert second.cached and second.provider == "a"
    assert outcomes(second) == [("a", AttemptOutcome.CACHED)]
    assert len(a.prompts) == 1


def test_cached_answer_that_now_fails_check_is_regenerated(tmp_path):
    cache = ResponseCache(tmp_path)
    run(LLMGateway([FakeProvider("a", [Out(text="old 0.99")])], cache))
    fresh = FakeProvider("a", [Out(text="new 0.27")])
    res = run(LLMGateway([fresh], cache), check=lambda v: ["bad"] if "0.99" in v.text else [])
    assert res.value.text == "new 0.27" and not res.cached


@pytest.mark.parametrize(
    "exc, expected",
    [
        (RuntimeError("Error code: 429 - rate limit"), AttemptOutcome.TRANSIENT_ERROR),
        (RuntimeError("503 UNAVAILABLE"), AttemptOutcome.TRANSIENT_ERROR),
        (TimeoutError(), AttemptOutcome.TRANSIENT_ERROR),
        (InvalidOutput("x"), AttemptOutcome.INVALID_OUTPUT),
        (ValueError("400 bad request"), AttemptOutcome.PROVIDER_ERROR),
    ],
)
def test_classify(exc, expected):
    assert classify(exc) == expected


def test_classify_looks_at_wrapped_causes():
    try:
        try:
            raise RuntimeError("Error code: 429")
        except RuntimeError as inner:
            raise ValueError("service failed") from inner
    except ValueError as outer:
        assert classify(outer) is AttemptOutcome.TRANSIENT_ERROR


def test_parse_json_output_tolerates_fences_and_prose():
    assert parse_json_output('```json\n{"text": "a"}\n```', Out).text == "a"
    assert parse_json_output('Sure! {"text": "b"} hope that helps', Out).text == "b"
    with pytest.raises(InvalidOutput):
        parse_json_output("no json here", Out)
    with pytest.raises(InvalidOutput):
        parse_json_output('{"wrong": 1}', Out)
