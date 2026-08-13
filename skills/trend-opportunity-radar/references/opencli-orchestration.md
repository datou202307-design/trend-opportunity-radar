# OpenCLI Xiaohongshu orchestration

Use OpenCLI only for user-authorized, read-only Xiaohongshu controlled capture. This Skill version does not validate OpenCLI for X.

## Preflight and route

Run `check_collection_adapter.py --adapter opencli` without installing anything. A ready result requires the CLI, Chrome extension bridge, and an authorized Xiaohongshu session. Run `select_collection_adapter.py` with every available status. Xiaohongshu prefers OpenCLI and falls back to DokoBot; other platforms ignore OpenCLI unless a later Skill version adds explicit capability evidence.

## Search capture

Initialize and advance `orchestrate_collection.py`. Execute each `start_query` through `run_collection_capture.py`, then record its metadata and extraction with `record-capture`. Preserve the content ID, visible engagement, author, publication time, and original signed detail URL containing `xsec_token`. Do not replace that URL with the canonical URL before detail retrieval.

OpenCLI's bounded result limit is not proof that the platform is exhausted. Let the sampling contract decide whether the observed count is sufficient. If the layer remains deficient, use the remaining query budget for a non-duplicate recovery query rather than repeating an identical search.

## Detail backfill

When the orchestrator returns `backfill_details`, run `run_opencli_detail_backfill.py`. It processes eligible signed URLs sequentially, preserves each raw response, retries one all-zero anomaly once, merges complete detail fields into `raw-signals.json`, and stops on access controls. A detail counts only when title, author, body, and visible engagement parse successfully.

Use DokoBot only to verify a missing field, content mismatch, QR/login state, abnormal redirect, or recommendation-feed pollution. Never switch adapters to evade a captcha, rate limit, or other platform restriction.

## Portability

Treat OpenCLI as optional. Another Agent may use this Skill without it by selecting DokoBot, importing an authorized export, or using public-web discovery with the corresponding evidence limits. Never package browser sessions, tokens, credentials, private records, or installation side effects in the Skill.
