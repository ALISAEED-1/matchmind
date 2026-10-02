"""The three LLM agents: Insight, Narrator and Personalizer.

Each agent has one job, its own instructions and a Pydantic output schema.
They only see FACTS built by the Stats agent and never compute numbers. Every
answer goes through the Verifier inside the gateway's retry loop.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from matchmind.agents.facts import MomentFacts
from matchmind.agents.verifier import Verifier
from matchmind.cards import Audience, Language
from matchmind.llm.gateway import LLMGateway, LLMResult, OnAttempt

_RULES = (
    "Rules:\n"
    "- Use only names and numbers that appear in FACTS. "
    "Never invent statistics, players or clubs.\n"
    "- Copy numbers exactly as written in FACTS (for example 0.27 or 57). "
    "Minutes are written like 59' or 90+2'.\n"
    "- All clubs and players are fictional; never mention real leagues, clubs or players.\n"
    "- Reply with JSON only."
)


def _facts_block(facts: dict[str, Any]) -> str:
    return "FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- insight


class InsightOut(BaseModel):
    title: str = Field(description="Headline, at most 6 words")
    explanation: str = Field(description="1-2 sentences: what happened")
    why_it_matters: str = Field(description="1 sentence: why this moment matters for the match")


class InsightAgent:
    name = "insight_agent"
    instructions = (
        "You are the Insight Agent in an AI broadcast booth for a fictional football league. "
        "You receive FACTS about one key moment and the match so far, all computed by a stats "
        "engine. Explain WHY the moment matters, not just that it happened: connect it to "
        "momentum, pressing, control versus chaos, chance quality or the scoreline.\n"
        "Write in neutral, precise English. title: at most 6 words. explanation: 1-2 sentences. "
        "why_it_matters: 1 sentence.\n" + _RULES
    )

    def __init__(self, gateway: LLMGateway, verifier: Verifier):
        self.gateway = gateway
        self.verifier = verifier

    async def run(
        self, mf: MomentFacts, on_attempt: OnAttempt | None = None
    ) -> LLMResult[InsightOut]:
        def check(v: InsightOut) -> list[str]:
            return self.verifier.check_text(
                {"title": v.title, "body": v.explanation, "why_it_matters": v.why_it_matters},
                mf.facts,
            )

        return await self.gateway.generate(
            agent_name=self.name,
            instructions=self.instructions,
            prompt=_facts_block(mf.facts) + "\n\nWrite the insight for this moment.",
            schema=InsightOut,
            check=check,
            on_attempt=on_attempt,
        )


# --------------------------------------------------------------- narrator


class CommentaryOut(BaseModel):
    line: str = Field(description="One spoken commentary line, at most 25 words")
    tone: Literal["calm", "excited", "tense", "dramatic"]


class RecapOut(BaseModel):
    headline: str = Field(description="At most 10 words")
    summary: str = Field(description="3-4 sentences telling the story of the match")
    turning_points: list[str] = Field(
        description="Exactly 3 short items, each starting with a minute"
    )


class NarratorAgent:
    name = "narrator_agent"
    instructions = (
        "You are the Narrator Agent: a live TV commentator for a fictional football league. "
        "Given FACTS and the analyst's INSIGHT, write what a commentator would say at this "
        "moment. Vivid and emotional, but every fact must be accurate. English only.\n" + _RULES
    )
    recap_instructions = (
        "You are the Narrator Agent writing the full-time recap of a fictional football match. "
        "Tell the story of the match from the FACTS: how it started, the turning points and "
        "how it ended. English only. headline: at most 10 words. summary: 3-4 sentences. "
        "turning_points: exactly 3 items, each starting with a minute like 59'.\n" + _RULES
    )

    def __init__(self, gateway: LLMGateway, verifier: Verifier):
        self.gateway = gateway
        self.verifier = verifier

    async def commentate(
        self, mf: MomentFacts, insight: InsightOut | None, on_attempt: OnAttempt | None = None
    ) -> LLMResult[CommentaryOut]:
        insight_block = (
            "\n\nINSIGHT:\n" + insight.model_dump_json(indent=1) if insight is not None else ""
        )

        def check(v: CommentaryOut) -> list[str]:
            return self.verifier.check_text({"line": v.line}, mf.facts)

        return await self.gateway.generate(
            agent_name=self.name,
            instructions=self.instructions,
            prompt=_facts_block(mf.facts) + insight_block + "\n\nWrite the commentary line.",
            schema=CommentaryOut,
            check=check,
            on_attempt=on_attempt,
        )

    async def recap(
        self, mf: MomentFacts, on_attempt: OnAttempt | None = None
    ) -> LLMResult[RecapOut]:
        def check(v: RecapOut) -> list[str]:
            problems = self.verifier.check_text(
                {"headline": v.headline, "summary": v.summary, "body": " ".join(v.turning_points)},
                mf.facts,
            )
            if len(v.turning_points) != 3:
                problems.append("turning_points must have exactly 3 items")
            return problems

        return await self.gateway.generate(
            agent_name=self.name,
            instructions=self.recap_instructions,
            prompt=_facts_block(mf.facts) + "\n\nWrite the full-time recap.",
            schema=RecapOut,
            check=check,
            on_attempt=on_attempt,
        )


# ----------------------------------------------------------- personalizer


class Variant(BaseModel):
    language: Language
    audience: Audience
    title: str
    body: str
    why_it_matters: str = ""


class PersonalizedOut(BaseModel):
    variants: list[Variant]


class ViewerProfile(BaseModel):
    """A live viewer's preferences (live mode personalizes for exactly this profile)."""

    audience: Audience = Audience.FAN
    language: Language = Language.EN
    favourite_club: str | None = None  # club name
    favourite_player: str | None = None  # player name


