"""CLI: generate synthetic matches.

Examples (from backend/):
    uv run python -m matchmind.generator --seed 7 --story comeback
    uv run python -m matchmind.generator --seed 3 --home KES --away RIV
    uv run python -m matchmind.generator --shipped      # regenerate data/matches
    uv run python -m matchmind.generator --schema       # regenerate the JSON Schema
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from matchmind.generator import (
    MATCHES_DIR,
    SCHEMA_PATH,
    SHIPPED_MATCHES,
    Story,
    generate,
    match_json_schema,
    write_match,
)
from matchmind.generator.clubs import CLUB_SPECS
from matchmind.models import EventType, Match


def summarize(match: Match) -> str:
    counts = Counter(e.type for e in match.events)
    passes = [e for e in match.events if e.type is EventType.PASS]
    completed = sum(e.outcome == "complete" for e in passes)
    m = match.meta
    return (
        f"{m.match_id}: {m.home.name} {m.final_score.home}-{m.final_score.away} {m.away.name} | "
        f"events={len(match.events)} passes={len(passes)} "
        f"completion={completed / max(1, len(passes)):.0%} shots={counts[EventType.SHOT]} "
        f"cards={counts[EventType.CARD]} subs={counts[EventType.SUBSTITUTION]}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m matchmind.generator",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--story", choices=[s.value for s in Story], default=Story.NONE.value)
    parser.add_argument("--home", choices=sorted(CLUB_SPECS), default="RIV")
    parser.add_argument("--away", choices=sorted(CLUB_SPECS), default="IRN")
    parser.add_argument("--out", type=Path, default=MATCHES_DIR)
    parser.add_argument("--shipped", action="store_true", help="regenerate the committed matches")
    parser.add_argument("--schema", action="store_true", help="write docs/schema/match.schema.json")
    args = parser.parse_args()

    if args.schema:
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_text(match_json_schema(), encoding="utf-8", newline="\n")
        print(f"schema -> {SCHEMA_PATH}")
        return

    specs = (
        [(s.seed, s.story, s.home, s.away) for s in SHIPPED_MATCHES]
        if args.shipped
        else [(args.seed, Story(args.story), args.home, args.away)]
    )
    for seed, story, home, away in specs:
        match = generate(seed, story, home, away)
        path = write_match(match, args.out)
        print(summarize(match))
        print(f"  -> {path}")


if __name__ == "__main__":
    main()
