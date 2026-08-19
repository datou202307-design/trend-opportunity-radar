from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from append_collection_result import signal_key
from check_collection_adapter import executable_command, resolve_opencli
from collection_pacing import pacing_policy, throttle_before_read
from orchestrate_dokobot_collection import action, load_state, record_detail_backfill
from parse_opencli_xhs_search import parse_count
from parse_opencli_x_search import parse_count as parse_x_count
from parse_opencli_youtube_search import parse_count as parse_youtube_count
from run_collection_capture import classify_opencli_failure, command_hash


YOUTUBE_COMMENT_SAMPLE_LIMIT = 10
X_COMMENT_SAMPLE_LIMIT = 5
XHS_COMMENT_SAMPLE_LIMIT = 5


def throttle_before_detail(platform: str, request_index: int, sleeper=None) -> dict[str, Any]:
    """Apply the shared serialized detail-read cadence."""
    return throttle_before_read(platform, "detail", request_index, sleeper) if sleeper else throttle_before_read(platform, "detail", request_index)


def fields_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return {}
    return {
        str(item.get("field")): item.get("value")
        for item in value
        if isinstance(item, dict) and item.get("field")
    }


def x_detail(value: Any, target: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(value, list):
        return None
    match = __import__("re").search(r"/status/(\d+)", str(target.get("url") or ""))
    target_id = match.group(1) if match else ""
    record = next((item for item in value if isinstance(item, dict) and str(item.get("id") or "") == target_id), None)
    if not isinstance(record, dict):
        return None
    body = str(record.get("text") or "").strip()
    author = str(record.get("author") or "").strip().lstrip("@")
    if not body or not author:
        return None
    representative_comments = x_thread_comments(value, target_id)
    return {
        "title": " ".join(body.split())[:180],
        "summary": body,
        "published_at": str(record.get("created_at") or "").strip(),
        "metrics": {
            "views": parse_x_count(record.get("views")),
            "likes": parse_x_count(record.get("likes")),
            "comments": parse_x_count(record.get("replies")),
            "shares": parse_x_count(record.get("retweets")),
        },
        "author": {"id": author, "name": author},
        "platform_facts": {
            "representative_comments": representative_comments,
            "representative_comment_count": len(representative_comments),
            "comment_sample_limit": X_COMMENT_SAMPLE_LIMIT,
            "comment_capture_status": "complete",
        },
    }


def x_thread_comments(value: Any, target_id: str, limit: int = X_COMMENT_SAMPLE_LIMIT) -> list[dict[str, Any]]:
    """Keep a bounded reply sample from the already-opened X thread."""
    if not isinstance(value, list):
        return []
    comments: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict) or str(row.get("id") or "") == target_id:
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        comments.append({
            "author_name": str(row.get("author") or "").strip().lstrip("@"),
            "text": text,
            "likes": parse_x_count(row.get("likes")),
            "reply_count": parse_x_count(row.get("replies")),
            "observed_time_label": str(row.get("created_at") or "").strip(),
        })
        if len(comments) >= limit:
            break
    return comments


def youtube_detail(value: Any) -> dict[str, Any] | None:
    fields = fields_map(value)
    title = str(fields.get("title") or "").strip()
    channel = str(fields.get("channel") or "").strip()
    description = str(fields.get("description") or "").strip()
    if not title or not channel or not description:
        return None
    return {
        "title": title,
        "summary": description,
        "published_at": str(fields.get("publishDate") or fields.get("published_at") or "").strip(),
        "metrics": {
            "views": parse_youtube_count(fields.get("views")),
            "likes": parse_youtube_count(fields.get("likes")),
            "comments": None,
            "shares": None,
        },
        "author": {
            "id": str(fields.get("channelId") or "").strip(),
            "name": channel,
            "follower_count": parse_youtube_count(fields.get("subscribers")),
        },
        "platform_facts": {
            "category": str(fields.get("category") or "").strip(),
            "duration_seconds": parse_youtube_count(str(fields.get("duration") or "").rstrip("s")),
            "thumbnail": str(fields.get("thumbnail") or "").strip(),
        },
    }


