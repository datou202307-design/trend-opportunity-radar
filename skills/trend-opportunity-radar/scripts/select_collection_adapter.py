from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from platform_adapter_contract import controlled_capture_preference, normalize_platform, status_supports


SCHEMA_VERSION = "collection-adapter-selection-v0.1"
def normalized_platform(value: str) -> str:
    return normalize_platform(value)


def select_adapter(platform: str, statuses: list[dict[str, Any]]) -> dict[str, Any]:
    platform_key = normalized_platform(platform)
    by_adapter = {
        str(item.get("adapter", "")).casefold(): item
        for item in statuses
        if isinstance(item, dict)
    }
    preference = controlled_capture_preference(platform_key)
    rejected: list[dict[str, str]] = []
    selected = ""
    selected_status: dict[str, Any] = {}
    for adapter in preference:
        status = by_adapter.get(adapter)
        if not status:
            rejected.append({"adapter": adapter, "reason": "preflight_missing"})
            continue
        if status.get("ready") is not True or status.get("status") != "ready":
            rejected.append({"adapter": adapter, "reason": str(status.get("status") or "not_ready")})
            continue
        if not status_supports(status, platform_key):
            rejected.append({"adapter": adapter, "reason": "platform_not_validated"})
            continue
        selected = adapter
        selected_status = status
        break
    return {
        "schema_version": SCHEMA_VERSION,
        "platform": platform_key,
        "adapter": selected,
        "selected_adapter": selected,
        "source_mode": "controlled_capture" if selected else "",
        "ready": bool(selected),
        "status": "ready" if selected else "no_ready_controlled_capture_adapter",
        "preference": preference,
        "capabilities": selected_status.get("capabilities", {}),
        "selected_preflight": selected_status,
        "rejected": rejected,
        "fallback": "import_or_public_web" if not selected else "",
        "selected_at": now_iso(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Select a validated read-only collection adapter without installing or changing credentials.")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--status", action="append", default=[], help="Adapter preflight JSON; repeat for each available adapter.")
    parser.add_argument("--output")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    statuses = [load_data(Path(path)) for path in args.status]
    result = select_adapter(args.platform, statuses)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_ready and not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
