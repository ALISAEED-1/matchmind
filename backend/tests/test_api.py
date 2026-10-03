from collections import Counter

import pytest
from fakes import FakeLLM, no_sleep
from fastapi.testclient import TestClient

from matchmind.agents.ask import AskMatchMind
from matchmind.api.app import create_app
from matchmind.llm.gateway import LLMGateway

MATCH = "mm-0004-comeback"


def client(llm: FakeLLM | None = None) -> TestClient:
    gateway = LLMGateway([llm], sleep=no_sleep) if llm else None
    return TestClient(create_app(gateway=gateway, use_mcp=False))


def drain(ws, until: str = "done", limit: int = 5000) -> list[dict]:
    msgs = []
    for _ in range(limit):
        msg = ws.receive_json()
        msgs.append(msg)
        if msg["type"] in (until, "error"):
            return msgs
    raise AssertionError(f"no {until!r} message")


def test_rest_endpoints():
    c = client()
    assert c.get("/api/health").json() == {"status": "ok"}
    matches = c.get("/api/matches").json()
    assert {m["match_id"] for m in matches} >= {MATCH, "mm-0003-red_card", "mm-0020-late_winner"}
    assert all(m["has_demo"] for m in matches)
    full = c.get(f"/api/matches/{MATCH}").json()
    assert full["meta"]["match_id"] == MATCH and len(full["events"]) > 900
    bundle = c.get(f"/api/demo/{MATCH}").json()
    assert bundle["cards"] and bundle["timeline"] and bundle["recap"]
    assert c.get("/api/matches/nope").status_code == 404
    assert c.get("/api/demo/nope").status_code == 404


def test_live_replay_streams_events_stats_cards_and_handoffs():
    c = client(FakeLLM())
    with c.websocket_connect(f"/ws/live/{MATCH}?speed=6000&audience=analyst&language=ur") as ws:
        msgs = drain(ws)
    kinds = Counter(m["type"] for m in msgs)
    assert msgs[0]["type"] == "hello" and msgs[-1]["type"] == "done"
    assert kinds["events"] > 80 and kinds["stats"] > 80 and kinds["cards"] > 10
    cards = [c for m in msgs if m["type"] == "cards" for c in m["cards"]]
    assert {(c["language"], c["audience"]) for c in cards if c["type"] != "commentary"} == {
        ("ur", "analyst")
    }
    commentary = [c for c in cards if c["type"] == "commentary"]
    assert commentary and all(c["language"] == "ur" for c in commentary)
    events = sum(len(m["events"]) for m in msgs if m["type"] == "events")
    assert events == len(c.get(f"/api/matches/{MATCH}").json()["events"])
    final = [m for m in msgs if m["type"] == "stats"][-1]["point"]
    assert (final["score_home"], final["score_away"]) == (3, 2)
    handoffs = [h for m in msgs if m["type"] == "handoffs" for h in m["handoffs"]]
    assert any(h["source"] == "stats_agent" and h["target"] == "producer" for h in handoffs)
    assert msgs[-1]["recap"]["headline"] == "What a match"


def test_live_personalizes_for_the_viewer():
    llm = FakeLLM()
    c = client(llm)
    url = f"/ws/live/{MATCH}?speed=6000&club=Ironmere%20Athletic&player=Femi%20Okarie"
    with c.websocket_connect(url) as ws:
        hello = ws.receive_json()
        drain(ws)
    assert hello["config"]["profile"]["favourite_club"] == "Ironmere Athletic"
    assert "personalizer_agent" in llm.calls


def test_controls_pause_speed_resume_and_outage_toggle():
    c = client(FakeLLM())
    with c.websocket_connect(f"/ws/live/{MATCH}?speed=1") as ws:
        assert ws.receive_json()["type"] == "hello"
        for action, check in [
            ({"action": "pause"}, lambda s: s["paused"]),
            ({"action": "speed", "value": 50}, lambda s: s["speed"] == 50),
            ({"action": "outage", "value": True}, lambda s: s["outage"]),
            ({"action": "resume"}, lambda s: not s["paused"]),
            ({"action": "warp"}, None),
        ]:
            ws.send_json(action)
            msg = drain(ws, until="status")[-1]
            if check is None:
                assert msg["type"] == "error"
            else:
                assert msg["type"] == "status" and check(msg), (action, msg)


