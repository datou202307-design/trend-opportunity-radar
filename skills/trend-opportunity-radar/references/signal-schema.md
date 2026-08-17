# Signal schema

Use one platform per snapshot. Read [sampling-contract.md](sampling-contract.md) for the required `collection` ledger.

```json
{
  "schema_version": "trend-signal-snapshot-v0.4",
  "platform": "x",
  "raw_sample_count": 60,
  "retained_sample_count": 35,
  "unique_sample_count": 32,
  "collection": {},
  "signals": [
    {
      "signal_id": "signal-...",
      "platform": "x",
      "source_mode": "controlled_capture",
      "source_type": "direct_post|exported_item|search_card|platform_summary|profile|webpage|search_snippet|historical_item|unknown",
      "evidence_role": "support|counter|neutral",
      "detail_captured": true,
      "content_id": "...",
      "canonical_url": "https://...",
      "query_term": "...",
      "query_layer": "platform_baseline|category|subject_bridge",
      "query_terms": ["all queries that found this signal"],
      "query_layers": ["all layers that found this signal"],
      "semantic_relevance": "direct|adjacent|weak|unreviewed",
      "topic_key": "stable-topic-key",
      "title": "...",
      "summary": "...",
      "published_at": "ISO-8601 or empty",
      "captured_at": "ISO-8601",
      "metrics_captured_at": "ISO-8601",
      "metrics": {
        "views": null,
        "likes": null,
        "saves": null,
        "comments": null,
        "shares": null
      },
      "author": {
        "id": "",
        "name": "public display name when a stable id is unavailable",
        "type": "",
        "follower_count": null,
        "verified": null
      },
      "discovery": {
        "search_rank": null,
        "search_result_count": null,
        "observed_content_count": null
      },
      "time_series": {
        "growth_rate_percent": null,
        "current_window_count": null,
        "previous_window_count": null,
        "comparison_count": null
      },
      "platform_facts": {
        "representative_comments": [
          {
            "author_name": "public display name or empty",
            "text": "bounded public comment text",
            "likes": null,
            "reply_count": null,
            "observed_time_label": "platform label or empty"
          }
        ],
        "representative_comment_count": 0,
        "comment_sample_limit": 10,
        "comment_capture_status": "complete|unavailable",
        "comment_analysis": {
          "status": "reviewed",
          "review_version": "comment-evidence-review-v0.1",
          "reviewed_count": 5,
          "relevant_count": 3,
          "support_count": 2,
          "counter_count": 1,
          "category_counts": {"pain": 1, "question": 1, "objection": 1},
          "insights": ["short fact-bound user feedback insight"],
          "comment_keys": ["comment-..."]
        }
      },
      "evidence_refs": ["https://..."],
      "limitations": [],
      "permission_scope": "public|user_authorized|exported|unspecified",
      "dedupe_hash": "sha256"
    }
  ]
}
```

`raw_sample_count` means every observed result card, not only selected evidence. `retained_sample_count` is the number selected before deduplication. Use `null` for unavailable metrics; zero means the platform explicitly displayed zero. Preserve source-specific raw exports separately when available.

Representative comments are a bounded qualitative sample attached to a selected detail. They do not increase `raw_sample_count`, do not populate the content's total comment metric, and must preserve capture provenance. X keeps at most 5 replies from the already-opened thread; Xiaohongshu performs a separately throttled read of at most 5 top-level comments; YouTube keeps at most 10 comments. Missing comments remain unavailable and never invalidate an otherwise usable detail unless the read encounters a platform-wide safety stop.

When comments exist, [comment-evidence-contract.md](comment-evidence-contract.md) governs their complete review and merge. `comment_analysis` summarizes only reviewed visible text, preserves the original comment sample, and may inform a topic's qualitative decision reasoning without changing sample counts or observed heat.

For `controlled_capture`, a post visible only in search results is `search_card` with `detail_captured: false`. Do not manually force it to `direct_post`; normalization will downgrade that combination.

Stable deduplication prefers `platform + content_id`, then canonical URL, then an author/text/time fallback. Duplicate observations are merged: the richer direct/detail variant becomes primary while query terms, query layers, evidence references, limitations, and source variants are preserved.
