from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from _common import SAMPLING_CONTRACTS, as_text


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "references" / "platform-adapter-registry.json"
SCHEMA_VERSION = "platform-adapter-registry-v0.2"
CONTRACT_VERSION = "platform-adapter-contract-v0.2"
RESEARCH_SCOPES = {"topic_research", "account_research"}
RELEASE_STATUSES = {"validated", "pilot", "import_only", "unsupported"}
ZERO_RESULT_ACCEPTANCE_MODES = {"explicit_empty_twice", "explicit_empty_twice_or_false_zero_protection"}
REQUIRED_CAPABILITY_FIELDS = {
    "capability_key", "search_builder", "detail_builder", "search_parser",
    "detail_runner", "pagination", "terminal_evidence", "safety_stops", "research_scopes",
}
OPTIONAL_CAPABILITY_FIELDS = {"comment_builder", "comment_sample_limit"}
FORBIDDEN_WRITE_OPERATION_PREFIXES = ("create_", "update_", "delete_", "post_", "reply_", "vote_", "follow_")


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry = json.loads((path or REGISTRY_PATH).read_text(encoding="utf-8"))
    validate_registry(registry)
    return registry


def validate_registry(registry: Any) -> None:
    if not isinstance(registry, dict) or registry.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Registry must use {SCHEMA_VERSION}.")
    if registry.get("contract_version") != CONTRACT_VERSION:
        raise ValueError(f"Registry must use {CONTRACT_VERSION}.")
    platforms = registry.get("platforms")
    adapters = registry.get("adapters")
    if not isinstance(platforms, dict) or not platforms or not isinstance(adapters, dict) or not adapters:
        raise ValueError("Registry requires non-empty platforms and adapters objects.")
    aliases: set[str] = set()
    for platform, spec in platforms.items():
        if not isinstance(spec, dict) or not isinstance(spec.get("aliases"), list):
            raise ValueError(f"Platform {platform} requires aliases.")
        for alias in spec["aliases"]:
            normalized = as_text(alias).casefold()
            if not normalized or normalized in aliases:
                raise ValueError(f"Platform alias is empty or duplicated: {alias}")
            aliases.add(normalized)
        preference = spec.get("controlled_capture_preference")
        if not isinstance(preference, list):
            raise ValueError(f"Platform {platform} requires controlled_capture_preference.")
        if any(adapter not in adapters for adapter in preference):
            raise ValueError(f"Platform {platform} references an unknown preferred adapter.")
        research_scopes = spec.get("research_scopes")
        if not isinstance(research_scopes, dict) or set(research_scopes) != RESEARCH_SCOPES:
            raise ValueError(f"Platform {platform} must declare every supported research scope.")
        if any(status not in RELEASE_STATUSES for status in research_scopes.values()):
            raise ValueError(f"Platform {platform} has an invalid research-scope release status.")
        release_gates = spec.get("release_gates", {})
        if not isinstance(release_gates, dict) or any(scope not in RESEARCH_SCOPES for scope in release_gates):
            raise ValueError(f"Platform {platform} has invalid release gates.")
        for scope, gate in release_gates.items():
            if not isinstance(gate, dict):
                raise ValueError(f"Platform {platform}/{scope} release gate must be an object.")
            mode = as_text(gate.get("zero_result_acceptance"))
            if mode not in ZERO_RESULT_ACCEPTANCE_MODES:
                raise ValueError(f"Platform {platform}/{scope} has an invalid zero-result acceptance mode.")
            if not isinstance(gate.get("requires_live_explicit_empty"), bool):
                raise ValueError(f"Platform {platform}/{scope} must declare whether live explicit empty is required.")
            if mode == "explicit_empty_twice_or_false_zero_protection":
                if not isinstance(gate.get("minimum_frozen_low_yield_probes"), int) or gate["minimum_frozen_low_yield_probes"] < 2:
                    raise ValueError(f"Platform {platform}/{scope} requires at least two frozen low-yield probes.")
                for key in (
                    "require_query_identity_on_every_probe",
                    "require_no_false_verified_zero",
                    "require_semantic_exclusion_of_irrelevant_fallback",
                ):
                    if gate.get(key) is not True:
                        raise ValueError(f"Platform {platform}/{scope} must enable {key}.")
    for adapter, spec in adapters.items():
        if not isinstance(spec, dict) or not as_text(spec.get("source_mode")):
            raise ValueError(f"Adapter {adapter} requires source_mode.")
        capabilities = spec.get("platforms")
        if not isinstance(capabilities, dict) or not capabilities:
            raise ValueError(f"Adapter {adapter} requires platform capabilities.")
        allowlist = spec.get("operation_allowlist", [])
        denylist = spec.get("operation_denylist", [])
        if not isinstance(allowlist, list) or not isinstance(denylist, list):
            raise ValueError(f"Adapter {adapter} operation lists must be arrays.")
        normalized_allowlist = {as_text(item).casefold() for item in allowlist}
        normalized_denylist = {as_text(item).casefold() for item in denylist}
        if "" in normalized_allowlist or "" in normalized_denylist or normalized_allowlist & normalized_denylist:
            raise ValueError(f"Adapter {adapter} operation lists are empty or overlap.")
        if any(operation.startswith(FORBIDDEN_WRITE_OPERATION_PREFIXES) for operation in normalized_allowlist):
            raise ValueError(f"Adapter {adapter} allowlist contains a write-like operation.")
        for platform, capability in capabilities.items():
            if platform != "*" and platform not in platforms:
                raise ValueError(f"Adapter {adapter} references unknown platform {platform}.")
            if (
                not isinstance(capability, dict)
                or not REQUIRED_CAPABILITY_FIELDS.issubset(capability)
                or not set(capability).issubset(REQUIRED_CAPABILITY_FIELDS | OPTIONAL_CAPABILITY_FIELDS)
            ):
                raise ValueError(f"Adapter {adapter}/{platform} does not match the capability contract.")
            if not isinstance(capability["terminal_evidence"], list) or not isinstance(capability["safety_stops"], list):
                raise ValueError(f"Adapter {adapter}/{platform} terminal and safety fields must be arrays.")
            scopes = capability["research_scopes"]
            if not isinstance(scopes, list) or not scopes or any(scope not in RESEARCH_SCOPES for scope in scopes):
                raise ValueError(f"Adapter {adapter}/{platform} has invalid research scopes.")
            has_comment_builder = "comment_builder" in capability
            has_comment_limit = "comment_sample_limit" in capability
            if has_comment_builder != has_comment_limit:
                raise ValueError(f"Adapter {adapter}/{platform} must declare comment builder and limit together.")
            if has_comment_builder:
                limit = capability["comment_sample_limit"]
                if not as_text(capability["comment_builder"]) or not isinstance(limit, int) or not 1 <= limit <= 10:
                    raise ValueError(f"Adapter {adapter}/{platform} has an invalid bounded comment capability.")


