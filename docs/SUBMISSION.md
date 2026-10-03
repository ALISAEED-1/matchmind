# Submission kit

Everything needed for the hackathon submission form. Items marked **(you)** need you.

- **Repository:** https://github.com/ALISAEED-1/matchmind
- **Live demo (no install, no keys):** https://alisaeed-1.github.io/matchmind/
- **Demo video (you):** record from [DEMO_SCRIPT.md](DEMO_SCRIPT.md), upload to YouTube or Vimeo (unlisted is fine), paste the link in the form.
- **Category:** Best Multi-Agent Orchestration

## Pitch (about 150 words)

MatchMind is an AI broadcast booth for football. A team of specialised agents, orchestrated with
the **Microsoft Agent Framework**, turns a live stream of match events into explainable match
intelligence: a Stats agent computes every number in code through an **MCP** server; a Producer
routes each moment by importance; Insight, Narrator and Personalizer agents explain why the moment
matters, commentate, and rewrite every card for fans or analysts in English, Urdu and Arabic. A
deterministic Verifier checks every answer against the facts, so no statistic is ever invented.
When models fail, the system recovers visibly: corrective retries, fallback across models down
to **Microsoft Foundry Local** on-device, verified template cards, and a circuit breaker. Every
handoff is logged and shown in a debug drawer. The output is a set of timed, machine-readable
overlay cards that can sit on screen alongside the match. All data is synthetic, from a seeded
match generator with calibrated metrics.

## Microsoft technology used

- **Microsoft Agent Framework (Python):** the orchestration workflow (executors, switch-case
  routing, shared state), every LLM agent (`Agent` with structured output), and the MCP client
  (`MCPStdioTool`)
- **Microsoft Foundry Local:** on-device model (`qwen2.5-1.5b`) in the provider chain, via the
  Foundry Local SDK
- **Model Context Protocol:** the stats engine as an MCP server usable by any MCP client
- **GitHub Actions:** CI (Python lint and tests, Flutter analyze and tests) and the Pages deployment
- Google Gemini's free API is used first in the chain for text quality; Foundry Local is the
  local fallback

## Problem it solves

Broadcast graphics today show *what* happened (possession 61%) but rarely *why it matters*, and
they're one-size-fits-all. MatchMind explains moments (pressure shifts, momentum swings, control
vs chaos), personalises them per viewer (casual fan vs analyst, three languages, favourite club
and player), and does it with guaranteed-accurate numbers and graceful failure, which is what a
live production system needs.

## Testing instructions for judges

**Fastest (about 2 minutes, browser only):**
1. Open https://alisaeed-1.github.io/matchmind/ in Chrome or Edge.
2. Pick **Rivermouth Rovers v Ironmere Athletic** (a comeback) and press **Kick off**.
   Speed is set to 30x by default; change it with the tune icon.
3. Switch **Fan / Analyst / Player focus** at any time: the same moment re-renders for each audience.
4. Open **tune** → set language to **اردو** or **العربية**, pick a favourite club or player.
5. Open the **hub** icon (top right) to see the agent handoffs, retries and fallbacks.
6. Use **Skip to full time** → **Read the recap**.

Shortcut links:
- Analyst view at the 72' equaliser: https://alisaeed-1.github.io/matchmind/?match=mm-0004-comeback&seek=74.6&audience=analyst
- Urdu fan of Ironmere at their 35' goal: https://alisaeed-1.github.io/matchmind/?match=mm-0004-comeback&seek=34.3&lang=ur&club=IRN

(`seek` is minutes of play since kickoff, including first-half stoppage time.)
- Agent handoff drawer: https://alisaeed-1.github.io/matchmind/?match=mm-0003-red_card&seek=40&audience=analyst&drawer=1
- Recap: https://alisaeed-1.github.io/matchmind/?match=mm-0020-late_winner&recap=1

**Live agents (optional, about 10 minutes, Windows/macOS/Linux):**
1. Install [uv](https://docs.astral.sh/uv/). Optional: a free Gemini key in `.env`, or install
   Foundry Local (`winget install Microsoft.FoundryLocal`) for fully local inference.
2. `cd backend && uv sync && uv run uvicorn matchmind.api.app:app`
3. In the web app choose **Live agents**, backend URL `http://127.0.0.1:8000`, pick a match.
   The agent team now runs while you watch. Open the hub drawer and flip
   **Simulate model outage** to watch the recovery path live.
4. Tests: `cd backend && uv run pytest -q` (145+ tests, about 1 minute).
