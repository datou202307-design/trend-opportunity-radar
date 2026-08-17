from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

from _common import SAMPLING_CONTRACTS, as_bool, as_list, as_text, load_data, merge_signals, now_iso, write_json
from append_collection_result import append_query_result, signal_key
from platform_adapter_contract import CONTRACT_VERSION, SCHEMA_VERSION as ADAPTER_REGISTRY_VERSION, build_detail_command, build_search_command, normalize_platform, status_supports
from research_context import load_context


SCHEMA_VERSION = "collection-orchestrator-v0.2"
LEGACY_SCHEMA_VERSION = "dokobot-collection-orchestrator-v0.1"
LAYERS = {"platform_baseline", "category", "subject_bridge"}
HARD_STOPS = {"captcha", "rate_limit", "login_expired", "permission_prompt", "abnormal_redirect"}
QUERY_LOCAL_STOPS = {"continuation_unresolved", "repeated_timeout", "cli_error", "session_recovery_failed"}
SESSION_RECOVERY_STOPS = {"session_expired"}
ZERO_RESULT_STOPS = {"zero_results", "no_results", "no_results_returned"}
TERMINAL_EVIDENCE = {"explicit_platform_end", "zero_results", "no_more_results"}
GENERIC_RECOVERY_TOKENS = {
    "ai", "automatic", "automated", "automation", "meeting", "meetings",
    "tool", "tools", "software", "app", "apps", "system", "systems",
}


def query_tokens(value: str) -> list[str]:
    return [
        item.casefold()
        for item in re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?|[\u4e00-\u9fff]+", as_text(value))
    ]
def required_layers(mode: str) -> int:
    return SAMPLING_CONTRACTS[mode]["layer_query_min"]


def search_budget(state: dict[str, Any]) -> dict[str, Any]:
    """Return an honest pre-capture budget guard without truncating observed cards."""
    contract = SAMPLING_CONTRACTS[state["mode"]]
    observed = snapshot_counts(state)["observed_result_count"]
    lower, upper = contract["observed_result_target"]
    atomic_read_reserve = int(contract["atomic_read_reserve"])
    launch_ceiling = max(lower, upper - atomic_read_reserve)
    return {
        "observed": observed,
        "upper": upper,
        "estimated_atomic_read": atomic_read_reserve,
        "launch_ceiling": launch_ceiling,
        "may_start_search": observed <= launch_ceiling,
        "atomic_overshoot": max(0, observed - upper),
    }


def new_active_query(query: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": query["id"],
        "term": query["term"],
        "layer": query["layer"],
        "url": query["url"],
        "query_intent": query.get("query_intent", ""),
        "session_id": "",
        "can_continue": False,
        "observed_result_keys": [],
        "signals": [],
        "detail_open_keys": [],
        "raw_artifacts": [],
        "capture_executions": [],
        "chunk_count": 0,
        "timeout_count": 0,
        "continuation_unknown_count": 0,
        "empty_continuation_count": 0,
        "session_restart_count": 0,
        "next_screens": 0,
        "stop_reason": "",
    }


def validate_plan(plan: Any, mode: str, context: dict[str, Any] | None = None) -> list[dict[str, str]]:
    source = plan.get("queries") if isinstance(plan, dict) else None
    if not isinstance(source, list):
        raise SystemExit("Query plan requires a queries array.")
    contract = SAMPLING_CONTRACTS[mode]
    if not contract["query_target"][0] <= len(source) <= contract["query_target"][1]:
        raise SystemExit(f"{mode} requires {contract['query_target'][0]}-{contract['query_target'][1]} queries.")
    queries: list[dict[str, str]] = []
    ids: set[str] = set()
    layer_counts = {layer: 0 for layer in LAYERS}
    for index, item in enumerate(source):
        if not isinstance(item, dict):
            raise SystemExit("Every query definition must be an object.")
        query_id = as_text(item.get("id")) or f"query-{index + 1}"
        term = as_text(item.get("term") or item.get("query_term"))
        layer = as_text(item.get("layer") or item.get("query_layer"))
        url = as_text(item.get("url"))
        query_intent = as_text(item.get("query_intent"))
        if query_id in ids or not term or layer not in LAYERS or not url.startswith(("http://", "https://")):
            raise SystemExit("Each query needs a unique id, term, valid layer, and http(s) platform search URL.")
        ids.add(query_id)
        layer_counts[layer] += 1
        if context:
            allowed = set(context["query_intents"])
            if not query_intent and context["research_intent"] != "business_opportunity":
                raise SystemExit("Non-default Decision Profiles require query_intent on every query.")
            if query_intent and query_intent not in allowed:
                raise SystemExit("Query intent is not allowed by the frozen Decision Profile.")
        queries.append({"id": query_id, "term": term, "layer": layer, "url": url, **({"query_intent": query_intent} if query_intent else {})})
    minimum = required_layers(mode)
    if any(count < minimum for count in layer_counts.values()):
        raise SystemExit(f"{mode} requires at least {minimum} queries in each query layer.")
    return queries


def validate_recovery_plan(plan: Any, state: dict[str, Any]) -> list[dict[str, str]]:
    source = plan.get("queries") if isinstance(plan, dict) else None
    if not isinstance(source, list) or not source:
        raise SystemExit("Recovery query plan requires a non-empty queries array.")
    maximum = SAMPLING_CONTRACTS[state["mode"]]["query_target"][1]
    remaining = maximum - len(state["queries"])
    if remaining <= 0 or len(source) > remaining:
        raise SystemExit(f"Recovery query plan exceeds the remaining query budget of {max(remaining, 0)}.")
    if len(source) != 1:
        raise SystemExit("Add exactly one recovery query per round so its yield can be evaluated before spending more query budget.")
    known_ids = {item["id"] for item in state["queries"]}
    known_terms = {as_text(item["term"]).casefold() for item in state["queries"]}
    known_urls = {as_text(item["url"]) for item in state["queries"]}
    queries: list[dict[str, str]] = []
    context = load_context(Path(state["research_context"])) if state.get("research_context") else None
    for index, item in enumerate(source):
        if not isinstance(item, dict):
            raise SystemExit("Every recovery query definition must be an object.")
        query_id = as_text(item.get("id")) or f"recovery-{len(state['queries']) + index + 1}"
        term = as_text(item.get("term") or item.get("query_term"))
        layer = as_text(item.get("layer") or item.get("query_layer"))
        url = as_text(item.get("url"))
        query_intent = as_text(item.get("query_intent"))
        if not term or layer not in LAYERS or not url.startswith(("http://", "https://")):
            raise SystemExit("Each recovery query needs an id, term, valid layer, and http(s) platform search URL.")
        if query_id in known_ids or term.casefold() in known_terms or url in known_urls:
            raise SystemExit("Recovery queries must not repeat an existing id, term, or URL.")
        if context:
            allowed = set(context["query_intents"])
            if not query_intent and context["research_intent"] != "business_opportunity":
                raise SystemExit("Non-default Decision Profiles require query_intent on every recovery query.")
            if query_intent and query_intent not in allowed:
                raise SystemExit("Recovery query intent is not allowed by the frozen Decision Profile.")
        word_count = len(re.findall(r"[\w'-]+", term, flags=re.UNICODE))
        if word_count > 4:
            raise SystemExit("Recovery query terms must contain at most four words so they broaden rather than restack constraints.")
        known_ids.add(query_id)
        known_terms.add(term.casefold())
        known_urls.add(url)
        queries.append({"id": query_id, "term": term, "layer": layer, "url": url, **({"query_intent": query_intent} if query_intent else {})})
    deficient = set(recovery_diagnostics(state)["recommended_layers"])
    if deficient and queries[0]["layer"] not in deficient:
        raise SystemExit("The recovery query must target one of the currently deficient layers.")
    diagnostics = recovery_diagnostics(state)
    volume_recovery = diagnostics.get("volume_recovery") or {}
    if volume_recovery.get("required"):
        recommended = {as_text(item).casefold() for item in volume_recovery.get("recommended_terms", []) if as_text(item)}
        proposed = queries[0]["term"].casefold()
        if not recommended:
            raise SystemExit("No evidence-derived recovery terms remain. Stop collection and deliver a bounded snapshot instead of inventing a query.")
        if proposed not in recommended:
            raise SystemExit(
                "When only sample volume remains deficient, use one evidence-derived recommended term instead of inventing another narrow phrase: "
                + ", ".join(sorted(recommended))
            )
    return queries


