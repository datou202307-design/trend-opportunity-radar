from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from _common import as_text, load_data, now_iso, write_json


REQUEST_SCHEMA = "tiktok-visible-comment-request-v0.1"
CAPTURE_SCHEMA = "tiktok-visible-comment-browser-capture-v0.1"
RECEIPT_SCHEMA = "tiktok-visible-comment-receipt-v0.1"
TIKTOK_URL = re.compile(
    r"https://(?:www\.)?tiktok\.com/@([A-Za-z0-9._-]+)/(?:video|photo)/(\d+)(?:[?#/].*)?$",
    re.IGNORECASE,
)
HARD_STOPS = {
    "captcha",
    "rate_limit",
    "login_expired",
    "permission_prompt",
    "abnormal_redirect",
    "content_mismatch",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def request_hash(payload: dict[str, Any]) -> str:
    frozen = {key: value for key, value in payload.items() if key not in {"generated_at", "request_sha256"}}
    return hashlib.sha256(canonical_json(frozen).encode("utf-8")).hexdigest()


def identity(url: str) -> tuple[str, str] | None:
    match = TIKTOK_URL.fullmatch(as_text(url))
    return (match.group(1), match.group(2)) if match else None


def signal_identity(signal: dict[str, Any]) -> tuple[str, str, str] | None:
    url = as_text(signal.get("canonical_url") or signal.get("url"))
    parsed = identity(url)
    if not parsed:
        return None
    handle, content_id = parsed
    stored_id = as_text(signal.get("content_id"))
    author = signal.get("author") if isinstance(signal.get("author"), dict) else {}
    stored_handle = as_text(author.get("handle") or author.get("id")).lstrip("@")
    if stored_id and stored_id != content_id:
        return None
    if stored_handle and stored_handle.casefold() != handle.casefold():
        return None
    return url, handle, content_id


def eligible_signal(signal: dict[str, Any]) -> bool:
    if not signal_identity(signal):
        return False
    if signal.get("detail_captured") is not True and as_text(signal.get("source_type")) != "direct_post":
        return False
    facts = signal.get("platform_facts") if isinstance(signal.get("platform_facts"), dict) else {}
    comments = facts.get("representative_comments") if isinstance(facts.get("representative_comments"), list) else []
    return not comments and as_text(facts.get("comment_capture_status")) != "captured"


def build_request(snapshot: dict[str, Any], signal_key: str = "") -> dict[str, Any]:
    if as_text(snapshot.get("platform")).casefold() != "tiktok":
        raise SystemExit("TikTok comment enrichment requires a TikTok signal snapshot.")
    eligible = [item for item in snapshot.get("signals", []) if isinstance(item, dict) and eligible_signal(item)]
    target = next(
        (
            item for item in eligible
            if not signal_key
            or as_text(item.get("signal_id") or item.get("dedupe_hash") or item.get("content_id")) == signal_key
        ),
        None,
    )
    if target is None:
        raise SystemExit("No verified TikTok detail is eligible for comment enrichment.")
    parsed = signal_identity(target)
    assert parsed is not None
    url, handle, content_id = parsed
    payload = {
        "schema_version": REQUEST_SCHEMA,
        "generated_at": now_iso(),
        "platform": "tiktok",
        "signal_key": as_text(target.get("signal_id") or target.get("dedupe_hash") or content_id),
        "canonical_url": url,
        "content_id": content_id,
        "author_handle": handle,
        "source_mode": "user_authorized_logged_in_chrome",
        "max_comments": 5,
        "allowed_action": "expand_exact_target_comments_once_and_read_visible_dom",
        "required_checks": [
            "stable_content_id",
            "author_path",
            "target_comments_panel",
            "top_level_visible_comments_only",
            "no_recommended_content",
            "no_write_actions",
        ],
        "hard_stops": sorted(HARD_STOPS),
    }
    payload["request_sha256"] = request_hash(payload)
    return payload


def normalize_comment(comment: dict[str, Any]) -> dict[str, Any]:
    author = as_text(comment.get("author_name") or comment.get("author"))
    text = as_text(comment.get("text"))
    if not author or not text:
        raise SystemExit("Every captured comment requires author_name and visible text.")
    if comment.get("top_level_visible") is not True:
        raise SystemExit("Every captured comment must be explicitly marked top_level_visible=true.")
    likes = comment.get("likes")
    if likes is not None and not isinstance(likes, (int, float, str)):
        raise SystemExit("Comment likes must be a visible number, label, or null.")
    return {
        "author_name": author,
        "text": text,
        "likes": likes,
        "reply_count": None,
        "published_at": as_text(comment.get("published_at")),
        "observed_time_label": as_text(comment.get("observed_time_label")),
    }


def validate_capture(request: dict[str, Any], capture: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str]:
    if capture.get("schema_version") != CAPTURE_SCHEMA:
        raise SystemExit("Unsupported TikTok browser capture schema.")
    if capture.get("request_sha256") != request.get("request_sha256"):
        raise SystemExit("Capture request_sha256 does not match the frozen request.")
    stop_reason = as_text(capture.get("stop_reason")).casefold()
    if stop_reason:
        if stop_reason not in HARD_STOPS | {"timeout", "comments_unavailable"}:
            raise SystemExit("Unsupported TikTok comment stop_reason.")
        return "blocked" if stop_reason in HARD_STOPS else "unavailable", [], stop_reason
    requested_identity = identity(as_text(request.get("canonical_url")))
    captured_identity = identity(as_text(capture.get("canonical_url")))
    if not requested_identity or captured_identity != requested_identity:
        return "blocked", [], "content_mismatch"
    if as_text(capture.get("content_id")) != as_text(request.get("content_id")):
        return "blocked", [], "content_mismatch"
    if as_text(capture.get("author_handle")).lstrip("@").casefold() != as_text(request.get("author_handle")).casefold():
        return "blocked", [], "content_mismatch"
    checks = capture.get("checks") if isinstance(capture.get("checks"), dict) else {}
    required = {
        "stable_content_id": True,
        "author_path": True,
        "target_comments_panel": True,
        "top_level_visible_comments_only": True,
        "no_recommended_content": True,
        "no_write_actions": True,
    }
    if any(checks.get(key) is not value for key, value in required.items()):
        return "blocked", [], "content_mismatch"
    rows = capture.get("comments")
    if not isinstance(rows, list):
        raise SystemExit("TikTok browser capture comments must be an array.")
    limit = int(request.get("max_comments") or 5)
    if len(rows) > limit:
        raise SystemExit(f"TikTok visible comment capture exceeds the {limit}-comment limit.")
    comments = [normalize_comment(item) for item in rows if isinstance(item, dict)]
    if len(comments) != len(rows):
        raise SystemExit("Every captured comment must be an object.")
    keys = {(item["author_name"].casefold(), item["text"]) for item in comments}
    if len(keys) != len(comments):
        raise SystemExit("Duplicate visible comments are not allowed in one capture.")
    if not comments:
        return "unavailable", [], "comments_unavailable"
    total = capture.get("visible_comment_entry_count")
    if not isinstance(total, int) or total < len(comments):
        raise SystemExit("visible_comment_entry_count must be an integer not smaller than captured bodies.")
    return "captured", comments, ""


def apply_capture(snapshot: dict[str, Any], request: dict[str, Any], capture: dict[str, Any], raw_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    status, comments, stop_reason = validate_capture(request, capture)
    result = copy.deepcopy(snapshot)
    target = next(
        (
            signal for signal in result.get("signals", [])
            if isinstance(signal, dict)
            and as_text(signal.get("signal_id") or signal.get("dedupe_hash") or signal.get("content_id")) == as_text(request.get("signal_key"))
        ),
        None,
    )
    if target is None:
        raise SystemExit("The frozen TikTok comment target no longer exists in the snapshot.")
    if signal_identity(target) != (
        as_text(request.get("canonical_url")),
        as_text(request.get("author_handle")),
        as_text(request.get("content_id")),
    ):
        raise SystemExit("The frozen TikTok target identity no longer matches the snapshot.")
    raw_sha256 = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    if status == "captured":
        facts = target.setdefault("platform_facts", {})
        facts["representative_comments"] = comments
        facts["representative_comment_count"] = len(comments)
        facts["comment_sample_limit"] = int(request.get("max_comments") or 5)
        facts["comment_capture_status"] = "captured"
        facts["visible_comment_entry_count"] = capture["visible_comment_entry_count"]
        refs = target.setdefault("evidence_refs", [])
        raw_ref = str(raw_path.resolve())
        if raw_ref not in refs:
            refs.append(raw_ref)
        artifacts = target.setdefault("raw_artifacts", [])
        if raw_ref not in artifacts:
            artifacts.append(raw_ref)
        limitations = target.get("limitations") if isinstance(target.get("limitations"), list) else []
        target["limitations"] = [
            item for item in limitations
            if "comment text was visible" not in as_text(item).casefold()
            and "comment text was unavailable" not in as_text(item).casefold()
        ]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "recorded_at": now_iso(),
        "platform": "tiktok",
        "request_sha256": request["request_sha256"],
        "signal_key": request["signal_key"],
        "content_id": request["content_id"],
        "canonical_url": request["canonical_url"],
        "source_mode": request["source_mode"],
        "status": status,
        "stop_reason": stop_reason,
        "captured_comment_count": len(comments),
        "visible_comment_entry_count": capture.get("visible_comment_entry_count"),
        "raw_capture": str(raw_path.resolve()),
        "raw_capture_sha256": raw_sha256,
        "snapshot_mutated": status == "captured",
    }
    return result, receipt


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan or record bounded TikTok visible-comment enrichment without browser credentials.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan")
    plan.add_argument("--snapshot", required=True)
    plan.add_argument("--output", required=True)
    plan.add_argument("--signal-key", default="", help="Optional eligible signal_id; otherwise freeze the first eligible detail.")
    record = subparsers.add_parser("record")
    record.add_argument("--snapshot", required=True)
    record.add_argument("--request", required=True)
    record.add_argument("--capture", required=True)
    record.add_argument("--output", required=True)
    record.add_argument("--receipt", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        snapshot = load_data(args.snapshot)
        if not isinstance(snapshot, dict):
            raise SystemExit("TikTok comment plan requires a signal snapshot object.")
        write_json(args.output, build_request(snapshot, args.signal_key))
        return
    snapshot = load_data(args.snapshot)
    request = load_data(args.request)
    capture_path = Path(args.capture).resolve()
    capture = load_data(str(capture_path))
    if not all(isinstance(item, dict) for item in (snapshot, request, capture)):
        raise SystemExit("Snapshot, request, and capture must all be JSON objects.")
    updated, receipt = apply_capture(snapshot, request, capture, capture_path)
    write_json(args.output, updated)
    write_json(args.receipt, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
