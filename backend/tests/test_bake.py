import asyncio
import json

from matchmind.agents.orchestrator import PipelineConfig
from matchmind.bake import bake
from matchmind.cards import Language
from matchmind.generator import MATCHES_DIR
from matchmind.models import Match


def test_template_bake_writes_a_complete_bundle(tmp_path):
    config = PipelineConfig(languages=(Language.EN, Language.AR), llm_enabled=False)
    path = asyncio.run(
        bake("mm-0003-red_card", config, use_mcp=False, out_dir=tmp_path, verbose=False)
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    match = Match.load(MATCHES_DIR / "mm-0003-red_card.json")

    assert data["match_id"] == "mm-0003-red_card"
    assert data["cards"] and data["handoffs"]
    times = [c["display_at_ms"] for c in data["cards"]]
    assert times == sorted(times)
    assert {c["language"] for c in data["cards"]} == {"en", "ar"}

    last = data["timeline"][-1]
    assert (last["score_home"], last["score_away"]) == (
        match.meta.final_score.home,
        match.meta.final_score.away,
    )
    assert all(-1 <= p["momentum"] <= 1 for p in data["timeline"])
    assert data["counters"]["route_template"] > 0 and data["recap"] is None
