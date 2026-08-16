from __future__ import annotations

from typing import Any

from _common import as_text


SCHEMA_VERSION = "profile-decision-findings-v0.1"
POLARITIES = {"support", "counter", "neutral"}
CONCLUSION_STATUSES = {"candidate", "review_ready", "confirmed", "rejected"}
TEMPORAL_CLAIMS = {"current_snapshot", "spreading", "rising", "falling", "resolved_over_time"}


def _refs(value: Any) -> list[str]:
    return [as_text(item) for item in value] if isinstance(value, list) else []


def validate_findings(payload: Any, context: dict[str, Any], *, topic_keys: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        return [f"Decision findings must use {SCHEMA_VERSION}."]
    if payload.get("research_intent") != context.get("research_intent"):
        errors.append("research_intent does not match the frozen research context.")
    if payload.get("profile_version") != context.get("profile_version"):
        errors.append("profile_version does not match the frozen research context.")
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return errors + ["findings must be an array."]
    seen: set[str] = set()
    allowed_roles = set(context["evidence_roles"])
    thresholds = context["decision_thresholds"]
    required_action_fields = set(context["action_contract"]["required_fields"])
    required_sections = set(context["report_sections"])
    temporal_contract = context.get("temporal_contract") or {}
    for index, finding in enumerate(findings):
        label = f"findings[{index}]"
        if not isinstance(finding, dict):
            errors.append(f"{label} must be an object.")
            continue
        finding_id = as_text(finding.get("id"))
        if not finding_id or finding_id in seen:
            errors.append(f"{label}.id must be non-empty and unique.")
        seen.add(finding_id)
        for field in ("title", "analysis_unit_statement", "decision_summary", "audience", "evidence_boundary"):
            if not as_text(finding.get(field)):
                errors.append(f"{label}.{field} is required.")
        topic_key = as_text(finding.get("topic_key"))
        if not topic_key or (topic_keys is not None and topic_key not in topic_keys):
            errors.append(f"{label}.topic_key must reference an eligible audited topic.")
        roles = finding.get("profile_evidence_roles")
        if not isinstance(roles, list) or not set(roles).issubset(allowed_roles):
            errors.append(f"{label}.profile_evidence_roles contains a role outside the selected Profile.")
            roles = []
        support_refs = _refs(finding.get("support_refs"))
        counter_refs = _refs(finding.get("counter_refs"))
        if set(support_refs).intersection(counter_refs):
            errors.append(f"{label} cannot use the same source as support and counterevidence.")
        counter_status = as_text(finding.get("counter_search_status"))
        counter_complete = bool(counter_refs) and counter_status == "found"
        counter_complete = counter_complete or counter_status == "searched_none_found"
        actions = finding.get("recommended_actions")
        if not isinstance(actions, list) or not actions:
            errors.append(f"{label}.recommended_actions requires at least one action.")
        else:
            for action_index, action in enumerate(actions):
                missing = required_action_fields - set(action) if isinstance(action, dict) else required_action_fields
                if missing or any(not as_text(action.get(field)) for field in required_action_fields if isinstance(action, dict)):
                    errors.append(f"{label}.recommended_actions[{action_index}] misses: {', '.join(sorted(missing or required_action_fields))}.")
        sections = finding.get("report_sections")
        if not isinstance(sections, dict) or set(sections) != required_sections or any(not as_text(value) for value in sections.values()):
            errors.append(f"{label}.report_sections must populate exactly the selected Profile sections.")
        status = as_text(finding.get("conclusion_status"))
        if status not in CONCLUSION_STATUSES:
            errors.append(f"{label}.conclusion_status is invalid.")
        deterministic_ready = (
            len(support_refs) >= int(thresholds["minimum_support_refs"])
            and counter_complete
            and len(set(roles)) >= int(thresholds["minimum_profile_roles"])
            and bool(finding.get("direct_source_present"))
        )
        if status in {"review_ready", "confirmed"} and not deterministic_ready:
            errors.append(f"{label} cannot be {status} before the Profile decision thresholds pass.")
        if status == "confirmed" and not as_text(finding.get("human_confirmation")):
            errors.append(f"{label}.human_confirmation is required for confirmed conclusions.")
        temporal_claim = as_text(finding.get("temporal_claim") or "current_snapshot")
        if temporal_claim not in TEMPORAL_CLAIMS:
            errors.append(f"{label}.temporal_claim is invalid.")
        history_count = int(finding.get("compatible_snapshot_count") or 1)
        if temporal_claim in set(temporal_contract.get("history_required_for") or []) and history_count < 2:
            errors.append(f"{label} cannot claim {temporal_claim} from a single snapshot; use current_snapshot or add compatible history.")
    return errors


def require_valid_findings(payload: Any, context: dict[str, Any], *, topic_keys: set[str] | None = None) -> None:
    errors = validate_findings(payload, context, topic_keys=topic_keys)
    if errors:
        raise SystemExit("Decision finding validation failed:\n- " + "\n- ".join(errors))
