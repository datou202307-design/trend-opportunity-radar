# Comment evidence contract

Version: `comment-evidence-review-v0.1`

Representative comments are qualitative context attached to an opened platform detail. They never increase trend sample volume, replace the platform's total comment metric, or independently prove demand.

After normalization, run `prepare_comment_review.py`. Review every queued comment and create UTF-8 JSON with:

```json
{
  "schema_version": "comment-evidence-review-v0.1",
  "queue_sha256": "copied from comment-review-queue.json",
  "reviews": [
    {
      "comment_key": "comment-...",
      "category": "need|pain|question|workaround|purchase_intent|objection|positive_outcome|comparison|other|irrelevant",
      "semantic_relevance": "direct|adjacent|weak",
      "evidence_role": "support|counter|neutral",
      "insight": "short fact-bound description of what this comment reveals",
      "reason": "why the label follows from the visible comment text"
    }
  ]
}
```

Classify the visible text only. Do not infer identity, demographics, purchase, sentiment, or product usage that the commenter did not state. Use `irrelevant` and `weak` for spam, tagging-only replies, keyword collisions, or context-free reactions. Keep `insight` empty for weak or irrelevant comments; use plain reader-facing language for direct and adjacent comments.

Run `apply_comment_review.py` with the unchanged queue and snapshot. It requires exactly one review for every queued comment, preserves the raw comments, adds per-signal `platform_facts.comment_analysis`, and adds a snapshot-level `comment_evidence` summary. Relevant comment evidence may refine a user task, objection, workaround, or next validation action, but must not change the source signal's polarity automatically.
