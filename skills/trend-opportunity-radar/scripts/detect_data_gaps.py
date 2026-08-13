from __future__ import annotations

import argparse
from collections import defaultdict

from _common import calculate_index, load_data, now_iso, write_json


RECOMMENDATIONS = {
    "content_volume": "Record the observed result count for the same query and snapshot window.",
    "engagement": "Open direct details and capture the platform-visible metrics at one recorded timestamp.",
    "velocity": "Repeat the same query, source, filters, and capture method in a comparable later window.",
    "diffusion": "Capture stable direct-post author identifiers; diffusion is derived at topic level.",
    "search_demand": "Use an authorized search-volume source or record search demand as unavailable; do not infer it from engagement.",
    "freshness": "Open direct details and record the content publication time, not the collection time.",
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
    collection = snapshot.get("collection", {})
    if collection.get("contract_status") != "met":
        failed = [name for name, passed in collection.get("contract_checks", {}).items() if not passed]
        tasks.append({
            "field": "collection.sampling_contract",
            "affected_signal_ids": [],
            "priority": "high",
            "recommended_action": f"Resume only the failed gates and layers, preserving this snapshot. Failed checks: {', '.join(failed) or 'untracked ledger'}. Layer stats: {collection.get('layer_stats', {})}.",
            "reuse_prior_snapshot": True,
            "stop_condition": "Contract is met, or a platform/access stop reason is recorded.",
        })
    for layer, stats in collection.get("layer_stats", {}).items():
        if stats.get("detail_open_count", 0) < collection.get("sampling_contract", {}).get("layer_detail_min", 0):
            tasks.append({
                "field": f"collection.layer.{layer}.detail_opens",
                "affected_signal_ids": [],
                "priority": "high",
                "recommended_action": f"Reopen direct results for the existing {layer} queries until the per-layer detail minimum is met.",
                "reuse_prior_snapshot": True,
                "stop_condition": "Layer detail minimum is met or an access stop reason is recorded.",
            })
    bridge = collection.get("layer_stats", {}).get("subject_bridge", {})
    if bridge.get("direct_relevance_count", 0) < collection.get("sampling_contract", {}).get("subject_bridge_direct_min", 0):
        tasks.append({
            "field": "collection.layer.subject_bridge.direct_relevance",
            "affected_signal_ids": [],
            "priority": "high",
            "recommended_action": "Collect and open subject-bridge results that directly match the subject-to-task transition; label semantic_relevance explicitly.",
            "reuse_prior_snapshot": True,
            "stop_condition": "Subject-bridge direct-evidence minimum is met or the bridge hypothesis is rejected.",
        })
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
