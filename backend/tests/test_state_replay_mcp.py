import asyncio

import pytest

from matchmind.agents.stats_source import LocalStatsSource, MCPStatsSource
from matchmind.generator import MATCHES_DIR
from matchmind.models import Match
from matchmind.replay import batches, live_batches
from matchmind.state import HandoffStatus, MatchState
from matchmind.stats import detect_moments

MATCH_ID = "mm-0004-comeback"


@pytest.fixture(scope="module")
def match() -> Match:
    return Match.load(MATCHES_DIR / f"{MATCH_ID}.json")


def test_batches_cover_all_events_in_minute_windows(match):
    bs = list(batches(match.events))
    assert [e for b in bs for e in b] == match.events
    for b in bs:
        assert len({e.timestamp_ms // 60_000 for e in b}) == 1


def test_live_batches_respect_speed(match):
    async def first_two():
        out = []
        async for b in live_batches(match.events[:200], speed=600):  # 1 minute -> 0.1 s
            out.append(b)
        return out

    assert [e for b in asyncio.run(first_two()) for e in b] == match.events[:200]
    with pytest.raises(ValueError):
        asyncio.run(anext(live_batches(match.events, speed=0)))


def test_match_state_dedupes_moments_and_logs_handoffs(match):
    state = MatchState(meta=match.meta)
    state.ingest(match.events[:400])
    moments = detect_moments(state.events)
    assert state.add_moments(moments) == moments
    assert state.add_moments(moments) == []  # second time: nothing new
    state.log("stats_agent", "producer", moment_id=moments[0].id)
    state.log("insight_agent", "verifier", status=HandoffStatus.RETRY, detail="bad number")
    assert [h.seq for h in state.handoffs] == [1, 2]
    assert state.counters["handoff_retry"] == 1
    assert state.handoffs[0].match_ms == state.clock_ms


def test_mcp_source_matches_local_source(match):
    until = match.events[600].timestamp_ms

    async def via_mcp():
        async with MCPStatsSource(MATCH_ID) as src:
            return await src.snapshot(until), await src.moments(until), src.calls

    local = LocalStatsSource(match.meta, match.events)
    snap_mcp, moments_mcp, calls = asyncio.run(via_mcp())
    assert snap_mcp == asyncio.run(local.snapshot(until))
    assert moments_mcp == asyncio.run(local.moments(until))
    assert calls == 2
