from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _common import as_text, load_data, write_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize an explicit cluster plan from reviewed topic keys without changing semantic decisions."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    snapshot = load_data(Path(args.input))
    config = load_data(Path(args.config))
    signals = snapshot.get("signals", []) if isinstance(snapshot, dict) else []
    cluster_specs = config.get("clusters", []) if isinstance(config, dict) else []
    if not isinstance(signals, list) or not signals:
        raise SystemExit("Input requires a non-empty signals array.")
    if not isinstance(cluster_specs, list) or not cluster_specs:
        raise SystemExit("Config requires a non-empty clusters array.")

    topic_to_cluster: dict[str, int] = {}
    fallback_index: int | None = None
    clusters: list[dict[str, Any]] = []
    for index, spec in enumerate(cluster_specs):
        if not isinstance(spec, dict):
            raise SystemExit("Every cluster config must be an object.")
        required = ("topic_key", "title", "analysis_unit_statement", "inclusion_rule", "exclusion_rule")
        if any(not as_text(spec.get(field)) for field in required):
            raise SystemExit("Every cluster config must define its reader-facing contract.")
        source_keys = spec.get("source_topic_keys", [])
        if not isinstance(source_keys, list):
            raise SystemExit("source_topic_keys must be an array.")
        if spec.get("fallback") is True:
            if fallback_index is not None:
                raise SystemExit("Only one fallback cluster is allowed.")
            fallback_index = index
        for source_key in source_keys:
            key = as_text(source_key)
            if not key or key in topic_to_cluster:
                raise SystemExit("Each non-empty source topic key can map to only one cluster.")
            topic_to_cluster[key] = index
        cluster = {key: spec[key] for key in required}
        cluster["assignments"] = []
        clusters.append(cluster)

    for signal in signals:
        signal_id = as_text(signal.get("signal_id"))
        source_topic = as_text(signal.get("topic_key"))
        target_index = topic_to_cluster.get(source_topic, fallback_index)
        if not signal_id or target_index is None:
            raise SystemExit(f"Signal lacks an explicit cluster mapping: {signal_id or '<missing-id>'}")
        relevance = as_text(signal.get("semantic_relevance"))
        evidence_role = as_text(signal.get("evidence_role"))
        if relevance == "weak":
            fit = "supporting"
            transition_match = False
            reason = "独立语义审查已判定为关键词碰撞或无法回答当前决策问题。"
        else:
            fit = "counter" if evidence_role == "counter" else ("core" if relevance == "direct" else "supporting")
            transition_match = True
            role = as_text(signal.get("profile_evidence_role")) or "目标相关证据"
            reason = f"独立语义审查将其判为{relevance}相关，并归入 {source_topic}；目标证据角色为 {role}。"
        clusters[target_index]["assignments"].append({
            "signal_id": signal_id,
            "fit": fit,
            "reason": reason,
            "task_transition_match": transition_match,
        })

    write_json(Path(args.output), {"clusters": clusters})


if __name__ == "__main__":
    main()
