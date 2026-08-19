from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from _common import as_number, as_text, now_iso, write_json


REQUEST_SCHEMA = "instagram-hashtag-read-request-v0.1"
CAPTURE_SCHEMA = "instagram-hashtag-browser-capture-v0.1"
RECEIPT_SCHEMA = "instagram-hashtag-read-receipt-v0.1"
SNAPSHOT_SCHEMA = "trend-signal-snapshot-v0.4"
POST_URL = re.compile(
    r"^https://(?:www\.)?instagram\.com/(?:(?:[A-Za-z0-9._]{1,30})/)?(?P<kind>p|reel)/(?P<content_id>[A-Za-z0-9_-]+)/?$",
    re.IGNORECASE,
)
HASHTAG = re.compile(r"^[^\s#/?:&]{1,100}$", re.UNICODE)
QUERY_LAYERS = {"platform_baseline", "category", "subject_bridge"}
HARD_STOPS = {"captcha", "rate_limit", "login_expired", "permission_prompt", "abnormal_redirect", "content_mismatch"}
FORBIDDEN_KEYS = {"cookies", "cookie", "session", "token", "password", "followers", "following"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(payload: dict[str, Any]) -> str:
    frozen = {key: value for key, value in payload.items() if key not in {"generated_at", "request_sha256"}}
    return hashlib.sha256(canonical_json(frozen).encode("utf-8")).hexdigest()


def normalize_hashtag(value: Any) -> str:
    tag = as_text(value).strip().lstrip("#")
    if not HASHTAG.fullmatch(tag):
        raise SystemExit("Instagram topic capture requires one explicit hashtag without spaces.")
    return tag.casefold()


def canonical_post(value: Any) -> tuple[str, str, str] | None:
    url = as_text(value).split("?", 1)[0]
    match = POST_URL.fullmatch(url)
    if not match:
        return None
    kind = match.group("kind").casefold()
    content_id = match.group("content_id")
    return kind, content_id, f"https://www.instagram.com/{kind}/{content_id}/"


def contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(as_text(key).casefold() in FORBIDDEN_KEYS or contains_forbidden_key(child) for key, child in value.items())
    if isinstance(value, list):
        return any(contains_forbidden_key(item) for item in value)
    return False


def build_request(subject: str, hashtag: str, query_layer: str, max_posts: int = 24, max_detail_posts: int = 6) -> dict[str, Any]:
    topic = as_text(subject)
    if not topic:
        raise SystemExit("Instagram topic capture requires a research subject.")
    tag = normalize_hashtag(hashtag)
    layer = as_text(query_layer).casefold()
    if layer not in QUERY_LAYERS:
        raise SystemExit("Instagram query_layer must be platform_baseline, category, or subject_bridge.")
    max_posts = min(24, max(6, int(max_posts)))
    max_detail_posts = min(max_posts, max(1, int(max_detail_posts)))
    query_url = f"https://www.instagram.com/explore/search/keyword/?q={quote('#' + tag)}"
    payload = {
        "schema_version": REQUEST_SCHEMA,
        "generated_at": now_iso(),
        "platform": "instagram",
        "research_scope": "topic_research",
        "subject": topic,
        "hashtag": tag,
        "query_term": f"#{tag}",
        "query_layer": layer,
        "query_url": query_url,
        "max_posts": max_posts,
        "max_detail_posts": max_detail_posts,
        "max_comments_per_detail": 5,
        "repeat_probe_passes": 2,
        "source_mode": "user_authorized_logged_in_browser",
        "allowed_actions": ["read_hashtag_results", "read_canonical_post_links", "read_bounded_post_details", "read_visible_top_level_comments"],
        "forbidden_actions": ["use_account_search_as_topic_evidence", "use_personalized_explore_feed", "follow", "like", "comment", "save", "publish", "export_credentials"],
        "hard_stops": sorted(HARD_STOPS),
    }
    payload["request_sha256"] = request_hash(payload)
    return payload


def parse_metric(value: Any) -> int | None:
    number = as_number(value)
    return int(number) if number is not None else None


def normalize_comment(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("top_level_visible") is not True:
        raise SystemExit("Every Instagram comment must be a visible top-level comment object.")
    text = as_text(value.get("text"))
    if not text:
        raise SystemExit("Every Instagram comment requires visible text.")
    return {
        "author_name": as_text(value.get("author_name")),
        "text": text,
        "likes": parse_metric(value.get("likes")),
        "published_at": as_text(value.get("published_at")),
        "observed_time_label": as_text(value.get("observed_time_label")),
    }


def validate_capture(request: dict[str, Any], capture: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any], str]:
    if capture.get("schema_version") != CAPTURE_SCHEMA:
        raise SystemExit("Unsupported Instagram hashtag capture schema.")
    if capture.get("request_sha256") != request.get("request_sha256"):
        raise SystemExit("Instagram hashtag capture does not match the frozen request.")
    if contains_forbidden_key(capture):
        raise SystemExit("Instagram hashtag capture contains credentials or follow-graph fields.")
    stop_reason = as_text(capture.get("stop_reason")).casefold()
    if stop_reason:
        if stop_reason not in HARD_STOPS | {"timeout", "no_visible_posts", "details_unavailable"}:
            raise SystemExit("Unsupported Instagram hashtag stop_reason.")
        return ("blocked" if stop_reason in HARD_STOPS else "unavailable"), [], {}, stop_reason
    if normalize_hashtag(capture.get("hashtag")) != request["hashtag"]:
        return "blocked", [], {}, "content_mismatch"
    checks = capture.get("checks") if isinstance(capture.get("checks"), dict) else {}
    required = {
        "hashtag_identity": True,
        "canonical_post_links": True,
        "public_fields_only": True,
        "no_account_search_proxy": True,
        "no_personalized_explore_feed": True,
        "no_write_actions": True,
        "no_credential_export": True,
    }
    if any(checks.get(key) is not expected for key, expected in required.items()):
        return "blocked", [], {}, "content_mismatch"
    passes = capture.get("result_passes")
    if not isinstance(passes, list) or not passes or len(passes) > 2:
        raise SystemExit("Instagram hashtag capture requires one or two bounded result passes.")
    normalized_passes: list[list[str]] = []
    for pass_links in passes:
        if not isinstance(pass_links, list) or len(pass_links) > int(request["max_posts"]):
            raise SystemExit("Instagram hashtag result pass is invalid or exceeds the frozen limit.")
        links: list[str] = []
        seen_ids: set[str] = set()
        for value in pass_links:
            identity = canonical_post(value)
            if not identity:
                raise SystemExit("Instagram hashtag results require canonical /p/ or /reel/ links.")
            _, content_id, url = identity
            if content_id not in seen_ids:
                seen_ids.add(content_id)
                links.append(url)
        normalized_passes.append(links)
    observed = normalized_passes[0]
    if not observed:
        return "unavailable", [], {}, "no_visible_posts"
    card_rows = capture.get("result_cards") if isinstance(capture.get("result_cards"), list) else []
    if len(card_rows) > int(request["max_posts"]):
        raise SystemExit("Instagram hashtag result cards exceed the frozen limit.")
    card_by_id: dict[str, dict[str, Any]] = {}
    for row in card_rows:
        if not isinstance(row, dict):
            raise SystemExit("Every Instagram hashtag result card must be an object.")
        identity = canonical_post(row.get("canonical_url"))
        if not identity or identity[2] not in observed:
            return "blocked", [], {}, "content_mismatch"
        kind, content_id, canonical_url = identity
        if content_id in card_by_id:
            raise SystemExit("Duplicate Instagram result-card IDs are not allowed.")
        preview_text = as_text(row.get("preview_text"))
        if not preview_text:
            raise SystemExit("Every Instagram result card requires visible preview_text.")
        card_by_id[content_id] = {
            "kind": kind,
            "content_id": content_id,
            "canonical_url": canonical_url,
            "author_username": as_text(row.get("author_username")).lstrip("@"),
            "preview_text": preview_text,
        }
    detail_rows = capture.get("posts") if isinstance(capture.get("posts"), list) else []
    if len(detail_rows) > int(request["max_detail_posts"]):
        raise SystemExit("Instagram hashtag details exceed the frozen limit.")
    detail_by_id: dict[str, dict[str, Any]] = {}
    for row in detail_rows:
        if not isinstance(row, dict):
            raise SystemExit("Every Instagram hashtag detail must be an object.")
        identity = canonical_post(row.get("canonical_url"))
        if not identity or identity[2] not in observed:
            return "blocked", [], {}, "content_mismatch"
        kind, content_id, canonical_url = identity
        if content_id in detail_by_id:
            raise SystemExit("Duplicate Instagram detail IDs are not allowed.")
        caption = as_text(row.get("caption"))
        published_at = as_text(row.get("published_at"))
        if not caption or not published_at:
            raise SystemExit("An opened Instagram detail requires caption and publication time.")
        comments_raw = row.get("representative_comments") if isinstance(row.get("representative_comments"), list) else []
        if len(comments_raw) > int(request["max_comments_per_detail"]):
            raise SystemExit("Instagram representative comments exceed the frozen limit.")
        detail_by_id[content_id] = {
            "kind": kind,
            "content_id": content_id,
            "canonical_url": canonical_url,
            "author_username": as_text(row.get("author_username")).lstrip("@"),
            "caption": caption,
            "published_at": published_at,
            "likes": parse_metric(row.get("likes")),
            "comments": parse_metric(row.get("comments")),
            "views": parse_metric(row.get("views")),
            "representative_comments": [normalize_comment(item) for item in comments_raw],
        }
    normalized: list[dict[str, Any]] = []
    for url in observed:
        kind, content_id, canonical_url = canonical_post(url)  # type: ignore[misc]
        row = detail_by_id.get(content_id)
        card = card_by_id.get(content_id, {})
        normalized.append(row or {
            "kind": kind,
            "content_id": content_id,
            "canonical_url": canonical_url,
            "author_username": card.get("author_username", ""),
            "caption": card.get("preview_text", ""),
            "published_at": "",
            "likes": None,
            "comments": None,
            "views": None,
            "representative_comments": [],
        })
    overlap = None
    if len(normalized_passes) == 2:
        overlap = len(set(normalized_passes[0]) & set(normalized_passes[1])) / max(1, len(set(normalized_passes[0]) | set(normalized_passes[1])))
    repeatability = {"pass_count": len(normalized_passes), "overlap_jaccard": overlap, "ranked_surface": True}
    return ("captured" if detail_by_id else "unavailable"), normalized, repeatability, ("" if detail_by_id else "details_unavailable")


def build_snapshot(request: dict[str, Any], capture: dict[str, Any], raw_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    status, posts, repeatability, stop_reason = validate_capture(request, capture)
    captured_at = as_text(capture.get("captured_at")) or now_iso()
    raw_ref = str(raw_path.resolve())
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    signals: list[dict[str, Any]] = []
    for rank, post in enumerate(posts, 1):
        detailed = bool(post["caption"] and post["published_at"])
        comments = post["representative_comments"]
        signals.append({
            "signal_id": f"instagram-{post['content_id']}",
            "platform": "instagram",
            "source_mode": "controlled_capture",
            "source_type": "direct_post" if detailed else "search_card",
            "evidence_role": "neutral",
            "detail_captured": detailed,
            "content_id": post["content_id"],
            "canonical_url": post["canonical_url"],
            "source_url": post["canonical_url"],
            "detail_access": {"url": post["canonical_url"], "source": "logged_in_hashtag_results"},
            "query_term": request["query_term"],
            "query_layer": request["query_layer"],
            "query_terms": [request["query_term"]],
            "query_layers": [request["query_layer"]],
            "semantic_relevance": "pending_review",
            "topic_key": request["hashtag"],
            "title": " ".join(post["caption"].split())[:180],
            "summary": post["caption"],
            "published_at": post["published_at"],
            "captured_at": captured_at,
            "metrics_captured_at": captured_at,
            "metrics": {"views": post["views"], "likes": post["likes"], "saves": None, "comments": post["comments"], "shares": None},
            "author": {"id": post["author_username"], "name": post["author_username"], "type": "instagram_creator", "follower_count": None, "verified": None},
            "discovery": {"search_rank": rank, "search_result_count": len(posts), "observed_content_count": len(posts)},
            "time_series": {"growth_rate_percent": None, "current_window_count": None, "previous_window_count": None, "comparison_count": None},
            "platform_facts": {
                "content_format": post["kind"],
                "hashtag": request["query_term"],
                "displayed_hashtag_volume_label": as_text(capture.get("displayed_post_count_label")),
                "representative_comments": comments,
                "representative_comment_count": len(comments),
                "comment_sample_limit": request["max_comments_per_detail"],
                "comment_capture_status": "captured" if comments else "unavailable",
            },
            "evidence_refs": [post["canonical_url"], raw_ref],
            "raw_artifacts": [raw_ref],
            "limitations": [] if detailed else (["Hashtag result preview was observed, but the post detail was not opened."] if post["caption"] else ["Hashtag result link was observed, but the post detail was not opened and no preview text was available."]),
            "permission_scope": "user_authorized",
            "dedupe_hash": hashlib.sha256(f"instagram:{post['content_id']}".encode("utf-8")).hexdigest(),
        })
    detailed_count = sum(1 for item in signals if item["detail_captured"])
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA,
        "platform": "instagram",
        "research_scope": "topic_research",
        "subject": request["subject"],
        "query": {"term": request["query_term"], "layer": request["query_layer"], "url": request["query_url"]},
        "raw_sample_count": len(signals),
        "retained_sample_count": len(signals),
        "unique_sample_count": len(signals),
        "collection": {
            "scope": "bounded_ranked_hashtag_results",
            "counts": {"observed_result_count": len(signals), "unique_signal_count": len(signals), "detail_open_count": detailed_count},
            "limits": {"posts": request["max_posts"], "detail_posts": request["max_detail_posts"], "comments_per_detail": request["max_comments_per_detail"]},
            "repeatability": repeatability,
            "terminal_reason": "bounded_hashtag_result_limit_reached" if len(signals) >= request["max_posts"] else "visible_hashtag_results_exhausted",
        },
        "signals": signals,
        "platform_adapter": {"contract_version": "platform-adapter-contract-v0.2", "adapter": "instagram_hashtag_browser_capture", "source_mode": "controlled_capture", "live_collection": True, "research_scope": "topic_research"},
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "recorded_at": now_iso(),
        "platform": "instagram",
        "research_scope": "topic_research",
        "hashtag": request["query_term"],
        "request_sha256": request["request_sha256"],
        "status": status,
        "stop_reason": stop_reason,
        "observed_post_count": len(posts),
        "detail_post_count": detailed_count,
        "visible_comment_count": sum(len(item["representative_comments"]) for item in posts),
        "preview_card_count": sum(1 for item in posts if item["caption"]),
        "repeatability": repeatability,
        "raw_capture": raw_ref,
        "raw_capture_sha256": raw_sha256,
        "snapshot_written": status == "captured",
    }
    return snapshot, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan or record bounded Instagram hashtag topic research without packaging browser credentials.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--subject", required=True)
    plan.add_argument("--hashtag", required=True)
    plan.add_argument("--query-layer", required=True, choices=sorted(QUERY_LAYERS))
    plan.add_argument("--max-posts", type=int, default=24)
    plan.add_argument("--max-detail-posts", type=int, default=6)
    plan.add_argument("--output", required=True)
    record = sub.add_parser("record")
    record.add_argument("--request", required=True)
    record.add_argument("--capture", required=True)
    record.add_argument("--output", required=True)
    record.add_argument("--receipt", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        write_json(args.output, build_request(args.subject, args.hashtag, args.query_layer, args.max_posts, args.max_detail_posts))
        return
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    capture_path = Path(args.capture).resolve()
    capture = json.loads(capture_path.read_text(encoding="utf-8"))
    snapshot, receipt = build_snapshot(request, capture, capture_path)
    write_json(args.output, snapshot)
    write_json(args.receipt, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if receipt["status"] != "captured":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
