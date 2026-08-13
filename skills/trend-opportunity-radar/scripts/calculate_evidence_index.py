from __future__ import annotations

import argparse
from collections import defaultdict

from _common import calculate_index, calculate_topic_index, load_data, now_iso, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate evidence heat indices without redistributing missing weights.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = load_data(args.input)
    signals = snapshot.get("signals", [])
    groups: dict[str, list[dict]] = defaultdict(list)
    for signal in signals:
        signal["evidence_index"] = calculate_index(signal)
        key = signal.get("topic_key") or f"{signal.get('query_layer', 'unspecified')}:{signal.get('query_term') or signal.get('signal_id')}"
        groups[key].append(signal)
    topics = []
    audits = {item.get("topic_key"): item for item in snapshot.get("cluster_audits", []) if isinstance(item, dict)}
    clustering_applied = bool((snapshot.get("clustering") or {}).get("applied"))
    for key, members in groups.items():
        topic_index = calculate_topic_index(
            members,
            collection=snapshot.get("collection"),
            cluster_audit=audits.get(key),
            clustering_applied=clustering_applied,
        )
        refs = list(dict.fromkeys(ref for member in members for ref in member.get("evidence_refs", [])))
        comparable = any(((member.get("time_series") or {}).get("comparison_count") or 0) >= 2 for member in members)
        topics.append({
            "topic_key": key,
            "title": (audits.get(key) or {}).get("title") or next((member.get("title") for member in members if member.get("title")), key),
            "platform": snapshot.get("platform"),
            "status": "comparable" if comparable else "snapshot",
            **topic_index,
            "sample_count": len(members),
            "evidence_refs": refs,
        })
    topics.sort(key=lambda item: (-item["evidence_confidence"], -item["observed_heat"], item["topic_key"]))
    snapshot["scored_at"] = now_iso()
    snapshot["topics"] = topics
    write_json(args.output, snapshot)


if __name__ == "__main__":
    main()
