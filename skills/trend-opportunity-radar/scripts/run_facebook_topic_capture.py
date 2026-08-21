from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from _common import as_number, as_text, now_iso, write_json


REQUEST_SCHEMA = "facebook-posts-read-request-v0.1"
CAPTURE_SCHEMA = "facebook-posts-browser-capture-v0.1"
RECEIPT_SCHEMA = "facebook-posts-read-receipt-v0.1"
SNAPSHOT_SCHEMA = "trend-signal-snapshot-v0.4"
QUERY_LAYERS = {"platform_baseline", "category", "subject_bridge"}
HARD_STOPS = {"captcha", "rate_limit", "login_expired", "permission_prompt", "abnormal_redirect", "content_mismatch", "private_content"}
FORBIDDEN_KEYS = {"cookies", "cookie", "session", "token", "password", "friends", "notifications"}
CONTENT_ID = re.compile(r"^[A-Za-z0-9._-]{4,160}$")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(payload: dict[str, Any]) -> str:
    frozen = {key: value for key, value in payload.items() if key not in {"generated_at", "request_sha256"}}
    return hashlib.sha256(canonical_json(frozen).encode("utf-8")).hexdigest()


def contains_forbidden_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(as_text(key).casefold() in FORBIDDEN_KEYS or contains_forbidden_key(child) for key, child in value.items())
    if isinstance(value, list):
        return any(contains_forbidden_key(item) for item in value)
    return False


def canonical_content(value: Any) -> tuple[str, str, str] | None:
    raw = as_text(value)
    if not raw:
        return None
    parsed = urlparse(raw)
    host = parsed.hostname.casefold() if parsed.hostname else ""
    if host not in {"facebook.com", "www.facebook.com", "m.facebook.com"}:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    kind = ""
    content_id = ""
    canonical = ""
    if len(parts) >= 2 and parts[0].casefold() == "reel":
        kind, content_id = "reel", parts[1]
        canonical = f"https://www.facebook.com/reel/{content_id}/"
    elif len(parts) >= 3 and parts[1].casefold() == "posts":
        author, content_id = parts[0], parts[2]
        kind = "post"
        canonical = f"https://www.facebook.com/{author}/posts/{content_id}/"
    elif len(parts) >= 3 and parts[0].casefold() == "share" and parts[1].casefold() == "p":
        kind, content_id = "post", parts[2]
        canonical = f"https://www.facebook.com/share/p/{content_id}/"
    elif parts and parts[0].casefold() == "photo":
        content_id = as_text(parse_qs(parsed.query).get("fbid", [""])[0])
        kind = "photo"
        canonical = f"https://www.facebook.com/photo/?fbid={content_id}"
    elif parts and parts[0].casefold() == "permalink.php":
        content_id = as_text(parse_qs(parsed.query).get("story_fbid", [""])[0])
        kind = "post"
        canonical = f"https://www.facebook.com/permalink.php?story_fbid={content_id}"
    if not CONTENT_ID.fullmatch(content_id):
        return None
    return kind, content_id, canonical


def integer(value: Any) -> int | None:
    number = as_number(value)
    return int(number) if number is not None else None


def build_request(subject: str, query: str, query_layer: str, max_posts: int = 20, max_detail_posts: int = 5) -> dict[str, Any]:
    subject = as_text(subject)
    query = as_text(query)
    layer = as_text(query_layer).casefold()
    if not subject or not query:
        raise SystemExit("Facebook topic capture requires a research subject and query.")
    if layer not in QUERY_LAYERS:
        raise SystemExit("Facebook query_layer must be platform_baseline, category, or subject_bridge.")
    max_posts = min(20, max(5, int(max_posts)))
    max_detail_posts = min(max_posts, max(1, int(max_detail_posts)))
    payload = {
        "schema_version": REQUEST_SCHEMA,
        "generated_at": now_iso(),
        "platform": "facebook",
        "research_scope": "topic_research",
        "subject": subject,
        "query_term": query,
        "query_layer": layer,
        "query_url": f"https://www.facebook.com/search/posts/?q={quote(query)}",
        "max_posts": max_posts,
        "max_detail_posts": max_detail_posts,
        "max_comments_per_detail": 5,
        "repeat_probe_passes": 2,
        "source_mode": "user_authorized_logged_in_browser",
        "allowed_actions": ["read_posts_search_results", "read_canonical_public_post_links", "read_public_post_detail", "expand_exact_detail_comments_once", "read_visible_comments"],
        "forbidden_actions": ["use_home_feed", "use_mixed_search", "read_friends", "read_notifications", "read_private_groups", "read_marketplace", "join_group", "add_friend", "follow", "react", "like", "comment", "share", "publish", "export_credentials"],
        "hard_stops": sorted(HARD_STOPS),
    }
    payload["request_sha256"] = request_hash(payload)
    return payload


