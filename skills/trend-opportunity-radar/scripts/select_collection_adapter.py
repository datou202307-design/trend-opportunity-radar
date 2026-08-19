from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from platform_adapter_contract import adapter_capability, controlled_capture_preference, normalize_platform, platform_scope_status, status_supports


SCHEMA_VERSION = "collection-adapter-selection-v0.2"
def normalized_platform(value: str) -> str:
    return normalize_platform(value)


def select_adapter(platform: str, statuses: list[dict[str, Any]], research_scope: str = "topic_research", allow_pilot: bool = False) -> dict[str, Any]:
    platform_key = normalized_platform(platform)
    scope_status = platform_scope_status(platform_key, research_scope)
    by_adapter = {
        str(item.get("adapter", "")).casefold(): item
        for item in statuses
        if isinstance(item, dict)
    }
    preference = controlled_capture_preference(platform_key, research_scope=research_scope)
    rejected: list[dict[str, str]] = []
    selected = ""
    selected_status: dict[str, Any] = {}
    selected_source_mode = ""
    scope_allowed = scope_status == "validated" or (scope_status == "pilot" and allow_pilot)
    for adapter in preference if scope_allowed else []:
        status = by_adapter.get(adapter)
        if not status:
            rejected.append({"adapter": adapter, "reason": "preflight_missing"})
            continue
        if status.get("ready") is not True or status.get("status") != "ready":
            rejected.append({"adapter": adapter, "reason": str(status.get("status") or "not_ready")})
            continue
        if not status_supports(status, platform_key, research_scope=research_scope):
            rejected.append({"adapter": adapter, "reason": "platform_not_validated"})
            continue
        capability = adapter_capability(adapter, platform_key, research_scope=research_scope)
        if not capability or not capability.get("search_builder"):
            rejected.append({"adapter": adapter, "reason": "search_not_supported"})
            continue
        selected = adapter
        selected_status = status
        selected_source_mode = str(capability.get("source_mode") or "")
        break
    detail_adapter = ""
    detail_status: dict[str, Any] = {}
    if selected:
        for adapter in preference:
            status = by_adapter.get(adapter)
            capability = adapter_capability(adapter, platform_key, research_scope=research_scope)
            if (
                status
                and capability
                and capability.get("detail_builder")
                and status_supports(status, platform_key, research_scope=research_scope)
            ):
                detail_adapter = adapter
                detail_status = status
                break
    return {
        "schema_version": SCHEMA_VERSION,
        "platform": platform_key,
        "research_scope": research_scope,
        "release_status": scope_status,
        "adapter": selected,
        "selected_adapter": selected,
        "source_mode": selected_source_mode,
        "ready": bool(selected),
        "status": "ready" if selected else ("research_scope_not_live_supported" if not scope_allowed else "no_ready_controlled_capture_adapter"),
        "preference": preference,
        "capabilities": selected_status.get("capabilities", {}),
        "selected_preflight": selected_status,
        "detail_adapter": detail_adapter,
        "detail_ready": bool(detail_adapter),
        "detail_selected_preflight": detail_status,
        "rejected": rejected,
        "fallback": "import_or_public_web" if not selected else "",
        "selected_at": now_iso(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Select a validated read-only collection adapter without installing or changing credentials.")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--research-scope", default="topic_research", choices=["topic_research", "account_research"])
    parser.add_argument("--allow-pilot", action="store_true", help="Allow an explicitly registered pilot scope for development testing.")
    parser.add_argument("--status", action="append", default=[], help="Adapter preflight JSON; repeat for each available adapter.")
    parser.add_argument("--output")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    statuses = [load_data(Path(path)) for path in args.status]
    result = select_adapter(args.platform, statuses, args.research_scope, args.allow_pilot)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_ready and not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