def normalize_platform(value: str, registry: dict[str, Any] | None = None) -> str:
    source = registry or load_registry()
    key = as_text(value).casefold()
    for platform, spec in source["platforms"].items():
        if key in {as_text(alias).casefold() for alias in spec["aliases"]}:
            return platform
    return key


def platform_scope_status(platform: str, research_scope: str = "topic_research", registry: dict[str, Any] | None = None) -> str:
    source = registry or load_registry()
    platform_key = normalize_platform(platform, source)
    scope = as_text(research_scope).casefold()
    spec = source["platforms"].get(platform_key)
    if not isinstance(spec, dict) or scope not in RESEARCH_SCOPES:
        return "unsupported"
    return as_text(spec.get("research_scopes", {}).get(scope)).casefold() or "unsupported"


def platform_scope_release_gate(platform: str, research_scope: str = "topic_research", registry: dict[str, Any] | None = None) -> dict[str, Any]:
    source = registry or load_registry()
    platform_key = normalize_platform(platform, source)
    scope = as_text(research_scope).casefold()
    spec = source["platforms"].get(platform_key)
    if not isinstance(spec, dict) or scope not in RESEARCH_SCOPES:
        return {}
    gate = spec.get("release_gates", {}).get(scope, {})
    return dict(gate) if isinstance(gate, dict) else {}


def adapter_capability(adapter: str, platform: str, registry: dict[str, Any] | None = None, research_scope: str = "topic_research") -> dict[str, Any] | None:
    source = registry or load_registry()
    adapter_spec = source["adapters"].get(as_text(adapter).casefold())
    if not isinstance(adapter_spec, dict):
        return None
    platform_key = normalize_platform(platform, source)
    capability = adapter_spec["platforms"].get(platform_key) or adapter_spec["platforms"].get("*")
    if not isinstance(capability, dict):
        return None
    scope = as_text(research_scope).casefold()
    if scope not in capability.get("research_scopes", []):
        return None
    return {"adapter": as_text(adapter).casefold(), "platform": platform_key, "source_mode": adapter_spec["source_mode"], **capability}


