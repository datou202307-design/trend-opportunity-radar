# Video Evidence Contract

Version: `video-evidence-contract-v0.1`

Use this optional contract after discovery and semantic review when a platform item's meaning is materially carried by speech or visuals. It enriches selected content; it never increases the trend sample count.

## Evidence channels

Keep these channels separate:

- platform caption and metadata: platform-provided facts;
- native subtitle: platform-provided timed text;
- ASR transcript: machine-derived audio text;
- OCR text: machine-derived visible text;
- keyframe: a local derived visual artifact;
- visual interpretation: model inference created only during semantic review;
- comments: bounded audience context governed by `comment-evidence-contract-v0.1`.

Never rewrite ASR, OCR, or visual interpretation as a platform claim. Never use comments or media segments as additional trend samples.

## Two-stage workflow

1. Discover and deduplicate search-card signals with the platform adapter.
2. Select at most 10 representative video candidates across query layers and authors.
3. Analyze candidates sequentially. Prefer native subtitles, then ASR; sample scene changes before OCR.
4. Store the analyzer's immutable JSON response in the run directory and merge a bounded normalized projection into `content_evidence`.
5. Generate `video-review-queue.json`, let the Agent review every queued item, and validate the result with `apply_video_review.py`.
6. Run the normal signal semantic review again when the reviewed media changes the meaning, relevance, evidence role, or topic assignment.

The default pilot analyzes no more than 10 videos, keeps at most 8 keyframe receipts per video, 200 transcript segments, and 80 OCR rows. These are pilot ceilings to control cost and copyright exposure, not evidence-quality guarantees.

## Normalized shape

```json
{
  "content_evidence": {
    "contract_version": "video-evidence-contract-v0.1",
    "status": "complete|partial|unavailable",
    "analyzer": {"name": "mcp-video-analyzer", "version": "0.8.0"},
    "analyzed_at": "ISO-8601",
    "source_url": "https://...",
    "transcript": {
      "provenance": "native_subtitle|asr|unknown",
      "language": "",
      "segments": [{"start_seconds": 0, "end_seconds": 2.5, "text": "..."}]
    },
    "visual_text": {
      "provenance": "ocr",
      "rows": [{"timestamp_seconds": 1.2, "text": "...", "confidence": null}]
    },
    "keyframes": [{"timestamp_seconds": 1.2, "artifact_retained": false}],
    "metadata": {"title": "", "duration_seconds": null, "uploader": "", "upload_date": ""},
    "raw_artifact": "local immutable analyzer JSON path",
    "limitations": []
  }
}
```

`complete` requires transcript or OCR evidence plus a successful analyzer response. `partial` means some usable media evidence exists with warnings. `unavailable` preserves the failed attempt without promoting the search card to opened detail.

Keyframes without transcript or OCR are not usable semantic evidence and must not promote a search card to a verified detail.

## Semantic review and report projection

The Agent creates one `video-content-review-v0.1` row for every queued item. Each row contains:

- `signal_key`, confirmed `content_format`, and non-empty `summary`;
- `usable_channels`, limited to `native_subtitle`, `asr`, and `ocr`;
- one to four exact excerpts copied from the unchanged queue;
- per-excerpt `semantic_relevance`, `evidence_role`, and a concrete review reason;
- optional limitations that affect interpretation.

The validator rejects missing items, unknown channels, or excerpts that do not exactly match one queued channel row. Applying the review stores it under `content_evidence.semantic_review`, marks the media review complete, and leaves trend sample counts unchanged. It does not automatically rewrite the signal's main semantic labels.

Human-readable HTML and Markdown may show only reviewed direct or adjacent excerpts. Label native subtitles as video subtitles, ASR as machine-extracted speech, and OCR as machine-extracted on-screen text. Show at most four excerpts on a finding card and state once that media detail does not increase trend sample volume. Keep raw transcript/OCR, analyzer warnings, and machine fields in JSON audit data.

## Runtime and access boundary

The reference runner uses the optional MIT-licensed `mcp-video-analyzer@0.8.0` CLI. It is not bundled with this Skill. Run it only for public or explicitly authorized individual video URLs.

- Keep concurrency at one.
- Do not pass browser cookies, cookie files, tokens, or account credentials through Skill inputs or artifacts.
- Stop when the source requires login, permission, captcha handling, or access-control bypass.
- Reject profile, channel, playlist, recommendation-feed, and bulk-download URLs.
- Use a temporary frame directory and delete frames by default after extracting timestamps and OCR.
- Do not retain full media files. Retain only normalized text, timestamps, warnings, hashes, and the analyzer JSON needed for audit.
- Do not enable AI summaries from the analyzer; business interpretation remains in the Skill's separately audited semantic-review step.

Douyin is not claimed by this reference runtime. Keep Douyin media analysis `unsupported` until a separate lawful single-video path passes real acceptance.

## Acceptance

Before marking a platform's video-evidence path validated, verify:

- a captioned video, a no-caption video, and a visually text-heavy video;
- transcript/OCR provenance and bounded output;
- no sample-count increase;
- deterministic candidate selection and single concurrency;
- missing runtime, login requirement, unavailable video, timeout, and malformed analyzer output;
- temporary frame deletion and absence of credentials in artifacts;
- semantic review is repeated when media evidence changes the conclusion.
- the human report contains only reviewed excerpts and never leaks raw, unreviewed ASR/OCR into the visible reading path.
