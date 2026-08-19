# Instagram Hashtag Topic Adapter (pilot)

This adapter supports bounded `topic_research` only through an explicit hashtag surface in a user-authorized logged-in browser. It does not turn Instagram account search, personalized Explore, or the generic Reels feed into topic evidence.

## Contract

1. Translate the research subject into explicit candidate hashtags, then freeze one request per hashtag and assign it to `platform_baseline`, `category`, or `subject_bridge`.
2. Confirm that Instagram displays the exact hashtag identity before reading results.
3. Retain at most 24 unique canonical `/p/` or `/reel/` links from the ranked hashtag result surface.
4. When practical, repeat the same frozen hashtag once and store overlap as a repeatability diagnostic. Ranking is personalized and is not an exhaustive or chronological corpus.
5. Open at most 6 retained posts, sequentially, and keep caption, author, publication time, visible engagement fields, and at most 5 visible top-level comments.
6. Record the platform-displayed hashtag post-count label only as a supply-volume hint. It is not observed sample count, search demand, reach, or future performance.
7. Send retained details through semantic and evidence review before they affect a decision card. A hashtag match alone does not prove topical relevance.

Use `scripts/run_instagram_topic_capture.py plan` before browser work and `record` after a redacted structured capture is available. Use `scripts/check_instagram_topic_adapter.py` for a capability probe. Do not package cookies, credentials, browser profiles, raw private data, or real test captures.

When access constraints leave a useful but incomplete snapshot, create a fact-bound analysis and use `scripts/generate_instagram_topic_report.py` to produce JSON, Markdown, and HTML. The visible report must lead with what the current evidence can support, what it cannot support, and the concrete continuation path. Do not show browser retries or internal gate names to the reader.

Before reporting, write an Agent semantic-review file and run `scripts/apply_instagram_topic_review.py`; do not edit the recorded snapshot in place. Unopened hashtag links may remain unreviewed and auditable, but only reviewed details may support a visible finding.

Stop safely on CAPTCHA, rate limiting, expired login, permission prompts, abnormal redirect, or target mismatch. A timeout or unavailable detail ends the bounded attempt without inventing evidence; previously verified results remain auditable but cannot become a completed snapshot without at least one verified detail.