def load_state(path: Path) -> dict[str, Any]:
    state = load_data(str(path))
    if not isinstance(state, dict) or state.get("schema_version") not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        raise SystemExit("Invalid collection orchestrator state.")
    return state


def normalized_platform(value: str) -> str:
    return normalize_platform(value)


def search_capture_command(state: dict[str, Any], active: dict[str, Any], raw_output: Path, screens: int) -> list[str]:
    return build_search_command(state, active, raw_output, screens)


def detail_capture_command(state: dict[str, Any], url: str, output: Path) -> list[str]:
    return build_detail_command(state, url, output)


def merged_snapshot_signals(signals: list[Any], platform: str) -> list[dict[str, Any]]:
    """Merge search/detail variants before evaluating layer evidence gates."""
    merged: dict[str, dict[str, Any]] = {}
    for item in signals:
        if not isinstance(item, dict):
            continue
        key = signal_key(item, platform)
        merged[key] = merge_signals(merged[key], item) if key in merged else dict(item)
    return list(merged.values())


def snapshot_counts(state: dict[str, Any]) -> dict[str, int]:
    snapshot_path = Path(state["snapshot"])
    if not snapshot_path.exists():
        return {"query_count": 0, "observed_result_count": 0, "unique_sample_count": 0, "detail_open_count": 0, "counter_signal_count": 0}
    snapshot = load_data(str(snapshot_path))
    collection = snapshot.setdefault("collection", {}) if isinstance(snapshot, dict) else {}
    counts = collection.setdefault("counts", {})
    signals = snapshot.get("signals", []) if isinstance(snapshot, dict) else []
    runs = collection.get("query_runs", []) if isinstance(collection.get("query_runs"), list) else []
    platform = as_text(state.get("platform"))
    valid_signals = [item for item in signals if isinstance(item, dict)]
    unique_keys = {signal_key(item, platform) for item in valid_signals}
    canonical = {
        "query_count": len(runs),
        "observed_result_count": sum(int(item.get("observed_result_count") or 0) for item in runs if isinstance(item, dict)),
        "retained_sample_count": len(valid_signals),
        "unique_sample_count": len(unique_keys),
        "duplicate_count": len(valid_signals) - len(unique_keys),
        "discarded_result_count": sum(int(item.get("discarded_result_count") or 0) for item in runs if isinstance(item, dict)),
        "detail_open_count": len({signal_key(item, platform) for item in valid_signals if item.get("detail_captured")}),
        "counter_signal_count": len({signal_key(item, platform) for item in valid_signals if item.get("evidence_role") == "counter"}),
    }
    if any(int(counts.get(key) or 0) != value for key, value in canonical.items()):
        counts.update(canonical)
        collection["counts"] = counts
        write_json(str(snapshot_path), snapshot)
    return {key: int(counts.get(key) or 0) for key in (
        "query_count", "observed_result_count", "unique_sample_count", "detail_open_count", "counter_signal_count"
    )}


def contract_checks(state: dict[str, Any]) -> dict[str, bool]:
    counts = snapshot_counts(state)
    contract = SAMPLING_CONTRACTS[state["mode"]]
    completed = [query for query in state["queries"] if query["status"] == "completed"]
    layer_counts = {layer: sum(1 for query in completed if query["layer"] == layer) for layer in LAYERS}
    snapshot_path = Path(state["snapshot"])
    snapshot = load_data(str(snapshot_path)) if snapshot_path.exists() else {}
    raw_rows = snapshot.get("signals", []) if isinstance(snapshot, dict) else []
    raw_signals = merged_snapshot_signals(raw_rows, as_text(state.get("platform")))
    runs = ((snapshot.get("collection") or {}).get("query_runs") or []) if isinstance(snapshot, dict) else []
    layer_stats = {}
    for layer in LAYERS:
        layer_runs = [item for item in runs if item.get("query_layer") == layer]
        layer_signals = [item for item in raw_signals if item.get("query_layer") == layer or layer in as_list(item.get("query_layers"))]
        layer_stats[layer] = {
            "observed": sum(int(item.get("observed_result_count") or 0) for item in layer_runs),
            "unique": len({signal_key(item, state.get("platform", "")) for item in layer_signals}),
            "relevant": len({signal_key(item, state.get("platform", "")) for item in layer_signals if item.get("semantic_relevance") in {"direct", "adjacent"}}),
            "direct_relevance": len({signal_key(item, state.get("platform", "")) for item in layer_signals if item.get("semantic_relevance") == "direct"}),
            "details": sum(1 for item in layer_signals if item.get("detail_captured")),
            "direct": sum(1 for item in layer_signals if item.get("semantic_relevance") == "direct" and (item.get("detail_captured") or item.get("source_type") in {"direct_post", "exported_item"})),
        }
    reviewed = sum(1 for item in raw_signals if item.get("semantic_relevance") in {"direct", "adjacent", "weak"})
    relevant_unique = len({signal_key(item, state.get("platform", "")) for item in raw_signals if item.get("semantic_relevance") in {"direct", "adjacent"}})
    return {
        "queries": counts["query_count"] >= contract["query_target"][0],
        "query_layers": all(count >= required_layers(state["mode"]) for count in layer_counts.values()),
        "observed_results": counts["observed_result_count"] >= contract["observed_result_target"][0],
        "unique_signals": counts["unique_sample_count"] >= contract["unique_signal_target"][0],
        "relevant_unique_signals": relevant_unique >= contract["relevant_unique_signal_min"],
        "detail_opens": counts["detail_open_count"] >= contract["detail_open_target"][0],
        "counter_signals": counts["counter_signal_count"] >= contract["counter_signal_min"],
        "layer_observed_results": all(item["observed"] >= contract["layer_observed_min"] for item in layer_stats.values()),
        "layer_unique_signals": all(item["unique"] >= contract["layer_unique_signal_min"] for item in layer_stats.values()),
        "layer_relevant_signals": all(item["relevant"] >= contract["layer_relevant_signal_min"] for item in layer_stats.values()),
        "layer_direct_signals": all(item["direct_relevance"] >= contract["layer_direct_signal_min"] for item in layer_stats.values()),
        "layer_detail_opens": all(item["details"] >= contract["layer_detail_min"] for item in layer_stats.values()),
        "subject_bridge_direct_evidence": layer_stats["subject_bridge"]["direct"] >= contract["subject_bridge_direct_min"],
        "relevance_review_coverage": reviewed / max(len(raw_signals), 1) >= contract["relevance_review_coverage_min"],
    }


