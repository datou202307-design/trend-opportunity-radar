# Output contract

Always deliver:

1. A self-contained local HTML report with inline CSS and JavaScript.
2. A concise Markdown report.
3. Machine-readable JSON.

For the five Decision Profiles, use `profile-research-report-v0.4` as the shared report model. Keep one visual system, but read its first-screen question, finding label, evidence explanation, action fields, and section order from the frozen Profile. Do not implement five unrelated renderers or reuse opportunity wording for brand, competitor, content, or demand reports.

Generate all three formats from the same UTF-8 inputs and run `validate_report_artifacts.py` before delivery. For HTML delivery, serve the run directory over loopback HTTP, inspect the real page in a browser, record `html-visual-qa.json` with `record_html_visual_qa.py`, and pass it through `--visual-qa-receipt`. The validator rejects likely mojibake, requires the exact subject name in human-readable outputs, requires the HTML embedded JSON to equal the standalone JSON, and verifies that the receipt matches the exact HTML hash. Never patch generated HTML or Markdown after generation.

The HTML leads with one primary decision answer, then a compact `collection_summary`, an optional `platform_native_context`, and then one to three eligible finding cards in the main reading path. `collection_summary` must show the query count, observed result count, deduplicated signal count, relevant signal count when semantic review exists, opened-detail count, counter-signal count, reviewed representative-comment count when available, and `complete|bounded` sampling status. Translate these values into one short reader-facing paragraph; do not expose query IDs, adapter diagnostics, gate names, or raw ledger detail. `platform_native_context` may explain only observed platform structure and how it changes evidence reading: Facebook prioritizes verified public-post discussion, user experience, objections, and reviewed comments; Instagram prioritizes Post/Reel/Carousel format, caption, reviewed media or visual evidence, and then comments. Preserve observed format counts, and keep Instagram Hashtag volume labels as supply hints rather than demand or growth. Do not add this block for a platform without a maintained platform-native contract. When a topic has reviewed relevant comments, its card shows one compact user-feedback block with deduplicated insights and an explicit qualitative-sample boundary; do not dump raw comments into the main path. Card count follows independently qualified topics: keep one when only one topic passes, show the second or third when they also pass, and never pad or suppress cards for visual symmetry. Put additional eligible items, excluded exploratory topics, evidence, gates, and raw JSON behind progressive disclosure. Do not include external brand assets, analytics, remote fonts, credentials, or network dependencies. A screenshot is optional and never replaces HTML.

When semantically reviewed video evidence exists, add reviewed and relevant video counts to `collection_summary`. A matching finding may show one compact `video_evidence` block containing at most four exact, reviewed excerpts. Use reader-facing labels for video subtitles, machine-extracted speech, and machine-extracted on-screen text; state once that this enriches existing posts and does not increase trend sample volume. Never render raw, unreviewed transcript or OCR rows in HTML or Markdown. Preserve them only in the JSON audit payload.

Apply visible semantic deduplication without deleting audit fields. Render the Profile's `decision_answer` once in the top decision block, each finding's `decision_summary` once as its explanation, and `evidence_boundary` once inside that finding's evidence disclosure. Do not repeat these fields in the card detail grid. When a Profile section exactly duplicates a shared card field, suppress the duplicate only in human-readable HTML and Markdown; for `brand_sentiment`, render the shared audience block and suppress the duplicate `affected_audience` detail. Preserve every original Profile field unchanged in JSON and embedded audit data.

Localize the report from `subject.communication.language`, which follows the user's request language rather than the target market language. Fall back to subject-text detection only for legacy inputs. If confidence is capped, show the raw value, capped value, and a concrete way to strengthen the evidence.

Add `communication` and `decision_support` to the JSON result. The visible report must lead with: what the current result can already help decide, what it cannot support yet, and the recommended resolution path. Never show an evidence gap without an action that addresses it.

Do not render recoverable sampling-gate labels such as `layer_detail_opens` or reader-facing paraphrases like “all-layer detail count.” The collection workflow must attempt retained-link detail backfill before report generation. If recovery remains externally blocked, describe only the user-relevant condition and the exact action that restores access; preserve internal gate names in JSON.

Keep machine audit keys unchanged in JSON and the collapsed machine-readable section. In the visible HTML interface, translate contract states, opportunity states, query layers, missing dimensions, and failed gates into plain reader-facing language. `blocked` means the evidence contract needs more collection; it must appear as “待补采” or an equivalent research-status label, not as a runtime error. Name the concrete missing layer or evidence type whenever available.

Keep every original per-signal limitation in `limitations` for auditability. Add `limitation_summary` with no more than four localized, decision-impact summaries and counts. Show only `limitation_summary` in visible HTML and Markdown; never render the complete limitation list as a reader-facing wall of text.

For a single snapshot, add `monitoring_recommendation` or the Profile-equivalent `follow_up_recommendation` with a localized reason, suggested cadence, number of runs, reusable inputs, confirmation requirements, and an `automation_prompt`. Render it as a compact optional follow-up panel after the main decision. Never imply that a static HTML button has created a scheduled task. A supporting Agent may create the task only after explicit user confirmation; other Agents should expose the prompt for reuse. Preserve action adoption and outcome as feedback evidence; never let feedback rewrite scoring weights automatically.

## Opportunity

```json
{
  "title": "...",
  "reader_title": "plain-language display title",
  "title_readability": {"status": "passed|rewritten", "replaced_terms": []},
  "topic_key": "...",
  "audience": "...",
  "task_gap": "...",
  "subject_entry": "...",
  "expected_action": "...",
  "support_refs": [],
  "counter_refs": [],
  "counter_review": "...",
  "counter_search_status": "found|searched_none_found|not_searched",
  "semantic_review": "agent_reviewed|human_reviewed|not_reviewed",
  "risk_boundaries": [],
  "missing_evidence": [],
  "gates": {},
  "failed_gates": [],
  "evidence_status": "candidate|review_ready|confirmed|rejected"
}
```

Preserve `title` as the supplied audit value. Use `reader_title` in human-facing HTML and Markdown. For a general audience, reject or deterministically rewrite unexplained metaphors and internal product terms; a readable title should name a concrete user, task, action, or outcome rather than a conceptual architecture.

`review_ready` requires a completed sampling contract, at least three independent signals, at least two independent direct authors, one direct source, evidence confidence of at least 55, explicit counterevidence search, semantic-link review, and all structural fields. Only a human may promote it to `confirmed`.

Only topics whose cluster audit is `passed` or `not_required` may appear in `topics` or back a finding. Preserve failed topics in `excluded_topics` with an exclusion reason. Emit at most one finding for each eligible topic; preserve rejected duplicates or ineligible proposals in `excluded_opportunities`.

Lead with the decision, then show opportunity cards and evidence, then expose raw data and scoring. Use `signal snapshot` when comparable time-series evidence is absent.

When sampling is incomplete or no opportunity is `review_ready`, describe the result as suitable for designing a validation experiment only. Do not say it can rank opportunities, establish priority, or judge demand strength.
