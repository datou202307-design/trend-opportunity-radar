# Instagram Hashtag Topic Adapter

This adapter supports bounded `topic_research` only through an explicit hashtag surface in a user-authorized logged-in browser. It does not turn Instagram account search, personalized Explore, or the generic Reels feed into topic evidence.

## Contract

1. Translate the research subject into explicit candidate hashtags, then freeze one request per hashtag and assign it to `platform_baseline`, `category`, or `subject_bridge`.
2. Confirm that Instagram displays the exact hashtag identity before reading results.
3. Confirm that the browser remains on the frozen query URL and exposes canonical `/p/` or `/reel/` links. A loaded page shell with zero parsed links is not a platform result.
3. Retain at most 24 unique canonical `/p/` or `/reel/` links from the ranked hashtag result surface.
4. When practical, repeat the same frozen hashtag once and store overlap as a repeatability diagnostic. Ranking is personalized and is not an exhaustive or chronological corpus.
5. Open at most 6 retained posts, sequentially, and keep caption, author, publication time, visible engagement fields, and at most 5 visible top-level comments.
6. Record the platform-displayed hashtag post-count label only as a supply-volume hint. It is not observed sample count, search demand, reach, or future performance.
7. Send retained details through semantic and evidence review before they affect a decision card. A hashtag match alone does not prove topical relevance.

Use `scripts/run_instagram_topic_capture.py plan` before browser work. When a logged-in Chrome session and OpenCLI browser control are available, `scripts/run_instagram_opencli_capture.py` performs two paced result reads in dedicated pass sessions, validates the target surface after each navigation, preserves a successful pass when its companion pass fails, unions links observed across bounded scrolls, and opens details sequentially. Keep formal collection at the runner's bounded default scroll depth; `--scrolls 0` is only a shallow diagnostic and cannot satisfy the formal sampling contract. Then use `scripts/run_instagram_topic_capture.py record` to validate and normalize the redacted capture. Use `scripts/check_instagram_topic_adapter.py` for a capability probe. Do not package cookies, credentials, browser profiles, raw private data, or real test captures.

Two zero-link passes may be recorded as `verified_zero_results` only when both page probes match the frozen URL, display the exact hashtag identity, and expose an explicit Instagram empty-state message. Otherwise record `surface_unreadable` and let the orchestrator retry or use another already validated read path. Controller errors must be attributed to the controller actually executed: an OpenCLI failure does not prove that the Browser plugin is missing, and Browser/Chrome repair must not be requested unless that route was selected and its own connection preflight failed.

For a standard study, run at least one frozen hashtag in each of `platform_baseline`, `category`, and `subject_bridge`, with 24 observed links and 6 opened details per query when the visible surface permits it. Merge the three independently recorded snapshots through `scripts/merge_instagram_topic_snapshots.py`. The merged snapshot must still pass the global and per-layer rules in `sampling-contract.md`; totals never excuse a weak layer.

When access constraints leave a useful but incomplete snapshot, create a fact-bound analysis and use `scripts/generate_instagram_topic_report.py` to produce JSON, Markdown, and HTML. The visible report must lead with what the current evidence can support, what it cannot support, and the concrete continuation path. Do not show browser retries or internal gate names to the reader.

Before reporting, write an Agent semantic-review file and run `scripts/apply_instagram_topic_review.py`; do not edit the recorded snapshot in place. If visible comments were retained, run `prepare_comment_review.py` and `apply_comment_review.py` before using them in findings. Unopened hashtag links may remain auditable, but only cards with visible preview text or opened details enter the merged review set, and only reviewed evidence may support a visible finding.

Stop safely on CAPTCHA, rate limiting, expired login, permission prompts, abnormal redirect, or target mismatch. A timeout or unavailable detail ends the bounded attempt without inventing evidence; previously verified results remain auditable but cannot become a completed snapshot without at least one verified detail.
