from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "references" / "decision-profile-registry.json"
SCHEMA_VERSION = "decision-profile-registry-v0.2"
INTENTS = {"business_opportunity", "brand_sentiment", "competitor_users", "content_opportunity", "product_demand"}
REQUIRED_FIELDS = {
    "version", "implementation_status", "decision_question", "analysis_unit", "evidence_roles",
    "counterevidence_targets", "query_profile", "query_intents", "decision_thresholds",
    "action_contract", "report_profile", "report_sections",
}


def validate_registry(registry: Any) -> None:
    if not isinstance(registry, dict) or registry.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Decision profile registry must use {SCHEMA_VERSION}.")
    profiles = registry.get("profiles")
    if not isinstance(profiles, dict) or set(profiles) != INTENTS:
        raise ValueError("Decision profile registry must contain exactly the five supported intents.")
    versions: set[str] = set()
    for intent, profile in profiles.items():
        if not isinstance(profile, dict) or not REQUIRED_FIELDS.issubset(profile):
            raise ValueError(f"Profile {intent} does not match the profile contract.")
        if profile["implementation_status"] not in {"available", "contract_only"}:
            raise ValueError(f"Profile {intent} has an invalid implementation status.")
        questions = profile["decision_question"]
        if not isinstance(questions, dict) or not questions.get("zh-CN") or not questions.get("en"):
            raise ValueError(f"Profile {intent} requires Chinese and English decision questions.")
        for field in ("evidence_roles", "counterevidence_targets", "query_intents", "report_sections"):
            if not isinstance(profile[field], list) or not profile[field]:
                raise ValueError(f"Profile {intent}.{field} must be a non-empty array.")
        version = profile["version"]
        if not isinstance(version, str) or not version or version in versions:
            raise ValueError("Profile versions must be non-empty and unique.")
        versions.add(version)
        thresholds = profile["decision_thresholds"]
        if not isinstance(thresholds, dict) or not all(field in thresholds for field in (
            "minimum_support_refs", "minimum_counter_refs_or_searched_none", "minimum_profile_roles", "requires_direct_source"
        )):
            raise ValueError(f"Profile {intent}.decision_thresholds is incomplete.")
        action = profile["action_contract"]
        if not isinstance(action, dict) or not action.get("primary_action") or not action.get("required_fields"):
            raise ValueError(f"Profile {intent}.action_contract is incomplete.")


def load_registry(path: Path | None = None) -> dict[str, Any]:
    registry = json.loads((path or REGISTRY_PATH).read_text(encoding="utf-8"))
    validate_registry(registry)
    return registry


def get_profile(intent: str, registry: dict[str, Any] | None = None) -> dict[str, Any]:
    source = registry or load_registry()
    profile = source["profiles"].get(intent)
    if not profile:
        raise ValueError(f"Unknown research intent: {intent}")
    return {"research_intent": intent, **profile}
