# Comment evidence contract

Version: `comment-evidence-review-v0.2`

Representative comments are qualitative context attached to an opened platform detail. They never increase trend sample volume or replace the platform's total comment metric. Repeated reviewed comments may form a separate comment-derived demand topic under the deterministic recurrence gate below.

## Candidate prominence and diversity rule

Use `comment-prominence-v0.1-candidate` to rank visible comments within the same opened detail. Calculate `log1p(likes) + 1.5 × log1p(reply_count)`, then normalize the largest measured value in that detail to 100. Missing metrics remain unmeasured. The 1.5 reply multiplier is a candidate discussion-depth preference, not a validated causal or credibility weight; never compare the resulting score across posts or platforms.

Prominence changes which reviewed insights are surfaced, not whether a statement is true. Select the highest-prominence relevant comment for each available `support`, `counter`, and `neutral` role first, then add distinct categories and fill remaining slots by prominence. A specific low-engagement need, workaround, objection, or counterexample may therefore remain visible. Never let likes or replies upgrade semantic relevance, evidence direction, identity confidence, purchase intent, or source quality.

After normalization, run `prepare_comment_review.py`. Review every queued comment and create UTF-8 JSON with:

```json
{
  "schema_version": "comment-evidence-review-v0.2",
  "queue_sha256": "copied from comment-review-queue.json",
  "reviews": [
    {
      "comment_key": "comment-...",
      "category": "need|pain|question|workaround|purchase_intent|objection|positive_outcome|comparison|other|irrelevant",
      "semantic_relevance": "direct|adjacent|weak",
      "evidence_role": "support|counter|neutral",
      "demand_topic_key": "stable-key-for-materially-same-need",
      "insight": "short fact-bound description of what this comment reveals",
      "reason": "why the label follows from the visible comment text"
    }
  ]
}
```

Classify the visible text only. Do not infer identity, demographics, purchase, sentiment, or product usage that the commenter did not state. Use `irrelevant` and `weak` for spam, tagging-only replies, keyword collisions, or context-free reactions. Keep `insight` empty for weak or irrelevant comments; use plain reader-facing language for direct and adjacent comments. Give materially equivalent direct or adjacent comments the same stable `demand_topic_key`; do not merge different jobs, pains, objections, or outcomes merely because they mention the same product category.

## Demand recurrence and attitude salience

`apply_comment_review.py` derives snapshot-level `comment_demand_topics` deterministically:

- `eligible_comment_demand`: the same topic appears in at least two independent parent posts and comes from at least two independent commenters.
- `cross_post_recurrence_unverified_commenters`: the same topic appears in at least two parent posts and two separate comment records, but commenter identity was not captured well enough to prove independence. Keep it visible as a validation candidate, not a qualified demand conclusion.
- `salient_single_thread`: the topic is limited to one parent post but contains a high-prominence relevant comment. This is a visible attitude or validation hypothesis, not broad demand.
- `observation`: the topic does not pass either display threshold and remains in the audit record.

Query-layer diversity, categories, evidence roles, source links, examples, and high-prominence counts are retained for interpretation. Never average or compare prominence scores across parent posts. Recurrence qualifies demand; likes and replies only prioritize visible attitudes within a thread. A repeated counterexample or workaround can qualify as a recurring topic and must not be erased by more popular support comments.

Run `apply_comment_review.py` with the unchanged queue and snapshot. It requires exactly one review for every queued comment, preserves the raw comments, adds per-signal `platform_facts.comment_analysis`, and adds snapshot-level `comment_evidence` and `comment_demand_topics`. Relevant comment evidence may refine a user task, objection, workaround, or next validation action, but must not change the source signal's polarity automatically. Legacy `comment-evidence-review-v0.1` files remain replayable and do not create comment-derived demand topics because they lack stable topic keys.