def controlled_capture_preference(platform: str, registry: dict[str, Any] | None = None, research_scope: str = "topic_research") -> list[str]:
    source = registry or load_registry()
    platform_key = normalize_platform(platform, source)
    spec = source["platforms"].get(platform_key)
    if not isinstance(spec, dict) or platform_scope_status(platform_key, research_scope, source) in {"unsupported", "import_only"}:
        return []
    return list(spec.get("controlled_capture_preference", []))


def adapter_operation_allowed(adapter: str, operation: str, registry: dict[str, Any] | None = None) -> bool:
    source = registry or load_registry()
    spec = source["adapters"].get(as_text(adapter).casefold())
    if not isinstance(spec, dict):
        return False
    normalized = as_text(operation).casefold()
    allowlist = {as_text(item).casefold() for item in spec.get("operation_allowlist", [])}
    denylist = {as_text(item).casefold() for item in spec.get("operation_denylist", [])}
    return bool(normalized and normalized in allowlist and normalized not in denylist)


def build_mcp_search_request(state: dict[str, Any], active: dict[str, Any]) -> dict[str, Any]:
    capability = adapter_capability(state["adapter"], state["platform"])
    if not capability or capability.get("search_builder") != "reddit_mcp_search_plan_v1":
        raise ValueError(f"No MCP search request builder for {state.get('adapter')}/{state.get('platform')}.")
    operation = as_text(active.get("operation") or "search_subreddit").casefold()
    if not adapter_operation_allowed(state["adapter"], operation):
        raise ValueError(f"Operation is not allowed for {state.get('adapter')}: {operation}")
    term = as_text(active.get("term"))
    if not term:
        raise ValueError("A Reddit MCP request requires a query term.")
    if operation == "discover_subreddits":
        return {"operation": operation, "arguments": {"query": term, "limit": min(5, max(1, int(active.get("limit") or 5)))}}
    subreddit = as_text(active.get("subreddit")).removeprefix("r/").strip("/")
    if not subreddit:
        raise ValueError("A Reddit subreddit search requires one discovered subreddit.")
    if operation == "search_subreddit":
        return {"operation": operation, "arguments": {
            "subreddit": subreddit,
            "query": term,
            "sort": as_text(active.get("sort") or "relevance").casefold(),
            "time_filter": as_text(active.get("time_filter") or "month").casefold(),
            "limit": min(20, max(1, int(active.get("limit") or 20))),
        }}
    return {"operation": operation, "arguments": {
        "subreddit": subreddit,
        "sort": as_text(active.get("sort") or "new").casefold(),
        "time_filter": as_text(active.get("time_filter") or "month").casefold(),
        "limit": min(20, max(1, int(active.get("limit") or 20))),
    }}


def status_supports(status: dict[str, Any], platform: str, registry: dict[str, Any] | None = None, research_scope: str = "topic_research") -> bool:
    source = registry or load_registry()
    adapter = as_text(status.get("adapter")).casefold()
    capability = adapter_capability(adapter, platform, source, research_scope)
    if not capability or status.get("ready") is not True or status.get("status") != "ready":
        return False
    capability_key = capability.get("capability_key")
    if capability_key:
        advertised = status.get("capabilities")
        return isinstance(advertised, dict) and advertised.get(capability_key) is True
    return True


