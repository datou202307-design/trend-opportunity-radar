from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from _common import as_number, as_text, now_iso, write_json


REQUEST_SCHEMA = "instagram-account-read-request-v0.1"
CAPTURE_SCHEMA = "instagram-account-browser-capture-v0.1"
SNAPSHOT_SCHEMA = "trend-signal-snapshot-v0.4"
RECEIPT_SCHEMA = "instagram-account-read-receipt-v0.1"
USERNAME = re.compile(r"^[A-Za-z0-9._]{1,30}$")
POST_URL = re.compile(
    r"^https://(?:www\.)?instagram\.com/(?:(?P<profile>[A-Za-z0-9._]{1,30})/)?(?P<kind>p|reel)/(?P<content_id>[A-Za-z0-9_-]+)/?$",
    re.IGNORECASE,
)
HARD_STOPS = {"captcha", "rate_limit", "login_expired", "private_account", "account_not_found", "permission_prompt", "abnormal_redirect", "content_mismatch"}
FORBIDDEN_KEYS = {"followers", "follower_count", "following", "following_count", "cookies", "cookie", "session", "token", "password"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(payload: dict[str, Any]) -> str:
    frozen = {key: value for key, value in payload.items() if key not in {"generated_at", "request_sha256"}}
    return hashlib.sha256(canonical_json(frozen).encode("utf-8")).hexdigest()


def normalize_username(value: Any) -> str:
    username = as_text(value).lstrip("@").strip("/")
    if not USERNAME.fullmatch(username):
        raise SystemExit("Instagram account research requires one valid public username.")
    return username


def post_identity(url: Any) -> tuple[str, str, str, str] | None:
    match = POST_URL.fullmatch(as_text(url).split("?", 1)[0])
    if not match:
        return None
    profile = as_text(match.group("profile"))
    kind = match.group("kind").casefold()
    content_id = match.group("content_id")
    prefix = f"{profile}/" if profile else ""
    return kind, content_id, profile, f"https://www.instagram.com/{prefix}{kind}/{content_id}/"


def contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(as_text(key).casefold() in FORBIDDEN_KEYS or contains_forbidden_key(child) for key, child in value.items())
    if isinstance(value, list):
        return any(contains_forbidden_key(item) for item in value)
    return False


def build_request(username: str, max_posts: int = 12, max_detail_posts: int = 6) -> dict[str, Any]:
    account = normalize_username(username)
    max_posts = min(12, max(3, int(max_posts)))
    max_detail_posts = min(max_posts, max(1, int(max_detail_posts)))
    payload = {
        "schema_version": REQUEST_SCHEMA,
        "generated_at": now_iso(),
        "platform": "instagram",
        "research_scope": "account_research",
        "username": account,
        "profile_url": f"https://www.instagram.com/{account}/",
        "max_posts": max_posts,
        "max_detail_posts": max_detail_posts,
        "max_comments_per_detail": 5,
        "source_mode": "user_authorized_logged_in_browser",
        "allowed_actions": ["read_public_profile", "read_recent_post_links", "read_bounded_post_details", "read_visible_top_level_comments"],
        "forbidden_actions": ["read_followers", "read_following", "follow", "unfollow", "like", "comment", "save", "publish", "export_credentials"],
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
        "reply_count": None,
        "published_at": as_text(value.get("published_at")),
        "observed_time_label": as_text(value.get("observed_time_label")),
    }


def validate_capture(request: dict[str, Any], capture: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    if capture.get("schema_version") != CAPTURE_SCHEMA:
        raise SystemExit("Unsupported Instagram browser capture schema.")
    if capture.get("request_sha256") != request.get("request_sha256"):
        raise SystemExit("Instagram capture does not match the frozen request.")
    if contains_forbidden_key(capture):
        raise SystemExit("Instagram capture contains credentials, sessions, or follower/following graph fields.")
    stop_reason = as_text(capture.get("stop_reason")).casefold()
    if stop_reason:
        if stop_reason not in HARD_STOPS | {"timeout", "no_recent_posts"}:
            raise SystemExit("Unsupported Instagram stop_reason.")
        return "blocked" if stop_reason in HARD_STOPS else "unavailable", [], stop_reason
    username = normalize_username(request.get("username"))
    if normalize_username(capture.get("username")).casefold() != username.casefold():
        return "blocked", [], "content_mismatch"
    checks = capture.get("checks") if isinstance(capture.get("checks"), dict) else {}
    required = {"profile_identity": True, "canonical_post_links": True, "public_fields_only": True, "no_follow_graph": True, "no_write_actions": True, "no_credential_export": True}
    if any(checks.get(key) is not expected for key, expected in required.items()):
        return "blocked", [], "content_mismatch"
    rows = capture.get("posts")
    if not isinstance(rows, list):
        raise SystemExit("Instagram capture posts must be an array.")
    if len(rows) > int(request.get("max_posts") or 12):
        raise SystemExit("Instagram capture exceeds the frozen recent-post limit.")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    detailed = 0
    for row in rows:
        if not isinstance(row, dict):
            raise SystemExit("Every Instagram post must be an object.")
        identity = post_identity(row.get("canonical_url"))
        if not identity:
            raise SystemExit("Every Instagram post requires a canonical /p/ or /reel/ URL.")
        kind, content_id, profile_path, canonical_url = identity
        if content_id in seen:
            raise SystemExit("Duplicate Instagram content IDs are not allowed.")
        seen.add(content_id)
        author = normalize_username(row.get("author_username"))
        if author.casefold() != username.casefold():
            return "blocked", [], "content_mismatch"
        if profile_path and profile_path.casefold() != username.casefold():
            return "blocked", [], "content_mismatch"
        detail_captured = row.get("detail_captured") is True
        caption = as_text(row.get("caption"))
        published_at = as_text(row.get("published_at"))
        if detail_captured and (not caption or not published_at):
            raise SystemExit("A detailed Instagram post requires caption and publication time.")
        detailed += int(detail_captured)
        comments_raw = row.get("representative_comments") if isinstance(row.get("representative_comments"), list) else []
        if len(comments_raw) > int(request.get("max_comments_per_detail") or 5):
            raise SystemExit("Instagram representative comments exceed the frozen limit.")
        comments = [normalize_comment(item) for item in comments_raw]
        normalized.append({
            "kind": kind,
            "content_id": content_id,
            "canonical_url": canonical_url,
            "author_username": author,
            "detail_captured": detail_captured,
            "caption": caption,
            "published_at": published_at,
            "likes": parse_metric(row.get("likes")),
            "comments": parse_metric(row.get("comments")),
            "views": parse_metric(row.get("views")),
            "representative_comments": comments,
        })
    if not normalized:
        return "unavailable", [], "no_recent_posts"
    if detailed > int(request.get("max_detail_posts") or 6):
        raise SystemExit("Instagram detailed posts exceed the frozen detail budget.")
    if detailed == 0:
        return "unavailable", normalized, "details_unavailable"
    return "captured", normalized, ""


def build_snapshot(request: dict[str, Any], capture: dict[str, Any], raw_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    status, posts, stop_reason = validate_capture(request, capture)
    captured_at = as_text(capture.get("captured_at")) or now_iso()
    raw_ref = str(raw_path.resolve())
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    signals: list[dict[str, Any]] = []
    for index, post in enumerate(posts):
        comments = post["representative_comments"]
        limitations = [] if post["detail_captured"] else ["Only the stable recent-post link was captured; post details were not opened."]
        signals.append({
            "signal_id": f"instagram-{post['content_id']}",
            "platform": "instagram",
            "source_mode": "controlled_capture",
            "source_type": "direct_post" if post["detail_captured"] else "search_card",
            "evidence_role": "neutral",
            "detail_captured": post["detail_captured"],
            "content_id": post["content_id"],
            "canonical_url": post["canonical_url"],
            "source_url": post["canonical_url"],
            "detail_access": {"url": post["canonical_url"], "source": "logged_in_profile_grid"},
            "query_term": request["username"],
            "query_layer": "category",
            "query_terms": [request["username"]],
            "query_layers": ["category"],
            "semantic_relevance": "direct",
            "topic_key": request["username"],
            "title": " ".join(post["caption"].split())[:180],
            "summary": post["caption"],
            "published_at": post["published_at"],
            "captured_at": captured_at,
            "metrics_captured_at": captured_at,
            "metrics": {"views": post["views"], "likes": post["likes"], "saves": None, "comments": post["comments"], "shares": None},
            "author": {"id": request["username"], "name": request["username"], "type": "instagram_account", "follower_count": None, "verified": None},
            "discovery": {"search_rank": index + 1, "search_result_count": len(posts), "observed_content_count": len(posts)},
            "time_series": {"growth_rate_percent": None, "current_window_count": None, "previous_window_count": None, "comparison_count": None},
            "platform_facts": {"content_format": post["kind"], "representative_comments": comments, "representative_comment_count": len(comments), "comment_sample_limit": 5, "comment_capture_status": "captured" if comments else "unavailable"},
            "evidence_refs": [post["canonical_url"], raw_ref],
            "raw_artifacts": [raw_ref],
            "limitations": limitations,
            "permission_scope": "user_authorized",
            "dedupe_hash": hashlib.sha256(f"instagram:{post['content_id']}".encode("utf-8")).hexdigest(),
        })
    detailed = sum(1 for item in signals if item["detail_captured"])
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA,
        "platform": "instagram",
        "research_scope": "account_research",
        "account": {"username": request["username"], "profile_url": request["profile_url"], "display_name": as_text((capture.get("profile") or {}).get("display_name")), "bio": as_text((capture.get("profile") or {}).get("bio"))},
        "raw_sample_count": len(signals),
        "retained_sample_count": len(signals),
        "unique_sample_count": len(signals),
        "collection": {"scope": "bounded_recent_account_content", "counts": {"observed_result_count": len(signals), "unique_signal_count": len(signals), "detail_open_count": detailed}, "limits": {"recent_posts": request["max_posts"], "detail_posts": request["max_detail_posts"], "comments_per_detail": 5}, "terminal_reason": "profile_grid_limit_reached" if len(signals) >= request["max_posts"] else "visible_recent_posts_exhausted"},
        "signals": signals,
        "platform_adapter": {"contract_version": "platform-adapter-contract-v0.2", "adapter": "browser_readonly_capture", "source_mode": "controlled_capture", "live_collection": True, "research_scope": "account_research"},
    }
    receipt = {"schema_version": RECEIPT_SCHEMA, "recorded_at": now_iso(), "platform": "instagram", "research_scope": "account_research", "username": request["username"], "request_sha256": request["request_sha256"], "status": status, "stop_reason": stop_reason, "observed_post_count": len(posts), "detail_post_count": detailed, "visible_comment_count": sum(len(item["representative_comments"]) for item in posts), "raw_capture": raw_ref, "raw_capture_sha256": raw_sha256, "snapshot_written": status == "captured"}
    return snapshot, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan or record bounded Instagram known-account research without packaging browser credentials.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--username", required=True)
    plan.add_argument("--max-posts", type=int, default=12)
    plan.add_argument("--max-detail-posts", type=int, default=6)
    plan.add_argument("--output", required=True)
    record = sub.add_parser("record")
    record.add_argument("--request", required=True)
    record.add_argument("--capture", required=True)
    record.add_argument("--output", required=True)
    record.add_argument("--receipt", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        write_json(args.output, build_request(args.username, args.max_posts, args.max_detail_posts))
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
