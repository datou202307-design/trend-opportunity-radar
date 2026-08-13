from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from _common import write_json


STATUS_URL = re.compile(r"https://(?:www\.)?x\.com/([A-Za-z0-9_]+)/status/(\d+)", re.IGNORECASE)
HEADER = re.compile(r"(?m)^\*\*(.+?)\s+\[\d+\]\*\*\s+@([A-Za-z0-9_]+).*?$")
METRIC = re.compile(r"([\d,.]+)\s+(Replies?|reposts?|Likes?|views?|Bookmarks?)", re.IGNORECASE)


def parse_number(value: str) -> int | None:
    try:
        return int(float(value.replace(",", "")))
    except ValueError:
        return None


def clean_body(block: str, header_end: int) -> str:
    body = block[header_end:]
    lines = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line == "Show more" or line.startswith(("http://", "https://")):
            continue
        if re.fullmatch(r"(?:[\d,.]+\s+(?:Replies?|reposts?|Likes?|views?|Bookmarks?)\s*)+", line, re.IGNORECASE):
            continue
        line = re.sub(r"\[\d+\]", "", line).replace("**", "").strip()
        if line:
            lines.append(line)
    return " ".join(lines).strip()


def parse_text(text: str, query: dict[str, Any]) -> dict[str, Any]:
    normalized = text.replace("\r\n", "\n")
    urls_by_handle: dict[str, list[tuple[str, str]]] = {}
    for handle, content_id in STATUS_URL.findall(normalized):
        urls_by_handle.setdefault(handle.casefold(), []).append((content_id, f"https://x.com/{handle}/status/{content_id}"))
    used: set[str] = set()
    observed: list[str] = []
    signals: list[dict[str, Any]] = []
    for block in re.split(r"(?m)^---\s*$", normalized):
        header = HEADER.search(block)
        if not header:
            continue
        author_name, handle = header.group(1).strip(), header.group(2)
        candidates = urls_by_handle.get(handle.casefold(), [])
        selected = next(((cid, url) for cid, url in candidates if cid not in used), None)
        if not selected:
            continue
        content_id, canonical_url = selected
        body = clean_body(block, header.end())
        if not body:
            continue
        used.add(content_id)
        observed.append(content_id)
        metrics = {"views": None, "likes": None, "comments": None, "shares": None, "saves": None}
        mapping = {"view": "views", "like": "likes", "repl": "comments", "repost": "shares", "bookmark": "saves"}
        for value, label in METRIC.findall(block):
            key = next((target for prefix, target in mapping.items() if label.casefold().startswith(prefix)), None)
            if key:
                metrics[key] = parse_number(value)
        signals.append({
            "content_id": content_id,
            "canonical_url": canonical_url,
            "source_type": "search_card",
            "evidence_role": "neutral",
            "detail_captured": False,
            "semantic_relevance": "unreviewed",
            "semantic_review": {"status": "pending", "reason": "Mechanical search-card extraction does not judge topic relevance."},
            "topic_key": "unreviewed",
            "title": body[:180],
            "summary": body,
            "published_at": "",
            "metrics": metrics,
            "author": {"id": handle, "name": author_name, "handle": f"@{handle}", "type": "unknown"},
            "evidence_refs": [canonical_url],
            "limitations": ["Search card only", "Semantic relevance requires a separate review."],
            "permission_scope": "public",
            "query_term": str(query.get("term") or query.get("query_term") or ""),
            "query_layer": str(query.get("layer") or query.get("query_layer") or ""),
            "query_id": str(query.get("id") or query.get("query_id") or ""),
        })
    return {
        "query_id": str(query.get("id") or query.get("query_id") or ""),
        "observed_result_keys": observed, "signals": signals, "detail_open_keys": [],
    }


def parse_file(path: Path, query: dict[str, Any]) -> dict[str, Any]:
    return parse_text(path.read_text(encoding="utf-8", errors="replace"), query)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mechanically extract X search cards from preserved DokoBot output.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--query-term", required=True)
    parser.add_argument("--query-layer", required=True, choices=("platform_baseline", "category", "subject_bridge"))
    args = parser.parse_args()
    write_json(args.output, parse_file(Path(args.input), {"term": args.query_term, "layer": args.query_layer}))


if __name__ == "__main__":
    main()
