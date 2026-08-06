from __future__ import annotations

import argparse

from _common import SCHEMA_VERSION, SOURCE_MODES, load_data, normalize_platform, normalize_signal, now_iso, write_json


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
    deduped = list({signal["dedupe_hash"]: signal for signal in normalized}.values())
    platforms = sorted({signal["platform"] for signal in deduped if signal["platform"]})
    if len(platforms) > 1:
        raise SystemExit("A snapshot must contain exactly one platform. Split multi-platform input before analysis.")
    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": captured_at,
        "platform": platforms[0] if platforms else platform,
        "raw_sample_count": len(rows),
        "unique_sample_count": len(deduped),
        "signals": deduped,
    }
    write_json(args.output, result)


if __name__ == "__main__":
    main()