def youtube_comments(value: Any, limit: int = YOUTUBE_COMMENT_SAMPLE_LIMIT) -> list[dict[str, Any]]:
    """Normalize a bounded comment sample without treating it as trend volume."""
    if not isinstance(value, list):
        return []
    comments: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        text = str(row.get("text") or row.get("content") or row.get("comment") or "").strip()
        if not text:
            continue
        author_value = row.get("author")
        if isinstance(author_value, dict):
            author = str(author_value.get("name") or author_value.get("handle") or "").strip()
        else:
            author = str(author_value or row.get("authorName") or "").strip()
        comments.append({
            "author_name": author,
            "text": text,
            "likes": parse_youtube_count(row.get("likes")),
            "reply_count": parse_youtube_count(row.get("replies") or row.get("replyCount")),
            "observed_time_label": str(row.get("time") or row.get("published") or row.get("publishedAt") or "").strip(),
        })
        if len(comments) >= limit:
            break
    return comments


def xhs_comments(value: Any, limit: int = XHS_COMMENT_SAMPLE_LIMIT) -> list[dict[str, Any]]:
    """Normalize a bounded top-level Xiaohongshu comment sample."""
    if not isinstance(value, list):
        return []
    comments: list[dict[str, Any]] = []
    for row in value:
        if not isinstance(row, dict) or row.get("is_reply") is True:
            continue
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        comments.append({
            "author_name": str(row.get("author") or "").strip(),
            "text": text,
            "likes": parse_count(row.get("likes")),
            "reply_count": None,
            "observed_time_label": str(row.get("time") or "").strip(),
        })
        if len(comments) >= limit:
            break
    return comments


def immutable_attempt_path(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}-run-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def capture_youtube_comments(
    target: dict[str, Any], detail_raw_path: Path, timeout: int, throttle: dict[str, Any] | None = None
) -> dict[str, Any]:
    throttle = throttle or throttle_before_read("youtube", "comment", 0)
    requested = [
        "opencli", "youtube", "comments", str(target["url"]),
        "--limit", str(YOUTUBE_COMMENT_SAMPLE_LIMIT), "-f", "json",
        "--window", "background", "--trace", "retain-on-failure",
    ]
    started_at = now_iso()
    code, stdout, stderr, timed_out = execute(requested, timeout)
    finished_at = now_iso()
    raw_path = immutable_attempt_path(detail_raw_path.with_name(f"{detail_raw_path.stem}-comments.json"))
    raw_path.write_text(stdout, encoding="utf-8")
    stdout_path = raw_path.with_suffix(raw_path.suffix + ".stdout.txt")
    stderr_path = raw_path.with_suffix(raw_path.suffix + ".stderr.txt")
    metadata_path = raw_path.with_suffix(raw_path.suffix + ".capture.json")
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    stop_reason = ""
    hard_stop = ""
    normalized: list[dict[str, Any]] = []
    if timed_out:
        stop_reason = "timeout"
    elif code != 0:
        stop_reason, hard_stop = classify_opencli_failure(f"{stdout}\n{stderr}")
    else:
        try:
            normalized = youtube_comments(json.loads(stdout))
        except json.JSONDecodeError:
            stop_reason = "cli_error"
    write_json(str(metadata_path), {
        "schema_version": "collection-comment-execution-v0.1",
        "adapter": "opencli",
        "platform": "youtube",
        "signal_key": target["signal_key"],
        "sample_limit": YOUTUBE_COMMENT_SAMPLE_LIMIT,
        "sample_count": len(normalized),
        "requested_command": requested,
        "requested_command_sha256": command_hash(requested),
        "exit_code": code,
        "timed_out": timed_out,
        "stop_reason": stop_reason,
        "hard_stop": hard_stop,
        "throttle": throttle,
        "started_at": started_at,
        "finished_at": finished_at,
        "raw_artifact": str(raw_path.resolve()),
        "stdout_artifact": str(stdout_path.resolve()),
        "stderr_artifact": str(stderr_path.resolve()),
        "metadata_artifact": str(metadata_path.resolve()),
    })
    return {
        "comments": normalized,
        "sample_limit": YOUTUBE_COMMENT_SAMPLE_LIMIT,
        "stop_reason": stop_reason,
        "hard_stop": hard_stop,
        "artifacts": [
            str(raw_path.resolve()), str(stdout_path.resolve()),
            str(stderr_path.resolve()), str(metadata_path.resolve()),
        ],
        "metadata_artifact": str(metadata_path.resolve()),
    }


