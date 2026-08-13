from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from _common import now_iso, write_json


def parse_count(value: Any) -> int | None:
    text = str(value or "").strip().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(万|w)?", text, flags=re.IGNORECASE)
    if not match:
        return None
    return round(float(match.group(1)) * (10000 if match.group(2) else 1))


def content_id_from_url(url: str) -> str:
    match = re.search(r"/(?:search_result|explore)/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else ""


def author_id_from_url(url: str) -> str:
    match = re.search(r"/user/profile/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else ""


def parse_search_records(records: Any, query: dict[str, str], raw_artifact: str) -> dict[str, Any]:
    if not isinstance(records, list):
        raise SystemExit("OpenCLI Xiaohongshu search output must be a JSON array.")
    captured_at = now_iso()
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        source_url = str(record.get("url") or "").strip()
        content_id = content_id_from_url(source_url)
        title = str(record.get("title") or "").strip()
        if not content_id or not title or content_id in seen:
            continue
        seen.add(content_id)
        author_url = str(record.get("author_url") or "").strip()
        signals.append({
            "signal_id": f"xhs-{content_id}",
            "platform": "xiaohongshu",
            "source_mode": "controlled_capture",
            "source_type": "search_card",
            "evidence_role": "neutral",
            "detail_captured": False,
            "content_id": content_id,
            "canonical_url": f"https://www.xiaohongshu.com/explore/{content_id}",
            "source_url": source_url,
            "detail_access": {"url": source_url, "token_present": "xsec_token=" in source_url, "source": "search_card"},
            "query_term": query["term"],
            "query_layer": query["layer"],
            "query_terms": [query["term"]],
            "query_layers": [query["layer"]],
            "semantic_relevance": "unreviewed",
            "topic_key": query["term"],
            "title": title,
            "summary": "",
            "published_at": str(record.get("published_at") or "").strip(),
            "captured_at": captured_at,
            "metrics_captured_at": captured_at,
            "metrics": {"views": None, "likes": parse_count(record.get("likes")), "saves": None, "comments": None, "shares": None},
            "author": {"id": author_id_from_url(author_url), "name": str(record.get("author") or "").strip(), "type": "", "follower_count": None, "verified": None},
            "discovery": {"search_rank": int(record.get("rank") or index + 1), "search_result_count": len(records), "observed_content_count": len(records)},
            "time_series": {"growth_rate_percent": None, "current_window_count": None, "previous_window_count": None, "comparison_count": None},
            "evidence_refs": [source_url, raw_artifact],
            "limitations": [
                "Search-card visibility depends on the authorized browser session and current platform ranking.",
                "The detail was not opened; body and comment claims are not available yet.",
            ],
            "permission_scope": "user_authorized",
            "dedupe_hash": hashlib.sha256(f"xiaohongshu:{content_id}".encode("utf-8")).hexdigest(),
        })
    return {
        "observed_result_keys": [item["content_id"] for item in signals],
        "signals": signals,
        "detail_open_keys": [],
    }


def parse_file(input_path: Path, query: dict[str, str]) -> dict[str, Any]:
    try:
        records = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot parse OpenCLI raw search output: {error}") from error
    return parse_search_records(records, query, str(input_path.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert OpenCLI Xiaohongshu search JSON into a controlled-capture extraction chunk.")
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
