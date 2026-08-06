from __future__ import annotations

import argparse
from collections import defaultdict

from _common import calculate_index, load_data, now_iso, write_json


RECOMMENDATIONS = {
    "content.observed_content_count": "Record the visible result count or the number of observed qualifying items.",
    "metrics.views_likes_saves_comments_shares": "Capture the platform-visible metrics using the same source and time window.",
    "time_series.current_and_previous_window": "Repeat the same query with the same source in a comparable later window.",
    "author.unique_author_count": "Capture stable author identifiers so diffusion can be measured.",
    "search.volume_rank_or_result_count": "Capture search rank, result count, search index, or an explicitly unavailable status.",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate gap-fill tasks for sparse platform evidence.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = load_data(args.input)
    by_field: dict[str, list[str]] = defaultdict(list)
    for signal in snapshot.get("signals", []):
        index = signal.get("evidence_index") or calculate_index(signal)
        for field in index.get("missing_fields", []):
            by_field[field].append(signal.get("signal_id", "unknown"))
    tasks = []
    for field, signal_ids in sorted(by_field.items(), key=lambda item: (-len(item[1]), item[0])):
        tasks.append({
            "field": field,
            "affected_signal_ids": signal_ids,
            "priority": "high" if len(signal_ids) == len(snapshot.get("signals", [])) else "medium",
            "recommended_action": RECOMMENDATIONS.get(field, "Collect the missing field without replacing prior snapshots."),
            "reuse_prior_snapshot": True,
            "stop_condition": "Field collected with a stable source, or source limitation recorded as unavailable.",
        })
    write_json(args.output, {
        "schema_version": "trend-data-gaps-v0.1",
        "generated_at": now_iso(),
        "platform": snapshot.get("platform"),
        "task_count": len(tasks),
        "tasks": tasks,
    })


if __name__ == "__main__":
    main()

