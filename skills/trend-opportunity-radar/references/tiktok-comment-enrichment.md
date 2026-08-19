# TikTok visible-comment enrichment

Use this optional path only after a TikTok detail read has verified the exact content ID and author route but returned no comment bodies.

1. Freeze one eligible target:

```bash
python scripts/run_tiktok_comment_enrichment.py plan --snapshot raw-signals.json --output tiktok-comment-request.json
```

Add `--signal-key SIGNAL_ID` when a specific verified support or counterevidence item should receive the bounded comment read. Without it, the planner deterministically selects the first eligible detail.

2. Use a user-authorized, already logged-in Chrome control surface to open or claim the request's exact `canonical_url`. Recheck `content_id` and `author_handle`, expand the target Comments entry once, and read no more than five visible top-level comments. Do not type, like, reply, post, follow, scroll recommended content, or export browser state.

3. Save the browser result as `tiktok-comment-capture.json` with:

- `schema_version`: `tiktok-visible-comment-browser-capture-v0.1`
- the unchanged `request_sha256`, `canonical_url`, `content_id`, and `author_handle`
- integer `visible_comment_entry_count`
- `comments`: at most five objects with `author_name`, `text`, `top_level_visible: true`, and optional visible likes/time label
- all six required checks from the frozen request set to `true`
- an empty `stop_reason`

If the panel is unavailable, save no comments and use `timeout` or `comments_unavailable`. For captcha, rate limit, login expiry, permission prompt, abnormal redirect, or target mismatch, use the matching hard-stop value and stop browser work.

4. Validate and merge atomically:

```bash
python scripts/run_tiktok_comment_enrichment.py record --snapshot raw-signals.json --request tiktok-comment-request.json --capture tiktok-comment-capture.json --output comment-enriched-signals.json --receipt tiktok-comment-receipt.json
```

The recorder binds the capture to the frozen request, rejects identity drift, duplicate or excess comments, preserves the raw capture hash, and leaves the snapshot unchanged when enrichment is unavailable or blocked. Comments remain qualitative context and never increase trend sample volume.