def recovery_diagnostics(state: dict[str, Any]) -> dict[str, Any]:
    contract = SAMPLING_CONTRACTS[state["mode"]]
    snapshot_path = Path(state["snapshot"])
    snapshot = load_data(str(snapshot_path)) if snapshot_path.exists() else {}
    raw_signals = snapshot.get("signals", []) if isinstance(snapshot, dict) else []
    runs = ((snapshot.get("collection") or {}).get("query_runs") or []) if isinstance(snapshot, dict) else []
    low_yield_queries = []
    for item in runs:
        observed = int(item.get("observed_result_count") or 0)
        relevant = int(item.get("relevant_signal_count") or 0)
        if observed == 0 or (observed >= 8 and relevant <= max(1, math.floor(observed * 0.1))):
            low_yield_queries.append({
                "query_term": as_text(item.get("query_term")),
                "query_layer": as_text(item.get("query_layer")),
                "observed": observed,
                "relevant": relevant,
                "reason": "zero_results" if observed == 0 else "high_volume_low_relevance",
            })
    recommended_layers: list[str] = []
    layer_deficits: dict[str, dict[str, int]] = {}
    layer_current: dict[str, dict[str, int]] = {}
    for layer in sorted(LAYERS):
        layer_runs = [item for item in runs if item.get("query_layer") == layer]
        layer_signals = [item for item in raw_signals if item.get("query_layer") == layer or layer in as_list(item.get("query_layers"))]
        observed = sum(int(item.get("observed_result_count") or 0) for item in layer_runs)
        unique = len({signal_key(item, state.get("platform", "")) for item in layer_signals})
        details = sum(1 for item in layer_signals if item.get("detail_captured"))
        relevant = len({signal_key(item, state.get("platform", "")) for item in layer_signals if item.get("semantic_relevance") in {"direct", "adjacent"}})
        direct_relevance = len({signal_key(item, state.get("platform", "")) for item in layer_signals if item.get("semantic_relevance") == "direct"})
        direct = sum(
            1 for item in layer_signals
            if item.get("semantic_relevance") == "direct"
            and (item.get("detail_captured") or item.get("source_type") in {"direct_post", "exported_item"})
        )
        deficits = {
            "observed": max(0, contract["layer_observed_min"] - observed),
            "unique": max(0, contract["layer_unique_signal_min"] - unique),
            "relevant": max(0, contract["layer_relevant_signal_min"] - relevant),
            "direct_relevance": max(0, contract["layer_direct_signal_min"] - direct_relevance),
            "details": max(0, contract["layer_detail_min"] - details),
            "direct": max(0, contract["subject_bridge_direct_min"] - direct) if layer == "subject_bridge" else 0,
        }
        layer_current[layer] = {"observed": observed, "unique": unique, "relevant": relevant, "direct_relevance": direct_relevance, "details": details}
        layer_deficits[layer] = deficits
        if any(deficits.values()):
            recommended_layers.append(layer)
    counts = snapshot_counts(state)
    relevant_unique = len({signal_key(item, state.get("platform", "")) for item in raw_signals if item.get("semantic_relevance") in {"direct", "adjacent"}})
    global_deficits = {
        "observed": max(0, contract["observed_result_target"][0] - counts["observed_result_count"]),
        "unique": max(0, contract["unique_signal_target"][0] - counts["unique_sample_count"]),
        "relevant": max(0, contract["relevant_unique_signal_min"] - relevant_unique),
        "details": max(0, contract["detail_open_target"][0] - counts["detail_open_count"]),
        "counters": max(0, contract["counter_signal_min"] - counts["counter_signal_count"]),
    }
    for metric in ("observed", "unique", "relevant", "details"):
        if global_deficits[metric]:
            for layer in sorted(LAYERS, key=lambda item: (layer_current[item][metric], item)):
                if layer not in recommended_layers:
                    recommended_layers.append(layer)
    if global_deficits["counters"]:
        for layer in ("subject_bridge", "category", "platform_baseline"):
            if layer not in recommended_layers:
                recommended_layers.append(layer)
    quality_deficit = (
        global_deficits["relevant"] > 0
        or global_deficits["details"] > 0
        or global_deficits["counters"] > 0
        or any(any(values.values()) for values in layer_deficits.values())
    )
    completed_runs = [item for item in runs if isinstance(item, dict) and int(item.get("observed_result_count") or 0) > 0]
    successful_seeds = sorted(
        ({
            "query_term": as_text(item.get("query_term")),
            "query_layer": as_text(item.get("query_layer")),
            "observed": int(item.get("observed_result_count") or 0),
            "relevant": int(item.get("relevant_signal_count") or 0),
            "relevant_yield_rate": float(item.get("relevant_yield_rate") or 0),
        } for item in completed_runs),
        key=lambda item: (-item["relevant"], -item["observed"], -item["relevant_yield_rate"], item["query_term"]),
    )
    known_terms = {as_text(item.get("query_term")).casefold() for item in runs if isinstance(item, dict)}
    recommended_terms: list[str] = []
    for seed in successful_seeds:
        distinctive = [item for item in query_tokens(seed["query_term"]) if item not in GENERIC_RECOVERY_TOKENS]
        candidates: list[str] = []
        if 2 <= len(distinctive) <= 4:
            candidates.append(" ".join(distinctive))
        if len(distinctive) == 1 and re.fullmatch(r"[\u4e00-\u9fff]{2,12}", distinctive[0]):
            # Removing a generic Latin product token such as AI from a proven
            # Chinese query yields a real contiguous platform phrase rather
            # than an invented synonym or compound query.
            candidates.append(distinctive[0])
        # When the first mechanical broadening has already been used, continue by
        # taking real contiguous phrases from the same proven query. Never invent
        # a new compound phrase merely because one query slot remains.
        for size in range(min(len(distinctive) - 1, 3), 1, -1):
            candidates.extend(" ".join(distinctive[start:start + size]) for start in range(len(distinctive) - size + 1))
        for candidate in candidates:
            folded = candidate.casefold()
            if folded not in known_terms and folded not in {item.casefold() for item in recommended_terms}:
                recommended_terms.append(candidate)
    volume_only = not quality_deficit and (global_deficits["observed"] > 0 or global_deficits["unique"] > 0)
    if volume_only and successful_seeds:
        preferred_layers: list[str] = []
        for seed in successful_seeds:
            if seed["query_layer"] and seed["query_layer"] not in preferred_layers:
                preferred_layers.append(seed["query_layer"])
        recommended_layers = preferred_layers
    return {
        "query_budget_remaining": max(0, contract["query_target"][1] - len(state["queries"])),
        "recommended_layers": recommended_layers,
        "layer_deficits": layer_deficits,
        "global_deficits": global_deficits,
        "low_yield_queries": low_yield_queries,
        "successful_query_seeds": successful_seeds[:5],
        "volume_recovery": {
            "required": volume_only,
            "reason": "Only sample volume remains below the contract; broaden from proven platform language instead of inventing another concept phrase." if volume_only else "",
            "recommended_terms": recommended_terms[:5],
            "avoid_terms": [as_text(item.get("query_term")) for item in runs if isinstance(item, dict) and int(item.get("observed_result_count") or 0) <= 1],
        },
        "rewrite_rules": [
            "remove stacked constraints and search one task phrase at a time",
            "use no more than four words in each recovery query",
            "replace product labels with platform-native problem or outcome language",
            "add one synonym or adjacent workflow term, not a near-duplicate query",
            "include a failure, objection, or human-handoff query when counterevidence is low",
        ],
        "layer_rewrite_guidance": {
            "platform_baseline": "Use one platform-native problem or outcome phrase without product labels.",
            "category": "Use one task, failure, or workflow phrase without stacking audience and solution qualifiers.",
            "subject_bridge": "Use one capability-to-outcome phrase; include the technology or the audience, not both.",
        },
    }


