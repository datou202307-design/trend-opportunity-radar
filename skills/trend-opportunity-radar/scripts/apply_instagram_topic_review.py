from __future__ import annotations

import argparse
from pathlib import Path

from _common import load_data, write_json
from apply_semantic_review import apply_review


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply an Agent semantic review to an Instagram topic snapshot without changing raw capture evidence.")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = load_data(str(Path(args.snapshot).resolve()))
    review = load_data(str(Path(args.review).resolve()))
    if not isinstance(snapshot, dict) or snapshot.get("platform") != "instagram" or snapshot.get("research_scope") != "topic_research":
        raise SystemExit("Instagram topic review requires a topic_research snapshot.")
    write_json(args.output, apply_review(snapshot, review))


if __name__ == "__main__":
    main()
