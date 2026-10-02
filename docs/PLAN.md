# MatchMind: Plan

This file records the agreed architecture and schedule, plus changes from the brief.

## Changes from the brief

| Change | Why |
|---|---|
| **Verifier step** (deterministic, no LLM) | Checks every number in LLM text against `MatchState`. On a mismatch: one retry, then a template card. Gives visible handoffs and recovery at zero quota cost. |
| **Orchestrator routes per event** | Routine passes skip the LLM; shots go to Insight; goals and red cards trigger every agent. Turns a fixed chain into orchestration. |
| **Stats exposed as an MCP server** (FastMCP) | Agents call stat tools over MCP. Covers the "MCP integration" judging point for about 2–3h. |
| **Personalizer returns all variants in one call** | fan/analyst/player_focus × en/ur/ar in one JSON response. Cuts LLM calls about 6×. |
| **Static Demo Mode** | Flutter replays a pre-baked JSON bundle from GitHub Pages with no backend. Judges can't drain the quota. Live mode runs locally. |
| **Demo bundles baked from Oct 14** | Free quota is about 150 requests/day on low-tier models, so baking needs several days. |
| Hours moved from stats to agents | Stats are pure functions; the Agent Framework is the unfamiliar part. |

## Phase 0 findings

- Agent Framework is installed as `agent-framework-core` + `agent-framework-openai` + `agent-framework-orchestrations` (1.x). The `agent-framework` meta-package pulls in ~30 unused integrations.
- `OpenAIChatClient` targets the Responses API. GitHub Models uses Chat Completions, so we use `OpenAIChatCompletionClient` with `base_url`. No adapter needed (`backend/src/matchmind/llm/client.py`).
- Still to confirm with a real token: the model ID `openai/gpt-4.1-mini` and its rate-limit tier.

## Architecture

```
generator ──► data/matches/*.json (seeded)
                    │
              Replayer (speed x N)
                    │ events
                    ▼
        ┌──── Orchestrator (Agent Framework workflow) ────┐
        │   MatchState (shared): events, stats, moments,   │
        │   cards, handoff_log                             │
        │                                                  │
        │   Stats Agent ──(MCP: stats server)──► stats     │
        │        │ route by event importance               │
        │        ▼                                         │
        │   Insight Agent (LLM) ──► Verifier ──┐           │
        │   Narrator Agent (LLM) ──► Verifier ─┤ retry /   │
        │   Personalizer (LLM, all variants) ──┘ fallback  │
        └──────────────────────┬───────────────────────────┘
                               ▼
         FastAPI WebSocket (live)  |  export ► demo bundle JSON
                               ▼
         Flutter Web: pitch, cards, momentum, modes, debug drawer
```

## Folder structure

```
matchmind/
  backend/
    pyproject.toml   (uv project, Python 3.12)
    scripts/         one-off tools (hello_models.py, bake_demo.py)
    src/matchmind/
      config.py      .env settings
      generator/     squads, simulator, stories, CLI (__main__)
      stats/         pure functions + MCP server (mcp_server.py)
      state/         MatchState, Card, Event models (Pydantic)
      agents/        stats, insight, narrator, personalizer, verifier, orchestrator
      llm/           GitHub Models client/adapter, cache, retry/backoff
      replay/        replayer + demo-bundle exporter
      api/           FastAPI app + WebSocket
    tests/
  frontend/          Flutter web app
  data/
    matches/         3 generated matches
    demo/            baked card bundles (per match)
    cache/           LLM response cache (gitignored)
  docs/              BRIEF, PLAN, ARCHITECTURE, DATA_SCHEMA, AGENTS, DEMO_SCRIPT
  .github/workflows/ ci.yml (pytest + ruff + flutter analyze/test), pages.yml
  .env.example
  README.md
```

## Day-by-day (3h/day)

| Date | Phase | Work |
|---|---|---|
| Oct 3 | 0 Setup | git + .gitignore (.env) + .env.example, Python project, CI skeleton, GitHub Models hello world through the Agent Framework. **Register for the hackathon.** |
| Oct 4 | 1 Data | Squads (fictional), event models, possession-chain simulator |
| Oct 5 | 1 Data | Shots/goals/fouls/subs, story params (comeback, red card, late winner) |
| Oct 6 | 1 Data | CLI, 3 matches, DATA_SCHEMA.md, realism tests. *Submissions open: create the project on the site.* |
| Oct 7 | 2 Stats | Possession, pass accuracy, pass difficulty, shot/ball speed + tests |
| Oct 8 | 2 Stats | Pressure index, momentum, control-vs-chaos + tests |
| Oct 9 | 3 Agents | MatchState, replayer, stats MCP server |
| Oct 10 | 3 Agents | Agent Framework basics; Stats agent, Insight agent (Pydantic output) |
| Oct 11 | 3 Agents | Narrator + Personalizer (all variants, one call) |
| Oct 12 | 3 Agents | Orchestrator workflow: routing, handoff log |
| Oct 13 | 3 Agents | Verifier, retry/backoff on 429/timeout/bad JSON, template fallback, hash cache |
| Oct 14 | 3 Agents | End-to-end live run; **bake match 1** |
| Oct 15 | 4 API | FastAPI WebSocket, demo-bundle exporter; bake match 2 |
| Oct 16 | 5 UI | Flutter scaffold, theme, models, data source (static / WebSocket); bake match 3 |
| Oct 17 | 5 UI | Scoreboard, pitch CustomPainter |
| Oct 18 | 5 UI | Timed overlay cards, mode switch |
| Oct 19 | 5 UI | Settings sheet, Urdu/Arabic (RTL), momentum chart |
| Oct 20 | 5 UI | Debug drawer, recap screen. *Registration closes.* |
| Oct 21 | 5 UI | Player-focus mode, polish, Flutter tests in CI |
| Oct 22 | 6 Deploy | GitHub Pages via Actions; optional Hugging Face Space for live mode |
| Oct 23 | 6 Docs | README, Mermaid diagram, ARCHITECTURE/AGENTS docs, screenshots |
| Oct 24 | 7 Video | Record under 2 minutes, write pitch text |
| Oct 25 | 7 Submit | Submit. Oct 26–27 = buffer |

**Cut order:** 3rd language → player-focus → momentum graph → live hosting → MCP server.
**Never cut:** 5 pipeline stages, 4 agents + Verifier with visible handoffs, fallback, fan vs analyst.