def detail_backfill_plan(state: dict[str, Any]) -> dict[str, Any]:
    """Plan detail opens from retained links without spending search-query budget."""
    snapshot_path = Path(state["snapshot"])
    snapshot = load_data(str(snapshot_path)) if snapshot_path.exists() else {}
    signals = snapshot.get("signals", []) if isinstance(snapshot, dict) else []
    deficits = recovery_diagnostics(state)["layer_deficits"]
    attempted = set(as_list(state.get("detail_backfill_attempts")))
    targets: list[dict[str, str]] = []
    selected: set[str] = set()
    for layer in sorted(LAYERS):
        needed = int(deficits.get(layer, {}).get("details") or 0)
        if layer == "subject_bridge":
            needed = max(needed, int(deficits.get(layer, {}).get("direct") or 0))
        if needed <= 0:
            continue
        candidates = []
        for signal in signals:
            layers = {as_text(signal.get("query_layer")), *[as_text(item) for item in as_list(signal.get("query_layers"))]}
            key = signal_key(signal, state.get("platform", ""))
            detail_access = signal.get("detail_access") if isinstance(signal.get("detail_access"), dict) else {}
            url = as_text(detail_access.get("url") or signal.get("source_url") or signal.get("canonical_url") or signal.get("url"))
            if layer not in layers or signal.get("semantic_relevance") not in {"direct", "adjacent"} or signal.get("detail_captured") or key in attempted or key in selected or not url.startswith(("http://", "https://")):
                continue
            relevance = {"direct": 3, "adjacent": 2, "weak": 1}.get(as_text(signal.get("semantic_relevance")), 0)
            role = {"counter": 2, "support": 1, "neutral": 0}.get(as_text(signal.get("evidence_role")), 0)
            candidates.append((relevance, role, key, signal, url))
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
        for _, _, key, signal, url in candidates[: max(needed * 2, needed)]:
            targets.append({
                "signal_key": key,
                "layer": layer,
                "url": url,
                "title": as_text(signal.get("title")),
            })
            selected.add(key)
    global_needed = int(recovery_diagnostics(state)["global_deficits"]["details"] or 0)
    remaining_needed = max(0, global_needed - len(selected))
    if remaining_needed:
        candidates = []
        for signal in signals:
            key = signal_key(signal, state.get("platform", ""))
            detail_access = signal.get("detail_access") if isinstance(signal.get("detail_access"), dict) else {}
            url = as_text(detail_access.get("url") or signal.get("source_url") or signal.get("canonical_url") or signal.get("url"))
            if signal.get("semantic_relevance") not in {"direct", "adjacent"} or signal.get("detail_captured") or key in attempted or key in selected or not url.startswith(("http://", "https://")):
                continue
            relevance = {"direct": 3, "adjacent": 2, "weak": 1}.get(as_text(signal.get("semantic_relevance")), 0)
            role = {"counter": 2, "support": 1, "neutral": 0}.get(as_text(signal.get("evidence_role")), 0)
            layer = as_text(signal.get("query_layer")) or "category"
            candidates.append((relevance, role, key, layer, signal, url))
        candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
        for _, _, key, layer, signal, url in candidates[:remaining_needed]:
            targets.append({"signal_key": key, "layer": layer, "url": url, "title": as_text(signal.get("title"))})
            selected.add(key)
    required = max(global_needed, sum(int(item.get("details") or 0) for item in deficits.values()))
    return {"required_detail_count": required, "targets": targets}


