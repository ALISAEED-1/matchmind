"""Ask MatchMind: a GitHub Copilot agent that answers viewer questions about the match.

Built on Agent Framework's `GitHubCopilotAgent` (GitHub Copilot SDK). The agent
gets the matchmind-stats MCP server as its only tool source and looks the
answer up itself: snapshot, key moments, player stats, momentum, pass/shot
explanations, always at the viewer's current match time (`until_ms`).

Safety: the Copilot runtime is a general agent (shell, files, web). Every
permission request is rejected unless it is a call to a matchmind-stats MCP
tool, and those are read-only. The tools it called are returned with the
answer, so the UI can show how it was grounded.

Recovery: if Copilot is unavailable (not signed in, quota used up, timeout),
the question goes to the regular LLM chain with the stats snapshot as FACTS.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from typing import Any

from pydantic import BaseModel, Field

from matchmind.agents.facts import FactBuilder, display_minute
from matchmind.cards import Language
from matchmind.config import REPO_ROOT
from matchmind.llm.gateway import AllProvidersFailed, LLMGateway
from matchmind.models import Match
from matchmind.stats import compute_snapshot, detect_moments

MCP_SERVER = "matchmind-stats"
LANGUAGE_NAMES = {
    Language.EN: "English",
    Language.UR: "Urdu, in Urdu script (keep player and club names in English letters)",
    Language.AR: "Modern Standard Arabic (keep player and club names in English letters)",
}

SYSTEM = """You are Ask MatchMind, the match analyst in an AI broadcast booth for a
fictional football league. Answer the viewer's question about ONE match using only the
matchmind-stats tools: match_snapshot, key_moments, player_stats, momentum_timeline,
explain_event. Always pass the match_id and until_ms you are given, so you never look past
the current moment.
Rules:
- Look the facts up with the tools before answering; never guess or invent numbers,
  players or events.
- Quote match minutes exactly as the tools' "clock" field (e.g. 18', 45+2'); never use the
  raw "minute" field.
- Refer to players and clubs by name (player_name, team_name), never by id. Team totals
  (shots, xG, possession) belong to the team, not to one player; use player_stats for players.
- All clubs and players are fictional. Never mention real leagues, clubs or players.
- Answer in at most 90 words, in plain sentences (no markdown, no lists), in the requested
  language.
