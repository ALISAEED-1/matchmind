"""Open the MatchMind agents in Microsoft Agent Framework DevUI (a local visual debugger).

Run from backend/:  uv run python scripts/devui.py     ->  http://127.0.0.1:8080

Entities shown in DevUI:
* matchmind-broadcast: the real orchestration workflow. Send "mm-0004-comeback 60" to
  replay the first 60 minutes of play through the agent team and watch each executor run.
* ask_matchmind: the GitHub Copilot agent with the matchmind-stats MCP tools. Ask e.g.
  "In mm-0004-comeback (until_ms 2900000), why are Ironmere ahead?"
* insight_agent: the Insight agent's instructions on the first model in the chain; paste FACTS
  JSON to see how it explains a moment.
"""

from __future__ import annotations

import sys

from agent_framework import Agent, Executor, WorkflowContext, handler
from agent_framework_devui import serve

from matchmind.agents.ask import MCP_SERVER, SYSTEM, _permission_handler
from matchmind.agents.llm_agents import InsightAgent
from matchmind.agents.orchestrator import MatchOrchestrator, PipelineConfig, Window
from matchmind.agents.stats_source import LocalStatsSource
from matchmind.bake import CACHE_DIR
from matchmind.config import REPO_ROOT, load_settings
from matchmind.generator import MATCHES_DIR
from matchmind.llm.client import make_chat_client
from matchmind.llm.gateway import LLMGateway, ResponseCache
from matchmind.models import Match
from matchmind.replay import batches
from matchmind.state import MatchState


class ReplayEntry(Executor):
    """DevUI entry point: 'match_id minutes' -> replay windows into stats_agent."""

    def __init__(self, state: MatchState, match: Match):
        super().__init__(id="replayer")
        self.state, self.match = state, match

    @handler
    async def start(self, text: str, ctx: WorkflowContext[Window]) -> None:
        parts = text.split()
        minutes = float(parts[-1]) if parts and parts[-1].replace(".", "").isdigit() else 15.0
        until = int(minutes * 60_000)
        events = [e for e in self.match.events if e.timestamp_ms <= until]
        self.state.events.clear()
        self.state.moments.clear()
        for window in batches(events):
            await ctx.send_message(Window(window))


def build_workflow(gateway: LLMGateway):
    match = Match.load(MATCHES_DIR / "mm-0004-comeback.json")
    state = MatchState(meta=match.meta)
    entry = ReplayEntry(state, match)
    orch = MatchOrchestrator(
        state, gateway, LocalStatsSource(match.meta, state.events), PipelineConfig(), front=entry
    )
    return orch.workflow


def build_copilot_agent():
    from agent_framework_github_copilot import GitHubCopilotAgent

    tools: list[str] = []
    return GitHubCopilotAgent(
        name="ask_matchmind",
        description="GitHub Copilot agent answering questions with the matchmind-stats MCP tools",
        default_options={
            "system_message": {"mode": "replace", "content": SYSTEM},
            "mcp_servers": {
                MCP_SERVER: {
                    "type": "local",
                    "command": sys.executable,
                    "args": ["-m", "matchmind.mcp_server"],
                    "tools": ["*"],
                    "working_directory": str(REPO_ROOT / "backend"),
                }
            },
            "on_permission_request": _permission_handler(tools),
            "timeout": 120,
        },
    )


def main() -> None:
    settings = load_settings()
    gateway = LLMGateway.from_settings(settings, ResponseCache(CACHE_DIR))
    insight = Agent(
        make_chat_client(settings.chain[0], settings),
        instructions=InsightAgent.instructions,
        name="insight_agent",
        description="Explains why a match moment matters, from FACTS JSON",
    )
    entities = [build_workflow(gateway), build_copilot_agent(), insight]
    serve(entities=entities, port=8080, auto_open=True)


if __name__ == "__main__":
    main()