def test_simulated_outage_runs_the_recovery_path():
    c = client(FakeLLM())
    with c.websocket_connect(f"/ws/live/{MATCH}?speed=6000&outage=1") as ws:
        msgs = drain(ws)
    cards = [c for m in msgs if m["type"] == "cards" for c in m["cards"]]
    llm_moments = [c for c in cards if c["importance"] >= 0.45]
    # every LLM-routed moment still gets a correct card: template fallback or breaker routing
    assert llm_moments and all(c["source_agent"] == "template_writer" for c in llm_moments)
    assert any(c["fallback_used"] for c in llm_moments)
    handoffs = [h for m in msgs if m["type"] == "handoffs" for h in m["handoffs"]]
    assert any(
        "simulated outage" in h["detail"] and h["status"] == "provider_fallback" for h in handoffs
    )
    assert any("circuit breaker" in h["detail"] for h in handoffs)
    assert msgs[-1]["counters"]["breaker_trips"] >= 1


class _NoCopilot(AskMatchMind):
    """Copilot is unavailable in CI: force the fallback path."""

    async def _copilot(self, *args, **kwargs):
        raise RuntimeError("copilot CLI not signed in")


class _FakeCopilot(AskMatchMind):
    async def _copilot(self, match, question, until_ms, minute, language):
        return f"At {minute}: answered with tools.", ["match_snapshot", "key_moments"]


def test_ask_uses_copilot_and_reports_tools():
    c = TestClient(create_app(use_mcp=False, asker=_FakeCopilot()))
    r = c.post(
        "/api/ask", json={"match_id": MATCH, "question": "Who is on top?", "until_ms": 2_000_000}
    )
    body = r.json()
    assert r.status_code == 200 and body["provider"] == "github-copilot"
    assert body["tools_used"] == ["match_snapshot", "key_moments"] and not body["fallback_used"]
    assert body["minute"] in body["answer"] and body["until_ms"] <= 2_000_000


def test_ask_falls_back_when_copilot_is_unavailable():
    gateway = LLMGateway([_AnswerLLM()], sleep=no_sleep)
    c = TestClient(create_app(use_mcp=False, asker=_NoCopilot(gateway=gateway)))
    body = c.post("/api/ask", json={"match_id": MATCH, "question": "Why did they win?"}).json()
    assert body["fallback_used"] and body["provider"].startswith("fake:model")
    assert body["answer"] == "Fallback answer from the stats snapshot."


def test_serves_the_web_app_alongside_the_api(tmp_path):
    (tmp_path / "index.html").write_text("<title>MatchMind</title>", encoding="utf-8")
    c = TestClient(create_app(use_mcp=False, web_dir=tmp_path))
    assert "MatchMind" in c.get("/").text
    assert c.get("/api/health").json() == {"status": "ok"}  # API routes still win


def test_ask_validates_input():
    c = TestClient(create_app(use_mcp=False, asker=_FakeCopilot()))
    assert c.post("/api/ask", json={"match_id": "nope", "question": "Why?"}).status_code == 404
    assert c.post("/api/ask", json={"match_id": MATCH, "question": ""}).status_code == 422


class _AnswerLLM:
    name = "fake:model"

    async def complete(self, agent_name, instructions, prompt, schema):
        return schema(answer="Fallback answer from the stats snapshot.")


@pytest.mark.parametrize("query", ["audience=coach", "language=fr", "speed=fast"])
def test_bad_query_is_rejected(query):
    with client().websocket_connect(f"/ws/live/{MATCH}?{query}") as ws:
        assert ws.receive_json()["type"] == "error"


def test_templates_only_when_llm_disabled():
    with client(FakeLLM()).websocket_connect(f"/ws/live/{MATCH}?speed=6000&llm=0") as ws:
        msgs = drain(ws)
    cards = [c for m in msgs if m["type"] == "cards" for c in m["cards"]]
    assert cards and all(c["source_agent"] == "template_writer" for c in cards)
