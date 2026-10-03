"""Bake 'Ask MatchMind' answers (GitHub Copilot agent + MCP tools) into the demo bundles.

Demo Mode has no backend, so a few questions per match are answered ahead of time
and shown as suggested questions with Copilot's answers.

Run from backend/:  uv run python scripts/bake_qa.py [match_id ...]
"""

from __future__ import annotations

import asyncio
import json
import sys

from matchmind.agents.ask import AskMatchMind
from matchmind.bake import CACHE_DIR, DEMO_DIR
from matchmind.cards import Language
from matchmind.config import load_settings
from matchmind.generator import MATCHES_DIR
from matchmind.llm.gateway import LLMGateway, ResponseCache
from matchmind.models import Match

FT = None  # full time

# match_id -> [(minutes of play, question, language)]
QUESTIONS: dict[str, list[tuple[float | None, str, Language]]] = {
    "mm-0004-comeback": [
        (48.1, "Why are Ironmere Athletic ahead at half time?", Language.EN),
        (75.0, "What changed for Rivermouth Rovers in the second half?", Language.EN),
        (FT, "How did Rivermouth Rovers come back to win?", Language.EN),
        (FT, "میچ کا بہترین کھلاڑی کون تھا اور کیوں؟", Language.UR),
    ],
    "mm-0003-red_card": [
        (31.5, "How does the red card change this match?", Language.EN),
        (FT, "How did Duncairn Harbour turn the game around?", Language.EN),
        (FT, "ما الذي غيّره الطرد في هذه المباراة؟", Language.AR),
    ],
    "mm-0020-late_winner": [
        (49.0, "Who is on top at half time, and why?", Language.EN),
        (FT, "How was the late winner created?", Language.EN),
        (FT, "Was the result fair, judging by the chances?", Language.EN),
    ],
}


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    wanted = sys.argv[1:] or list(QUESTIONS)
    asker = AskMatchMind(
        gateway=LLMGateway.from_settings(load_settings(), ResponseCache(CACHE_DIR))
    )
    for match_id in wanted:
        match = Match.load(MATCHES_DIR / f"{match_id}.json")
        path = DEMO_DIR / f"{match_id}.json"
        bundle = json.loads(path.read_text(encoding="utf-8"))
        answers = []
        for minutes, question, lang in QUESTIONS[match_id]:
            until = None if minutes is None else int(minutes * 60_000)
            a = await asker.ask(match, question, until, lang)
            answers.append(a.model_dump(mode="json"))
            tag = "FALLBACK " if a.fallback_used else ""
            secs = a.latency_ms / 1000
            print(f"[{match_id} {a.minute}] {tag}{a.provider} {secs:.0f}s tools={a.tools_used}")
            print(f"   Q: {question}\n   A: {a.answer}\n", flush=True)
        bundle["qa"] = answers
        path.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