def record_detail_backfill(state: dict[str, Any], payload: Any) -> None:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list) or not payload["results"]:
        raise SystemExit("record-details requires a non-empty results array.")
    plan = detail_backfill_plan(state)
    allowed = {item["signal_key"]: item for item in plan["targets"]}
    snapshot_path = Path(state["snapshot"])
    snapshot = load_data(str(snapshot_path))
    signals = snapshot.get("signals", []) if isinstance(snapshot, dict) else []
    if not isinstance(signals, list):
        raise SystemExit("The canonical snapshot signals field must be an array.")
    attempts = state.setdefault("detail_backfill_attempts", [])
    audits = snapshot.setdefault("collection", {}).setdefault("detail_backfills", [])
    hard_stop = as_text(payload.get("hard_stop"))
    if hard_stop and hard_stop not in HARD_STOPS:
        raise SystemExit("Detail payload contains an unsupported hard stop.")
    audited_payload = as_text(payload.get("schema_version")).endswith("v0.2")
    for result in payload["results"]:
        if not isinstance(result, dict):
            raise SystemExit("Every detail result must be an object.")
        key = as_text(result.get("signal_key"))
        if key not in allowed:
            raise SystemExit("Detail result does not match a currently eligible backfill target.")
        if key not in attempts:
            attempts.append(key)
        success = as_bool(result.get("success"))
        raw_artifact = as_text(result.get("raw_artifact"))
        stop_reason = as_text(result.get("stop_reason"))
        execution = result.get("execution")
        if audited_payload:
            if not isinstance(execution, dict):
                raise SystemExit("Audited detail results require deterministic execution evidence.")
            for field in ("stdout_artifact", "stderr_artifact", "metadata_artifact"):
                value = as_text(execution.get(field))
                artifact = Path(value)
                if not value or not artifact.is_file():
                    raise SystemExit(f"Audited detail result requires an existing {field} file.")
        if not raw_artifact:
            raise SystemExit("Every detail result must preserve raw_artifact.")
        raw_path = Path(raw_artifact)
        if not raw_path.is_absolute():
            raw_path = (snapshot_path.parent / raw_path).resolve()
        if not raw_path.is_file():
            raise SystemExit("Every detail result raw_artifact must reference an existing file.")
        target_index = next((index for index, item in enumerate(signals) if signal_key(item, state.get("platform", "")) == key), None)
        if target_index is None:
            raise SystemExit("Backfill target is missing from the canonical snapshot.")
        if success:
            detail = result.get("signal") or result.get("detail")
            if not isinstance(detail, dict):
                raise SystemExit("A successful detail result requires signal or detail data.")
            detail = dict(detail)
            original = signals[target_index]
            detail.setdefault("content_id", original.get("content_id"))
            detail.setdefault("canonical_url", original.get("canonical_url") or original.get("url"))
            detail.setdefault("query_term", original.get("query_term"))
            detail.setdefault("query_layer", original.get("query_layer"))
            detail.setdefault("source_mode", original.get("source_mode", "controlled_capture"))
            detail["detail_captured"] = True
            detail["source_type"] = as_text(detail.get("source_type")) or "direct_post"
            signals[target_index] = merge_signals(original, detail)
        elif stop_reason in HARD_STOPS:
            hard_stop = stop_reason
        audit_entry = {
            "signal_key": key, "layer": allowed[key]["layer"], "success": success,
            "raw_artifact": raw_artifact, "stop_reason": stop_reason,
            "execution": execution if isinstance(execution, dict) else {}, "recorded_at": now_iso(),
        }
        execution_key = as_text((audit_entry.get("execution") or {}).get("metadata_artifact"))
        duplicate = any(
            as_text(item.get("signal_key")) == key
            and as_text((item.get("execution") or {}).get("metadata_artifact")) == execution_key
            and as_bool(item.get("success")) == success
            for item in audits if isinstance(item, dict)
        )
        if not duplicate:
            audits.append(audit_entry)
    unique = {}
    for signal in signals:
        unique[signal_key(signal, state.get("platform", ""))] = signal
    counts = snapshot["collection"].setdefault("counts", {})
    counts["detail_open_count"] = sum(1 for signal in unique.values() if signal.get("detail_captured"))
    snapshot["signals"] = signals
    snapshot["collection"]["stop_reason"] = hard_stop or "collection_in_progress"
    write_json(str(snapshot_path), snapshot)
    state["status"] = "blocked" if hard_stop else "in_progress"
    state["stop_reason"] = hard_stop
    set_snapshot_stop(state, hard_stop or "collection_in_progress")
    if not hard_stop and isinstance(state.get("queries"), list) and all(contract_checks(state).values()):
        state["status"] = "complete"
        state["stop_reason"] = "sampling_contract_met"
        set_snapshot_stop(state, "sampling_contract_met")
    state["updated_at"] = now_iso()


def set_snapshot_stop(state: dict[str, Any], reason: str) -> None:
    target = Path(state["snapshot"])
    if not target.exists():
        return
    snapshot = load_data(str(target))
    snapshot.setdefault("collection", {})["stop_reason"] = reason
    limitations = snapshot["collection"].setdefault("limitations", [])
    transient = (
        "collection_in_progress", "detail_backfill_required", "recovery_queries_required",
        "sampling_contract_met",
    )
    limitations[:] = [
        item for item in limitations
        if item not in transient
        and not as_text(item).startswith("sampling_contract_unmet:")
        and not as_text(item).startswith("observed_budget_guard:")
    ]
    if reason and reason not in {"collection_in_progress", "sampling_contract_met"} and reason not in limitations:
        limitations.append(reason)
    write_json(str(target), snapshot)


def set_budget_audit(state: dict[str, Any]) -> None:
    target = Path(state["snapshot"])
    if not target.exists():
        return
    snapshot = load_data(str(target))
    contract = SAMPLING_CONTRACTS[state["mode"]]
    counts = ((snapshot.get("collection") or {}).get("counts") or {})
    observed = int(counts.get("observed_result_count") or 0)
    upper = int(contract["observed_result_target"][1])
    snapshot.setdefault("collection", {})["observed_budget_audit"] = {
        "upper_bound": upper,
        "observed_result_count": observed,
        "atomic_overshoot": max(0, observed - upper),
        "truncated": False,
        "reason": "atomic_read_overshoot" if observed > upper else "within_budget",
    }
    write_json(str(target), snapshot)


