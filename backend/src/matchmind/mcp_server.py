"""MatchMind stats as an MCP server.

Exposes the deterministic stats engine as Model Context Protocol tools, so any
MCP client can query a match: our Stats agent uses it over stdio, and the same
server works from Claude Desktop, VS Code or GitHub Copilot.

Every tool takes `until_ms` (match time) and only uses events up to that
point, so a live client never sees the future.

Run:  uv run python -m matchmind.mcp_server
"""

from __future__ import annotations

from dataclasses import asdict
from functools import cache
from typing import Any

from mcp.server.fastmcp import FastMCP

from matchmind.generator import MATCHES_DIR
from matchmind.models import Event, EventType, Match
from matchmind.stats import (
    compute_snapshot,
    detect_moments,
    momentum_series,
    pass_difficulty,
    player_snapshot,
    shot_xg,
)

mcp = FastMCP(
    "matchmind-stats",
    log_level="WARNING",
    instructions=(
        "Deterministic football statistics for synthetic MatchMind matches. "
        "All numbers are computed in code. Pass until_ms to see the match as it was at that time."
    ),
)


@cache
def _load(match_id: str) -> Match:
    path = MATCHES_DIR / f"{match_id}.json"
    if not path.exists():
        raise ValueError(f"Unknown match_id {match_id!r}. Call list_matches first.")
    return Match.load(path)


def _until(match_id: str, until_ms: int | None) -> tuple[Match, list[Event]]:
    match = _load(match_id)
    if until_ms is None:
        return match, match.events
    return match, [e for e in match.events if e.timestamp_ms <= until_ms]


def _moment_dict(m) -> dict[str, Any]:
    d = asdict(m)
    d["kind"] = m.kind.value
    d["team"] = m.team.value if m.team else None
    return d


@mcp.tool()
def list_matches() -> list[dict[str, Any]]:
    """List available matches with teams, story and final score."""
    out = []
    for path in sorted(MATCHES_DIR.glob("*.json")):
        meta = _load(path.stem).meta
        out.append(
            {
                "match_id": meta.match_id,
                "home": meta.home.name,
                "away": meta.away.name,
                "story": meta.story,
                "final_score": f"{meta.final_score.home}-{meta.final_score.away}",
            }
        )
    return out


@mcp.tool()
def match_snapshot(match_id: str, until_ms: int | None = None) -> dict[str, Any]:
    """Score, possession, passing, shooting, pressing, momentum, chaos index and top players."""
    match, events = _until(match_id, until_ms)
    if not events:
        raise ValueError("No events before until_ms.")
    return compute_snapshot(match.meta, events).model_dump(mode="json")


@mcp.tool()
def key_moments(
    match_id: str,
    until_ms: int | None = None,
    since_ms: int = 0,
    min_importance: float = 0.0,
) -> list[dict[str, Any]]:
    """Key moments (goals, big chances, momentum shifts, pressure surges...), importance 0-1."""
    _, events = _until(match_id, until_ms)
    return [
        _moment_dict(m)
        for m in detect_moments(events)
        if m.timestamp_ms >= since_ms and m.importance >= min_importance
    ]


@mcp.tool()
def player_stats(match_id: str, player_id: str, until_ms: int | None = None) -> dict[str, Any]:
    """Passing, shooting, physical and defensive numbers for one player."""
    match, events = _until(match_id, until_ms)
    return player_snapshot(match.meta, events, player_id).model_dump(mode="json")


@mcp.tool()
def momentum_timeline(match_id: str, until_ms: int | None = None) -> list[dict[str, Any]]:
    """Per-minute momentum (-1 away .. +1 home) with each side's smoothed threat."""
    _, events = _until(match_id, until_ms)
    return [asdict(p) for p in momentum_series(events)]


@mcp.tool()
def explain_event(match_id: str, event_id: str) -> dict[str, Any]:
    """Pass difficulty or xG breakdown for a single pass or shot."""
    event = next((e for e in _load(match_id).events if e.event_id == event_id), None)
    if event is None:
        raise ValueError(f"No event {event_id!r} in {match_id}.")
    if event.type is EventType.PASS:
        d = pass_difficulty(event)
        return {"event_id": event_id, "type": "pass", **asdict(d), "label": d.label}
    if event.type is EventType.SHOT:
        return {"event_id": event_id, "type": "shot", **asdict(shot_xg(event))}
    raise ValueError(f"{event_id} is a {event.type.value}; only passes and shots can be explained.")


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