def capture_xhs_comments(
    target: dict[str, Any], detail_raw_path: Path, timeout: int, throttle: dict[str, Any]
) -> dict[str, Any]:
    requested = [
        "opencli", "xiaohongshu", "comments", str(target["url"]),
        "--limit", str(XHS_COMMENT_SAMPLE_LIMIT), "--with-replies", "false", "-f", "json",
        "--window", "background", "--trace", "retain-on-failure",
    ]
    started_at = now_iso()
    code, stdout, stderr, timed_out = execute(requested, timeout)
    finished_at = now_iso()
    raw_path = immutable_attempt_path(detail_raw_path.with_name(f"{detail_raw_path.stem}-comments.json"))
    raw_path.write_text(stdout, encoding="utf-8")
    stdout_path = raw_path.with_suffix(raw_path.suffix + ".stdout.txt")
    stderr_path = raw_path.with_suffix(raw_path.suffix + ".stderr.txt")
    metadata_path = raw_path.with_suffix(raw_path.suffix + ".capture.json")
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    stop_reason = ""
    hard_stop = ""
    normalized: list[dict[str, Any]] = []
    if timed_out:
        stop_reason = "timeout"
    elif code != 0:
        stop_reason, hard_stop = classify_opencli_failure(f"{stdout}\n{stderr}")
    else:
        try:
            normalized = xhs_comments(json.loads(stdout))
        except json.JSONDecodeError:
            stop_reason = "cli_error"
    write_json(str(metadata_path), {
        "schema_version": "collection-comment-execution-v0.1",
        "adapter": "opencli",
        "platform": "xiaohongshu",
        "signal_key": target["signal_key"],
        "sample_limit": XHS_COMMENT_SAMPLE_LIMIT,
        "sample_count": len(normalized),
        "requested_command": requested,
        "requested_command_sha256": command_hash(requested),
        "exit_code": code,
        "timed_out": timed_out,
        "stop_reason": stop_reason,
        "hard_stop": hard_stop,
        "throttle": throttle,
        "started_at": started_at,
        "finished_at": finished_at,
        "raw_artifact": str(raw_path.resolve()),
        "stdout_artifact": str(stdout_path.resolve()),
        "stderr_artifact": str(stderr_path.resolve()),
        "metadata_artifact": str(metadata_path.resolve()),
    })
    return {
        "comments": normalized,
        "sample_limit": XHS_COMMENT_SAMPLE_LIMIT,
        "stop_reason": stop_reason,
        "hard_stop": hard_stop,
        "artifacts": [
            str(raw_path.resolve()), str(stdout_path.resolve()),
            str(stderr_path.resolve()), str(metadata_path.resolve()),
        ],
        "metadata_artifact": str(metadata_path.resolve()),
    }


