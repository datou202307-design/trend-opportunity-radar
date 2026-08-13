# Output contract

Always deliver:

1. A self-contained local HTML report with inline CSS and JavaScript.
2. A concise Markdown report.
3. Machine-readable JSON.

Generate all three formats from the same UTF-8 inputs and run `validate_report_artifacts.py` before delivery. For HTML delivery, serve the run directory over loopback HTTP, inspect the real page in a browser, record `html-visual-qa.json` with `record_html_visual_qa.py`, and pass it through `--visual-qa-receipt`. The validator rejects likely mojibake, requires the exact subject name in human-readable outputs, requires the HTML embedded JSON to equal the standalone JSON, and verifies that the receipt matches the exact HTML hash. Never patch generated HTML or Markdown after generation.

The HTML first screen shows up to three eligible topics and the primary opportunity. Never pad topic or opportunity counts. Put other eligible items, excluded exploratory topics, evidence, gates, and raw JSON behind progressive disclosure. Do not include external brand assets, analytics, remote fonts, credentials, or network dependencies. A screenshot is optional and never replaces HTML.

Localize the report from `subject.communication.language`, which follows the user's request language rather than the target market language. Fall back to subject-text detection only for legacy inputs. If confidence is capped, show the raw value, capped value, and a concrete way to strengthen the evidence.

Add `communication` and `decision_support` to the JSON result. The visible report must lead with: what the current result can already help decide, what it cannot support yet, and the recommended resolution path. Never show an evidence gap without an action that addresses it.

Do not render recoverable sampling-gate labels such as `layer_detail_opens` or reader-facing paraphrases like “all-layer detail count.” The collection workflow must attempt retained-link detail backfill before report generation. If recovery remains externally blocked, describe only the user-relevant condition and the exact action that restores access; preserve internal gate names in JSON.

Keep machine audit keys unchanged in JSON and the collapsed machine-readable section. In the visible HTML interface, translate contract states, opportunity states, query layers, missing dimensions, and failed gates into plain reader-facing language. `blocked` means the evidence contract needs more collection; it must appear as “待补采” or an equivalent research-status label, not as a runtime error. Name the concrete missing layer or evidence type whenever available.

Keep every original per-signal limitation in `limitations` for auditability. Add `limitation_summary` with no more than four localized, decision-impact summaries and counts. Show only `limitation_summary` in visible HTML and Markdown; never render the complete limitation list as a reader-facing wall of text.

For a single snapshot, add `monitoring_recommendation` with a localized reason, suggested cadence, number of runs, reusable inputs, confirmation requirements, and an `automation_prompt`. Render it as a compact optional follow-up panel after the decision boundaries. Never imply that a static HTML button has created a scheduled task. A supporting Agent may create the task only after explicit user confirmation; other Agents should expose the prompt for reuse.

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

Only topics whose cluster audit is `passed` or `not_required` may appear in `topics` or back an opportunity. Preserve failed topics in `excluded_topics` with an exclusion reason. Emit at most one primary opportunity for each eligible topic; preserve rejected duplicates or ineligible proposals in `excluded_opportunities`.

Lead with the decision, then show opportunity cards and evidence, then expose raw data and scoring. Use `signal snapshot` when comparable time-series evidence is absent.

When sampling is incomplete or no opportunity is `review_ready`, describe the result as suitable for designing a validation experiment only. Do not say it can rank opportunities, establish priority, or judge demand strength.
