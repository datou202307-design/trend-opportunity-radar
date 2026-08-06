# Signal schema

Use one platform per snapshot.

```json
{
  "schema_version": "trend-signal-snapshot-v0.1",
  "platform": "x",
  "raw_sample_count": 1,
  "unique_sample_count": 1,
  "signals": [
    {
      "signal_id": "signal-...",
      "platform": "x",
      "source_mode": "controlled_capture",
      "content_id": "...",
      "canonical_url": "https://...",
      "query_term": "...",
      "query_layer": "platform_baseline|category|subject_bridge",
      "topic_key": "optional-stable-topic-key",
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
      "evidence_refs": ["https://..."],
      "limitations": [],
      "permission_scope": "public|user_authorized|exported|unspecified",
      "dedupe_hash": "sha256"
    }
  ]
}
```

Do not use zero for unavailable metrics; use `null`. Zero means the platform explicitly reported zero. Preserve source-specific raw data separately when available.

