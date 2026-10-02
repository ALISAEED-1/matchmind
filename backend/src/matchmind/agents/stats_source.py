"""Where the Stats agent gets its numbers.

`MCPStatsSource` (used by the orchestrator) calls the matchmind-stats MCP server
through Agent Framework's MCPStdioTool. `LocalStatsSource` calls the same stats
functions in-process; tests use it, and it is the fallback if the MCP server
cannot start. Both return identical results (tested).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any, Protocol

from agent_framework import MCPStdioTool

from matchmind.models import Event, MatchMeta, Side
from matchmind.stats import MatchSnapshot, Moment, MomentKind, compute_snapshot, detect_moments


class StatsSource(Protocol):
    name: str

    async def snapshot(self, until_ms: int) -> MatchSnapshot: ...

    async def moments(self, until_ms: int) -> list[Moment]: ...


class LocalStatsSource:
    """In-process stats over the events the orchestrator has ingested so far."""

    name = "local"

    def __init__(self, meta: MatchMeta, events: Sequence[Event]):
        self.meta = meta
        self.events = events  # live list owned by MatchState

    def _until(self, until_ms: int) -> list[Event]:
        return [e for e in self.events if e.timestamp_ms <= until_ms]

    async def snapshot(self, until_ms: int) -> MatchSnapshot:
        return compute_snapshot(self.meta, self._until(until_ms))

    async def moments(self, until_ms: int) -> list[Moment]:
        return detect_moments(self._until(until_ms))


def moment_from_dict(d: dict[str, Any]) -> Moment:
    return Moment(
        id=d["id"],
        kind=MomentKind(d["kind"]),
        timestamp_ms=d["timestamp_ms"],
        period=d["period"],
        minute=d["minute"],
        importance=d["importance"],
        team=Side(d["team"]) if d.get("team") else None,
        player_id=d.get("player_id"),
        event_id=d.get("event_id"),
        data=d.get("data") or {},
    )


def _parse_tool_result(result: Any) -> Any:
    text = (
        result if isinstance(result, str) else "".join(getattr(c, "text", "") or "" for c in result)
    )
    data = json.loads(text)
    if isinstance(data, dict) and set(data) == {"result"}:
        return data["result"]
    return data


class MCPStatsSource:
    """Stats via the matchmind-stats MCP server (stdio). Use as an async context manager."""

    name = "mcp"

    def __init__(self, match_id: str):
        self.match_id = match_id
        self.tool = MCPStdioTool(
            "matchmind_stats",
            command=sys.executable,
            args=["-m", "matchmind.mcp_server"],
            load_prompts=False,
            description="Deterministic MatchMind football statistics",
        )
        self.calls = 0

    async def __aenter__(self) -> MCPStatsSource:
        await self.tool.__aenter__()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.tool.__aexit__(*exc)

    async def _call(self, tool_name: str, **kwargs: Any) -> Any:
        self.calls += 1
        return _parse_tool_result(await self.tool.call_tool(tool_name, **kwargs))

    async def snapshot(self, until_ms: int) -> MatchSnapshot:
        data = await self._call("match_snapshot", match_id=self.match_id, until_ms=until_ms)
        return MatchSnapshot.model_validate(data)

    async def moments(self, until_ms: int) -> list[Moment]:
        data = await self._call("key_moments", match_id=self.match_id, until_ms=until_ms)
        return [moment_from_dict(d) for d in data]
