"""Test doubles shared by the orchestrator and API tests."""

import json

from matchmind.agents.llm_agents import (
    CommentaryOut,
    InsightOut,
    PersonalizedOut,
    RecapOut,
    Variant,
)
from matchmind.cards import Audience, Language

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
            lang = Language.EN
            if "Urdu" in instructions:
                lang = Language.UR
            elif "Arabic" in instructions:
                lang = Language.AR
            return CommentaryOut(line=TEXT[lang][1], tone="excited")
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


async def no_sleep(_s: float) -> None:
    return None
