from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from _common import now_iso, write_json


def parse_count(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb])?", text, flags=re.IGNORECASE)
    if not match:
        return None
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get((match.group(2) or "").casefold(), 1)
    return round(float(match.group(1)) * multiplier)


def video_id_from_url(url: str) -> str:
    match = re.search(r"/video/(\d+)", url)
    return match.group(1) if match else ""


def excerpt(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    return compact if len(compact) <= limit else compact[: limit - 1].rstrip() + "…"


def parse_search_records(records: Any, query: dict[str, str], raw_artifact: str) -> dict[str, Any]:
    if not isinstance(records, list):
        raise SystemExit("OpenCLI TikTok search output must be a JSON array.")
    captured_at = now_iso()
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        source_url = str(record.get("url") or "").strip()
        item_id = str(record.get("video_id") or "").strip() or video_id_from_url(source_url)
        body = str(record.get("desc") or record.get("description") or "").strip()
        if not item_id or not body or item_id in seen:
            continue
        seen.add(item_id)
        author = str(record.get("author") or "").strip().lstrip("@")
        canonical_url = f"https://www.tiktok.com/@{author}/video/{item_id}" if author else source_url
        signals.append({
            "signal_id": f"tiktok-{item_id}",
            "platform": "tiktok",
            "source_mode": "controlled_capture",
            "source_type": "search_card",
            "evidence_role": "neutral",
            "detail_captured": False,
            "content_id": item_id,
            "canonical_url": canonical_url,
            "source_url": source_url or canonical_url,
            "detail_access": {"url": canonical_url, "source": "structured_search_result"},
            "query_term": query["term"],
            "query_layer": query["layer"],
            "query_terms": [query["term"]],
            "query_layers": [query["layer"]],
            "semantic_relevance": "unreviewed",
            "topic_key": query["term"],
            "title": excerpt(body),
            "summary": body,
            "published_at": "",
            "captured_at": captured_at,
            "metrics_captured_at": captured_at,
            "metrics": {
                "views": parse_count(record.get("plays")),
                "likes": parse_count(record.get("likes")),
                "saves": None,
                "comments": parse_count(record.get("comments")),
                "shares": parse_count(record.get("shares")),
            },
            "author": {"id": author, "name": author, "type": "creator", "follower_count": None, "verified": None},
            "discovery": {
                "search_rank": int(record.get("rank") or index + 1),
                "search_result_count": len(records),
                "observed_content_count": len(records),
            },
            "time_series": {"growth_rate_percent": None, "current_window_count": None, "previous_window_count": None, "comparison_count": None},
            "evidence_refs": [source_url or canonical_url, raw_artifact],
            "limitations": [
                "TikTok search ranking may depend on locale, session, and the current platform surface.",
                "The adapter did not provide publication time or an independent detail read; the item remains search-card evidence.",
            ],
            "permission_scope": "user_authorized",
            "dedupe_hash": hashlib.sha256(f"tiktok:{item_id}".encode("utf-8")).hexdigest(),
        })
    result = {"observed_result_keys": [item["content_id"] for item in signals], "signals": signals, "detail_open_keys": []}
    if query.get("id"):
        result["query_id"] = query["id"]
    return result


def parse_file(input_path: Path, query: dict[str, str]) -> dict[str, Any]:
    try:
        records = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot parse OpenCLI TikTok search output: {error}") from error
    return parse_search_records(records, query, str(input_path.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert OpenCLI TikTok search JSON into a controlled-capture extraction chunk.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--query-term", required=True)
    parser.add_argument("--query-layer", required=True)
    args = parser.parse_args()
    result = parse_file(Path(args.input), {"id": args.query_id, "term": args.query_term, "layer": args.query_layer})
    write_json(args.output, result)
    print(json.dumps({"observed": len(result["observed_result_keys"]), "output": str(Path(args.output).resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
