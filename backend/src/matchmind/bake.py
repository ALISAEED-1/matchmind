"""Bake a demo bundle: run a whole match through the agent pipeline and save everything.

The bundle (data/demo/<match_id>.json) is what Demo Mode replays: the cards,
the handoff log, the recap and a per-minute stats timeline. It needs no
backend, model or API key to view.

Run from backend/:
    uv run python -m matchmind.bake --match mm-0004-comeback --languages en,ur,ar

Validated LLM answers are cached under data/cache, so an interrupted bake
resumes where it stopped.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from matchmind.agents.facts import display_minute
from matchmind.agents.orchestrator import MatchOrchestrator, PipelineConfig
from matchmind.agents.stats_source import LocalStatsSource, MCPStatsSource
from matchmind.cards import Audience, Language
from matchmind.config import REPO_ROOT, load_settings
from matchmind.generator import MATCHES_DIR
from matchmind.llm.gateway import LLMGateway, ResponseCache
from matchmind.models import Event, Match, Side
from matchmind.replay import batches
from matchmind.state import Handoff, HandoffStatus, MatchState
from matchmind.stats import momentum_series, possession_share, pressure_index, recent_chaos

DEMO_DIR = REPO_ROOT / "data" / "demo"
CACHE_DIR = REPO_ROOT / "data" / "cache"
BUNDLE_VERSION = "1.0"


def timeline(events: list[Event]) -> list[dict[str, Any]]:
    """Per-minute stats for the momentum graph and scoreboard (computed in code)."""
    out = []
    goals = {Side.HOME: 0, Side.AWAY: 0}
    goal_ts = sorted((e.timestamp_ms, e.team) for e in events if e.type.value == "goal")
    for point in momentum_series(events):
        end = (point.t_min + 1) * 60_000
        upto = [e for e in events if e.timestamp_ms < end]
        while goal_ts and goal_ts[0][0] < end:
            goals[goal_ts.pop(0)[1]] += 1
        chaos = recent_chaos(upto)
        out.append(
            {
                "t_min": point.t_min,
                "minute": display_minute(point.period, point.minute),
                "period": point.period,
                "score_home": goals[Side.HOME],
                "score_away": goals[Side.AWAY],
                "momentum": point.value,
                "possession_home": possession_share(upto)[Side.HOME],
                "pressure_home": pressure_index(upto, Side.HOME, max(0, end - 600_000), end),
                "pressure_away": pressure_index(upto, Side.AWAY, max(0, end - 600_000), end),
                "chaos_index": chaos.index,
                "chaos_label": chaos.label,
            }
        )
    return out


def bundle(state: MatchState, config: PipelineConfig, chain: list[str], seconds: float) -> dict:
    cards = sorted(state.cards, key=lambda c: (c.display_at_ms, c.group_id, c.language, c.audience))
    return {
        "bundle_version": BUNDLE_VERSION,
        "match_id": state.meta.match_id,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pipeline": {
            "languages": [lang.value for lang in config.languages],
            "audiences": [a.value for a in config.audiences],
            "llm_chain": chain,
            "full_threshold": config.full_threshold,
            "insight_threshold": config.insight_threshold,
            "bake_seconds": round(seconds),
        },
        "counters": dict(state.counters),
        "recap": state.recap.model_dump() if state.recap else None,
        "timeline": timeline(state.events),
        "cards": [c.model_dump(mode="json", exclude_none=True) for c in cards],
        "handoffs": [h.model_dump(mode="json", exclude_none=True) for h in state.handoffs],
    }


async def bake(
    match_id: str,
    config: PipelineConfig,
    use_mcp: bool = True,
    minutes: int | None = None,
    out_dir: Path = DEMO_DIR,
    verbose: bool = True,
) -> Path:
    match = Match.load(MATCHES_DIR / f"{match_id}.json")
    settings = load_settings()
    gateway = LLMGateway.from_settings(settings, ResponseCache(CACHE_DIR))
    state = MatchState(meta=match.meta)
    started = time.perf_counter()
    if verbose:

        def show(h: Handoff) -> None:
            if h.status in (
                HandoffStatus.RETRY,
                HandoffStatus.PROVIDER_FALLBACK,
                HandoffStatus.FALLBACK,
            ):
                ms = f" {h.latency_ms / 1000:.1f}s" if h.latency_ms else ""
                print(
                    f"       ! {h.status.value:<17} {h.source} -> {h.target}{ms}: {h.detail[:150]}",
                    flush=True,
                )

        state.listener = show

    async def run(source) -> None:
        orch = MatchOrchestrator(state, gateway, source, config)
        events = match.events
        if minutes is not None:  # quick partial runs for debugging prompts and providers
            events = [e for e in events if e.timestamp_ms < minutes * 60_000]
        for window in batches(events):
            cards = await orch.process(window)
            if verbose and cards:
                last = window[-1]
                fb = sum(c.fallback_used for c in cards)
                providers = sorted({c.provider for c in cards if c.provider})
                print(
                    f"{display_minute(last.period, last.minute):>6} "
                    f"+{len(cards):>2} cards"
                    + (f"  fallback={fb}" if fb else "")
                    + (f"  via {', '.join(providers)}" if providers else "")
                    + f"  [{time.perf_counter() - started:5.0f}s]",
                    flush=True,
                )

    if use_mcp:
        async with MCPStatsSource(match_id) as source:
            await run(source)
    else:
        await run(LocalStatsSource(match.meta, state.events))

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{match_id}.json"
    data = bundle(state, config, [s.name for s in settings.chain], time.perf_counter() - started)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if verbose:
        c = state.counters
        print(
            f"\n{match_id}: {len(state.cards)} cards, {len(state.handoffs)} handoffs, "
            f"llm ok={c['llm_ok']} cached={c['llm_cached']} retries="
            f"{c['llm_rejected'] + c['llm_invalid_output']} provider_errors="
            f"{c['llm_transient_error'] + c['llm_provider_error']} "
            f"fallback cards={sum(x.fallback_used for x in state.cards)} "
            f"in {time.perf_counter() - started:.0f}s\n-> {path}"
        )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m matchmind.bake",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--match", required=True, help="match id, e.g. mm-0004-comeback")
    parser.add_argument("--languages", default="en,ur,ar")
    parser.add_argument("--audiences", default="fan,analyst")
    parser.add_argument("--local-stats", action="store_true", help="skip the MCP server")
    parser.add_argument("--no-llm", action="store_true", help="templates only (instant)")
    parser.add_argument("--minutes", type=int, help="only the first N minutes of play (debug)")
    args = parser.parse_args()

    config = PipelineConfig(
        languages=tuple(Language(x) for x in args.languages.split(",")),
        audiences=tuple(Audience(x) for x in args.audiences.split(",")),
        llm_enabled=not args.no_llm,
    )
    asyncio.run(bake(args.match, config, use_mcp=not args.local_stats, minutes=args.minutes))


if __name__ == "__main__":
    main()