def action(state: dict[str, Any]) -> dict[str, Any]:
    counts = snapshot_counts(state)
    checks = contract_checks(state)
    base = {"status": state["status"], "counts": counts, "contract_checks": checks}
    if state["status"] == "complete" and all(checks.values()):
        state["stop_reason"] = "sampling_contract_met"
        set_snapshot_stop(state, "sampling_contract_met")
        return {**base, "action": "complete", "stop_reason": "sampling_contract_met"}
    if state["status"] == "complete":
        state["status"] = "in_progress"
        state["stop_reason"] = ""
        set_snapshot_stop(state, "collection_in_progress")
    if state["status"] == "blocked" and all(checks.values()):
        state["status"] = "complete"
        state["stop_reason"] = "sampling_contract_met"
        set_snapshot_stop(state, "sampling_contract_met")
        return {**base, "status": "complete", "action": "complete", "stop_reason": "sampling_contract_met"}
    if state["status"] == "blocked":
        query_local_recoverable = (
            as_text(state.get("stop_reason")) in QUERY_LOCAL_STOPS
            and any(query.get("status") == "pending" for query in state.get("queries", []))
        )
        if query_local_recoverable:
            state["status"] = "in_progress"
            state["stop_reason"] = ""
            set_snapshot_stop(state, "collection_in_progress")
        else:
            missing_now = {name for name, passed in checks.items() if not passed}
            sampling_block = as_text(state.get("stop_reason")).startswith("sampling_contract_unmet:")
            detail_recoverable = sampling_block and bool(detail_backfill_plan(state)["targets"])
            recovery_now = recovery_diagnostics(state)
            query_recoverable = (
                sampling_block
                and int(recovery_now.get("query_budget_remaining") or 0) > 0
                and bool((recovery_now.get("volume_recovery") or {}).get("recommended_terms"))
                and search_budget(state)["may_start_search"]
            )
            if not detail_recoverable and not query_recoverable:
                return {**base, "action": "blocked", "stop_reason": state.get("stop_reason", "")}
            state["status"] = "in_progress"
            state["stop_reason"] = "detail_backfill_required" if detail_recoverable else ""
            set_snapshot_stop(state, "collection_in_progress")
    active = state.get("active_query")
    if isinstance(active, dict):
        capture_dir = Path(state["capture_dir"])
        capture_dir.mkdir(parents=True, exist_ok=True)
        raw_output = capture_dir / f"{active['id']}-{active['chunk_count'] + 1:03d}.json"
        screens = int(active.get("next_screens") or state["screens_per_chunk"])
        command = search_capture_command(state, active, raw_output, screens)
        adapter = as_text(state.get("adapter")) or "dokobot"
        return {
            **base,
            "action": "continue_query" if active.get("session_id") else "start_query",
            "query": {key: active[key] for key in ("id", "term", "layer", "url")},
            "session_id": active.get("session_id", ""),
            "raw_output": str(raw_output.resolve()),
            "capture_command": command,
            **({"dokobot_command": command} if adapter == "dokobot" else {"opencli_command": command}),
            "instruction": "Run the selected adapter command through the deterministic capture wrapper and preserve raw output unchanged. Never infer exhaustion from visible-card count alone; on timeout record read_status=timeout.",
        }
    if all(checks.values()):
        state["status"] = "complete"
        state["stop_reason"] = "sampling_contract_met"
        set_snapshot_stop(state, "sampling_contract_met")
        return {**base, "status": "complete", "action": "complete", "stop_reason": "sampling_contract_met"}
    missing = [name for name, passed in checks.items() if not passed]
    budget = search_budget(state)
    pending = next((query for query in state["queries"] if query["status"] == "pending"), None)
    if pending and not pending.get("recovery_round") and budget["may_start_search"]:
        state["active_query"] = new_active_query(pending)
        pending["status"] = "in_progress"
        state["updated_at"] = now_iso()
        return action(state)
    backfill = detail_backfill_plan(state)
    if backfill["targets"]:
        state["status"] = "in_progress"
        state["stop_reason"] = "detail_backfill_required"
        set_snapshot_stop(state, "collection_in_progress")
        capture_dir = Path(state["capture_dir"])
        capture_dir.mkdir(parents=True, exist_ok=True)
        targets = []
        for item in backfill["targets"]:
            safe_key = hashlib.sha256(item["signal_key"].encode("utf-8")).hexdigest()[:16]
            output = capture_dir / f"detail-backfill-{safe_key}.json"
            command = detail_capture_command(state, item["url"], output)
            targets.append({**item, "raw_output": str(output.resolve()), "capture_command": command, **({"dokobot_command": command} if state.get("adapter") == "dokobot" else {"opencli_command": command})})
        return {
            **base,
            "status": "in_progress",
            "action": "backfill_details",
            "missing": missing,
            "required_detail_count": backfill["required_detail_count"],
            "targets": targets,
            "instruction": "Open retained detail targets before creating a report, preserve each raw output, then record successes and failures with record-details. This does not spend search-query budget.",
        }
    if pending and budget["may_start_search"]:
        state["active_query"] = new_active_query(pending)
        pending["status"] = "in_progress"
        state["updated_at"] = now_iso()
        return action(state)
    if not budget["may_start_search"]:
        reason = "observed_budget_guard:" + ",".join(missing)
        state["status"] = "blocked"
        state["stop_reason"] = reason
        set_snapshot_stop(state, reason)
        return {
            **base,
            "status": "blocked",
            "action": "blocked",
            "stop_reason": reason,
            "missing": missing,
            "search_budget": budget,
            "instruction": "Do not start another search. Preserve all observed cards; resolve detail-only gaps by backfill and report other unmet quality gates as a bounded snapshot.",
        }
    recovery = recovery_diagnostics(state)
    if recovery["volume_recovery"]["required"] and not recovery["volume_recovery"]["recommended_terms"]:
        reason = "sampling_contract_unmet:" + ",".join(missing) + ",evidence_recovery_exhausted"
        state["status"] = "blocked"
        state["stop_reason"] = reason
        set_snapshot_stop(state, reason)
        return {
            **base, "status": "blocked", "action": "blocked", "stop_reason": reason,
            "missing": missing, "recovery": recovery,
            "instruction": "Evidence-derived recovery terms are exhausted. Do not invent another query; deliver a bounded snapshot.",
        }
    if recovery["query_budget_remaining"] > 0:
        state["status"] = "in_progress"
        state["stop_reason"] = "recovery_queries_required"
        set_snapshot_stop(state, "collection_in_progress")
        return {
            **base,
            "status": "in_progress",
            "action": "replan_queries",
            "stop_reason": "recovery_queries_required",
            "missing": missing,
            "recovery": recovery,
            "instruction": "Create a non-duplicative recovery query plan that prioritizes the deficient layers, then run add-queries. Do not normalize or report yet.",
        }
    reason = "sampling_contract_unmet:" + ",".join(missing)
    state["status"] = "blocked"
    state["stop_reason"] = reason
    set_snapshot_stop(state, reason)
    return {**base, "status": "blocked", "action": "blocked", "stop_reason": reason, "missing": missing}


def observed_keys(chunk: dict[str, Any]) -> list[str]:
    values = chunk.get("observed_result_keys")
    if values is None:
        values = chunk.get("observed_results")
    keys: list[str] = []
    for item in as_list(values):
        if isinstance(item, dict):
            key = as_text(item.get("key") or item.get("content_id") or item.get("url") or item.get("text"))
        else:
            key = as_text(item)
        if key:
            keys.append(key)
    return keys


def finalize_active(state: dict[str, Any], state_path: Path, stop_reason: str = "") -> None:
    active = state["active_query"]
    final_reason = stop_reason or active.get("stop_reason", "")
    if final_reason in QUERY_LOCAL_STOPS:
        outcome = "completed_partial"
    else:
        outcome = "completed_with_zero_results" if not active["observed_result_keys"] else "completed_with_results"
    relevant_keys = {
        signal_key(item, state.get("platform", "")) for item in active["signals"]
        if item.get("semantic_relevance") in {"direct", "adjacent"}
    }
    observed_count = len(active["observed_result_keys"])
    relevant_count = len(relevant_keys)
    query_result = {
        "query_term": active["term"],
        "query_layer": active["layer"],
        "query_intent": active.get("query_intent", ""),
        "observed_result_count": observed_count,
        "relevant_signal_count": relevant_count,
        "retention_rate": round(len(active["signals"]) / max(observed_count, 1), 3),
        "relevant_yield_rate": round(relevant_count / max(observed_count, 1), 3),
        "low_yield": observed_count == 0 or (observed_count >= 8 and relevant_count <= max(1, math.floor(observed_count * 0.1))),
        "detail_open_count": len(active["detail_open_keys"]),
        "signals": active["signals"],
        "stop_reason": final_reason,
        "outcome": outcome,
        "adapter": as_text(state.get("adapter")) or "dokobot",
        "raw_artifacts": active["raw_artifacts"],
        "capture_executions": active.get("capture_executions", []),
    }
    artifact_dir = state_path.parent / ".trend-collection"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifact_dir / f"query-{active['id']}.json"
    write_json(str(result_path), query_result)
    append_query_result(
        Path(state["snapshot"]), result_path, state["platform"], "controlled_capture", state["mode"]
    )
    set_budget_audit(state)
    for query in state["queries"]:
        if query["id"] == active["id"]:
            query["status"] = "completed"
            query["completion_status"] = outcome
            query["query_result"] = str(result_path.resolve())
            break
    state["active_query"] = None