- If the tools cannot answer the question, say so briefly.
You cannot use any other tool, file, command or website."""


class AskAnswer(BaseModel):
    match_id: str
    question: str
    answer: str
    language: Language = Language.EN
    until_ms: int
    minute: str
    provider: str = Field(description="'github-copilot' or the fallback model that answered")
    tools_used: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    fallback_used: bool = False


class _FallbackAnswer(BaseModel):
    answer: str


def _permission_handler(tools_used: list[str]):
    """Approve matchmind-stats MCP tool calls only; reject everything else."""
    from copilot.generated.rpc import (
        PermissionDecisionApproveOnce,
        PermissionDecisionReject,
    )

    def handle(request: Any, _invocation: Any):
        if type(request).__name__ == "PermissionRequestMcp" and request.server_name == MCP_SERVER:
            tools_used.append(str(request.tool_name).removeprefix(f"{MCP_SERVER}-"))
            return PermissionDecisionApproveOnce()
        return PermissionDecisionReject(
            feedback="Ask MatchMind may only use the read-only matchmind-stats tools."
        )

    return handle


class AskMatchMind:
    """One instance per process; Copilot sessions are created per question."""

    def __init__(self, gateway: LLMGateway | None = None, timeout_s: float = 120.0):
        self.gateway = gateway
        self.timeout_s = timeout_s
        self._lock = asyncio.Lock()  # one Copilot session at a time (quota + CPU)

    async def ask(
        self,
        match: Match,
        question: str,
        until_ms: int | None = None,
        language: Language = Language.EN,
    ) -> AskAnswer:
        events = (
            match.events
            if until_ms is None
            else [e for e in match.events if e.timestamp_ms <= until_ms]
        )
        if not events:
            raise ValueError("the match has not started at until_ms")
        last = events[-1]
        until = last.timestamp_ms
        minute = display_minute(last.period, last.minute)
        base = {
            "match_id": match.meta.match_id,
            "question": question.strip()[:400],
            "language": language,
            "until_ms": until,
            "minute": minute,
        }
        started = time.perf_counter()
        try:
            async with self._lock:
                answer, tools = await asyncio.wait_for(
                    self._copilot(match, base["question"], until, minute, language), self.timeout_s
                )
            return AskAnswer(
                **base, answer=answer, provider="github-copilot", tools_used=tools,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )  # fmt: skip
        except Exception as exc:  # noqa: BLE001 - any Copilot failure falls back
            reason = f"{type(exc).__name__}: {str(exc)[:160]}"
        answer, provider = await self._fallback(match, events, base["question"], language, reason)
        return AskAnswer(
            **base, answer=answer, provider=provider, fallback_used=True,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )  # fmt: skip

    async def _copilot(
        self, match: Match, question: str, until_ms: int, minute: str, language: Language
    ) -> tuple[str, list[str]]:
        from agent_framework_github_copilot import GitHubCopilotAgent

        tools_used: list[str] = []
        meta = match.meta
        options = {
            "system_message": {"mode": "replace", "content": SYSTEM},
            "mcp_servers": {
                MCP_SERVER: {
                    "type": "local",
                    "command": sys.executable,
                    "args": ["-m", "matchmind.mcp_server"],
                    "tools": ["*"],
                    "working_directory": str(REPO_ROOT / "backend"),
                    "timeout": 30_000,
                }
            },
            "on_permission_request": _permission_handler(tools_used),
            "timeout": self.timeout_s,
        }
        prompt = (
            f"match_id: {meta.match_id}\nuntil_ms: {until_ms}\n"
            f"Match: {meta.home.name} (home) v {meta.away.name} (away) at {meta.venue}; "
            f"current minute {minute}.\n"
            f"Answer in {LANGUAGE_NAMES[language]}.\n\nQuestion: {question}"
        )
        async with GitHubCopilotAgent(name="ask_matchmind", default_options=options) as agent:
            response = await agent.run(prompt)
        # Plain text for an overlay: drop markdown emphasis the model sometimes adds anyway.
        text = re.sub(r"(\*\*|__|\*|`)", "", response.text or "").strip()
        if not text:
            raise RuntimeError("Copilot returned an empty answer")
        return text, list(dict.fromkeys(tools_used))

    async def _fallback(
        self, match: Match, events, question: str, language: Language, reason: str
    ) -> tuple[str, str]:
        if self.gateway is None:
            return (
                "Ask MatchMind is unavailable right now (GitHub Copilot could not be reached "
                "and no other model is configured).",
                "unavailable",
            )
        snap = compute_snapshot(match.meta, events)
        builder = FactBuilder(match.meta)
        facts = builder.for_recap(snap, detect_moments(events)).facts
        facts["current_minute"] = display_minute(snap.period, snap.minute)
        prompt = (
            "FACTS:\n" + json.dumps(facts, ensure_ascii=False, indent=1)
            + f"\n\nAnswer the viewer's question in {LANGUAGE_NAMES[language]}, at most 90 words, "
            "using only FACTS.\n\nQuestion: " + question
        )  # fmt: skip
        try:
            result = await self.gateway.generate(
                agent_name="ask_matchmind_fallback",
                instructions=SYSTEM.split("Rules:")[0]
                + "Use only the FACTS given. Reply with JSON only.",
                prompt=prompt,
                schema=_FallbackAnswer,
            )
        except AllProvidersFailed:
            return (
                "Ask MatchMind could not answer right now; please try again shortly.",
                "unavailable",
            )
        return result.value.answer, f"{result.provider} (Copilot unavailable: {reason[:60]})"