def execute(requested: list[str], timeout: int) -> tuple[int | None, str, str, bool]:
    located = shutil.which(requested[0])
    if not located:
        located, _, _ = resolve_opencli()
    if not located:
        raise SystemExit("OpenCLI executable is not available for detail backfill.")
    command = executable_command(located, requested[1:], "@jackwener/opencli", ("dist", "src", "main.js"))
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return completed.returncode, completed.stdout, completed.stderr, False
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
        return None, stdout, stderr, True


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute eligible OpenCLI detail backfills for validated X, Xiaohongshu, or YouTube runs and atomically update the canonical ledger.")
    parser.add_argument("--state", required=True)
    parser.add_argument("--results-output", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--max-details", type=int, default=0, help="0 processes every currently eligible target.")
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()
    if args.timeout_seconds < 10 or args.timeout_seconds > 180:
        raise SystemExit("--timeout-seconds must be between 10 and 180.")
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    if state.get("adapter") != "opencli" or state.get("platform") not in {"xiaohongshu", "x", "youtube"}:
        raise SystemExit("This detail runner requires a validated OpenCLI X, Xiaohongshu, or YouTube run.")
    next_action = action(state)
    if next_action.get("action") != "backfill_details":
        raise SystemExit("The collection orchestrator does not currently request detail backfill.")
    targets = list(next_action.get("targets") or [])
    if args.max_details:
        targets = targets[:args.max_details]
    snapshot = load_data(state["snapshot"])
    by_key = {signal_key(item): item for item in snapshot.get("signals", []) if isinstance(item, dict)}
    results: list[dict[str, Any]] = []
    hard_stop = ""
    detail_request_index = 0
    for target in targets:
        attempts = 2
        accepted: dict[str, Any] | None = None
        last_raw = ""
        last_metadata = ""
        last_stop = ""
        for attempt in range(1, attempts + 1):
            requested = [str(item) for item in target["capture_command"]]
            throttle = throttle_before_detail(str(state.get("platform") or ""), detail_request_index)
            detail_request_index += 1
            started_at = now_iso()
            code, stdout, stderr, timed_out = execute(requested, args.timeout_seconds)
            finished_at = now_iso()
            base = Path(target["raw_output"])
            raw_path = base.with_name(f"{base.stem}-attempt-{attempt}{base.suffix}")
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(stdout, encoding="utf-8")
            stderr_path = raw_path.with_suffix(raw_path.suffix + ".stderr.txt")
            stdout_path = raw_path.with_suffix(raw_path.suffix + ".stdout.txt")
            metadata_path = raw_path.with_suffix(raw_path.suffix + ".capture.json")
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            write_json(str(metadata_path), {
                "schema_version": "collection-detail-execution-v0.1",
                "adapter": "opencli",
                "signal_key": target["signal_key"],
                "requested_command": requested,
                "requested_command_sha256": command_hash(requested),
                "exit_code": code,
                "timed_out": timed_out,
                "throttle": throttle,
                "started_at": started_at,
                "finished_at": finished_at,
                "raw_artifact": str(raw_path.resolve()),
                "stdout_artifact": str(stdout_path.resolve()),
                "stderr_artifact": str(stderr_path.resolve()),
                "metadata_artifact": str(metadata_path.resolve()),
            })
            last_raw = str(raw_path.resolve())
            last_metadata = str(metadata_path.resolve())
            if timed_out:
                last_stop = "repeated_timeout" if attempt == attempts else ""
                if attempt < attempts:
                    continue
                break
            if code != 0:
                stop_reason, hard_stop = classify_opencli_failure(f"{stdout}\n{stderr}")
                last_stop = hard_stop or stop_reason
                break
            try:
                decoded = json.loads(stdout)
            except json.JSONDecodeError:
                last_stop = "cli_error"
                break
            if state.get("platform") == "x":
                accepted = x_detail(decoded, target)
                if accepted:
                    accepted.update({
                        "evidence_refs": [str(raw_path.resolve()), str(metadata_path.resolve()), target["url"]],
                        "raw_artifacts": [str(raw_path.resolve()), str(stdout_path.resolve()), str(metadata_path.resolve()), str(stderr_path.resolve())],
                        "captured_at": now_iso(), "metrics_captured_at": now_iso(),
                    })
                    break
                last_stop = "cli_error"
                break
            if state.get("platform") == "youtube":
                accepted = youtube_detail(decoded)
                if accepted:
                    comment_throttle = throttle_before_read("youtube", "comment", detail_request_index)
                    detail_request_index += 1
                    comment_capture = capture_youtube_comments(target, raw_path, args.timeout_seconds, comment_throttle)
                    platform_facts = accepted.setdefault("platform_facts", {})
                    platform_facts["representative_comments"] = comment_capture["comments"]
                    platform_facts["representative_comment_count"] = len(comment_capture["comments"])
                    platform_facts["comment_sample_limit"] = comment_capture["sample_limit"]
                    platform_facts["comment_capture_status"] = (
                        "complete" if not comment_capture["stop_reason"] and not comment_capture["hard_stop"] else "unavailable"
                    )
                    if comment_capture["stop_reason"]:
                        accepted.setdefault("limitations", []).append(
                            "Bounded representative comments were unavailable; video detail remains usable."
                        )
                    if comment_capture["hard_stop"]:
                        hard_stop = comment_capture["hard_stop"]
                    accepted.update({
                        "evidence_refs": [str(raw_path.resolve()), str(metadata_path.resolve()), comment_capture["metadata_artifact"], target["url"]],
                        "raw_artifacts": [str(raw_path.resolve()), str(stdout_path.resolve()), str(metadata_path.resolve()), str(stderr_path.resolve()), *comment_capture["artifacts"]],
                        "captured_at": now_iso(), "metrics_captured_at": now_iso(),
                    })
                    break
                last_stop = "cli_error"
                break
            fields = fields_map(decoded)
            likes = parse_count(fields.get("likes"))
            saves = parse_count(fields.get("collects") or fields.get("saves"))
            comments = parse_count(fields.get("comments"))
            original = by_key.get(str(target["signal_key"]), {})
            original_likes = ((original.get("metrics") or {}).get("likes") or 0) if isinstance(original, dict) else 0
            all_zero = original_likes > 0 and likes == 0 and saves == 0 and comments == 0
            complete = bool(str(fields.get("title") or "").strip() and str(fields.get("author") or "").strip() and str(fields.get("content") or "").strip() and likes is not None and not all_zero)
            if complete:
                accepted = {
                    "title": str(fields.get("title") or "").strip(),
                    "summary": str(fields.get("content") or "").strip(),
                    "published_at": str(fields.get("published_at") or fields.get("date") or "").strip(),
                    "metrics": {"likes": likes, "saves": saves, "comments": comments},
                    "author": {"name": str(fields.get("author") or "").strip()},
                    "evidence_refs": [str(raw_path.resolve()), str(metadata_path.resolve()), target["url"]],
                    "raw_artifacts": [str(raw_path.resolve()), str(stdout_path.resolve()), str(metadata_path.resolve()), str(stderr_path.resolve())],
                    "captured_at": now_iso(),
                    "metrics_captured_at": now_iso(),
                }
                comment_throttle = throttle_before_detail("xiaohongshu", detail_request_index)
                detail_request_index += 1
                comment_capture = capture_xhs_comments(target, raw_path, args.timeout_seconds, comment_throttle)
                accepted["platform_facts"] = {
                    "representative_comments": comment_capture["comments"],
                    "representative_comment_count": len(comment_capture["comments"]),
                    "comment_sample_limit": comment_capture["sample_limit"],
                    "comment_capture_status": (
                        "complete" if not comment_capture["stop_reason"] and not comment_capture["hard_stop"] else "unavailable"
                    ),
                }
                accepted["evidence_refs"].append(comment_capture["metadata_artifact"])
                accepted["raw_artifacts"].extend(comment_capture["artifacts"])
                if comment_capture["stop_reason"]:
                    accepted.setdefault("limitations", []).append(
                        "Bounded representative comments were unavailable; note detail remains usable."
                    )
                if comment_capture["hard_stop"]:
                    hard_stop = comment_capture["hard_stop"]
                break
            last_stop = "cli_error"
            if not all_zero:
                break
        results.append({
            "signal_key": target["signal_key"],
            "success": accepted is not None,
            "raw_artifact": last_raw,
            "metadata_artifact": last_metadata,
            "stop_reason": "" if accepted else last_stop,
            "execution": {
                "requested_command_sha256": command_hash(requested), "exit_code": code,
                "started_at": started_at, "finished_at": finished_at,
                "throttle": throttle,
                "stdout_artifact": str(stdout_path.resolve()), "stderr_artifact": str(stderr_path.resolve()),
                "metadata_artifact": str(metadata_path.resolve()),
            },
            **({"signal": accepted} if accepted else {}),
        })
        if hard_stop:
            break
    payload = {
        "schema_version": "opencli-detail-backfill-v0.2",
        "adapter": "opencli",
        "platform": state.get("platform"),
        "status": "blocked" if hard_stop else "complete",
        "hard_stop": hard_stop,
        "throttle_policy": {
            **pacing_policy(str(state.get("platform") or ""), "detail"),
            "request_count": detail_request_index,
        },
        "results": results,
    }
    write_json(args.results_output, payload)
    if not args.no_record:
        record_detail_backfill(state, payload)
        write_json(str(state_path), state)
    print(json.dumps({"attempted": len(results), "successful": sum(1 for item in results if item["success"]), "hard_stop": hard_stop, "recorded": not args.no_record, "results": str(Path(args.results_output).resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
