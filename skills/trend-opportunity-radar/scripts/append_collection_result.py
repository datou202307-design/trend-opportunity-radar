from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _common import SAMPLING_CONTRACTS, as_number, as_text, load_data, now_iso, stable_signal_identity, write_json


def signal_key(signal: dict[str, Any], platform: str = "") -> str:
    return stable_signal_identity(signal, platform)


def resolve_artifact(value: str, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def validate_artifact_ledger(query: dict[str, Any], base: Path) -> None:
    raw_artifacts = query.get("raw_artifacts", [])
    executions = query.get("capture_executions", [])
    if not isinstance(raw_artifacts, list) or not isinstance(executions, list):
        raise SystemExit("raw_artifacts and capture_executions must be arrays.")
    for value in raw_artifacts:
        if not as_text(value) or not resolve_artifact(as_text(value), base).is_file():
            raise SystemExit("Every raw_artifacts entry must reference an existing file.")
    for execution in executions:
        if not isinstance(execution, dict):
            raise SystemExit("Every capture execution must be an object.")
        for field in ("stdout_artifact", "stderr_artifact", "metadata_artifact"):
            value = as_text(execution.get(field))
            if not value or not resolve_artifact(value, base).is_file():
                raise SystemExit(f"Every capture execution must preserve an existing {field} file.")


def append_query_result(
    target: Path,
    query_result: Path,
    platform: str,
    source_mode: str,
    mode: str,
    final_stop_reason: str = "",
) -> dict[str, Any]:
    snapshot = load_data(str(target)) if target.exists() else {
        "schema_version": "trend-raw-snapshot-v0.2",
        "platform": platform,
        "source_mode": source_mode,
        "captured_at": now_iso(),
        "collection": {"mode": mode, "query_runs": [], "counts": {}, "stop_reason": "collection_in_progress", "limitations": []},
        "signals": [],
    }
    if snapshot.get("platform") != platform:
        raise SystemExit("Snapshot platform does not match --platform.")
    if snapshot.get("source_mode", source_mode) != source_mode:
        raise SystemExit("Snapshot source mode does not match --source-mode.")

    query = load_data(str(query_result))
    if not isinstance(query, dict):
        raise SystemExit("Query result must be a JSON object.")
    validate_artifact_ledger(query, query_result.parent)
    query_term = as_text(query.get("query_term"))
    query_layer = as_text(query.get("query_layer"))
    query_intent = as_text(query.get("query_intent"))
    query_id = as_text(query.get("query_id"))
    if not query_term or query_layer not in {"platform_baseline", "category", "subject_bridge"}:
        raise SystemExit("Query result requires query_term and a valid query_layer.")
    existing_runs = snapshot.setdefault("collection", {}).setdefault("query_runs", [])
    if any(
        (query_id and as_text(item.get("query_id")) == query_id)
        or (not query_id and item.get("query_term") == query_term and item.get("query_layer") == query_layer)
        for item in existing_runs
    ):
        raise SystemExit("This query already exists in the snapshot; do not double-count it.")
    signals = query.get("signals", [])
    if not isinstance(signals, list) or any(not isinstance(item, dict) for item in signals):
        raise SystemExit("Query result signals must be a JSON array of objects.")
    observed = as_number(query.get("observed_result_count"))
    if observed is None or observed < len(signals):
        raise SystemExit("observed_result_count must be at least the number of retained signals.")
    detail_count = int(as_number(query.get("detail_open_count")) or sum(1 for item in signals if item.get("detail_captured")))
    run = {
        "query_id": query_id,
        "query_term": query_term,
        "query_layer": query_layer,
        "query_intent": query_intent,
        "observed_result_count": int(observed),
        "retained_signal_count": len(signals),
        "relevant_signal_count": int(as_number(query.get("relevant_signal_count")) or sum(1 for item in signals if item.get("semantic_relevance") in {"direct", "adjacent"})),
        "retention_rate": float(as_number(query.get("retention_rate")) or round(len(signals) / max(int(observed), 1), 3)),
        "relevant_yield_rate": float(as_number(query.get("relevant_yield_rate")) or round(sum(1 for item in signals if item.get("semantic_relevance") in {"direct", "adjacent"}) / max(int(observed), 1), 3)),
        "low_yield": bool(query.get("low_yield")),
        "detail_open_count": detail_count,
        "discarded_result_count": int(observed) - len(signals),
        "stop_reason": as_text(query.get("stop_reason")),
        "outcome": as_text(query.get("outcome")) or ("completed_with_zero_results" if int(observed) == 0 else "completed_with_results"),
        "raw_artifacts": query.get("raw_artifacts", []) if isinstance(query.get("raw_artifacts", []), list) else [],
        "capture_executions": query.get("capture_executions", []) if isinstance(query.get("capture_executions", []), list) else [],
        "recorded_at": now_iso(),
    }
    existing_runs.append(run)
    for signal in signals:
        signal.setdefault("query_term", query_term)
        signal.setdefault("query_layer", query_layer)
        signal.setdefault("query_intent", query_intent)
        signal.setdefault("platform", platform)
        signal.setdefault("source_mode", source_mode)
    snapshot.setdefault("signals", []).extend(signals)

    all_signals = snapshot["signals"]
    unique_keys = {signal_key(item, platform) for item in all_signals}
    counts = {
        "query_count": len(existing_runs),
        "observed_result_count": sum(int(item["observed_result_count"]) for item in existing_runs),
        "retained_sample_count": len(all_signals),
        "unique_sample_count": len(unique_keys),
        "duplicate_count": len(all_signals) - len(unique_keys),
        "discarded_result_count": sum(int(item["discarded_result_count"]) for item in existing_runs),
        "detail_open_count": sum(int(item["detail_open_count"]) for item in existing_runs),
        "counter_signal_count": len({signal_key(item, platform) for item in all_signals if item.get("evidence_role") == "counter"}),
    }
    snapshot["collection"]["mode"] = mode
    snapshot["collection"]["counts"] = counts
    snapshot["collection"]["stop_reason"] = final_stop_reason or "collection_in_progress"
    snapshot["raw_sample_count"] = counts["observed_result_count"]
    snapshot["retained_sample_count"] = counts["retained_sample_count"]
    snapshot["unique_sample_count"] = counts["unique_sample_count"]
    write_json(str(target), snapshot)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Atomically append one completed query to the canonical raw signal snapshot.")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--query-result", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--source-mode", required=True)
    parser.add_argument("--mode", default="standard", choices=sorted(SAMPLING_CONTRACTS))
    parser.add_argument("--final-stop-reason", default="")
    args = parser.parse_args()
    append_query_result(
        Path(args.snapshot), Path(args.query_result), args.platform, args.source_mode, args.mode, args.final_stop_reason
    )


if __name__ == "__main__":
    main()
