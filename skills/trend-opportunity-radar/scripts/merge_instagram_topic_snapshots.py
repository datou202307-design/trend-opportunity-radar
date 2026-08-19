from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
from typing import Any

from _common import as_text, load_data, now_iso, write_json


SCHEMA_VERSION = "instagram-topic-merged-snapshot-v0.1"
LAYERS = {"platform_baseline", "category", "subject_bridge"}


def merge_snapshots(paths: list[Path], mode: str = "standard") -> dict[str, Any]:
    if len(paths) < 3:
        raise SystemExit("Instagram standard topic research requires at least three hashtag snapshots.")
    snapshots = [load_data(str(path.resolve())) for path in paths]
    if any(not isinstance(item, dict) or item.get("platform") != "instagram" or item.get("research_scope") != "topic_research" for item in snapshots):
        raise SystemExit("Only Instagram topic_research snapshots can be merged.")
    subjects = {as_text(item.get("subject")).strip().casefold() for item in snapshots}
    if len(subjects) != 1 or "" in subjects:
        raise SystemExit("Instagram topic snapshots must share one non-empty subject.")
    query_keys: set[tuple[str, str]] = set()
    query_runs: list[dict[str, Any]] = []
    merged: dict[str, dict[str, Any]] = {}
    observed_total = 0
    retained_total = 0
    source_audit: list[dict[str, str]] = []
    for path, snapshot in zip(paths, snapshots):
        query = snapshot.get("query") if isinstance(snapshot.get("query"), dict) else {}
        term = as_text(query.get("term"))
        layer = as_text(query.get("layer"))
        if not term or layer not in LAYERS or (term.casefold(), layer) in query_keys:
            raise SystemExit("Every merged Instagram snapshot requires one unique hashtag and valid query layer.")
        query_keys.add((term.casefold(), layer))
        all_signals = [item for item in snapshot.get("signals", []) if isinstance(item, dict)]
        signals = [item for item in all_signals if item.get("detail_captured") is True or bool(as_text(item.get("summary")))]
        counts = ((snapshot.get("collection") or {}).get("counts") or {})
        observed = int(counts.get("observed_result_count") or snapshot.get("raw_sample_count") or len(signals))
        observed_total += observed
        retained_total += len(signals)
        repeatability = (snapshot.get("collection") or {}).get("repeatability") or {}
        query_runs.append({
            "query_term": term,
            "query_layer": layer,
            "observed_result_count": observed,
            "retained_signal_count": len(signals),
            "discarded_result_count": max(0, observed - len(signals)),
            "detail_open_count": sum(1 for item in signals if item.get("detail_captured") is True),
            "repeatability": copy.deepcopy(repeatability),
            "stop_reason": as_text((snapshot.get("collection") or {}).get("terminal_reason")),
        })
        source_audit.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for signal in signals:
            signal_id = as_text(signal.get("signal_id"))
            if not signal_id:
                raise SystemExit("Every Instagram signal requires signal_id before merge.")
            incoming = copy.deepcopy(signal)
            incoming["query_terms"] = sorted(set([*incoming.get("query_terms", []), term]))
            incoming["query_layers"] = sorted(set([*incoming.get("query_layers", []), layer]))
            incoming["query_term"] = incoming["query_terms"][0]
            incoming["query_layer"] = incoming["query_layers"][0]
            if signal_id not in merged:
                merged[signal_id] = incoming
                continue
            current = merged[signal_id]
            if as_text(current.get("canonical_url")) != as_text(incoming.get("canonical_url")):
                raise SystemExit("Duplicate Instagram signal IDs must share one canonical URL.")
            current["query_terms"] = sorted(set([*current.get("query_terms", []), *incoming["query_terms"]]))
            current["query_layers"] = sorted(set([*current.get("query_layers", []), *incoming["query_layers"]]))
            current["evidence_refs"] = list(dict.fromkeys([*current.get("evidence_refs", []), *incoming.get("evidence_refs", [])]))
            current["raw_artifacts"] = list(dict.fromkeys([*current.get("raw_artifacts", []), *incoming.get("raw_artifacts", [])]))
            if incoming.get("detail_captured") is True and current.get("detail_captured") is not True:
                for key in ("source_type", "detail_captured", "title", "summary", "published_at", "metrics", "author", "platform_facts", "limitations"):
                    current[key] = copy.deepcopy(incoming.get(key))
    layers = {run["query_layer"] for run in query_runs}
    if layers != LAYERS:
        raise SystemExit("Instagram standard topic research must include platform_baseline, category, and subject_bridge.")
    signals = list(merged.values())
    detail_count = sum(1 for item in signals if item.get("detail_captured") is True)
    query_summary = " · ".join(run["query_term"] for run in query_runs)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "platform": "instagram",
        "research_scope": "topic_research",
        "subject": snapshots[0]["subject"],
        "query": {"term": query_summary, "layer": "multi_layer", "url": ""},
        "queries": [{"term": run["query_term"], "layer": run["query_layer"]} for run in query_runs],
        "raw_sample_count": observed_total,
        "retained_sample_count": retained_total,
        "unique_sample_count": len(signals),
        "collection": {
            "mode": mode,
            "query_runs": query_runs,
            "counts": {"query_count": len(query_runs), "observed_result_count": observed_total, "unique_signal_count": len(signals), "detail_open_count": detail_count},
            "status": "collection_complete_pending_review",
            "stop_reason": "",
            "limitations": ["Instagram hashtag result surfaces are ranked and may be personalized."],
        },
        "signals": signals,
        "source_snapshots": source_audit,
        "platform_adapter": {"contract_version": "platform-adapter-contract-v0.2", "adapter": "instagram_hashtag_browser_capture", "source_mode": "controlled_capture", "live_collection": True, "research_scope": "topic_research"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge frozen Instagram hashtag snapshots into one auditable multi-layer topic snapshot.")
    parser.add_argument("--snapshot", action="append", required=True)
    parser.add_argument("--mode", choices=["quick", "standard"], default="standard")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    write_json(args.output, merge_snapshots([Path(value) for value in args.snapshot], args.mode))


if __name__ == "__main__":
    main()
