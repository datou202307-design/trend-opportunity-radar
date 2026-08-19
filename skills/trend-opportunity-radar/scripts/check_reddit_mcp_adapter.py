from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import now_iso, write_json


REQUIRED_OPERATIONS = {"discover_subreddits", "search_subreddit", "fetch_posts"}
FORBIDDEN_OPERATIONS = {"fetch_comments", "fetch_multiple", "create_feed", "list_feeds", "get_feed", "update_feed", "delete_feed"}


def operation_names(value: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(value, list):
        for item in value:
            names.update(operation_names(item))
    elif isinstance(value, dict):
        operations = value.get("operations")
        if isinstance(operations, dict):
            names.update(
                str(name).strip().casefold()
                for name in operations
                if str(name).strip()
            )
        for key in ("name", "operation", "operation_name"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                names.add(candidate.strip().casefold())
        for key in ("operations", "results", "data", "result", "items", "content"):
            if key in value:
                names.update(operation_names(value[key]))
    elif isinstance(value, str):
        lowered = value.casefold()
        names.update(name for name in REQUIRED_OPERATIONS | FORBIDDEN_OPERATIONS if name in lowered)
    return names


def build_status(discovery: Any) -> dict[str, Any]:
    discovered = operation_names(discovery)
    missing = sorted(REQUIRED_OPERATIONS - discovered)
    ready = not missing
    return {
        "schema_version": "collection-adapter-status-v0.1",
        "adapter": "reddit_research_mcp",
        "status": "ready" if ready else "required_operations_missing",
        "ready": ready,
        "capabilities": {"reddit": ready},
        "required_operations": sorted(REQUIRED_OPERATIONS),
        "discovered_required_operations": sorted(REQUIRED_OPERATIONS & discovered),
        "missing_operations": missing,
        "enforced_operation_allowlist": sorted(REQUIRED_OPERATIONS),
        "enforced_operation_denylist": sorted(FORBIDDEN_OPERATIONS),
        "comment_collection": "disabled",
        "pagination_exhaustion_verified": False,
        "checked_at": now_iso(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a saved Reddit Research MCP operation-discovery response without connecting or changing credentials.")
    parser.add_argument("--discovery", required=True, help="Saved discover_operations response from the already connected MCP service.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    try:
        discovery = json.loads(Path(args.discovery).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot read Reddit MCP discovery response: {error}") from error
    result = build_status(discovery)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_ready and not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