def record_chunk(state: dict[str, Any], state_path: Path, chunk: Any) -> None:
    if not isinstance(chunk, dict) or not isinstance(state.get("active_query"), dict):
        raise SystemExit("record-chunk requires an active query and a JSON object.")
    active = state["active_query"]
    if as_text(chunk.get("query_id")) != active["id"]:
        raise SystemExit("Capture chunk query_id does not match the active query.")
    raw_artifact = as_text(chunk.get("raw_artifact"))
    if not raw_artifact:
        raise SystemExit("Capture chunk must preserve the raw adapter output path in raw_artifact.")
    incoming_keys = observed_keys(chunk)
    signals = chunk.get("signals", [])
    if not isinstance(signals, list) or any(not isinstance(item, dict) for item in signals):
        raise SystemExit("Capture chunk signals must be a JSON array of objects.")
    read_status = as_text(chunk.get("read_status")) or "success"
    if read_status not in {"success", "timeout", "error"}:
        raise SystemExit("read_status must be success, timeout, or error.")
    stop_reason = as_text(chunk.get("stop_reason"))
    hard_stop = as_text(chunk.get("hard_stop"))
    if hard_stop and hard_stop not in HARD_STOPS:
        raise SystemExit("hard_stop must name a recognized safety or access condition.")
    can_continue = as_bool(chunk.get("can_continue"))
    continuation_status = as_text(chunk.get("continuation_status"))
    terminal_evidence = as_text(chunk.get("terminal_evidence"))
    if not continuation_status:
        continuation_status = "available" if can_continue else "unknown"
    if continuation_status not in {"available", "exhausted", "unknown"}:
        raise SystemExit("continuation_status must be available, exhausted, or unknown.")
    if continuation_status == "exhausted" and terminal_evidence not in TERMINAL_EVIDENCE:
        raise SystemExit("An exhausted chunk requires terminal_evidence: explicit_platform_end, zero_results, or no_more_results.")
    if read_status == "timeout":
        active["timeout_count"] = int(active.get("timeout_count") or 0) + 1
        active["next_screens"] = 1
        continuation_status = "unknown"
        can_continue = True
        stop_reason = ""
        if active["timeout_count"] >= 2:
            stop_reason = "repeated_timeout"
    elif read_status == "error" and not hard_stop and stop_reason not in QUERY_LOCAL_STOPS | SESSION_RECOVERY_STOPS:
        raise SystemExit("A read_status=error chunk requires a recognized hard_stop or query-local error.")
    empty_result = not incoming_keys and not signals
    if empty_result:
        empty_continuation = (
            read_status == "success"
            and continuation_status == "available"
            and bool(active["observed_result_keys"])
        )
        if empty_continuation:
            active["empty_continuation_count"] = int(active.get("empty_continuation_count") or 0) + 1
            if active["empty_continuation_count"] >= 2:
                stop_reason = "continuation_unresolved"
        elif read_status == "success" and (continuation_status != "exhausted" or (not hard_stop and stop_reason not in ZERO_RESULT_STOPS)):
            raise SystemExit("A successful zero-result chunk must record an exhausted continuation with explicit zero-result terminal evidence, or a recognized hard_stop.")
        if as_list(chunk.get("detail_open_keys")):
            raise SystemExit("A zero-result chunk cannot contain detail_open_keys.")
    elif not incoming_keys:
        raise SystemExit("Signals cannot be recorded without observed result keys.")
    else:
        active["empty_continuation_count"] = 0
    known_keys = set(active["observed_result_keys"])
    for key in incoming_keys:
        if key not in known_keys:
            active["observed_result_keys"].append(key)
            known_keys.add(key)
    known_signals = {signal_key(item, state.get("platform", "")) for item in active["signals"]}
    for signal in signals:
        key = signal_key(signal, state.get("platform", ""))
        if key not in known_signals:
            active["signals"].append(signal)
            known_signals.add(key)
    detail_keys = [as_text(item) for item in as_list(chunk.get("detail_open_keys")) if as_text(item)]
    known_details = set(active["detail_open_keys"])
    for key in detail_keys:
        if key not in known_details:
            active["detail_open_keys"].append(key)
            known_details.add(key)
    raw_path = Path(raw_artifact)
    if read_status == "success" and (not raw_path.exists() or not raw_path.is_file()):
        raise SystemExit("A successful capture must preserve an existing raw_artifact file.")
    if raw_path.exists() and raw_artifact not in active["raw_artifacts"]:
        active["raw_artifacts"].append(raw_artifact)
    execution = chunk.get("execution")
    if isinstance(execution, dict):
        active.setdefault("capture_executions", []).append(execution)
    active["session_id"] = as_text(chunk.get("session_id"))
    active["can_continue"] = can_continue
    active["continuation_status"] = continuation_status
    active["chunk_count"] += 1
    active["stop_reason"] = stop_reason
    if read_status == "error" and stop_reason in SESSION_RECOVERY_STOPS and not hard_stop:
        active["session_restart_count"] = int(active.get("session_restart_count") or 0) + 1
        active["session_id"] = ""
        active["can_continue"] = True
        active["continuation_status"] = "unknown"
        active["next_screens"] = 1
        if active["session_restart_count"] <= 1:
            stop_reason = ""
            active["stop_reason"] = ""
        else:
            stop_reason = "session_recovery_failed"
            active["stop_reason"] = stop_reason
    contract = SAMPLING_CONTRACTS[state["mode"]]
    per_query_target = int(contract["per_query_observed_target"])
    under_target = len(active["observed_result_keys"]) < per_query_target
    if read_status == "success" and under_target and continuation_status == "unknown" and not hard_stop:
        active["continuation_unknown_count"] = int(active.get("continuation_unknown_count") or 0) + 1
        active["next_screens"] = 1
        active["can_continue"] = True
        active["stop_reason"] = ""
        if active["continuation_unknown_count"] >= 2:
            stop_reason = "continuation_unresolved"
            active["stop_reason"] = stop_reason
    should_finalize = (
        len(active["observed_result_keys"]) >= per_query_target
        or continuation_status == "exhausted"
        or stop_reason in QUERY_LOCAL_STOPS
        or bool(hard_stop)
    )
    if should_finalize:
        finalize_active(state, state_path, hard_stop or active["stop_reason"])
    if hard_stop:
        state["status"] = "blocked"
        state["stop_reason"] = hard_stop
        set_snapshot_stop(state, hard_stop)
    elif stop_reason in QUERY_LOCAL_STOPS:
        state["status"] = "in_progress"
        state["stop_reason"] = ""
        set_snapshot_stop(state, "collection_in_progress")
    state["updated_at"] = now_iso()


