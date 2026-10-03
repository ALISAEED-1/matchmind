"""Copy matches and demo bundles into the Flutter app's assets (Demo Mode needs no backend).

Run from backend/:  uv run python scripts/export_web_data.py
Writes frontend/assets/data/{index.json, matches/*.json, demo/*.json}.
"""

from __future__ import annotations

import json
import shutil

from matchmind.bake import DEMO_DIR
from matchmind.config import REPO_ROOT
from matchmind.generator import MATCHES_DIR
from matchmind.models import Match

OUT = REPO_ROOT / "frontend" / "assets" / "data"
STORY_TITLES = {
    "comeback": "A comeback for the ages?",
    "red_card": "Ten men, one big test",
    "late_winner": "Decided at the death?",
    "none": "Matchday",
}


def main() -> None:
    for sub in ("matches", "demo"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    index = []
    for demo in sorted(DEMO_DIR.glob("*.json")):
        match_path = MATCHES_DIR / demo.name
        meta = Match.load(match_path).meta
        shutil.copyfile(match_path, OUT / "matches" / demo.name)
        shutil.copyfile(demo, OUT / "demo" / demo.name)
        index.append(
            {
                "match_id": meta.match_id,
                "title": STORY_TITLES.get(meta.story, "Matchday"),
                "story": meta.story,
                "home": meta.home.name,
                "away": meta.away.name,
                "venue": meta.venue,
            }
        )
    (OUT / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"exported {len(index)} matches -> {OUT}")


if __name__ == "__main__":
    main()
