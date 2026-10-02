"""Print cards from a demo bundle for quick quality review.

uv run python scripts/show_cards.py mm-0004-comeback goal 3
uv run python scripts/show_cards.py mm-0004-comeback pressure_surge 0 --lang en
"""

from __future__ import annotations

import argparse
import json
import sys

from matchmind.bake import DEMO_DIR


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("match")
    p.add_argument("kind", help="moment kind prefix, e.g. goal, big_chance, recap")
    p.add_argument("index", type=int, nargs="?", default=0, help="which moment of that kind")
    p.add_argument("--lang")
    args = p.parse_args()

    data = json.loads((DEMO_DIR / f"{args.match}.json").read_text(encoding="utf-8"))
    moments = sorted(
        {c["moment_id"] for c in data["cards"] if c["moment_id"].startswith(args.kind)}
    )
    if not moments:
        sys.exit(f"no {args.kind} moments")
    mid = moments[min(args.index, len(moments) - 1)]
    print(f"== {mid}  ({len(moments)} {args.kind} moments)")
    for c in data["cards"]:
        if c["moment_id"] == mid and (not args.lang or c["language"] == args.lang):
            tag = f"{c['type']}/{c['language']}/{c['audience']}"
            fb = " [fallback]" if c.get("fallback_used") else ""
            print(f"[{tag}]{fb} {c['title']}\n    {c['body']}")
            if c.get("why_it_matters"):
                print(f"    why: {c['why_it_matters']}")


if __name__ == "__main__":
    main()
