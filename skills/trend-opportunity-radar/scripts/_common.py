from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCORE_VERSION = "evidence-heat-index-v0.1"
SCHEMA_VERSION = "trend-signal-snapshot-v0.1"
SOURCE_MODES = {"authorized_api", "customer_export", "controlled_capture", "public_web", "historical_snapshot"}
WEIGHTS = {
    "content_volume": 20,
    "engagement": 25,
    "velocity": 25,
    "diffusion": 15,
    "search_demand": 10,
    "freshness": 5,
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
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def nested_number(row: dict[str, Any], nested: str, *flat_keys: str) -> float | None:
    section_name, field_name = nested.split(".", 1)
    section = row.get(section_name)
    if isinstance(section, dict):
        value = as_number(section.get(field_name))
        if value is not None:
            return value
    return as_number(first(row, *flat_keys, nested, nested.replace(".", "_")))


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
        "twitter": "x", "推特": "x",
        "抖音": "douyin", "tiktok": "douyin",
        "视频号": "wechat_channels", "wechat channels": "wechat_channels",
    }
    return aliases.get(text, re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]+", "_", text).strip("_"))


def normalize_url(value: Any) -> str:
    text = as_text(value)
    return text if text.startswith(("http://", "https://", "snapshot://", "artifact://")) else ""


def normalize_signal(row: dict[str, Any], platform: str, source_mode: str, captured_at: str) -> dict[str, Any]:
    metrics = {
        "views": metric_number(row, "views", "view_count", "impressions", "impression_count"),
        "likes": metric_number(row, "likes", "like_count"),
        "saves": metric_number(row, "saves", "save_count", "bookmarks", "bookmark_count", "favorites"),
        "comments": metric_number(row, "comments", "comment_count", "replies", "reply_count"),
        "shares": metric_number(row, "shares", "share_count", "reposts", "retweet_count", "quote_count"),
    }
    metrics = {key: int(value) if value is not None else None for key, value in metrics.items()}
    author_section = row.get("author") if isinstance(row.get("author"), dict) else {}
    discovery_section = row.get("discovery") if isinstance(row.get("discovery"), dict) else {}
    url = normalize_url(first(row, "canonical_url", "canonicalUrl", "url", "link", "source_url"))
    title = as_text(first(row, "title", "name", "text", "body"))[:500]
    author_id = as_text(first(author_section, "id", "author_id") or first(row, "author_id", "authorId", "username"))
    published_at = as_text(first(row, "published_at", "publishedAt", "created_at", "createdAt"))
    row_captured_at = as_text(first(row, "captured_at", "capturedAt")) or captured_at
    identity = "|".join([platform, as_text(first(row, "content_id", "contentId", "id")), url, title, author_id, published_at])
    dedupe_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    evidence_refs = [normalize_url(item) for item in as_list(first(row, "evidence_refs", "evidenceRefs", "refs"))]
    if url:
        evidence_refs.insert(0, url)
    evidence_refs = list(dict.fromkeys(item for item in evidence_refs if item))
    limitations = [as_text(item) for item in as_list(first(row, "limitations", "limits")) if as_text(item)]
    return {
        "signal_id": as_text(first(row, "signal_id", "signalId", "id")) or f"signal-{dedupe_hash[:12]}",
        "platform": normalize_platform(first(row, "platform") or platform),
        "source_mode": as_text(first(row, "source_mode", "sourceMode")) or source_mode,
        "content_id": as_text(first(row, "content_id", "contentId", "id")),
        "canonical_url": url,
        "query_term": as_text(first(row, "query_term", "queryTerm", "query", "keyword")),
        "query_layer": as_text(first(row, "query_layer", "queryLayer", "scope")) or "unspecified",
        "topic_key": as_text(first(row, "topic_key", "topicKey")),
        "title": title,
        "summary": as_text(first(row, "summary", "description", "body", "text"))[:4000],
        "published_at": published_at,
        "captured_at": row_captured_at,
        "metrics_captured_at": as_text(first(row, "metrics_captured_at", "metricsCapturedAt")) or row_captured_at,
        "metrics": metrics,
        "author": {
            "id": author_id,
            "type": as_text(first(author_section, "type", "author_type") or first(row, "author_type", "authorType")),
            "follower_count": as_number(first(author_section, "follower_count", "followerCount") or first(row, "follower_count", "followerCount")),
            "verified": first(author_section, "verified") if "verified" in author_section else first(row, "verified", "author_verified"),
        },
        "discovery": {
            "search_rank": as_number(first(discovery_section, "search_rank", "searchRank") or first(row, "search_rank", "searchRank")),
            "search_result_count": as_number(first(discovery_section, "search_result_count", "searchResultCount") or first(row, "search_result_count", "searchResultCount")),
            "observed_content_count": as_number(first(discovery_section, "observed_content_count", "observedContentCount") or first(row, "observed_content_count", "observedContentCount")),
        },
        "time_series": {
            "growth_rate_percent": as_number(first(row, "growth_rate_percent", "growthRatePercent")),
            "current_window_count": as_number(first(row, "current_window_count", "currentWindowCount")),
            "previous_window_count": as_number(first(row, "previous_window_count", "previousWindowCount")),
            "comparison_count": as_number(first(row, "comparison_count", "comparisonCount")),
        },
        "evidence_refs": evidence_refs,
        "limitations": limitations,
        "permission_scope": as_text(first(row, "permission_scope", "permissionScope")) or "unspecified",
        "dedupe_hash": dedupe_hash,
    }


