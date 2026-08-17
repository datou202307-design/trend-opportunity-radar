# OpenCLI X, Xiaohongshu, and YouTube orchestration

Use OpenCLI only for user-authorized, read-only X, Xiaohongshu, or YouTube controlled capture. Capability is proven per platform and must never be inferred from CLI visibility alone. YouTube is a validated supported adapter after passing fixed-query repeatability, sort complementarity, standard unique-volume, detail-merge, bounded-comment, missing-transcript, zero-result, safety-stop, and real-report acceptance. Re-probe the target platform on every run because support never guarantees that the current browser bridge, session, or page surface is ready.

## Preflight and route

Run `check_collection_adapter.py --adapter opencli` without installing anything. A ready platform capability requires the CLI and Chrome extension bridge; a platform session is required when the target surface demands it. Run `select_collection_adapter.py` with every available status. X and Xiaohongshu prefer OpenCLI and fall back to DokoBot. YouTube selects OpenCLI only after its own probe succeeds; support for X or Xiaohongshu never implies YouTube support.

## Search capture

Initialize and advance `orchestrate_collection.py`. Execute each `start_query` through `run_collection_capture.py`, then record its metadata and extraction with `record-capture`. Preserve the content ID, visible engagement, author, publication time, and original signed detail URL containing `xsec_token`. Do not replace that URL with the canonical URL before detail retrieval.

OpenCLI's bounded result limit is not proof that the platform is exhausted. Let the sampling contract decide whether the observed count is sufficient. On X, preserve the query plan's `f=live` choice as Latest and otherwise use Top; these products are complementary evidence views, not interchangeable rankings. If the layer remains deficient, use the remaining query budget for a non-duplicate recovery query rather than repeating an identical search.

On YouTube, preserve title, channel, view count, duration, publication label, result rank, URL, and the exact raw artifact. Treat localized relative labels such as “5 days ago” as display facts, not exact timestamps; only a successful video-detail read may populate `published_at`. Use different sort or upload-date views only when the frozen query plan requests them and keep the chosen view in the query audit.

## Detail backfill

When the orchestrator returns `backfill_details`, run `run_opencli_detail_backfill.py`. It processes eligible signed URLs sequentially, preserves each raw response, retries one all-zero anomaly once, merges complete detail fields into `raw-signals.json`, and stops on access controls. A detail counts only when title, author, body, and visible engagement parse successfully.

For X detail backfill, select the row matching the requested status id and merge the complete text, author, and available engagement fields into the search signal. Keep at most five non-target thread rows as representative replies without counting them as trend samples. Thread output can omit views; never replace an existing search metric with a missing detail metric. Use DokoBot only to verify a missing field, content mismatch, QR/login state, abnormal redirect, or recommendation-feed pollution. Never switch adapters to evade a captcha, rate limit, or other platform restriction.

For Xiaohongshu detail backfill, follow each successful detail with one separately throttled read of at most five top-level comments. Apply the same deterministic detail cadence to that request, preserve its raw output and execution metadata, and stop on a platform-wide safety condition. Comment unavailability does not erase a valid note detail.

For YouTube detail backfill, merge the exact publish timestamp, description, channel ID, subscribers, views, likes, category, duration, and thumbnail when present. Never replace a search metric with a missing detail value. Comments require a separate bounded read and transcripts are read only when needed to verify a video claim; neither is implied by a successful video-detail capture.

## Portability

Treat OpenCLI as optional. Another Agent may use this Skill without it by selecting DokoBot, importing an authorized export, or using public-web discovery with the corresponding evidence limits. Never package browser sessions, tokens, credentials, private records, or installation side effects in the Skill.