def normalize_comment(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("top_level_visible") is not True:
        raise SystemExit("Every Facebook comment must be a visible top-level comment object.")
    text = as_text(value.get("text"))
    if not text:
        raise SystemExit("Every Facebook comment requires visible text.")
    return {"author_name": as_text(value.get("author_name")), "text": text, "reactions": integer(value.get("reactions")), "observed_time_label": as_text(value.get("observed_time_label"))}


def normalize_row(value: Any, observed: set[str], detailed: bool, comment_limit: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SystemExit("Every Facebook result must be an object.")
    identity = canonical_content(value.get("canonical_url"))
    if not identity or identity[2] not in observed:
        raise SystemExit("Facebook result identity must match a retained Posts-search link.")
    kind, content_id, canonical_url = identity
    body = as_text(value.get("body_text") if detailed else value.get("preview_text"))
    if not body:
        raise SystemExit("Every Facebook result requires visible text.")
    time_value = as_text(value.get("published_at")) or as_text(value.get("observed_time_label"))
    if detailed and not time_value:
        raise SystemExit("Every opened Facebook detail requires a visible publication time or label.")
    comments = value.get("representative_comments") if isinstance(value.get("representative_comments"), list) else []
    if len(comments) > comment_limit:
        raise SystemExit("Facebook representative comments exceed the frozen limit.")
    return {
        "kind": as_text(value.get("content_format")) or kind,
        "content_id": content_id,
        "canonical_url": canonical_url,
        "author_name": as_text(value.get("author_name")),
        "text": body,
        "published_at": as_text(value.get("published_at")),
        "observed_time_label": as_text(value.get("observed_time_label")),
        "reactions": integer(value.get("reactions")),
        "comments": integer(value.get("comments")),
        "shares": integer(value.get("shares")),
        "views": integer(value.get("views")),
        "representative_comments": [normalize_comment(item) for item in comments],
        "detailed": detailed,
    }


def build_snapshot(request: dict[str, Any], capture: dict[str, Any], raw_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if capture.get("schema_version") != CAPTURE_SCHEMA or capture.get("request_sha256") != request.get("request_sha256"):
        raise SystemExit("Facebook capture schema or frozen request hash does not match.")
    if contains_forbidden_key(capture):
        raise SystemExit("Facebook capture contains forbidden personal, credential, or session fields.")
    stop_reason = as_text(capture.get("stop_reason")).casefold()
    if stop_reason and stop_reason not in HARD_STOPS | {"timeout", "no_visible_posts", "details_unavailable", "surface_unreadable", "controller_connection_failed", "verified_zero_results"}:
        raise SystemExit("Unsupported Facebook stop_reason.")
    checks = capture.get("checks") if isinstance(capture.get("checks"), dict) else {}
    required = {"posts_surface": True, "frozen_query_visible": True, "public_content_only": True, "no_home_feed": True, "no_mixed_search": True, "no_write_actions": True, "no_credential_export": True}
    if any(checks.get(key) is not value for key, value in required.items()):
        stop_reason = stop_reason or "content_mismatch"
    passes = capture.get("result_passes") if isinstance(capture.get("result_passes"), list) else []
    if not passes or len(passes) > 2:
        raise SystemExit("Facebook capture requires one or two bounded result passes.")
    normalized_passes: list[list[str]] = []
    for values in passes:
        if not isinstance(values, list) or len(values) > int(request["max_posts"]):
            raise SystemExit("Facebook result pass exceeds the frozen limit.")
        links: list[str] = []
        for value in values:
            identity = canonical_content(value)
            if not identity:
                raise SystemExit("Facebook result pass contains an unsupported content URL.")
            if identity[2] not in links:
                links.append(identity[2])
        normalized_passes.append(links)
    observed = normalized_passes[0]
    observed_set = set(observed)
    cards = capture.get("result_cards") if isinstance(capture.get("result_cards"), list) else []
    details = capture.get("posts") if isinstance(capture.get("posts"), list) else []
    if len(cards) > int(request["max_posts"]) or len(details) > int(request["max_detail_posts"]):
        raise SystemExit("Facebook capture exceeds a frozen result or detail limit.")
    card_by_id = {row["content_id"]: row for row in (normalize_row(item, observed_set, False, 0) for item in cards)}
    detail_by_id = {row["content_id"]: row for row in (normalize_row(item, observed_set, True, int(request["max_comments_per_detail"])) for item in details)}
    captured_at = as_text(capture.get("captured_at")) or now_iso()
    raw_ref = str(raw_path.resolve())
    signals: list[dict[str, Any]] = []
    for rank, url in enumerate(observed, 1):
        kind, content_id, canonical_url = canonical_content(url)  # type: ignore[misc]
        row = detail_by_id.get(content_id) or card_by_id.get(content_id)
        if not row:
            continue
        representative = row["representative_comments"]
        signals.append({
            "signal_id": f"facebook-{content_id}", "platform": "facebook", "source_mode": "controlled_capture",
            "source_type": "direct_post" if row["detailed"] else "search_card", "evidence_role": "neutral",
            "detail_captured": row["detailed"], "content_id": content_id, "canonical_url": canonical_url, "source_url": canonical_url,
            "detail_access": {"url": canonical_url, "source": "logged_in_posts_search"},
            "query_term": request["query_term"], "query_layer": request["query_layer"], "query_terms": [request["query_term"]], "query_layers": [request["query_layer"]],
            "semantic_relevance": "pending_review", "topic_key": request["query_term"], "title": " ".join(row["text"].split())[:180], "summary": row["text"],
            "published_at": row["published_at"], "captured_at": captured_at, "metrics_captured_at": captured_at,
            "metrics": {"views": row["views"], "likes": None, "reactions": row["reactions"], "comments": row["comments"], "shares": row["shares"], "bookmarks": None},
            "author": {"id": "", "name": row["author_name"], "type": "facebook_public_author", "follower_count": None, "verified": None},
            "discovery": {"search_rank": rank, "search_result_count": len(observed), "observed_content_count": len(observed)},
            "time_series": {"growth_rate_percent": None, "current_window_count": None, "previous_window_count": None, "comparison_count": None},
            "platform_facts": {"content_format": row["kind"], "observed_time_label": row["observed_time_label"], "representative_comments": representative, "representative_comment_count": len(representative), "comment_sample_limit": request["max_comments_per_detail"], "comment_capture_status": "captured" if representative else "unavailable"},
            "evidence_refs": [canonical_url, raw_ref], "raw_artifacts": [raw_ref],
            "limitations": [] if row["detailed"] else ["The public Facebook result was observed on the Posts search surface, but its detail was not verified."],
            "permission_scope": "user_authorized", "dedupe_hash": hashlib.sha256(f"facebook:{content_id}".encode("utf-8")).hexdigest(),
        })
    overlap = None
    if len(normalized_passes) == 2:
        overlap = len(set(normalized_passes[0]) & set(normalized_passes[1])) / max(1, len(set(normalized_passes[0]) | set(normalized_passes[1])))
    detail_count = sum(1 for item in signals if item["detail_captured"])
    status = "blocked" if stop_reason in HARD_STOPS else ("captured" if detail_count else "unavailable")
    if not stop_reason and not observed:
        stop_reason = "no_visible_posts"
    if not stop_reason and not detail_count:
        stop_reason = "details_unavailable"
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA, "platform": "facebook", "research_scope": "topic_research", "subject": request["subject"],
        "query": {"term": request["query_term"], "layer": request["query_layer"], "url": request["query_url"]},
        "raw_sample_count": len(observed), "retained_sample_count": len(signals), "unique_sample_count": len(signals),
        "collection": {"scope": "bounded_personalized_posts_results", "counts": {"observed_result_count": len(observed), "unique_signal_count": len(signals), "detail_open_count": detail_count}, "limits": {"posts": request["max_posts"], "detail_posts": request["max_detail_posts"], "comments_per_detail": request["max_comments_per_detail"]}, "repeatability": {"pass_count": len(normalized_passes), "overlap_jaccard": overlap, "personalized_ranked_surface": True}, "terminal_reason": stop_reason or ("bounded_posts_result_limit_reached" if len(observed) >= int(request["max_posts"]) else "visible_posts_results_exhausted")},
        "signals": signals,
        "platform_adapter": {"contract_version": "platform-adapter-contract-v0.2", "adapter": "facebook_posts_browser_capture", "source_mode": "controlled_capture", "live_collection": True, "research_scope": "topic_research"},
    }
    receipt = {"schema_version": RECEIPT_SCHEMA, "recorded_at": now_iso(), "platform": "facebook", "research_scope": "topic_research", "query_term": request["query_term"], "request_sha256": request["request_sha256"], "status": status, "stop_reason": stop_reason, "observed_result_count": len(observed), "retained_signal_count": len(signals), "detail_open_count": detail_count, "raw_capture_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest()}
    return snapshot, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan or record a bounded Facebook Posts topic capture.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--subject", required=True); plan.add_argument("--query", required=True); plan.add_argument("--query-layer", choices=sorted(QUERY_LAYERS), required=True)
    plan.add_argument("--max-posts", type=int, default=20); plan.add_argument("--max-detail-posts", type=int, default=5); plan.add_argument("--output", required=True)
    record = sub.add_parser("record")
    record.add_argument("--request", required=True); record.add_argument("--capture", required=True); record.add_argument("--output", required=True); record.add_argument("--receipt", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        write_json(Path(args.output), build_request(args.subject, args.query, args.query_layer, args.max_posts, args.max_detail_posts)); return
    request = json.loads(Path(args.request).read_text(encoding="utf-8")); capture_path = Path(args.capture)
    snapshot, receipt = build_snapshot(request, json.loads(capture_path.read_text(encoding="utf-8")), capture_path)
    write_json(Path(args.output), snapshot); write_json(Path(args.receipt), receipt)


if __name__ == "__main__":
    main()