LANGUAGE_NAMES = {
    Language.EN: "English",
    Language.UR: "Urdu (Urdu script)",
    Language.AR: "Modern Standard Arabic (Arabic script)",
}


class PersonalizerAgent:
    name = "personalizer_agent"
    instructions = (
        "You are the Personalizer Agent in an AI broadcast booth. You rewrite one overlay card "
        "for each requested (language, audience) pair.\n"
        "- fan: simple, warm, emotional words; no jargon; at most one number. If a favourite "
        "club is given, write from that supporter's point of view.\n"
        "- analyst: precise and tactical; include the key numbers from FACTS.\n"
        "- player_focus: centre the text on the player in FACTS.\n"
        "- Languages: en = English, ur = Urdu in Urdu script, ar = Modern Standard Arabic in "
        "Arabic script. Keep player and club names in English letters. Use Western digits "
        "(0-9).\n"
        "- title at most 8 words, body at most 2 sentences, why_it_matters 1 sentence.\n" + _RULES
    )

    def __init__(self, gateway: LLMGateway, verifier: Verifier):
        self.gateway = gateway
        self.verifier = verifier

    async def run(
        self,
        mf: MomentFacts,
        base_title: str,
        base_body: str,
        base_why: str | None,
        targets: list[tuple[Language, Audience]],
        profile: ViewerProfile | None = None,
        on_attempt: OnAttempt | None = None,
    ) -> LLMResult[PersonalizedOut]:
        wanted = [{"language": lang.value, "audience": aud.value} for lang, aud in targets]
        request: dict[str, Any] = {
            "base_card": {"title": base_title, "body": base_body, "why_it_matters": base_why or ""},
            "produce_exactly": wanted,
            "languages": {lang.value: LANGUAGE_NAMES[lang] for lang, _ in targets},
        }
        if profile and (profile.favourite_club or profile.favourite_player):
            request["viewer"] = {
                "favourite_club": profile.favourite_club,
                "favourite_player": profile.favourite_player,
            }

        def check(v: PersonalizedOut) -> list[str]:
            problems = []
            got = {(x.language, x.audience) for x in v.variants}
            missing = [
                f"{lang.value}/{aud.value}" for lang, aud in targets if (lang, aud) not in got
            ]
            if missing:
                problems.append(f"missing variants: {', '.join(missing)}")
            for x in v.variants:
                issues = self.verifier.check_text(
                    {"title": x.title, "body": x.body, "why_it_matters": x.why_it_matters},
                    mf.facts,
                    x.language.value,
                )
                problems += [f"{x.language.value}/{x.audience.value} {p}" for p in issues]
            return problems

        return await self.gateway.generate(
            agent_name=self.name,
            instructions=self.instructions,
            prompt=(
                _facts_block(mf.facts)
                + "\n\nREQUEST:\n"
                + json.dumps(request, ensure_ascii=False, indent=1)
            ),
            schema=PersonalizedOut,
            check=check,
            on_attempt=on_attempt,
        )
