from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import now_iso, write_json


def post_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            rows.extend(post_rows(item))
    elif isinstance(value, dict):
        if value.get("id") and value.get("title") and (value.get("subreddit") or value.get("permalink")):
            rows.append(value)
        else:
            for key in ("results", "posts", "data", "result", "items", "content"):
                if key in value:
                    rows.extend(post_rows(value[key]))
    return rows


def integer(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def ratio(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 1 else None


def published_at(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def reddit_url(row: dict[str, Any]) -> str:
    permalink = str(row.get("permalink") or "").strip()
    if permalink.startswith("/"):
        return f"https://www.reddit.com{permalink}"
    if permalink.startswith(("https://reddit.com/", "https://www.reddit.com/")):
        return permalink
    subreddit = str(row.get("subreddit") or "").removeprefix("r/").strip("/")
    content_id = str(row.get("id") or "").strip()
    return f"https://www.reddit.com/r/{subreddit}/comments/{content_id}/" if subreddit and content_id else ""


def parse_search_records(payload: Any, query: dict[str, Any], raw_artifact: str) -> dict[str, Any]:
    records = post_rows(payload)
    captured_at = now_iso()
    operation = str(query.get("operation") or "search_subreddit").casefold()
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(records):
        content_id = str(row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        if not content_id or not title or content_id in seen:
            continue
        seen.add(content_id)
        canonical_url = reddit_url(row)
        subreddit = str(row.get("subreddit") or "").removeprefix("r/").strip("/")
        author = str(row.get("author") or "").strip()
        body_present = bool(str(row.get("selftext") or "").strip())
        detail_captured = operation == "fetch_posts" and body_present
        source_type = "direct_post" if detail_captured else "search_card"
        limitations = [
            "Reddit score is a platform ranking signal, not a visible like or upvote count.",
            "The third-party MCP result set has no verified pagination cursor, so a bounded response is not proof that Reddit was exhausted.",
            "Comments are not collected in this pilot because the upstream comment tree does not enforce a deterministic response-size cap.",
        ]
        if not detail_captured:
            limitations.append("The post body was not returned by this operation; conclusions use the title and post-level metadata only.")
        external_url = str(row.get("url") or "").strip()
        signals.append({
            "signal_id": f"reddit-{content_id}",
            "platform": "reddit",
            "source_mode": "authorized_api",
            "source_type": source_type,
            "evidence_role": "neutral",
            "detail_captured": detail_captured,
            "content_id": content_id,
            "canonical_url": canonical_url,
            "source_url": canonical_url,
            "detail_access": {"url": canonical_url, "source": "reddit_permalink"},
            "query_term": str(query.get("term") or ""),
            "query_layer": str(query.get("layer") or "unspecified"),
            "query_intent": str(query.get("intent") or ""),
            "query_terms": [str(query.get("term") or "")],
            "query_layers": [str(query.get("layer") or "unspecified")],
            "semantic_relevance": "unreviewed",
            "topic_key": str(query.get("term") or ""),
            "title": title,
            "summary": str(row.get("selftext") or "").strip(),
            "published_at": published_at(row.get("created_utc")),
            "captured_at": captured_at,
            "metrics_captured_at": captured_at,
            "metrics": {"views": None, "likes": None, "saves": None, "comments": integer(row.get("num_comments")), "shares": None},
            "author": {"id": author, "name": author, "type": "redditor", "follower_count": None, "verified": None},
            "discovery": {"search_rank": index + 1, "search_result_count": len(records), "observed_content_count": len(records)},
            "time_series": {"growth_rate_percent": None, "current_window_count": None, "previous_window_count": None, "comparison_count": None},
            "platform_facts": {
                "subreddit": subreddit,
                "reddit_score": integer(row.get("score")),
                "upvote_ratio": ratio(row.get("upvote_ratio")),
                "external_url": external_url if external_url and external_url != canonical_url else "",
                "mcp_operation": operation,
            },
            "evidence_refs": [item for item in (canonical_url, raw_artifact) if item],
            "limitations": limitations,
            "permission_scope": "public",
            "dedupe_hash": hashlib.sha256(f"reddit:{content_id}".encode("utf-8")).hexdigest(),
        })
    observed_keys = [item["content_id"] for item in signals]
    result = {
        "query_term": str(query.get("term") or ""),
        "query_layer": str(query.get("layer") or "unspecified"),
        "query_intent": str(query.get("intent") or ""),
        "operation": operation,
        "observed_result_count": len(records),
        "retained_signal_count": len(signals),
        "detail_open_count": sum(1 for item in signals if item.get("detail_captured")),
        "observed_result_keys": observed_keys,
        "signals": signals,
        "detail_open_keys": [item["content_id"] for item in signals if item.get("detail_captured")],
        "raw_artifacts": [raw_artifact] if raw_artifact else [],
        "capture_executions": [],
        "stop_reason": "bounded_response_received",
        "outcome": "completed_with_results" if records else "completed_with_zero_results",
    }
    if query.get("id"):
        result["query_id"] = query["id"]
    return result


def parse_file(input_path: Path, query: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot parse Reddit MCP output: {error}") from error
    return parse_search_records(payload, query, str(input_path.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert bounded Reddit Research MCP post results into an extraction chunk.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--query-term", required=True)
    parser.add_argument("--query-layer", required=True)
    parser.add_argument("--query-intent", default="")
    parser.add_argument("--operation", choices=["search_subreddit", "fetch_posts"], default="search_subreddit")
    args = parser.parse_args()
    result = parse_file(Path(args.input), {"id": args.query_id, "term": args.query_term, "layer": args.query_layer, "intent": args.query_intent, "operation": args.operation})
    write_json(args.output, result)
    print(json.dumps({"observed": result["observed_result_count"], "retained": result["retained_signal_count"], "output": str(Path(args.output).resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
