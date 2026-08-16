from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from _common import SAMPLING_CONTRACTS, as_text


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "references" / "platform-adapter-registry.json"
SCHEMA_VERSION = "platform-adapter-registry-v0.1"
CONTRACT_VERSION = "platform-adapter-contract-v0.1"
REQUIRED_CAPABILITY_FIELDS = {
    "capability_key", "search_builder", "detail_builder", "search_parser",
    "detail_runner", "pagination", "terminal_evidence", "safety_stops",
}


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
    for adapter, spec in adapters.items():
        if not isinstance(spec, dict) or not as_text(spec.get("source_mode")):
            raise ValueError(f"Adapter {adapter} requires source_mode.")
        capabilities = spec.get("platforms")
        if not isinstance(capabilities, dict) or not capabilities:
            raise ValueError(f"Adapter {adapter} requires platform capabilities.")
        for platform, capability in capabilities.items():
            if platform != "*" and platform not in platforms:
                raise ValueError(f"Adapter {adapter} references unknown platform {platform}.")
            if not isinstance(capability, dict) or set(capability) != REQUIRED_CAPABILITY_FIELDS:
                raise ValueError(f"Adapter {adapter}/{platform} does not match the capability contract.")
            if not isinstance(capability["terminal_evidence"], list) or not isinstance(capability["safety_stops"], list):
                raise ValueError(f"Adapter {adapter}/{platform} terminal and safety fields must be arrays.")


def normalize_platform(value: str, registry: dict[str, Any] | None = None) -> str:
    source = registry or load_registry()
    key = as_text(value).casefold()
    for platform, spec in source["platforms"].items():
        if key in {as_text(alias).casefold() for alias in spec["aliases"]}:
            return platform
    return key


def adapter_capability(adapter: str, platform: str, registry: dict[str, Any] | None = None) -> dict[str, Any] | None:
    source = registry or load_registry()
    adapter_spec = source["adapters"].get(as_text(adapter).casefold())
    if not isinstance(adapter_spec, dict):
        return None
    platform_key = normalize_platform(platform, source)
    capability = adapter_spec["platforms"].get(platform_key) or adapter_spec["platforms"].get("*")
    if not isinstance(capability, dict):
        return None
    return {"adapter": as_text(adapter).casefold(), "platform": platform_key, "source_mode": adapter_spec["source_mode"], **capability}


def controlled_capture_preference(platform: str, registry: dict[str, Any] | None = None) -> list[str]:
    source = registry or load_registry()
    platform_key = normalize_platform(platform, source)
    spec = source["platforms"].get(platform_key)
    return list(spec.get("controlled_capture_preference", [])) if isinstance(spec, dict) else []


def status_supports(status: dict[str, Any], platform: str, registry: dict[str, Any] | None = None) -> bool:
    source = registry or load_registry()
    adapter = as_text(status.get("adapter")).casefold()
    capability = adapter_capability(adapter, platform, source)
    if not capability or status.get("ready") is not True or status.get("status") != "ready":
        return False
    capability_key = capability.get("capability_key")
    if capability_key:
        advertised = status.get("capabilities")
        return isinstance(advertised, dict) and advertised.get(capability_key) is True
    return True


def build_search_command(state: dict[str, Any], active: dict[str, Any], raw_output: Path, screens: int) -> list[str]:
    capability = adapter_capability(state["adapter"], state["platform"])
    if not capability or not capability.get("search_builder"):
        raise ValueError(f"No search builder for {state.get('adapter')}/{state.get('platform')}.")
    builder = capability["search_builder"]
    if builder in {"opencli_x_search_v1", "opencli_xhs_search_v1"}:
        contract = SAMPLING_CONTRACTS[state["mode"]]
        per_query_target = math.ceil(contract["observed_result_target"][0] / contract["query_target"][0])
        limit = min(20, max(per_query_target, 10))
        if builder == "opencli_x_search_v1":
            product = "live" if "f=live" in as_text(active.get("url")).casefold() else "top"
            return ["opencli", "twitter", "search", active["term"], "--product", product, "--exclude", "retweets", "--limit", str(limit), "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
        return ["opencli", "xiaohongshu", "search", active["term"], "--limit", str(limit), "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
    if builder == "dokobot_read_search_v1":
        command = ["dokobot", "read", active["url"], "--local", "--reuse-tab", "--format", "chunks", "--screens", str(screens)]
        if active.get("session_id"):
            command.extend(["--session-id", active["session_id"]])
        command.extend(["--output", str(raw_output.resolve())])
        return command
    raise ValueError(f"Unknown search builder: {builder}")


def build_detail_command(state: dict[str, Any], url: str, output: Path) -> list[str]:
    capability = adapter_capability(state["adapter"], state["platform"])
    if not capability or not capability.get("detail_builder"):
        raise ValueError(f"No detail builder for {state.get('adapter')}/{state.get('platform')}.")
    builder = capability["detail_builder"]
    if builder == "opencli_x_detail_v1":
        return ["opencli", "twitter", "thread", url, "--limit", "10", "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
    if builder == "opencli_xhs_detail_v1":
        return ["opencli", "xiaohongshu", "note", url, "-f", "json", "--window", "background", "--trace", "retain-on-failure"]
    if builder == "dokobot_read_detail_v1":
        return ["dokobot", "read", url, "--local", "--reuse-tab", "--format", "text", "--output", str(output.resolve())]
    raise ValueError(f"Unknown detail builder: {builder}")


def parse_search_capture(adapter: str, platform: str, raw_path: Path, query: dict[str, Any]) -> dict[str, Any] | None:
    capability = adapter_capability(adapter, platform)
    parser = capability.get("search_parser") if capability else None
    if parser == "opencli_x_search_v1":
        from parse_opencli_x_search import parse_file
        return parse_file(raw_path, query)
    if parser == "opencli_xhs_search_v1":
        from parse_opencli_xhs_search import parse_file
        return parse_file(raw_path, query)
    if parser == "dokobot_x_search_v1":
        from parse_dokobot_x_search import parse_file
        return parse_file(raw_path, query)
    return None
