from __future__ import annotations

import math
from typing import Any

from _common import as_number, as_text


VERSION = "comment-prominence-v0.1-candidate"
LIKE_WEIGHT = 1.0
REPLY_WEIGHT = 1.5


def annotate_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score visible comments within one opened detail; never treat prominence as truth."""
    prepared: list[tuple[dict[str, Any], float, bool]] = []
    for comment in comments:
        likes = as_number(comment.get("likes"))
        replies = as_number(comment.get("reply_count"))
        measured = likes is not None or replies is not None
        raw = LIKE_WEIGHT * math.log1p(likes or 0.0) + REPLY_WEIGHT * math.log1p(replies or 0.0)
        prepared.append((comment, raw, measured))
    maximum = max((raw for _, raw, _ in prepared), default=0.0)
    result: list[dict[str, Any]] = []
    for comment, raw, measured in prepared:
        score = round(100 * raw / maximum) if measured and maximum > 0 else 0
        tier = "unmeasured" if not measured else "high" if score >= 67 else "medium" if score >= 34 else "low"
        result.append({
            **comment,
            "prominence": {
                "version": VERSION,
                "score": score,
                "tier": tier,
                "measured": measured,
                "like_weight": LIKE_WEIGHT,
                "reply_weight": REPLY_WEIGHT,
                "scope": "within_opened_detail",
                "meaning": "platform_visibility_not_credibility",
            },
        })
    return result


def select_diverse_insights(
    rows: list[dict[str, Any]],
    limit: int = 5,
    *,
    compare_prominence: bool = True,
) -> list[dict[str, Any]]:
    relevant = [
        row for row in rows
        if row.get("semantic_relevance") in {"direct", "adjacent"} and as_text(row.get("insight"))
    ]
    ranked = (
        sorted(
            relevant,
            key=lambda row: (
                -int((row.get("prominence") or {}).get("score") or 0),
                0 if row.get("semantic_relevance") == "direct" else 1,
                as_text(row.get("comment_key")),
            ),
        )
        if compare_prominence else relevant
    )
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()

    def add(row: dict[str, Any]) -> None:
        key = as_text(row.get("comment_key")) or as_text(row.get("insight"))
        if key and key not in selected_keys and len(selected) < limit:
            selected.append(row)
            selected_keys.add(key)

    for role in ("support", "counter", "neutral"):
        candidate = next((row for row in ranked if row.get("evidence_role") == role), None)
        if candidate:
            add(candidate)
    represented_categories = {as_text(row.get("category")) for row in selected}
    for row in ranked:
        category = as_text(row.get("category"))
        if category and category not in represented_categories:
            add(row)
            represented_categories.add(category)
    for row in ranked:
        add(row)
    return selected
