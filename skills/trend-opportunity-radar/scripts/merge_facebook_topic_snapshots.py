from __future__ import annotations

import argparse
import copy
import hashlib
from pathlib import Path
from typing import Any

from _common import as_text, load_data, merge_signals, now_iso, write_json


SCHEMA_VERSION = "facebook-topic-merged-snapshot-v0.1"
LAYERS = {"platform_baseline", "category", "subject_bridge"}


def merge_snapshots(paths: list[Path], mode: str = "standard") -> dict[str, Any]:
    if len(paths) < 3:
        raise SystemExit("Facebook standard topic research requires at least three frozen query snapshots.")
    snapshots = [load_data(str(path.resolve())) for path in paths]
    if any(not isinstance(item, dict) or item.get("platform") != "facebook" or item.get("research_scope") != "topic_research" for item in snapshots):
        raise SystemExit("Only Facebook topic_research snapshots can be merged.")
    subjects = {as_text(item.get("subject")).strip().casefold() for item in snapshots}
    if len(subjects) != 1 or "" in subjects:
        raise SystemExit("Facebook topic snapshots must share one non-empty subject.")

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
        key = (term.casefold(), layer)
        if not term or layer not in LAYERS or key in query_keys:
            raise SystemExit("Every merged Facebook snapshot requires one unique query and valid query layer.")
        query_keys.add(key)
        signals = [copy.deepcopy(item) for item in snapshot.get("signals", []) if isinstance(item, dict) and (item.get("detail_captured") is True or bool(as_text(item.get("summary"))))]
        counts = ((snapshot.get("collection") or {}).get("counts") or {})
        observed = int(counts.get("observed_result_count") or snapshot.get("raw_sample_count") or len(signals))
        observed_total += observed
        retained_total += len(signals)
        repeatability = copy.deepcopy((snapshot.get("collection") or {}).get("repeatability") or {})
        query_runs.append({
            "query_term": term,
            "query_layer": layer,
            "observed_result_count": observed,
            "retained_signal_count": len(signals),
            "discarded_result_count": max(0, observed - len(signals)),
            "detail_open_count": sum(1 for item in signals if item.get("detail_captured") is True),
            "repeatability": repeatability,
            "stop_reason": as_text((snapshot.get("collection") or {}).get("terminal_reason")),
        })
        source_audit.append({"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        for signal in signals:
            signal_id = as_text(signal.get("signal_id"))
            if not signal_id:
                raise SystemExit("Every Facebook signal requires signal_id before merge.")
            signal["query_terms"] = sorted(set([*signal.get("query_terms", []), term]))
            signal["query_layers"] = sorted(set([*signal.get("query_layers", []), layer]))
            if signal_id not in merged:
                merged[signal_id] = signal
                continue
            current = merged[signal_id]
            if as_text(current.get("canonical_url")) != as_text(signal.get("canonical_url")):
                raise SystemExit("Duplicate Facebook signal IDs must share one canonical URL.")
            combined = merge_signals(current, signal)
            combined["query_terms"] = sorted(set([*current.get("query_terms", []), *signal.get("query_terms", [])]))
            combined["query_layers"] = sorted(set([*current.get("query_layers", []), *signal.get("query_layers", [])]))
            merged[signal_id] = combined

    if {run["query_layer"] for run in query_runs} != LAYERS:
        raise SystemExit("Facebook standard topic research must include platform_baseline, category, and subject_bridge.")
    signals = list(merged.values())
    detail_count = sum(1 for item in signals if item.get("detail_captured") is True)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "platform": "facebook",
        "research_scope": "topic_research",
        "query_id": "facebook-multilayer",
        "subject": snapshots[0]["subject"],
        "query": {"term": " · ".join(run["query_term"] for run in query_runs), "layer": "multi_layer", "url": ""},
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
            "limitations": ["Facebook Posts search is ranked, personalized, and not an exhaustive or chronological corpus."],
        },
        "signals": signals,
        "source_snapshots": source_audit,
        "platform_adapter": {"contract_version": "platform-adapter-contract-v0.2", "adapter": "facebook_posts_browser_capture", "source_mode": "controlled_capture", "live_collection": True, "research_scope": "topic_research"},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge frozen Facebook Posts snapshots into one auditable multi-layer topic snapshot.")
    parser.add_argument("--snapshot", action="append", required=True)
    parser.add_argument("--mode", choices=["quick", "standard"], default="standard")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    write_json(args.output, merge_snapshots([Path(value) for value in args.snapshot], args.mode))


if __name__ == "__main__":
    main()