def record_capture(state: dict[str, Any], state_path: Path, metadata: Any, extraction: Any) -> None:
    allowed_schemas = {"dokobot-capture-execution-v0.1", "collection-capture-execution-v0.2"}
    if not isinstance(metadata, dict) or metadata.get("schema_version") not in allowed_schemas:
        raise SystemExit("record-capture requires deterministic collection execution metadata.")
    if not isinstance(extraction, dict):
        raise SystemExit("record-capture extraction must be a JSON object.")
    extraction_query_id = as_text(extraction.get("query_id"))
    if extraction_query_id and extraction_query_id != as_text(metadata.get("query_id")):
        raise SystemExit("Extraction query_id does not match deterministic execution metadata.")
    extraction.pop("query_id", None)
    forbidden = {
        "read_status", "session_id", "can_continue", "continuation_status",
        "terminal_evidence", "raw_artifact", "stop_reason", "hard_stop", "execution",
    }
    supplied_forbidden = sorted(forbidden.intersection(extraction))
    if supplied_forbidden:
        raise SystemExit("Extraction cannot override deterministic execution fields: " + ", ".join(supplied_forbidden))
    active = state.get("active_query")
    if not isinstance(active, dict) or metadata.get("query_id") != active.get("id"):
        raise SystemExit("Execution metadata does not match the active query.")
    expected = action(state)
    expected_command = expected.get("capture_command") or expected.get("dokobot_command")
    expected_hash = hashlib.sha256(json.dumps(expected_command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    if metadata.get("requested_command_sha256") != expected_hash:
        raise SystemExit("Execution metadata command does not match the current orchestrator action.")
    if str(Path(as_text(metadata.get("raw_artifact"))).resolve()) != str(Path(as_text(expected.get("raw_output"))).resolve()):
        raise SystemExit("Execution metadata raw artifact does not match the orchestrator output path.")
    for field in ("stdout_artifact", "stderr_artifact", "metadata_artifact"):
        artifact = Path(as_text(metadata.get(field)))
        if not artifact.is_file():
            raise SystemExit(f"Execution metadata requires an existing {field} file.")
    raw_path = Path(as_text(metadata.get("raw_artifact")))
    if metadata.get("read_status") == "success" and not raw_path.is_file():
        raise SystemExit("Successful execution metadata requires an existing raw_artifact file.")
    chunk = {
        "query_id": metadata.get("query_id"),
        "read_status": metadata.get("read_status"),
        "session_id": metadata.get("session_id"),
        "can_continue": metadata.get("can_continue"),
        "continuation_status": metadata.get("continuation_status"),
        "terminal_evidence": metadata.get("terminal_evidence"),
        "raw_artifact": metadata.get("raw_artifact"),
        "stop_reason": metadata.get("stop_reason"),
        "hard_stop": metadata.get("hard_stop"),
        "execution": {
            "requested_command_sha256": metadata.get("requested_command_sha256"),
            "exit_code": metadata.get("exit_code"),
            "started_at": metadata.get("started_at"),
            "finished_at": metadata.get("finished_at"),
            "stdout_artifact": metadata.get("stdout_artifact"),
            "stderr_artifact": metadata.get("stderr_artifact"),
            "metadata_artifact": metadata.get("metadata_artifact"),
        },
        **extraction,
    }
    record_chunk(state, state_path, chunk)


def main() -> None:
    parser = argparse.ArgumentParser(description="Enforce adapter-neutral collection sequencing and sampling gates.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init = subparsers.add_parser("init")
    init.add_argument("--state", required=True)
    init.add_argument("--snapshot", required=True)
    init.add_argument("--plan", required=True)
    init.add_argument("--adapter-status", required=True)
    init.add_argument("--research-context")
    init.add_argument("--platform", required=True)
    init.add_argument("--mode", choices=sorted(SAMPLING_CONTRACTS), default="standard")
    init.add_argument("--screens-per-chunk", type=int, default=1)
    next_action = subparsers.add_parser("next")
    next_action.add_argument("--state", required=True)
    record = subparsers.add_parser("record-chunk")
    record.add_argument("--state", required=True)
    record.add_argument("--chunk", required=True)
    record_capture_parser = subparsers.add_parser("record-capture")
    record_capture_parser.add_argument("--state", required=True)
    record_capture_parser.add_argument("--metadata", required=True)
    record_capture_parser.add_argument("--extraction", required=True)
    record_details = subparsers.add_parser("record-details")
    record_details.add_argument("--state", required=True)
    record_details.add_argument("--results", required=True)
    add_queries = subparsers.add_parser("add-queries")
    add_queries.add_argument("--state", required=True)
    add_queries.add_argument("--plan", required=True)
    args = parser.parse_args()

    state_path = Path(args.state).resolve()
    if args.command == "init":
        if args.screens_per_chunk < 1 or args.screens_per_chunk > 10:
            raise SystemExit("--screens-per-chunk must be between 1 and 10.")
        research_context = load_context(Path(args.research_context).resolve()) if args.research_context else None
        queries = validate_plan(load_data(args.plan), args.mode, research_context)
        adapter_status = load_data(args.adapter_status)
        adapter = as_text(adapter_status.get("adapter")) if isinstance(adapter_status, dict) else ""
        if not isinstance(adapter_status, dict) or not status_supports(adapter_status, args.platform):
            raise SystemExit("The selected adapter preflight is not ready; do not initialize controlled collection.")
        platform_key = normalized_platform(args.platform)
        if research_context and research_context["platform"] != platform_key:
            raise SystemExit("Research context platform does not match the collection platform.")
        state = {
            "schema_version": SCHEMA_VERSION,
            "platform_adapter_contract": CONTRACT_VERSION,
            "platform_adapter_registry": ADAPTER_REGISTRY_VERSION,
            "adapter": adapter,
            "platform": platform_key,
            "source_mode": "controlled_capture",
            "mode": args.mode,
            "snapshot": str(Path(args.snapshot).resolve()),
            "plan": str(Path(args.plan).resolve()),
            "adapter_status": str(Path(args.adapter_status).resolve()),
            **({
                "research_context": str(Path(args.research_context).resolve()),
                "research_context_schema": research_context["schema_version"],
                "research_intent": research_context["research_intent"],
                "decision_profile_version": research_context["profile_version"],
                "source_prompt_sha256": research_context["source_prompt_sha256"],
            } if research_context else {}),
            "capture_dir": str((state_path.parent / "captures").resolve()),
            "screens_per_chunk": args.screens_per_chunk,
            "status": "in_progress",
            "stop_reason": "",
            "queries": [{**query, "status": "pending"} for query in queries],
            "active_query": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
    else:
        state = load_state(state_path)
        if args.command == "record-chunk":
            record_chunk(state, state_path, load_data(args.chunk))
        elif args.command == "record-capture":
            record_capture(state, state_path, load_data(args.metadata), load_data(args.extraction))
        elif args.command == "record-details":
            record_detail_backfill(state, load_data(args.results))
        elif args.command == "add-queries":
            recoverable_block = (
                state.get("status") == "blocked"
                and as_text(state.get("stop_reason")).startswith("sampling_contract_unmet:")
                and recovery_diagnostics(state)["query_budget_remaining"] > 0
            )
            if (state.get("status") != "in_progress" and not recoverable_block) or state.get("active_query") or any(query["status"] == "pending" for query in state["queries"]):
                raise SystemExit("Recovery queries can only be added after the initial plan is exhausted and replan_queries is requested.")
            queries = validate_recovery_plan(load_data(args.plan), state)
            round_number = int(state.get("recovery_round") or 0) + 1
            state["queries"].extend({**query, "status": "pending", "recovery_round": round_number} for query in queries)
            state["recovery_round"] = round_number
            state["status"] = "in_progress"
            state["stop_reason"] = ""
            set_snapshot_stop(state, "collection_in_progress")
    current_action = action(state)
    state["updated_at"] = now_iso()
    write_json(str(state_path), state)
    # CLI stdout is a machine-readable contract. Escaping non-ASCII keeps the
    # JSON portable on Windows consoles whose legacy code page cannot encode
    # emoji or some platform text. json.loads restores the original Unicode.
    print(__import__("json").dumps(current_action, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
