from __future__ import annotations

import argparse

from _common import (
    SCHEMA_VERSION,
    SOURCE_MODES,
    as_text,
    load_data,
    normalize_collection,
    merge_signals,
    normalize_platform,
    normalize_signal,
    now_iso,
    write_json,
)
from platform_adapter_contract import CONTRACT_VERSION as ADAPTER_CONTRACT_VERSION, SCHEMA_VERSION as ADAPTER_REGISTRY_VERSION, adapter_capability


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize platform signals from JSON or CSV.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--platform", default="")
    parser.add_argument("--source-mode", default="customer_export", choices=sorted(SOURCE_MODES))
    args = parser.parse_args()
    raw = load_data(args.input)
    rows = raw.get("signals", raw.get("items", [])) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise SystemExit("Input must be a JSON list, a JSON object with signals/items, or a CSV file.")
    captured_at = now_iso()
    platform = normalize_platform(args.platform or (raw.get("platform", "") if isinstance(raw, dict) else ""))
    normalized = [normalize_signal(row, platform, args.source_mode, captured_at) for row in rows if isinstance(row, dict)]
    merged: dict[str, dict] = {}
    for signal in normalized:
        key = signal["dedupe_hash"]
        merged[key] = merge_signals(merged[key], signal) if key in merged else signal
    deduped = list(merged.values())
    platforms = sorted({signal["platform"] for signal in deduped if signal["platform"]})
    if len(platforms) > 1:
        raise SystemExit("A snapshot must contain exactly one platform. Split multi-platform input before analysis.")
    collection = normalize_collection(raw, len(rows), len(deduped), deduped)
    adapter_audit = None
    if args.source_mode == "customer_export":
        capability = adapter_capability("structured_import", platforms[0] if platforms else platform)
        if capability is None:
            raise SystemExit("Structured import is not registered for this platform.")
        adapter_audit = {
            "adapter": "structured_import",
            "source_mode": capability["source_mode"],
            "contract_version": ADAPTER_CONTRACT_VERSION,
            "registry_version": ADAPTER_REGISTRY_VERSION,
            "live_collection": False,
        }
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": captured_at,
        "platform": platforms[0] if platforms else platform,
        "raw_sample_count": collection["counts"]["observed_result_count"],
        "retained_sample_count": len(rows),
        "unique_sample_count": len(deduped),
        "collection": collection,
        **({"adapter": as_text(raw.get("adapter"))} if isinstance(raw, dict) and as_text(raw.get("adapter")) else {}),
        **({"platform_adapter": adapter_audit} if adapter_audit else ({"platform_adapter": raw.get("platform_adapter")} if isinstance(raw, dict) and isinstance(raw.get("platform_adapter"), dict) else {})),
        "signals": deduped,
    }
    write_json(args.output, result)


if __name__ == "__main__":
    main()
