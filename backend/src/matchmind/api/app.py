"""MatchMind HTTP + WebSocket API.

Run from backend/:  uv run uvicorn matchmind.api.app:app --reload

    GET  /api/health
    GET  /api/matches                 list of matches (meta only)
    GET  /api/matches/{match_id}      full match: meta + events
    GET  /api/demo                    demo bundles available
    GET  /api/demo/{match_id}         pre-baked demo bundle (cards, handoffs, recap, timeline)
    WS   /ws/live/{match_id}          live replay with the agent team (see api/live.py)
         query: speed, audience, language, club, player, llm=0|1, outage=0|1
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import suppress
from functools import cache
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from matchmind.agents.llm_agents import ViewerProfile
from matchmind.api.live import LiveSession, SessionOptions
from matchmind.bake import CACHE_DIR, DEMO_DIR
from matchmind.cards import Audience, Language
from matchmind.config import ConfigError, load_settings
from matchmind.generator import MATCHES_DIR
from matchmind.llm.gateway import LLMGateway, ResponseCache
from matchmind.models import Match


@cache
def _match(match_id: str) -> Match:
    path = MATCHES_DIR / f"{match_id}.json"
    if not path.exists() or "/" in match_id or "\\" in match_id:
        raise HTTPException(404, f"unknown match {match_id!r}")
    return Match.load(path)


def create_app(gateway: LLMGateway | None = None, use_mcp: bool | None = None) -> FastAPI:
    app = FastAPI(title="MatchMind", version="0.1.0")
    # Local development and the static web app call this API from another origin.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"]
    )
    app.state.gateway = gateway
    app.state.use_mcp = (
        use_mcp if use_mcp is not None else os.getenv("MATCHMIND_USE_MCP", "1") != "0"
    )

    def get_gateway() -> LLMGateway | None:
        if app.state.gateway is None:
            try:
                app.state.gateway = LLMGateway.from_settings(
                    load_settings(), ResponseCache(CACHE_DIR)
                )
            except ConfigError:
                return None
        return app.state.gateway

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.get("/api/matches")
    def matches() -> list[dict[str, Any]]:
        out = []
        for path in sorted(MATCHES_DIR.glob("*.json")):
            meta = _match(path.stem).meta
            out.append(
                {
                    "match_id": meta.match_id,
                    "story": meta.story,
                    "home": {"id": meta.home.id, "name": meta.home.name},
                    "away": {"id": meta.away.id, "name": meta.away.name},
                    "venue": meta.venue,
                    "final_score": meta.final_score.model_dump(),
                    "has_demo": (DEMO_DIR / path.name).exists(),
                }
            )
        return out

    @app.get("/api/matches/{match_id}")
    def match(match_id: str) -> dict[str, Any]:
        return _match(match_id).model_dump(mode="json", exclude_defaults=True)

    @app.get("/api/demo")
    def demos() -> list[str]:
        return sorted(p.stem for p in DEMO_DIR.glob("*.json"))

    @app.get("/api/demo/{match_id}")
    def demo(match_id: str) -> dict[str, Any]:
        path = DEMO_DIR / f"{match_id}.json"
        if not path.exists() or "/" in match_id or "\\" in match_id:
            raise HTTPException(404, f"no demo bundle for {match_id!r}")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.websocket("/ws/live/{match_id}")
    async def live(ws: WebSocket, match_id: str) -> None:
        await ws.accept()
        q = ws.query_params
        try:
            match = _match(match_id)
            profile = ViewerProfile(
                audience=Audience(q.get("audience", "fan")),
                language=Language(q.get("language", "en")),
                favourite_club=q.get("club") or None,
                favourite_player=q.get("player") or None,
            )
            options = SessionOptions(
                speed=float(q.get("speed", 10)),
                profile=profile,
                llm_enabled=q.get("llm", "1") != "0",
                use_mcp=app.state.use_mcp,
                outage=q.get("outage", "0") == "1",
            )
        except (HTTPException, ValueError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            await ws.send_json({"type": "error", "message": detail})
            await ws.close(code=1008)
            return

        session = LiveSession(
            match, get_gateway() if options.llm_enabled else None, options, ws.send_json
        )

        async def controls() -> None:
            while True:
                await session.control(await ws.receive_json())

        listener = asyncio.create_task(controls())
        try:
            await session.run()
        except WebSocketDisconnect:
            return
        finally:
            listener.cancel()
            with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await listener
        with suppress(RuntimeError):
            await ws.close()

    return app


app = create_app()