def build_search_command(state: dict[str, Any], active: dict[str, Any], raw_output: Path, screens: int) -> list[str]:
    capability = adapter_capability(state["adapter"], state["platform"], research_scope=as_text(state.get("research_scope")) or "topic_research")
    if not capability or not capability.get("search_builder"):
        raise ValueError(f"No search builder for {state.get('adapter')}/{state.get('platform')}.")
    builder = capability["search_builder"]
    if builder in {"instagram_account_capture_v1", "instagram_hashtag_capture_v1"}:
        raise ValueError("Instagram browser research uses a frozen plan/record workflow, not a shell search command.")
    if builder in {"opencli_x_search_v1", "opencli_xhs_search_v1", "opencli_youtube_search_v1", "opencli_tiktok_search_v1"}:
        contract = SAMPLING_CONTRACTS[state["mode"]]
        per_query_target = math.ceil(contract["observed_result_target"][0] / contract["query_target"][0])
        limit = min(20, max(per_query_target, 10))
        if builder == "opencli_x_search_v1":
            product = "live" if "f=live" in as_text(active.get("url")).casefold() else "top"
            return ["opencli", "twitter", "search", active["term"], "--product", product, "--exclude", "retweets", "--limit", str(limit), "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
        if builder == "opencli_youtube_search_v1":
            command = ["opencli", "youtube", "search", active["term"], "--limit", str(limit)]
            params = parse_qs(urlparse(as_text(active.get("url"))).query)
            for option, allowed in {
                "sort": {"relevance", "date", "views", "rating"},
                "upload": {"hour", "today", "week", "month", "year"},
                "type": {"shorts", "video", "channel", "playlist"},
            }.items():
                value = as_text((params.get(option) or [""])[0]).casefold()
                if value in allowed:
                    command.extend([f"--{option}", value])
            command.extend(["-f", "json", "--window", "background", "--trace", "retain-on-failure"])
            return command
        if builder == "opencli_tiktok_search_v1":
            return ["opencli", "tiktok", "search", active["term"], "--limit", str(limit), "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
        return ["opencli", "xiaohongshu", "search", active["term"], "--limit", str(limit), "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
    if builder == "dokobot_read_search_v1":
        command = ["dokobot", "read", active["url"], "--local", "--reuse-tab", "--format", "chunks", "--screens", str(screens)]
        if active.get("session_id"):
            command.extend(["--session-id", active["session_id"]])
        command.extend(["--output", str(raw_output.resolve())])
        return command
    raise ValueError(f"Unknown search builder: {builder}")


def build_detail_command(state: dict[str, Any], url: str, output: Path) -> list[str]:
    capability = adapter_capability(state["adapter"], state["platform"], research_scope=as_text(state.get("research_scope")) or "topic_research")
    if not capability or not capability.get("detail_builder"):
        raise ValueError(f"No detail builder for {state.get('adapter')}/{state.get('platform')}.")
    builder = capability["detail_builder"]
    if builder in {"instagram_account_capture_v1", "instagram_hashtag_capture_v1"}:
        raise ValueError("Instagram browser detail reads are recorded through its scope-specific capture recorder.")
    if builder == "public_reddit_permalink_v1":
        raise ValueError("Reddit public permalink details are recorded through apply_reddit_public_detail_backfill.py after an Agent web read.")
    if builder == "opencli_x_detail_v1":
        return ["opencli", "twitter", "thread", url, "--limit", "10", "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
    if builder == "opencli_xhs_detail_v1":
        return ["opencli", "xiaohongshu", "note", url, "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
    if builder == "opencli_youtube_detail_v1":
        return ["opencli", "youtube", "video", url, "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
    if builder == "dokobot_read_detail_v1":
        return ["dokobot", "read", url, "--local", "--reuse-tab", "--format", "text", "--output", str(output.resolve())]
    if builder == "dokobot_tiktok_detail_v1":
        return ["dokobot", "read", url, "--local", "--reuse-tab", "--screens", "3", "--format", "text", "--output", str(output.resolve())]
    raise ValueError(f"Unknown detail builder: {builder}")


def parse_search_capture(adapter: str, platform: str, raw_path: Path, query: dict[str, Any]) -> dict[str, Any] | None:
    capability = adapter_capability(adapter, platform, research_scope=as_text(query.get("research_scope")) or "topic_research")
    parser = capability.get("search_parser") if capability else None
    if parser == "opencli_x_search_v1":
        from parse_opencli_x_search import parse_file
        return parse_file(raw_path, query)
    if parser == "opencli_xhs_search_v1":
        from parse_opencli_xhs_search import parse_file
        return parse_file(raw_path, query)
    if parser == "opencli_youtube_search_v1":
        from parse_opencli_youtube_search import parse_file
        return parse_file(raw_path, query)
    if parser == "opencli_tiktok_search_v1":
        from parse_opencli_tiktok_search import parse_file
        return parse_file(raw_path, query)
    if parser == "reddit_mcp_posts_v1":
        from parse_reddit_mcp_posts import parse_file
        return parse_file(raw_path, query)
    if parser == "dokobot_x_search_v1":
        from parse_dokobot_x_search import parse_file
        return parse_file(raw_path, query)
    return None
