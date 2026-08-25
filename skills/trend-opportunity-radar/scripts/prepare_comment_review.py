from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from _common import as_text, load_data, now_iso, write_json
from comment_prominence import VERSION as PROMINENCE_VERSION, annotate_comments


SCHEMA_VERSION = "comment-review-queue-v0.1"


def commenter_key(comment: dict[str, Any]) -> tuple[str, str]:
    for field in ("author_id", "author_handle", "username", "author_name"):
        value = as_text(comment.get(field))
        if value:
            return f"{field}:{value.lower()}", field
    return "", "unavailable"


def comment_key(signal_key: str, index: int, text: str) -> str:
    value = f"{signal_key}\n{index}\n{text}".encode("utf-8")
    return "comment-" + hashlib.sha256(value).hexdigest()[:20]


def build_queue(snapshot: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for signal in snapshot.get("signals", []):
        if not isinstance(signal, dict):
            continue
        signal_key = as_text(signal.get("signal_id") or signal.get("dedupe_hash"))
        facts = signal.get("platform_facts") if isinstance(signal.get("platform_facts"), dict) else {}
        comments = facts.get("representative_comments") if isinstance(facts.get("representative_comments"), list) else []
        comments = annotate_comments([comment for comment in comments if isinstance(comment, dict)])
        for index, comment in enumerate(comments):
            if not isinstance(comment, dict) or not as_text(comment.get("text")):
                continue
            text = as_text(comment["text"])
            generated_key = comment_key(signal_key, index, text)
            author_key, author_basis = commenter_key(comment)
            query_layers = signal.get("query_layers") if isinstance(signal.get("query_layers"), list) else []
            if as_text(signal.get("query_layer")) and as_text(signal.get("query_layer")) not in query_layers:
                query_layers = [*query_layers, as_text(signal.get("query_layer"))]
            entries.append({
                "comment_key": generated_key,
                "signal_key": signal_key,
                "topic_key": as_text(signal.get("topic_key")),
                "source_url": as_text(signal.get("canonical_url")),
                "comment_index": index,
                "text": text,
                "likes": comment.get("likes"),
                "reply_count": comment.get("reply_count"),
                "observed_time_label": as_text(comment.get("observed_time_label")),
                "prominence": comment.get("prominence"),
                "commenter_key": author_key,
                "commenter_key_basis": author_basis,
                "comment_instance_key": generated_key,
                "query_layers": query_layers,
            })
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "platform": as_text(snapshot.get("platform")),
        "prominence_version": PROMINENCE_VERSION,
        "comment_count": len(entries),
        "queue_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "comments": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a bounded representative-comment review queue.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = load_data(args.input)
    if not isinstance(snapshot, dict):
        raise SystemExit("Comment review input must be a signal snapshot object.")
    write_json(args.output, build_queue(snapshot))


if __name__ == "__main__":
    main()
