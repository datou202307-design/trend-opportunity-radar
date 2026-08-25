from __future__ import annotations

from collections import Counter
from typing import Any

from _common import as_text


VERSION = "comment-demand-topics-v0.1-candidate"
QUALIFYING_CATEGORIES = {"need", "pain", "question", "workaround", "purchase_intent", "objection", "positive_outcome", "comparison"}


def _layers(row: dict[str, Any]) -> set[str]:
    values = row.get("query_layers")
    if not isinstance(values, list):
        values = [row.get("query_layer")]
    return {as_text(value) for value in values if as_text(value)}


def _reader_examples(rows: list[dict[str, Any]], limit: int = 3) -> list[str]:
    ordered = sorted(
        rows,
        key=lambda row: (
            (row.get("prominence") or {}).get("tier") == "high",
            bool(as_text(row.get("insight"))),
            as_text(row.get("comment_key")),
        ),
        reverse=True,
    )
    return list(dict.fromkeys(as_text(row.get("insight")) for row in ordered if as_text(row.get("insight"))))[:limit]


def derive(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = as_text(row.get("demand_topic_key")).lower()
        if (
            key
            and row.get("semantic_relevance") in {"direct", "adjacent"}
            and row.get("category") in QUALIFYING_CATEGORIES
        ):
            grouped.setdefault(key, []).append(row)

    topics: list[dict[str, Any]] = []
    for key, topic_rows in sorted(grouped.items()):
        parent_keys = {as_text(row.get("signal_key")) for row in topic_rows if as_text(row.get("signal_key"))}
        commenter_keys = {as_text(row.get("commenter_key")) for row in topic_rows if as_text(row.get("commenter_key"))}
        comment_instance_keys = {as_text(row.get("comment_instance_key") or row.get("comment_key")) for row in topic_rows if as_text(row.get("comment_instance_key") or row.get("comment_key"))}
        layers: set[str] = set()
        for row in topic_rows:
            layers.update(_layers(row))
        high_rows = [row for row in topic_rows if (row.get("prominence") or {}).get("tier") == "high"]
        eligible = len(parent_keys) >= 2 and len(commenter_keys) >= 2
        cross_post_unverified = len(parent_keys) >= 2 and len(comment_instance_keys) >= 2 and not eligible
        status = "eligible_comment_demand" if eligible else ("cross_post_recurrence_unverified_commenters" if cross_post_unverified else ("salient_single_thread" if len(parent_keys) == 1 and high_rows else "observation"))
        topics.append({
            "topic_key": key,
            "status": status,
            "relevant_comment_count": len(topic_rows),
            "independent_parent_count": len(parent_keys),
            "independent_commenter_count": len(commenter_keys),
            "independent_comment_record_count": len(comment_instance_keys),
            "commenter_identity_available": bool(commenter_keys),
            "query_layers": sorted(layers),
            "evidence_role_counts": dict(sorted(Counter(as_text(row.get("evidence_role")) for row in topic_rows).items())),
            "category_counts": dict(sorted(Counter(as_text(row.get("category")) for row in topic_rows).items())),
            "high_prominence_comment_count": len(high_rows),
            "examples": _reader_examples(topic_rows),
            "source_refs": list(dict.fromkeys(as_text(row.get("source_url")) for row in topic_rows if as_text(row.get("source_url")))),
            "qualification": {
                "requires_independent_parents": 2,
                "requires_independent_commenters": 2,
                "passed": eligible,
                "rule": "Cross-parent recurrence qualifies demand; within-thread engagement only indicates attitude salience.",
            },
        })
    rank = {"eligible_comment_demand": 0, "cross_post_recurrence_unverified_commenters": 1, "salient_single_thread": 2, "observation": 3}
    return sorted(topics, key=lambda item: (rank[item["status"]], -item["independent_parent_count"], -item["relevant_comment_count"], item["topic_key"]))
