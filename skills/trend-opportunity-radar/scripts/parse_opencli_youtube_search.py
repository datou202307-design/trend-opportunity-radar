from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from _common import now_iso, write_json


def parse_count(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)(万|亿|[kmb])?", text, flags=re.IGNORECASE)
    if not match:
        return None
    multiplier = {"万": 10_000, "亿": 100_000_000, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
        (match.group(2) or "").casefold(), 1
    )
    return round(float(match.group(1)) * multiplier)


def video_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/", 1)[0]
    if parsed.hostname and parsed.hostname.endswith("youtube.com"):
        direct = parse_qs(parsed.query).get("v", [""])[0]
        if direct:
            return direct
        match = re.search(r"/(?:shorts|embed)/([A-Za-z0-9_-]{6,})", parsed.path)
        if match:
            return match.group(1)
    return ""


def parse_search_records(records: Any, query: dict[str, str], raw_artifact: str) -> dict[str, Any]:
    if not isinstance(records, list):
        raise SystemExit("OpenCLI YouTube search output must be a JSON array.")
    captured_at = now_iso()
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        source_url = str(record.get("url") or "").strip()
        content_id = str(record.get("video_id") or "").strip() or video_id_from_url(source_url)
        title = str(record.get("title") or "").strip()
        if not content_id or not title or content_id in seen:
            continue
        seen.add(content_id)
        canonical_url = f"https://www.youtube.com/watch?v={content_id}"
        channel = str(record.get("channel") or "").strip()
        signals.append({
            "signal_id": f"youtube-{content_id}",
            "platform": "youtube",
            "source_mode": "controlled_capture",
            "source_type": "search_card",
            "evidence_role": "neutral",
            "detail_captured": False,
            "content_id": content_id,
            "canonical_url": canonical_url,
            "source_url": source_url or canonical_url,
            "detail_access": {"url": canonical_url, "source": "structured_search_result"},
            "query_term": query["term"],
            "query_layer": query["layer"],
            "query_terms": [query["term"]],
            "query_layers": [query["layer"]],
            "semantic_relevance": "unreviewed",
            "topic_key": query["term"],
            "title": title,
            "summary": "",
            "published_at": "",
            "captured_at": captured_at,
            "metrics_captured_at": captured_at,
            "metrics": {
                "views": parse_count(record.get("views")),
                "likes": None,
                "saves": None,
                "comments": None,
                "shares": None,
            },
            "author": {"id": "", "name": channel, "type": "channel", "follower_count": None, "verified": None},
            "discovery": {
                "search_rank": int(record.get("rank") or index + 1),
                "search_result_count": len(records),
                "observed_content_count": len(records),
            },
            "time_series": {"growth_rate_percent": None, "current_window_count": None, "previous_window_count": None, "comparison_count": None},
            "platform_facts": {
                "published_label": str(record.get("published") or "").strip(),
                "duration": str(record.get("duration") or "").strip(),
            },
            "evidence_refs": [source_url or canonical_url, raw_artifact],
            "limitations": [
                "Search ranking depends on the current YouTube surface, locale, and selected sort filters.",
                "The video detail, transcript, and comments were not opened; search-card claims remain unverified.",
            ],
            "permission_scope": "public_read",
            "dedupe_hash": hashlib.sha256(f"youtube:{content_id}".encode("utf-8")).hexdigest(),
        })
    result = {
        "observed_result_keys": [item["content_id"] for item in signals],
        "signals": signals,
        "detail_open_keys": [],
    }
    if query.get("id"):
        result["query_id"] = query["id"]
    return result


def parse_file(input_path: Path, query: dict[str, str]) -> dict[str, Any]:
    try:
        records = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot parse OpenCLI YouTube search output: {error}") from error
    return parse_search_records(records, query, str(input_path.resolve()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert OpenCLI YouTube search JSON into a controlled-capture extraction chunk.")
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
