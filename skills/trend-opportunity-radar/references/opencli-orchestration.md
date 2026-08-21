# OpenCLI X, Xiaohongshu, YouTube, and TikTok orchestration

Use OpenCLI only for user-authorized, read-only X, Xiaohongshu, or YouTube controlled capture, plus explicitly enabled TikTok pilot runs. Capability is proven per platform and research scope and must never be inferred from CLI visibility alone. YouTube is a validated supported adapter after passing fixed-query repeatability, sort complementarity, standard unique-volume, detail-merge, bounded-comment, missing-transcript, zero-result, safety-stop, and real-report acceptance. Re-probe the target platform on every run because support never guarantees that the current browser bridge, session, or page surface is ready.

TikTok topic search is an explicit `pilot`, not a validated live platform. Use it only with the adapter selector's pilot opt-in during development. Run the redacted `whoami` check as a diagnostic, then prove capability with one bounded one-result topic-search probe. OpenCLI 1.8.6 can report that owner identity was not rehydrated while controlling a visibly logged-in Chrome page and successfully reading search; do not turn that parser mismatch into a second-login request. Require the separately preflighted DokoBot browser detail path to confirm the authorized logged-in page environment. The search stage preserves video URL/ID, author, description, rank, plays, likes, comments, and shares from bounded results. It does not itself claim publication time, independent detail access, or comment-text access. Never substitute Explore results for frozen topic queries, and never call TikTok write commands.

TikTok pilot search completion must not trigger a fabricated or unsupported OpenCLI detail command. Treat a user-authorized, already logged-in browser session as the required environment for TikTok live topic research; anonymous-browser compatibility is outside the release contract. When a separately preflighted DokoBot browser session is ready, the adapter selector freezes it as `detail_adapter`; the orchestrator then creates a bounded, deduplicated detail plan and `run_dokobot_detail_backfill.py` reads one retained URL at a time. Require the same TikTok content ID and author route in the opened page, record whether it resolves as video or photo, reject recommendation-feed mismatches, and keep visible comments to five. When no detail enhancer is ready, preserve the snapshot and return the bounded `video_evidence` handoff instead of adding searches solely to compensate for missing detail access. Query finalization remains idempotent.

## Preflight and route

Run `check_collection_adapter.py --adapter opencli --platform TARGET_PLATFORM` without installing anything. Probe only the current research platform; do not delay or contaminate one platform's readiness with unrelated platform checks. Omitting `--platform` is retained only for legacy diagnostics, not normal research runs. A ready platform capability requires the CLI and Chrome extension bridge; a platform session is required when the target surface demands it. Run `select_collection_adapter.py` with every available status. X and Xiaohongshu prefer OpenCLI and fall back to DokoBot. YouTube selects OpenCLI only after its own probe succeeds; support for X or Xiaohongshu never implies YouTube support.

## Search capture

Initialize and advance `orchestrate_collection.py`. Execute each `start_query` through `run_collection_capture.py`, then record its metadata and extraction with `record-capture`. Preserve the content ID, visible engagement, author, publication time, and original signed detail URL containing `xsec_token`. Do not replace that URL with the canonical URL before detail retrieval.

Apply [collection-pacing-contract.md](collection-pacing-contract.md) to every live read. The reusable runners serialize requests and preserve the pacing receipt. Never launch multiple capture or detail runners concurrently, and never accelerate a run because the sampling target has not yet been met.

OpenCLI's bounded result limit is not proof that the platform is exhausted. Let the sampling contract decide whether the observed count is sufficient. On X, preserve the query plan's `f=live` choice as Latest and otherwise use Top; these products are complementary evidence views, not interchangeable rankings. If the layer remains deficient, use the remaining query budget for a non-duplicate recovery query rather than repeating an identical search.

On YouTube, preserve title, channel, view count, duration, publication label, result rank, URL, and the exact raw artifact. Treat localized relative labels such as “5 days ago” as display facts, not exact timestamps; only a successful video-detail read may populate `published_at`. Use different sort or upload-date views only when the frozen query plan requests them and keep the chosen view in the query audit.

## Detail backfill

When the orchestrator returns `backfill_details`, run `run_opencli_detail_backfill.py`. It processes eligible signed URLs sequentially, preserves each raw response, retries one all-zero anomaly once, merges complete detail fields into `raw-signals.json`, and stops on access controls. A detail counts only when title, author, body, and visible engagement parse successfully.

For X detail backfill, select the row matching the requested status id and merge the complete text, author, and available engagement fields into the search signal. Keep at most five non-target thread rows as representative replies without counting them as trend samples. Thread output can omit views; never replace an existing search metric with a missing detail metric. Use DokoBot only to verify a missing field, content mismatch, QR/login state, abnormal redirect, or recommendation-feed pollution. Never switch adapters to evade a captcha, rate limit, or other platform restriction.

For Xiaohongshu detail backfill, follow each successful detail with one separately throttled read of at most five top-level comments. Apply the same deterministic detail cadence to that request, preserve its raw output and execution metadata, and stop on a platform-wide safety condition. Comment unavailability does not erase a valid note detail.

For YouTube detail backfill, merge the exact publish timestamp, description, channel ID, subscribers, views, likes, category, duration, and thumbnail when present. Never replace a search metric with a missing detail value. Comments require a separate bounded read and transcripts are read only when needed to verify a video claim; neither is implied by a successful video-detail capture.

## Portability

Treat OpenCLI as optional. Another Agent may use this Skill without it by selecting DokoBot, importing an authorized export, or using public-web discovery with the corresponding evidence limits. Never package browser sessions, tokens, credentials, private records, or installation side effects in the Skill.
