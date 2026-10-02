"""Synthetic match generator: fictional clubs, seeded simulation, story presets."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from matchmind.config import REPO_ROOT
from matchmind.generator.clubs import build_league
from matchmind.generator.simulator import GENERATOR_VERSION, generate_match
from matchmind.generator.stories import Story
from matchmind.models import Match

MATCHES_DIR = REPO_ROOT / "data" / "matches"
SCHEMA_PATH = REPO_ROOT / "docs" / "schema" / "match.schema.json"

__all__ = [
    "GENERATOR_VERSION",
    "MATCHES_DIR",
    "SCHEMA_PATH",
    "SHIPPED_MATCHES",
    "Story",
    "build_league",
    "generate",
    "generate_match",
    "write_match",
    "match_json_schema",
]


def match_json_schema() -> str:
    """JSON Schema (draft 2020-12) for a match file, generated from the Pydantic models."""
    schema = Match.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "MatchMind synthetic match"
    return json.dumps(schema, indent=2) + "\n"


@dataclass(frozen=True)
class MatchSpec:
    seed: int
    story: Story
    home: str
    away: str


# The three matches committed under data/matches.
SHIPPED_MATCHES = (
    MatchSpec(4, Story.COMEBACK, "RIV", "IRN"),
    MatchSpec(3, Story.RED_CARD, "KES", "DUN"),
    MatchSpec(20, Story.LATE_WINNER, "DUN", "RIV"),
)


def generate(seed: int, story: Story = Story.NONE, home: str = "RIV", away: str = "IRN") -> Match:
    league = build_league()
    if home == away:
        raise ValueError("home and away must be different clubs")
    return generate_match(league[home], league[away], seed, story)


def write_match(match: Match, out_dir: Path = MATCHES_DIR) -> Path:
    """Write a match as JSON: readable metadata, then one event per line (diff-friendly)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{match.meta.match_id}.json"
    meta = json.dumps(match.meta.model_dump(mode="json"), indent=2, ensure_ascii=False)
    events = ",\n".join(
        "    " + json.dumps(e.model_dump(mode="json", exclude_defaults=True), ensure_ascii=False)
        for e in match.events
    )
    body = (
        "{\n"
        f'  "schema_version": "{match.schema_version}",\n'
        f'  "meta": {meta.replace(chr(10), chr(10) + "  ")},\n'
        '  "events": [\n'
        f"{events}\n"
        "  ]\n"
        "}\n"
    )
    path.write_text(body, encoding="utf-8", newline="\n")
    return path
