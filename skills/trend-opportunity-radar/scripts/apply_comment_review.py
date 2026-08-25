from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

from _common import as_text, load_data, now_iso, write_json
from comment_prominence import VERSION as PROMINENCE_VERSION, select_diverse_insights
from derive_comment_demand_topics import VERSION as DEMAND_TOPICS_VERSION, derive as derive_comment_demand_topics
from prepare_comment_review import SCHEMA_VERSION as QUEUE_SCHEMA_VERSION


SCHEMA_VERSION = "comment-evidence-review-v0.2"
LEGACY_SCHEMA_VERSION = "comment-evidence-review-v0.1"
CATEGORIES = {
    "need", "pain", "question", "workaround", "purchase_intent",
    "objection", "positive_outcome", "comparison", "other", "irrelevant",
}
RELEVANCE = {"direct", "adjacent", "weak"}
ROLES = {"support", "counter", "neutral"}


def require_review(queue: dict[str, Any], review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if queue.get("schema_version") != QUEUE_SCHEMA_VERSION:
        raise SystemExit(f"Comment queue must use {QUEUE_SCHEMA_VERSION}.")
    review_version = review.get("schema_version")
    if review_version not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        raise SystemExit(f"Comment review must use {SCHEMA_VERSION} or legacy {LEGACY_SCHEMA_VERSION}.")
    if review.get("queue_sha256") != queue.get("queue_sha256"):
        raise SystemExit("Comment review queue_sha256 does not match the unchanged queue.")
    expected = {as_text(item.get("comment_key")) for item in queue.get("comments", []) if isinstance(item, dict)}
    rows = review.get("reviews")
    if not isinstance(rows, list):
        raise SystemExit("Comment review reviews must be an array.")
    indexed: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"reviews[{index}] must be an object.")
            continue
        key = as_text(row.get("comment_key"))
        if not key or key in indexed:
            errors.append(f"reviews[{index}].comment_key must be non-empty and unique.")
            continue
        if row.get("category") not in CATEGORIES:
            errors.append(f"reviews[{index}].category is invalid.")
        if row.get("semantic_relevance") not in RELEVANCE:
            errors.append(f"reviews[{index}].semantic_relevance is invalid.")
        if row.get("evidence_role") not in ROLES:
            errors.append(f"reviews[{index}].evidence_role is invalid.")
        if not as_text(row.get("reason")):
            errors.append(f"reviews[{index}].reason is required.")
        if row.get("semantic_relevance") in {"direct", "adjacent"} and not as_text(row.get("insight")):
            errors.append(f"reviews[{index}].insight is required for relevant comments.")
        if review_version == SCHEMA_VERSION and row.get("semantic_relevance") in {"direct", "adjacent"} and row.get("category") in CATEGORIES - {"other", "irrelevant"} and not as_text(row.get("demand_topic_key")):
            errors.append(f"reviews[{index}].demand_topic_key is required for relevant classified comments.")
        indexed[key] = row
    missing, extra = expected - set(indexed), set(indexed) - expected
    if missing:
        errors.append(f"Missing reviews for {len(missing)} queued comments.")
    if extra:
        errors.append(f"Review contains {len(extra)} unknown comment keys.")
    if errors:
        raise SystemExit("Comment review validation failed:\n- " + "\n- ".join(errors))
    return indexed


def summary(rows: list[dict[str, Any]], *, compare_prominence: bool = True, review_version: str = SCHEMA_VERSION) -> dict[str, Any]:
    relevant = [row for row in rows if row["semantic_relevance"] in {"direct", "adjacent"}]
    selected = select_diverse_insights(rows, compare_prominence=compare_prominence)
    insights = list(dict.fromkeys(as_text(row.get("insight")) for row in selected if as_text(row.get("insight"))))
    measured = [row for row in rows if (row.get("prominence") or {}).get("measured") is True]
    return {
        "status": "reviewed",
        "review_version": review_version,
        "reviewed_count": len(rows),
        "relevant_count": len(relevant),
        "support_count": sum(1 for row in relevant if row["evidence_role"] == "support"),
        "counter_count": sum(1 for row in relevant if row["evidence_role"] == "counter"),
        "category_counts": dict(sorted(Counter(row["category"] for row in relevant).items())),
        "insights": insights[:5],
        "prominence_version": PROMINENCE_VERSION,
        "prominence_coverage_count": len(measured),
        "high_prominence_relevant_count": sum(
            1 for row in relevant if (row.get("prominence") or {}).get("tier") == "high"
        ),
        "insight_selection": [
            {
                "comment_key": row.get("comment_key"),
                "category": row.get("category"),
                "evidence_role": row.get("evidence_role"),
                "semantic_relevance": row.get("semantic_relevance"),
                "prominence_score": int((row.get("prominence") or {}).get("score") or 0),
                "prominence_tier": (row.get("prominence") or {}).get("tier") or "unmeasured",
                "insight": row.get("insight"),
            }
            for row in selected
        ],
    }


def apply(snapshot: dict[str, Any], queue: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    indexed = require_review(queue, review)
    review_version = as_text(review.get("schema_version"))
    queued_by_signal: dict[str, list[dict[str, Any]]] = {}
    for item in queue.get("comments", []):
        queued_by_signal.setdefault(as_text(item.get("signal_key")), []).append(item)

    all_reviews: list[dict[str, Any]] = []
    source_refs: list[str] = []
    reviewed_signal_count = 0
    for signal in snapshot.get("signals", []):
        signal_key = as_text(signal.get("signal_id") or signal.get("dedupe_hash"))
        queued = queued_by_signal.get(signal_key, [])
        if not queued:
            continue
        rows = [{
            **indexed[item["comment_key"]],
            "prominence": item.get("prominence"),
            "signal_key": signal_key,
            "source_url": as_text(signal.get("canonical_url")),
            "commenter_key": item.get("commenter_key") or "",
            "commenter_key_basis": item.get("commenter_key_basis") or "unavailable",
            "comment_instance_key": item.get("comment_instance_key") or item["comment_key"],
            "query_layers": item.get("query_layers") or [],
        } for item in queued]
        analysis = summary(rows, review_version=review_version)
        analysis["comment_keys"] = [item["comment_key"] for item in queued]
        analysis["reviewed_comments"] = rows
        facts = signal.setdefault("platform_facts", {})
        facts["comment_analysis"] = analysis
        reviewed_signal_count += 1
        all_reviews.extend(rows)
        if as_text(signal.get("canonical_url")):
            source_refs.append(as_text(signal["canonical_url"]))

    aggregate = summary(all_reviews, compare_prominence=False, review_version=review_version)
    aggregate.update({
        "reviewed_signal_count": reviewed_signal_count,
        "captured_comment_count": len(queue.get("comments", [])),
        "source_refs": list(dict.fromkeys(source_refs)),
        "applied_at": now_iso(),
    })
    snapshot["comment_evidence"] = aggregate
    snapshot["comment_demand_topics_version"] = DEMAND_TOPICS_VERSION
    snapshot["comment_demand_topics"] = derive_comment_demand_topics(all_reviews)
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and merge reviewed comment evidence into a signal snapshot.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot, queue, review = load_data(args.input), load_data(args.queue), load_data(args.review)
    if not all(isinstance(item, dict) for item in (snapshot, queue, review)):
        raise SystemExit("Comment review inputs must be JSON objects.")
    write_json(args.output, apply(snapshot, queue, review))


if __name__ == "__main__":
    main()
