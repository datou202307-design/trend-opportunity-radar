from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCORE_VERSION = "trend-evidence-v0.5.0-candidate"
SCHEMA_VERSION = "trend-signal-snapshot-v0.4"
QUERY_LAYERS = ("platform_baseline", "category", "subject_bridge")
SOURCE_MODES = {"authorized_api", "customer_export", "controlled_capture", "public_web", "historical_snapshot"}
HEAT_WEIGHTS = {
    "content_volume": 20,
    "engagement": 25,
    "velocity": 25,
    "diffusion": 15,
    "search_demand": 10,
    "freshness": 5,
}
CONFIDENCE_WEIGHTS = {
    "sample_sufficiency": 25,
    "author_diversity": 20,
    "source_quality": 20,
    "field_coverage": 20,
    "counterevidence": 15,
}
SOURCE_QUALITY = {
    "direct_post": 100,
    "exported_item": 90,
    "search_card": 55,
    "platform_summary": 45,
    "profile": 35,
    "webpage": 50,
    "search_snippet": 25,
    "historical_item": 40,
    "unknown": 20,
}
ENGAGEMENT_WEIGHT_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "references" / "engagement-weight-registry.json"


def load_engagement_weight_registry() -> dict[str, Any]:
    with ENGAGEMENT_WEIGHT_REGISTRY_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("schema_version") != "platform-engagement-weights-v0.1-candidate":
        raise ValueError("Unsupported engagement weight registry version.")
    return payload


ENGAGEMENT_WEIGHT_REGISTRY = load_engagement_weight_registry()
SAMPLING_CONTRACTS = {
    "quick": {
        "query_target": [3, 5],
        "observed_result_target": [20, 40],
        "per_query_observed_target": 7,
        "atomic_read_reserve": 10,
        "unique_signal_target": [8, 15],
        "detail_open_target": [4, 8],
        "counter_signal_min": 2,
        "opportunity_target": [1, 3],
        "repeat_snapshot_min": 1,
        "layer_query_min": 1,
        "layer_observed_min": 4,
        "layer_unique_signal_min": 2,
        "layer_relevant_signal_min": 1,
        "layer_direct_signal_min": 0,
        "relevant_unique_signal_min": 4,
        "layer_detail_min": 0,
        "subject_bridge_direct_min": 0,
        "relevance_review_coverage_min": 0.0,
    },
    "standard": {
        "query_target": [3, 9],
        "observed_result_target": [60, 100],
        "per_query_observed_target": 10,
        "atomic_read_reserve": 20,
        "unique_signal_target": [30, 50],
        "detail_open_target": [12, 18],
        "counter_signal_min": 3,
        "opportunity_target": [3, 5],
        "repeat_snapshot_min": 1,
        "layer_query_min": 1,
        "layer_observed_min": 8,
        "layer_unique_signal_min": 4,
        "layer_relevant_signal_min": 4,
        "layer_direct_signal_min": 2,
        "relevant_unique_signal_min": 18,
        "layer_detail_min": 2,
        "subject_bridge_direct_min": 2,
        "relevance_review_coverage_min": 0.8,
    },
    "deep": {
        "query_target": [9, 15],
        "observed_result_target": [100, 300],
        "per_query_observed_target": 12,
        "atomic_read_reserve": 25,
        "unique_signal_target": [80, 200],
        "detail_open_target": [20, 40],
        "counter_signal_min": 8,
        "opportunity_target": [5, 8],
        "repeat_snapshot_min": 2,
        "layer_query_min": 3,
        "layer_observed_min": 15,
        "layer_unique_signal_min": 8,
        "layer_relevant_signal_min": 8,
        "layer_direct_signal_min": 3,
        "relevant_unique_signal_min": 48,
        "layer_detail_min": 3,
        "subject_bridge_direct_min": 3,
        "relevance_review_coverage_min": 0.9,
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_data(path: str) -> Any:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    with source.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


def first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return value
    return None


def as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, list) else [parsed]
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in re.split(r"[|,，;；\n]+", text) if item.strip()]
    return [value]


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) and float(value) >= 0 else None
    text = str(value).strip().lower().replace(",", "")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(k|m|b|万|亿)?", text)
    if not match:
        return None
    multiplier = {None: 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "万": 10_000, "亿": 100_000_000}[match.group(2)]
    return float(match.group(1)) * multiplier


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return as_text(value).lower() in {"1", "true", "yes", "y"}