def _log_score(value: float, ceiling: float) -> float:
    return max(0.0, min(100.0, math.log1p(max(value, 0)) / math.log1p(ceiling) * 100))


def _freshness_score(value: str, as_of: datetime) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        days = max(0.0, (as_of - parsed.astimezone(timezone.utc)).total_seconds() / 86400)
    except (ValueError, TypeError):
        return 0.0
    if days <= 1:
        return 100.0
    if days <= 7:
        return 80.0
    if days <= 30:
        return 55.0
    if days <= 90:
        return 30.0
    return 10.0


def calculate_index(signal: dict[str, Any], as_of: datetime | None = None) -> dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc)
    metrics = signal.get("metrics") or {}
    discovery = signal.get("discovery") or {}
    time_series = signal.get("time_series") or {}
    dimensions: dict[str, float] = {"freshness": _freshness_score(signal.get("metrics_captured_at") or signal.get("captured_at") or "", as_of)}
    missing: list[str] = []
    coverage = WEIGHTS["freshness"] if dimensions["freshness"] > 0 else 0
    count = as_number(discovery.get("observed_content_count"))
    if count is not None:
        dimensions["content_volume"] = _log_score(count, 1000)
        coverage += WEIGHTS["content_volume"]
    else:
        missing.append("content.observed_content_count")
    views = as_number(metrics.get("views"))
    interactions = [as_number(metrics.get(key)) for key in ("likes", "saves", "comments", "shares")]
    interactions = [value for value in interactions if value is not None]
    if views is not None or interactions:
        total = sum(interactions)
        dimensions["engagement"] = min(100.0, total / max(views or 0, 1) * 1000) if views is not None and interactions else _log_score(total or views or 0, 100000)
        coverage += WEIGHTS["engagement"]
    else:
        missing.append("metrics.views_likes_saves_comments_shares")
    growth = as_number(time_series.get("growth_rate_percent"))
    current = as_number(time_series.get("current_window_count"))
    previous = as_number(time_series.get("previous_window_count"))
    if growth is not None or (current is not None and previous is not None):
        rate = growth if growth is not None else (current - previous) / max(previous, 1) * 100
        dimensions["velocity"] = max(0.0, min(100.0, 50 + rate / 2))
        coverage += WEIGHTS["velocity"]
    else:
        missing.append("time_series.current_and_previous_window")
    author_count = 1 if (signal.get("author") or {}).get("id") else None
    if author_count is not None and count is not None:
        dimensions["diffusion"] = min(100.0, author_count / max(count, 1) * 100)
        coverage += WEIGHTS["diffusion"]
    else:
        missing.append("author.unique_author_count")
    search_count = as_number(discovery.get("search_result_count"))
    search_rank = as_number(discovery.get("search_rank"))
    if search_count is not None or search_rank is not None:
        dimensions["search_demand"] = _log_score(search_count, 10000) if search_count is not None else max(0.0, min(100.0, 105 - search_rank))
        coverage += WEIGHTS["search_demand"]
    else:
        missing.append("search.volume_rank_or_result_count")
    heat = round(sum(dimensions[key] * WEIGHTS[key] / 100 for key in dimensions))
    return {
        "heat_index": heat,
        "data_coverage": coverage,
        "score_status": "complete" if coverage >= 75 else "partial" if coverage >= 40 else "sparse",
        "score_version": SCORE_VERSION,
        "dimensions": {key: round(value, 2) for key, value in dimensions.items()},
        "missing_fields": missing,
    }
