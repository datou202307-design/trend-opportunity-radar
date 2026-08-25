from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from platform_adapter_contract import adapter_capability, controlled_capture_preference, normalize_platform, platform_scope_status, status_supports


SCHEMA_VERSION = "collection-adapter-selection-v0.2"


def _route_role(
    role: str,
    adapter: str,
    capability: dict[str, Any] | None,
    *,
    requirement: str,
) -> dict[str, Any]:
    capability = capability or {}
    runner_key = {
        "search": "search_runner",
        "detail": "detail_runner",
        "comments": "comment_runner",
        "media": "media_runner",
    }[role]
    builder_key = {
        "search": "search_builder",
        "detail": "detail_builder",
        "comments": "comment_builder",
        "media": "media_builder",
    }[role]
    builder = capability.get(builder_key)
    runner = capability.get(runner_key)
    if role == "search" and not runner:
        runner = adapter or builder
    elif role == "comments" and not runner and builder:
        runner = capability.get("detail_runner") or adapter
    available = bool(adapter and builder)
    return {
        "adapter": adapter or None,
        "builder": builder or None,
        "runner": runner or None,
        "available": available,
        "receipt_required": available and requirement in {"required", "required_for_standard_gates"},
        "requirement": requirement,
    }


def build_collection_route(
    platform: str,
    research_scope: str,
    search_adapter: str,
    detail_adapter: str,
) -> dict[str, Any]:
    search_capability = adapter_capability(search_adapter, platform, research_scope=research_scope) if search_adapter else None
    detail_capability = adapter_capability(detail_adapter, platform, research_scope=research_scope) if detail_adapter else None
    comment_adapter = detail_adapter if detail_capability and detail_capability.get("comment_builder") else ""
    media_adapter = detail_adapter if detail_capability and detail_capability.get("media_builder") else ""
    roles = {
        "search": _route_role("search", search_adapter, search_capability, requirement="required"),
        "detail": _route_role("detail", detail_adapter, detail_capability, requirement="required_for_standard_gates"),
        "comments": _route_role("comments", comment_adapter, detail_capability, requirement="required_when_used"),
        "media": _route_role("media", media_adapter, detail_capability, requirement="required_when_used"),
    }
    route_basis = {
        "platform": platform,
        "research_scope": research_scope,
        "research_surface": (search_capability or {}).get("research_surface") or "platform_registered_topic_surface",
        "roles": roles,
    }
    route_id = hashlib.sha256(json.dumps(route_basis, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "schema_version": "collection-route-v0.1",
        "route_id": route_id,
        **route_basis,
        "status": "frozen_ready" if roles["search"]["available"] else "unavailable",
        "fallback_policy": {
            "silent_fallback_allowed": False,
            "requires_new_preflight_and_route": True,
            "import_must_be_explicit": True,
        },
    }


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
    collection_route = build_collection_route(platform_key, research_scope, selected, detail_adapter)
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
        "collection_route": collection_route,
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