MOJIBAKE_MARKERS = (
    "\ufffd", "Ã", "Â", "â€", "â€™", "â€œ", "â€�", "æ�", "ç´", "å®",
    "°ï", "Öú", "¶À", "Á¢", "¹Ë", "ÎÊ", "¼¼ÄÜ", "È÷ÊÆ",
    "鏂囨梾", "鍏ㄩ摼", "璺惀", "閿€涓績",
)


def clean_isolated_replacement_characters(value: Any) -> tuple[str, bool]:
    """Remove U+FFFD from normalized text while retaining the immutable raw capture."""
    text = as_text(value)
    return text.replace("\ufffd", "").rstrip(), "\ufffd" in text


def text_integrity_issues(value: Any, path: str = "$") -> list[str]:
    """Return paths containing strong encoding-corruption markers.

    The check intentionally fails closed instead of trying to repair source text. Automatic
    transcoding can silently change legitimate names and evidence, while a rejected artifact can
    be regenerated from its UTF-8 source.
    """
    issues: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            issues.extend(text_integrity_issues(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(text_integrity_issues(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        hits = [marker for marker in MOJIBAKE_MARKERS if marker in value]
        if hits:
            issues.append(f"{path}: suspected text-encoding corruption ({', '.join(hits[:3])})")
    return issues


def require_text_integrity(value: Any, label: str) -> None:
    issues = text_integrity_issues(value)
    if issues:
        raise SystemExit(f"{label} failed UTF-8 text integrity:\n- " + "\n- ".join(issues[:20]))


def metric_number(row: dict[str, Any], *keys: str) -> float | None:
    for section_name in ("metrics", "public_metrics"):
        section = row.get(section_name)
        if isinstance(section, dict):
            for key in keys:
                value = as_number(section.get(key))
                if value is not None:
                    return value
    return as_number(first(row, *keys, *(f"metrics.{key}" for key in keys), *(f"public_metrics.{key}" for key in keys)))


def normalize_platform(value: Any) -> str:
    text = as_text(value).lower()
    aliases = {
        "小红书": "xiaohongshu", "rednote": "xiaohongshu", "red": "xiaohongshu", "xhs": "xiaohongshu",
        "twitter": "x", "推特": "x", "抖音": "douyin", "tiktok": "tiktok", "tik tok": "tiktok", "国际抖音": "tiktok",
        "yt": "youtube", "油管": "youtube",
        "reddit": "reddit",
        "instagram": "instagram", "ins": "instagram",
        "视频号": "wechat_channels", "wechat channels": "wechat_channels",
    }
    return aliases.get(text, re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "_", text).strip("_"))


def engagement_weights(platform: Any) -> dict[str, float]:
    normalized = normalize_platform(platform)
    configured = (ENGAGEMENT_WEIGHT_REGISTRY.get("platforms") or {}).get(normalized)
    source = configured if isinstance(configured, dict) else ENGAGEMENT_WEIGHT_REGISTRY["default"]
    return {key: float(source.get(key, 1.0)) for key in ("likes", "comments", "shares", "saves")}


def normalize_url(value: Any) -> str:
    text = as_text(value)
    return text if text.startswith(("http://", "https://", "snapshot://", "artifact://")) else ""


def stable_signal_identity(row: dict[str, Any], platform: str = "") -> str:
    """Return a source-stable identity, preferring platform content IDs over presentation fields."""
    normalized_platform = normalize_platform(first(row, "platform") or platform)
    content_id = as_text(first(row, "content_id", "contentId", "id"))
    if content_id:
        return f"{normalized_platform}|content_id|{content_id}"
    url = normalize_url(first(row, "canonical_url", "canonicalUrl", "url", "link", "source_url"))
    if url:
        canonical = url.split("#", 1)[0].rstrip("/")
        return f"{normalized_platform}|url|{canonical}"
    author = row.get("author") if isinstance(row.get("author"), dict) else {}
    author_id = as_text(first(author, "id", "author_id") or first(row, "author_id", "authorId", "username"))
    published_at = as_text(first(row, "published_at", "publishedAt", "created_at", "createdAt"))
    text = as_text(first(row, "title", "name", "text", "body", "summary"))[:500]
    return f"{normalized_platform}|fallback|{author_id}|{published_at}|{text}"


def stable_signal_key(row: dict[str, Any], platform: str = "") -> str:
    return hashlib.sha256(stable_signal_identity(row, platform).encode("utf-8")).hexdigest()


def infer_source_type(row: dict[str, Any], source_mode: str, url: str, detail_captured: bool) -> str:
    explicit = as_text(first(row, "source_type", "sourceType", "evidence_source_type"))
    limitations = {as_text(item).lower() for item in as_list(first(row, "limitations", "limits"))}
    if explicit == "direct_post" and source_mode == "controlled_capture" and not detail_captured:
        return "search_card"
    if "search_card_only" in limitations:
        return "search_card"
    if explicit in SOURCE_QUALITY:
        return explicit
    lowered = url.lower()
    if source_mode == "authorized_api":
        return "direct_post"
    if source_mode == "customer_export":
        return "exported_item"
    if source_mode == "historical_snapshot":
        return "historical_item"
    if "/i/trending/" in lowered:
        return "platform_summary"
    if re.search(r"/(status|note|explore|video)/", lowered):
        return "direct_post" if detail_captured else "search_card" if source_mode == "controlled_capture" else "search_snippet"
    if source_mode == "public_web" and not detail_captured:
        return "search_snippet"
    return "webpage" if url else "unknown"


def normalize_signal(row: dict[str, Any], platform: str, source_mode: str, captured_at: str) -> dict[str, Any]:
    metrics = {
        "views": metric_number(row, "views", "view_count", "impressions", "impression_count"),
        "likes": metric_number(row, "likes", "like_count"),
        "saves": metric_number(row, "saves", "save_count", "bookmarks", "bookmark_count", "favorites"),
        "comments": metric_number(row, "comments", "comment_count", "replies", "reply_count"),
        "shares": metric_number(row, "shares", "share_count", "reposts", "retweet_count", "quote_count"),
    }
    metrics = {key: int(value) if value is not None else None for key, value in metrics.items()}
    author = row.get("author") if isinstance(row.get("author"), dict) else {}
    discovery = row.get("discovery") if isinstance(row.get("discovery"), dict) else {}
    platform_facts = row.get("platform_facts") if isinstance(row.get("platform_facts"), dict) else {}
    content_evidence = row.get("content_evidence") if isinstance(row.get("content_evidence"), dict) else {}
    url = normalize_url(first(row, "canonical_url", "canonicalUrl", "url", "link", "source_url"))
    title, title_repaired = clean_isolated_replacement_characters(first(row, "title", "name", "text", "body"))
    summary, summary_repaired = clean_isolated_replacement_characters(first(row, "summary", "description", "body", "text"))
    title = title[:500]
    summary = summary[:4000]
    author_id = as_text(first(author, "id", "author_id") or first(row, "author_id", "authorId", "username"))
    published_at = as_text(first(row, "published_at", "publishedAt", "created_at", "createdAt"))
    row_captured_at = as_text(first(row, "captured_at", "capturedAt")) or captured_at
    detail_captured = as_bool(first(row, "detail_captured", "detailCaptured", "detail_opened"))
    signal_source_mode = as_text(first(row, "source_mode", "sourceMode")) or source_mode
    normalized_platform = normalize_platform(first(row, "platform") or platform)
    dedupe_hash = stable_signal_key(row, normalized_platform)
    content_id = as_text(first(row, "content_id", "contentId", "id"))
    supplied_signal_id = as_text(first(row, "signal_id", "signalId", "id"))
    stable_signal_id = supplied_signal_id or (
        f"{normalized_platform}-{content_id}" if normalized_platform and content_id else f"signal-{dedupe_hash[:12]}"
    )
    evidence_refs = [normalize_url(item) for item in as_list(first(row, "evidence_refs", "evidenceRefs", "refs"))]
    if url:
        evidence_refs.insert(0, url)
    limitations = [as_text(item) for item in as_list(first(row, "limitations", "limits")) if as_text(item)]
    if title_repaired or summary_repaired:
        limitations.append("An invalid replacement character was removed from platform card text; the immutable raw capture is retained for audit.")
    role = as_text(first(row, "evidence_role", "evidenceRole", "role")).lower()
    return {
        "signal_id": stable_signal_id,
        "platform": normalized_platform,
        "source_mode": signal_source_mode,
        "source_type": infer_source_type(row, signal_source_mode, url, detail_captured),
        "evidence_role": role if role in {"support", "counter", "neutral"} else "neutral",
        "profile_evidence_role": as_text(first(row, "profile_evidence_role", "profileEvidenceRole")),
        "detail_captured": detail_captured,
        "detail_access": row.get("detail_access") if isinstance(row.get("detail_access"), dict) else {},
        "detail_source_mode": as_text(first(row, "detail_source_mode", "detailSourceMode")),
        "detail_text_kind": as_text(first(row, "detail_text_kind", "detailTextKind")),
        "content_id": content_id,
        "canonical_url": url,
        "query_term": as_text(first(row, "query_term", "queryTerm", "query", "keyword")),
        "query_layer": as_text(first(row, "query_layer", "queryLayer", "scope")) or "unspecified",
        "query_intent": as_text(first(row, "query_intent", "queryIntent")),
        "query_terms": [as_text(item) for item in as_list(first(row, "query_terms", "queryTerms")) if as_text(item)],
        "query_layers": [as_text(item) for item in as_list(first(row, "query_layers", "queryLayers")) if as_text(item)],
        "semantic_relevance": as_text(first(row, "semantic_relevance", "semanticRelevance")).lower()
        if as_text(first(row, "semantic_relevance", "semanticRelevance")).lower() in {"direct", "adjacent", "weak"}
        else "unreviewed",
        "semantic_review": row.get("semantic_review") if isinstance(row.get("semantic_review"), dict) else {},
        "topic_key": as_text(first(row, "topic_key", "topicKey")),
        "title": title,
        "summary": summary,
        "published_at": published_at,
        "captured_at": row_captured_at,
        "metrics_captured_at": as_text(first(row, "metrics_captured_at", "metricsCapturedAt")) or row_captured_at,
        "metrics": metrics,
        "author": {
            "id": author_id,
            "name": as_text(first(author, "name", "display_name") or first(row, "author_name", "authorName")),
            "type": as_text(first(author, "type", "author_type") or first(row, "author_type", "authorType")),
            "follower_count": as_number(first(author, "follower_count", "followerCount") or first(row, "follower_count", "followerCount")),
            "verified": first(author, "verified") if "verified" in author else first(row, "verified", "author_verified"),
        },
        "discovery": {
            "search_rank": as_number(first(discovery, "search_rank", "searchRank") or first(row, "search_rank", "searchRank")),
            "search_result_count": as_number(first(discovery, "search_result_count", "searchResultCount") or first(row, "search_result_count", "searchResultCount")),
            "observed_content_count": as_number(first(discovery, "observed_content_count", "observedContentCount") or first(row, "observed_content_count", "observedContentCount")),
        },
        "time_series": {
            "growth_rate_percent": as_number(first(row, "growth_rate_percent", "growthRatePercent")),
            "current_window_count": as_number(first(row, "current_window_count", "currentWindowCount")),
            "previous_window_count": as_number(first(row, "previous_window_count", "previousWindowCount")),
            "comparison_count": as_number(first(row, "comparison_count", "comparisonCount")),
        },
        "platform_facts": platform_facts,
        "content_evidence": content_evidence,
        "evidence_refs": list(dict.fromkeys(item for item in evidence_refs if item)),
        "limitations": limitations,
        "permission_scope": as_text(first(row, "permission_scope", "permissionScope")) or "unspecified",
        "dedupe_hash": dedupe_hash,
        "merged_from_count": int(as_number(first(row, "merged_from_count", "mergedFromCount")) or 1),
        "source_variants": as_list(first(row, "source_variants", "sourceVariants")),
    }


def merge_signals(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Merge duplicate observations without losing query provenance or richer direct evidence."""
    left_quality = (1 if left.get("detail_captured") else 0, SOURCE_QUALITY.get(left.get("source_type", "unknown"), 0), len(as_text(left.get("summary"))))
    right_quality = (1 if right.get("detail_captured") else 0, SOURCE_QUALITY.get(right.get("source_type", "unknown"), 0), len(as_text(right.get("summary"))))
    primary, secondary = (right, left) if right_quality > left_quality else (left, right)
    merged = dict(primary)
    for field in ("canonical_url", "content_id", "title", "summary", "published_at", "captured_at", "metrics_captured_at", "permission_scope"):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    for section in ("metrics", "author", "discovery", "time_series", "platform_facts", "content_evidence"):
        combined = dict(secondary.get(section) or {})
        combined.update({key: value for key, value in (primary.get(section) or {}).items() if value not in (None, "")})
        merged[section] = combined
    merged["detail_captured"] = bool(left.get("detail_captured") or right.get("detail_captured"))
    merged["evidence_refs"] = list(dict.fromkeys([*(left.get("evidence_refs") or []), *(right.get("evidence_refs") or [])]))
    merged["limitations"] = list(dict.fromkeys([*(left.get("limitations") or []), *(right.get("limitations") or [])]))
    merged["query_terms"] = list(dict.fromkeys([left.get("query_term"), *(left.get("query_terms") or []), right.get("query_term"), *(right.get("query_terms") or [])]))
    merged["query_layers"] = list(dict.fromkeys([left.get("query_layer"), *(left.get("query_layers") or []), right.get("query_layer"), *(right.get("query_layers") or [])]))
    merged["query_terms"] = [item for item in merged["query_terms"] if item]
    merged["query_layers"] = [item for item in merged["query_layers"] if item]
    relevance_rank = {"unreviewed": 0, "weak": 1, "adjacent": 2, "direct": 3}
    merged["semantic_relevance"] = max((left.get("semantic_relevance", "unreviewed"), right.get("semantic_relevance", "unreviewed")), key=lambda item: relevance_rank.get(item, 0))
    # Detail reads enrich source content; they do not replace the independent
    # semantic decision already recorded for the search card.
    reviewed = left if left.get("semantic_review") else right if right.get("semantic_review") else None
    if reviewed:
        merged["semantic_review"] = reviewed["semantic_review"]
    for field in ("evidence_role", "profile_evidence_role", "query_intent", "topic_key"):
        reviewed_value = reviewed.get(field) if reviewed else None
        merged[field] = reviewed_value or left.get(field) or right.get(field)
    if merged["detail_captured"]:
        stale_detail_limits = {
            "search_card_only", "Search card only",
            "Semantic relevance requires a separate review.",
        }
        merged["limitations"] = [
            item for item in merged["limitations"]
            if as_text(item).strip() not in stale_detail_limits
        ]
    merged["merged_from_count"] = int(left.get("merged_from_count") or 1) + int(right.get("merged_from_count") or 1)
    variants = [*(left.get("source_variants") or []), *(right.get("source_variants") or [])]
    variants.extend({"source_type": item.get("source_type"), "query_term": item.get("query_term"), "query_layer": item.get("query_layer"), "detail_captured": item.get("detail_captured")} for item in (left, right))
    merged["source_variants"] = variants
    return merged


def _log_score(value: float, ceiling: float) -> float:
    return max(0.0, min(100.0, math.log1p(max(value, 0)) / math.log1p(ceiling) * 100))


def freshness_score(value: str, as_of: datetime) -> float | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        days = max(0.0, (as_of - parsed.astimezone(timezone.utc)).total_seconds() / 86400)
    except (ValueError, TypeError):
        return None
    if days <= 1:
        return 100.0
    if days <= 7:
        return 80.0
    if days <= 30:
        return 55.0
    if days <= 90:
        return 30.0
    return 10.0


def signal_dimensions(signal: dict[str, Any], as_of: datetime | None = None) -> dict[str, float]:
    as_of = as_of or datetime.now(timezone.utc)
    metrics = signal.get("metrics") or {}
    discovery = signal.get("discovery") or {}
    series = signal.get("time_series") or {}
    dimensions: dict[str, float] = {}
    count = as_number(discovery.get("observed_content_count"))
    if count is not None:
        dimensions["content_volume"] = _log_score(count, 1000)
    views = as_number(metrics.get("views"))
    weights = engagement_weights(signal.get("platform"))
    interactions = [
        value * weights[key]
        for key in ("likes", "saves", "comments", "shares")
        if (value := as_number(metrics.get(key))) is not None
    ]
    if views is not None or interactions:
        total = sum(interactions)
        dimensions["engagement"] = min(100.0, total / max(views or 0, 1) * 1000) if views is not None and interactions else _log_score(total or views or 0, 100000)
    growth = as_number(series.get("growth_rate_percent"))
    current = as_number(series.get("current_window_count"))
    previous = as_number(series.get("previous_window_count"))
    if growth is not None or (current is not None and previous is not None):
        rate = growth if growth is not None else (current - previous) / max(previous, 1) * 100
        dimensions["velocity"] = max(0.0, min(100.0, 50 + rate / 2))
    search_count = as_number(discovery.get("search_result_count"))
    search_rank = as_number(discovery.get("search_rank"))
    if search_count is not None or search_rank is not None:
        dimensions["search_demand"] = _log_score(search_count, 10000) if search_count is not None else max(0.0, min(100.0, 105 - search_rank))
    fresh = freshness_score(as_text(signal.get("published_at")), as_of)
    if fresh is not None:
        dimensions["freshness"] = fresh
    return dimensions


def calculate_index(signal: dict[str, Any], as_of: datetime | None = None) -> dict[str, Any]:
    dimensions = signal_dimensions(signal, as_of)
    missing = [name for name in HEAT_WEIGHTS if name not in dimensions and name != "diffusion"]
    coverage = sum(HEAT_WEIGHTS[name] for name in dimensions)
    observed_heat = round(sum(dimensions[name] * HEAT_WEIGHTS[name] / 100 for name in dimensions))
    source_quality = SOURCE_QUALITY.get(signal.get("source_type", "unknown"), SOURCE_QUALITY["unknown"])
    evidence_confidence = round(coverage * 0.6 + source_quality * 0.4)
    return {
        "observed_heat": observed_heat,
        "evidence_confidence": evidence_confidence,
        "heat_index": observed_heat,
        "data_coverage": coverage,
        "score_status": "complete" if coverage >= 75 else "partial" if coverage >= 40 else "sparse",
        "score_version": SCORE_VERSION,
        "engagement_weight_version": ENGAGEMENT_WEIGHT_REGISTRY["schema_version"],
        "engagement_weights": engagement_weights(signal.get("platform")),
        "dimensions": {key: round(value, 2) for key, value in dimensions.items()},
        "source_quality": source_quality,
        "missing_fields": missing,
    }


def calculate_topic_index(
    members: list[dict[str, Any]],
    as_of: datetime | None = None,
    collection: dict[str, Any] | None = None,
    cluster_audit: dict[str, Any] | None = None,
    clustering_applied: bool = False,
) -> dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc)
    member_dimensions = [signal_dimensions(member, as_of) for member in members]
    dimensions: dict[str, float] = {"content_volume": _log_score(len(members), 50)}
    for name in ("engagement", "velocity", "search_demand", "freshness"):
        values = [item[name] for item in member_dimensions if name in item]
        if values:
            dimensions[name] = statistics.median(values)
    author_ids = {
        as_text((member.get("author") or {}).get("id") or (member.get("author") or {}).get("name")).casefold()
        for member in members
        if as_text((member.get("author") or {}).get("id") or (member.get("author") or {}).get("name"))
        and member.get("source_type") not in {"platform_summary", "search_snippet"}
    }
    if author_ids:
        dimensions["diffusion"] = min(100.0, len(author_ids) / max(len(members), 1) * 100)
    coverage = sum(HEAT_WEIGHTS[name] for name in dimensions)
    observed_heat = round(sum(dimensions[name] * HEAT_WEIGHTS[name] / 100 for name in dimensions))
    source_scores = [SOURCE_QUALITY.get(member.get("source_type", "unknown"), SOURCE_QUALITY["unknown"]) for member in members]
    assigned_counter_ids = {
        as_text(item.get("signal_id"))
        for item in ((cluster_audit or {}).get("assignments") or [])
        if isinstance(item, dict) and item.get("fit") == "counter"
    }
    counters = sum(
        1 for member in members
        if member.get("evidence_role") == "counter" or as_text(member.get("signal_id")) in assigned_counter_ids
    )
    confidence_dimensions = {
        "sample_sufficiency": min(100.0, len(members) / 5 * 100),
        "author_diversity": min(100.0, len(author_ids) / 3 * 100),
        "source_quality": statistics.mean(source_scores) if source_scores else 0.0,
        "field_coverage": coverage,
        "counterevidence": 100.0 if counters else 0.0,
    }
    raw_confidence = round(sum(confidence_dimensions[name] * CONFIDENCE_WEIGHTS[name] / 100 for name in confidence_dimensions))
    collection_status = (collection or {}).get("contract_status", "untracked")
    confidence_cap = {"met": 100, "partial": 54, "blocked": 54, "untracked": 45}.get(collection_status, 45)
    cap_reasons = [] if confidence_cap == 100 else ["sampling_contract_incomplete"]
    if clustering_applied and (not cluster_audit or cluster_audit.get("status") != "passed"):
        confidence_cap = min(confidence_cap, 54)
        cap_reasons.append("cluster_audit_missing_or_failed")
    evidence_confidence = min(raw_confidence, confidence_cap)
    subject_bridge_members = [member for member in members if "subject_bridge" in {member.get("query_layer"), *(member.get("query_layers") or [])}]
    subject_bridge_direct = [
        member for member in subject_bridge_members
        if member.get("semantic_relevance") == "direct"
        and (member.get("detail_captured") or member.get("source_type") in {"direct_post", "exported_item"})
    ]
    reviewed_count = sum(1 for member in members if member.get("semantic_relevance") in {"direct", "adjacent", "weak"})
    return {
        "observed_heat": observed_heat,
        "evidence_confidence": evidence_confidence,
        "heat_index": observed_heat,
        "data_coverage": coverage,
        "score_status": "complete" if coverage >= 75 else "partial" if coverage >= 40 else "sparse",
        "score_version": SCORE_VERSION,
        "engagement_weight_version": ENGAGEMENT_WEIGHT_REGISTRY["schema_version"],
        "engagement_weights": engagement_weights(members[0].get("platform") if members else ""),
        "dimensions": {key: round(value, 2) for key, value in dimensions.items()},
        "confidence_dimensions": {key: round(value, 2) for key, value in confidence_dimensions.items()},
        "raw_evidence_confidence": raw_confidence,
        "confidence_cap": confidence_cap,
        "confidence_cap_reason": ",".join(dict.fromkeys(cap_reasons)) if cap_reasons else "none",
        "unique_author_count": len(author_ids),
        "direct_source_count": sum(1 for member in members if member.get("source_type") in {"direct_post", "exported_item"}),
        "search_card_count": sum(1 for member in members if member.get("source_type") == "search_card"),
        "counter_signal_count": counters,
        "subject_bridge_signal_count": len(subject_bridge_members),
        "subject_bridge_direct_count": len(subject_bridge_direct),
        "relevance_review_coverage": round(reviewed_count / max(len(members), 1), 3),
        "cluster_audit": cluster_audit or {"status": "not_required" if not clustering_applied else "missing"},
        "missing_fields": [name for name in HEAT_WEIGHTS if name not in dimensions],
    }


def normalize_collection(raw: Any, retained_count: int, unique_count: int, signals: list[dict[str, Any]]) -> dict[str, Any]:
    source = raw.get("collection", {}) if isinstance(raw, dict) and isinstance(raw.get("collection"), dict) else {}
    query_runs = source.get("query_runs", []) if isinstance(source.get("query_runs"), list) else []
    counts = source.get("counts", {}) if isinstance(source.get("counts"), dict) else {}
    mode = as_text(source.get("mode") or (raw.get("research_mode") if isinstance(raw, dict) else "")) or "quick"
    mode = mode if mode in SAMPLING_CONTRACTS else "quick"
    contract = SAMPLING_CONTRACTS[mode]
    query_count = int(as_number(counts.get("query_count")) or len(query_runs))
    observed = as_number(counts.get("observed_result_count"))
    if observed is None and query_runs:
        values = [as_number(item.get("observed_result_count")) for item in query_runs if isinstance(item, dict)]
        observed = sum(value for value in values if value is not None) if any(value is not None for value in values) else None
    detail_count = sum(1 for signal in signals if signal.get("detail_captured"))
    counter_count = sum(1 for signal in signals if signal.get("evidence_role") == "counter")
    duplicate_count = retained_count - unique_count
    discarded = as_number(counts.get("discarded_result_count"))
    if discarded is None and observed is not None:
        discarded = max(0, int(observed) - retained_count)
    tracked = observed is not None and query_count > 0
    minimums = {
        "queries": query_count >= contract["query_target"][0],
        "observed_results": observed is not None and observed >= contract["observed_result_target"][0],
        "unique_signals": unique_count >= contract["unique_signal_target"][0],
        "relevant_unique_signals": len({
            as_text(signal.get("dedupe_hash"))
            for signal in signals
            if signal.get("semantic_relevance") in {"direct", "adjacent"} and as_text(signal.get("dedupe_hash"))
        }) >= contract["relevant_unique_signal_min"],
        "detail_opens": detail_count >= contract["detail_open_target"][0],
        "counter_signals": counter_count >= contract["counter_signal_min"],
    }
    layer_stats: dict[str, dict[str, Any]] = {}
    for layer in QUERY_LAYERS:
        runs = [item for item in query_runs if isinstance(item, dict) and item.get("query_layer") == layer]
        layer_signals = [signal for signal in signals if layer in {signal.get("query_layer"), *(signal.get("query_layers") or [])}]
        layer_stats[layer] = {
            "query_count": len(runs),
            "observed_result_count": sum(int(as_number(item.get("observed_result_count")) or 0) for item in runs),
            "unique_signal_count": len(layer_signals),
            "relevant_signal_count": sum(1 for signal in layer_signals if signal.get("semantic_relevance") in {"direct", "adjacent"}),
            "direct_signal_count": sum(1 for signal in layer_signals if signal.get("semantic_relevance") == "direct"),
            "detail_open_count": sum(1 for signal in layer_signals if signal.get("detail_captured")),
            "direct_relevance_count": sum(
                1 for signal in layer_signals
                if signal.get("semantic_relevance") == "direct"
                and (signal.get("detail_captured") or signal.get("source_type") in {"direct_post", "exported_item"})
            ),
        }
    minimums.update({
        "layer_queries": all(item["query_count"] >= contract["layer_query_min"] for item in layer_stats.values()),
        "layer_observed_results": all(item["observed_result_count"] >= contract["layer_observed_min"] for item in layer_stats.values()),
        "layer_unique_signals": all(item["unique_signal_count"] >= contract["layer_unique_signal_min"] for item in layer_stats.values()),
        "layer_relevant_signals": all(item["relevant_signal_count"] >= contract["layer_relevant_signal_min"] for item in layer_stats.values()),
        "layer_direct_signals": all(item["direct_signal_count"] >= contract["layer_direct_signal_min"] for item in layer_stats.values()),
        "layer_detail_opens": all(item["detail_open_count"] >= contract["layer_detail_min"] for item in layer_stats.values()),
        "subject_bridge_direct_evidence": layer_stats["subject_bridge"]["direct_relevance_count"] >= contract["subject_bridge_direct_min"],
        "relevance_review_coverage": (
            sum(1 for signal in signals if signal.get("semantic_relevance") in {"direct", "adjacent", "weak"}) / max(len(signals), 1)
        ) >= contract["relevance_review_coverage_min"],
    })
    stop_reason = as_text(source.get("stop_reason"))
    # Search-card acquisition may finish before semantic review and controlled
    # detail backfill.  That checkpoint is intentionally not a sampling claim,
    # but a reviewed derived ledger may close it once every contract check passes.
    if stop_reason == "search_collection_complete" and all(minimums.values()):
        stop_reason = "sampling_contract_met"
    status = (
        "untracked" if not tracked
        else "in_progress" if stop_reason == "collection_in_progress"
        else "met" if all(minimums.values()) and stop_reason in {"", "sampling_contract_met"}
        else "blocked" if stop_reason
        else "partial"
    )
    return {
        "mode": mode,
        "sampling_contract": contract,
        "query_runs": query_runs,
        "detail_backfills": source.get("detail_backfills", []) if isinstance(source.get("detail_backfills"), list) else [],
        "counts": {
            "query_count": query_count,
            "observed_result_count": int(observed) if observed is not None else None,
            "retained_sample_count": retained_count,
            "unique_sample_count": unique_count,
            "duplicate_count": duplicate_count,
            "discarded_result_count": int(discarded) if discarded is not None else None,
            "detail_open_count": detail_count,
            "counter_signal_count": counter_count,
        },
        "contract_checks": minimums,
        "layer_stats": layer_stats,
        "contract_status": status,
        "stop_reason": stop_reason,
        "limitations": [as_text(item) for item in as_list(source.get("limitations")) if as_text(item)],
    }
