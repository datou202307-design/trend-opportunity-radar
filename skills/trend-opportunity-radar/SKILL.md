---
name: trend-opportunity-radar
description: Analyze a research topic on one platform as a constrained, evidence-backed decision study. Use when the user wants to find business opportunities, monitor brand sentiment, study competitor users, find content opportunities, or validate product demand on Xiaohongshu, X, or another single platform; collect or import platform signals; audit sampling; separate observed heat from evidence confidence; review counterevidence and risks; generate local reports; or compare compatible snapshots without claiming viral prediction.
---

# Trend Opportunity Radar

Analyze one research topic on one platform. Treat a product as a fact-bound subject and an opportunity or idea as a hypothesis to validate.

## Accept minimum input

Require only a comprehensible research topic and one target platform. Accept a product file or URL, opportunity, idea, problem, audience need, or project description.

Use this invocation pattern:

`Analyze [research topic] on [platform] for trend opportunities.`

Infer language, region, audience, queries, time window, source mode, collection mode, and output paths when safe. State material assumptions in the result. Ask one concise question only when the topic or platform is indeterminate, login or paid access requires authorization, or a choice materially changes the result. Never request passwords, cookies, sessions, or tokens in chat.

## Execute the workflow

### 1. Build a subject brief

Create UTF-8 JSON containing `name`, `subject_type`, `summary`, sourced `facts`, bounded `hypotheses`, `audiences`, `scenarios`, `constraints`, `source_refs`, and a `communication` object. Infer `communication.language` from the user's request language rather than the market language; infer `goal` and `audience` without adding required user input. Use `auto|zh-CN|en|bilingual` for language, `validate_business_opportunity|validate_product_demand|discover_content_opportunities|understand_trend|general_research` for goal, and `general|expert` for audience. Keep an idea or business premise in `hypotheses` until external evidence or a human confirms it.

Before collection, compile the original user request into `research-context.json` and freeze the selected intent, platform, Profile version, decision question, assumptions, and source prompt hash:

```bash
python scripts/compile_research_context.py --prompt "ORIGINAL USER REQUEST" --subject subject.json --output research-context.json --require-ready
```

If the compiler returns `clarification_required`, ask only its single generated question and do not collect yet. A clear explicit intent overrides incidental wording. The legacy “analyze a topic on a platform for trend opportunities” call remains `business_opportunity`. Read [research-context.md](references/research-context.md), [decision-profile-registry.json](references/decision-profile-registry.json), and [decision-profile-contract.md](references/decision-profile-contract.md). Freeze the selected Profile's query intents, evidence roles, decision thresholds, action contract, and report sections for the run.

Use only `product`, `opportunity`, `idea`, `problem`, or `project` for `subject_type`, then validate before collection:

```bash
python scripts/validate_subject.py --input subject.json
```

### 2. Select one source and collection mode

Read [platform-adapters.md](references/platform-adapters.md) and choose the strongest lawful source:

`authorized_api → customer_export → controlled_capture → public_web → historical_snapshot`

For the explicit Reddit topic-research pilot, read [reddit-mcp-adapter.md](references/reddit-mcp-adapter.md). Use only a user-connected third-party MCP service, enforce its three-operation read allowlist, keep comments and Feed operations disabled, and never treat a bounded response as platform exhaustion.

Treat [platform-adapter-registry.json](references/platform-adapter-registry.json) as the capability source of truth. Validate it through `scripts/validate_platform_adapters.py` when changing platform routing. Keep platform commands and mechanical parsers behind the adapter contract; do not place them in a Decision Profile or use them to make semantic conclusions.

Instagram has separate scope-specific routes. For a user-supplied public brand, competitor, or creator account under the `account_research` pilot, read [instagram-account-adapter.md](references/instagram-account-adapter.md). For validated `topic_research`, read [instagram-hashtag-topic-adapter.md](references/instagram-hashtag-topic-adapter.md), translate the subject into explicit hashtags across the three frozen query layers, execute two paced reads per hashtag, record each layer independently, merge the snapshots, and complete post plus comment review before reporting. Never route a general topic to account research, or use account search, personalized Explore, the generic Reels feed, Followers, or Following as topic or audience evidence. A displayed hashtag post count is a supply-volume hint, not observed sample count or search demand.

If Instagram topic collection stops after preserving a useful partial snapshot, use `generate_instagram_topic_report.py` for a bounded three-format report. It must explain what the evidence already supports, what it cannot establish, and how the next compatible run will continue; never expose browser retry mechanics as the user's problem.

Read [sampling-contract.md](references/sampling-contract.md) before collecting. Default to `standard`; use `quick` only for an explicitly quick scan, public-web fallback, or recorded access constraint. Use `deep` only when the source can lawfully support it. Never silently downgrade.

For a dynamic or logged-in browser, read [browser-collection.md](references/browser-collection.md). Preflight every considered adapter without installing or changing credentials. On Xiaohongshu and X, check OpenCLI and DokoBot when available; on YouTube, check OpenCLI; for TikTok topic-research Beta, require explicit enablement plus a user-authorized, already logged-in browser, then check both OpenCLI search and DokoBot logged-in detail capability. Treat OpenCLI TikTok `whoami` as diagnostic only when the same controlled Chrome page is visibly logged in and the bounded search probe succeeds; do not ask for a second login merely because owner identity was not rehydrated. Do not test or imply anonymous TikTok live-research support; use structured import as the session-independent fallback. Capability is platform-specific and requires a successful redacted probe:

```bash
python scripts/check_collection_adapter.py --adapter opencli --output opencli-status.json
python scripts/check_collection_adapter.py --adapter dokobot --output adapter-status.json
python scripts/select_collection_adapter.py --platform xiaohongshu --status opencli-status.json --status adapter-status.json --output adapter-selection.json
```

For validated Xiaohongshu or X collection, prefer `OpenCLI → DokoBot`. On X, OpenCLI performs structured Top/Latest search and retained-thread detail reads; DokoBot verifies rendered-page context when fields are missing, content mismatches, a login state appears, or visible UI evidence matters. On Xiaohongshu, OpenCLI performs structured search and signed detail reads with the same verification fallback. On YouTube, OpenCLI performs bounded search and video-detail reads; preserve locale-dependent publication labels from search, replace them with the exact detail timestamp when available, and do not claim comment or transcript coverage unless those bounded reads were actually preserved. On TikTok Beta runs, keep OpenCLI as the search adapter and use a separately preflighted DokoBot browser session only as the detail enhancer. Freeze both adapters in the selection and state files; never silently borrow an unprobed browser session. When no validated adapter is ready, degrade to an authorized export or public-web discovery without weakening the selected sampling contract.

Do not conclude that a CLI is absent from `Get-Command`, `which`, or PATH lookup alone. If a sandbox reports `cli_not_found`, `cli_not_visible`, or `cli_permission_denied`, try the standalone approved version and connection probes once before changing adapters. If they succeed, rerun the preflight with the required read/execute approval so it can write a genuine `ready` record; never hand-edit the status. Never install a CLI or extension without user authorization.

Keep recoverable adapter diagnostics internal. When the standalone probe and approved preflight succeed, tell the user only that the read-only collection environment is ready; do not narrate sandbox paths, npm locations, fallback probes, or approval mechanics. Surface adapter diagnostics only when the user must restore login, connect the browser, approve a narrowly scoped read, or choose a degraded source.

Read [opencli-orchestration.md](references/opencli-orchestration.md) for OpenCLI X, Xiaohongshu, or YouTube collection, or [dokobot-orchestration.md](references/dokobot-orchestration.md) for DokoBot. Use the deterministic adapter-neutral orchestrator instead of browser memory or a single read. Chrome browser control, OpenCLI, and DokoBot are supported examples, not dependencies. Let the user complete login personally.

Do not mix platforms. Run separate snapshots and compare only at report level.

When the user requests a cross-platform comparison, require completed single-platform Profile reports with the same subject name, research intent, Profile version, analysis unit, and report language. Keep every platform's collection basis, `observed_heat`, and `evidence_confidence` separate; never add, average, normalize, or rank platform scores. Create an explicit comparison synthesis, then generate the comparison artifacts:

```bash
python scripts/generate_platform_comparison.py \
  --report xiaohongshu=PATH/TO/XHS/profile-report.json \
  --report x=PATH/TO/X/profile-report.json \
  --synthesis comparison-synthesis.json \
  --json-output platform-comparison.json \
  --markdown-output platform-comparison.md \
  --html-output platform-comparison.html
```

The comparison must lead with one decision answer, show each platform's research basis, identify shared tasks and platform-specific differences, and end with a unified MVP sequence plus platform-specific validation. Link back to the original platform reports. Treat shared findings as model synthesis supported by the two independent snapshots, not as a new trend score.

### 3. Collect with a ledger

Create `raw-signals.json` as the only canonical collection ledger before searching. Do not create a second manually maintained ledger. Use all three query layers. In non-default Profiles, also assign every query one `query_intent` allowed by the frozen context; do not put platform commands inside a Profile:

- `platform_baseline`: platform-native language and attention
- `category`: the task, problem, audience, or category
- `subject_bridge`: terms connecting the signal to the research subject

For `content_opportunity_v1`, keep audience questions, resonance or controversy separate from existing content supply. Tool lists, universal prompts, product demonstrations, and generic warning posts are `content_supply` or saturation counterevidence; engagement alone cannot promote them into an opportunity. Write `subject_bridge` and recovery terms as a concrete task failure or outcome in platform-native language (for example, “AI travel planning failed”), not a generic technology complaint such as “AI is bad” or “not useful.” If a bridge query drifts into unrelated AI products, office work, or coding complaints, mark those cards weak and rewrite the next requested query around the specific user task. A deliverable content angle must connect a real audience question or controversy to an audience handoff, response metric, stop condition, and human verification boundary.

Count every observed result card before filtering. Separately record retained signals, duplicates, opened details, discarded results, independent authors, direct sources, and counter signals. Preserve query-level counts and a completion or stop reason. Never call a curated evidence list the raw sample.

After each query, save that query to `query-result.json` and append it atomically before navigating to the next query:

```bash
python scripts/append_collection_result.py --snapshot raw-signals.json --query-result query-result.json --platform x --source-mode controlled_capture --mode standard
```

For controlled collection, let `orchestrate_collection.py` generate every next action and perform the append. Do not bypass its `complete` or `blocked` decision. The legacy DokoBot entry point remains compatible, but new runs use the neutral entry:

```bash
python scripts/orchestrate_collection.py init --state collection-state.json --snapshot raw-signals.json --plan query-plan.json --adapter-status adapter-selection.json --research-context research-context.json --platform xiaohongshu --mode standard
python scripts/orchestrate_collection.py next --state collection-state.json
python scripts/run_collection_capture.py --state collection-state.json --metadata-output baseline-1-metadata.json --extraction-output baseline-1-extraction.json
python scripts/apply_semantic_review.py --extraction baseline-1-extraction.json --review baseline-1-semantic-review.json --output baseline-1-reviewed-extraction.json --audit-ledger semantic-review-ledger.json --research-context research-context.json
python scripts/orchestrate_collection.py record-capture --state collection-state.json --metadata baseline-1-metadata.json --extraction baseline-1-reviewed-extraction.json
python scripts/orchestrate_collection.py add-queries --state collection-state.json --plan recovery-query-plan.json
python scripts/run_opencli_detail_backfill.py --state collection-state.json --results-output detail-results.json
python scripts/run_dokobot_detail_backfill.py --state collection-state.json --results-output detail-results.json
```

Use `run_collection_capture.py` for live query reads. Read [collection-pacing-contract.md](references/collection-pacing-contract.md), keep one active browser read at a time, and never launch parallel query, detail, comment, tab, or fallback-adapter work for one browser profile. The runner preserves pacing, exit state, timeout, raw output, immutable metadata, stdout, stderr, and the exact command hash. For OpenCLI X, OpenCLI Xiaohongshu, OpenCLI YouTube, OpenCLI TikTok pilot, and DokoBot X search it deterministically creates a query-specific extraction file. Every search result starts as `unreviewed` and cannot satisfy a relevance gate. Use filenames containing the query id for the extraction, semantic review, and reviewed extraction; append every review to `semantic-review-ledger.json`, never overwrite one generic review file. Direct and adjacent reviews require a meaningful provisional `topic_key`; weak collisions use the excluded key. Pass the reviewed extraction to `record-capture`. Never label every keyword match `direct`; state a concrete review reason. The reusable metadata and extraction paths are only pointers consumed by `record-capture`. Use `record-chunk` only for non-live imported fixtures or compatibility recovery.

Start standard mode with three probe queries, one in each layer. Let the orchestrator stop as soon as the volume and quality gates pass; add only the deficient-layer queries it requests, up to nine total. If it returns `replan_queries`, add exactly one rewritten query for one recommended deficient layer, execute and review it, then ask the orchestrator again before spending another query slot. Rewrite a high-volume/low-relevance query instead of continuing it: use at most four words, remove stacked audience/product/task qualifiers, and search one platform-native problem, workflow, outcome, objection, or capability phrase at a time. Treat a zero-result query as low yield. When only total observed or unique volume remains deficient and every relevance, detail, counterevidence, and per-layer quality gate already passes, use `volume_recovery.recommended_terms` and its preferred layer; these terms form a deterministic queue of progressively shorter contiguous phrases derived from the highest-yield completed queries. Do not spend the remaining budget on a newly invented compound phrase or a term listed under `avoid_terms`. If the evidence-derived queue is empty, stop and deliver a bounded snapshot even when query budget remains. The orchestrator reserves room for one atomic read before the observed upper bound; never bypass `observed_budget_guard`, truncate visible cards, or start extra searches merely to complete a fixed plan. Do not normalize or report until it returns `complete` or terminal `blocked`. Never interpret a fixed plan ending as proof that the platform lacks demand.

If the orchestrator returns `backfill_details`, exhaust eligible retained links before reporting. On OpenCLI X, Xiaohongshu, or YouTube runs, execute `run_opencli_detail_backfill.py`. X thread output may omit views or replies, so merge it with—not over—existing search metrics and select the requested post id when replies are returned. YouTube detail reads merge exact publication time, description, channel identity, subscribers, views, and likes; missing detail fields never erase search facts. On DokoBot X runs, execute `run_dokobot_detail_backfill.py`; it opens the retained post URLs, mechanically extracts the rendered post, preserves immutable raw/stdout/stderr/metadata artifacts, and atomically updates the ledger. Use manual `record-details` only for imported compatibility data, never as a substitute for an available deterministic runner. Detail backfill does not spend search-query budget. Do not expose a recoverable detail deficit in the human report; only ask the user when login, permission, captcha, rate limit, or another external condition blocks the attempted recovery.

After detail backfill, require the orchestrator to close the reviewed evidence ledger and collection state to the same terminal result before reporting. For append-only adapters such as Reddit MCP search plus audited public-permalink detail reads, keep `raw-signals.json` as the immutable acquisition ledger and close its search phase with `search_collection_complete`; normalization may promote only that explicit checkpoint to `sampling_contract_met`, and only after semantic review, detail audits, and every sampling check pass. Other stale, blocked, or `collection_in_progress` ledgers must never be reinterpreted as complete. The report, latest reviewed/scored ledger, and `collection-state.json` must agree on the terminal result.

Treat detail backfill as evidence enrichment, not a new semantic review. Preserve the retained card's `semantic_review`, `semantic_relevance`, `evidence_role`, and `topic_key`; remove limitations that became false after the detail was opened. Reject delivery when stored counter totals differ from the canonical signal roles or any opened detail loses its semantic audit fields.

Capture only bounded representative conversation context for verified details: at most five replies from an X thread, five separately throttled top-level comments from a Xiaohongshu note, ten comments from a YouTube video, or five comments that are actually visible in a bounded TikTok browser detail read. Preserve comment artifacts and capture metadata, minimize personal fields, and never count comments as additional trend samples. A TikTok comment total is a metric, not captured comment text. Treat a recoverable comment failure as unavailable enrichment; honor captcha, rate-limit, login, permission, content-mismatch, and redirect safety stops.

For TikTok only, if the preflighted DokoBot detail verifies the target but exposes no comment bodies, read [tiktok-comment-enrichment.md](references/tiktok-comment-enrichment.md) and use the deterministic two-stage recorder. Freeze exactly one eligible target before touching Chrome, let an available user-authorized logged-in Chrome control surface return only the bounded visible result, then validate and merge it:

```bash
python scripts/run_tiktok_comment_enrichment.py plan --snapshot raw-signals.json --output tiktok-comment-request.json
python scripts/run_tiktok_comment_enrichment.py record --snapshot raw-signals.json --request tiktok-comment-request.json --capture tiktok-comment-capture.json --output comment-enriched-signals.json --receipt tiktok-comment-receipt.json
```

Use `comment-enriched-signals.json` for normalization only when the receipt status is `captured`; otherwise continue with the unchanged search/detail snapshot. The recorder binds the result to the exact content ID, author path, request hash, one Comments expansion, five-comment limit, and no-write checks. Do not type, like, reply, post, follow, or read recommended content. If the panel times out, mismatches, or remains empty, continue the completed search/detail report with comment enrichment unavailable.

When representative comments were captured, read [comment-evidence-contract.md](references/comment-evidence-contract.md). After normalization, create the deterministic review queue, review every queued comment from its visible text only, and merge the validated review before clustering or findings:

```bash
python scripts/prepare_comment_review.py --input normalized-signals.json --output comment-review-queue.json
python scripts/apply_comment_review.py --input normalized-signals.json --queue comment-review-queue.json --review comment-review.json --output comment-reviewed-signals.json
```

The Agent creates `comment-review.json`; do not ask the user to label comments. Use relevant comment evidence to refine user tasks, pain points, questions, workarounds, purchase intent, objections, positive outcomes, comparisons, and validation actions. Comments remain qualitative context: never promote them into trend samples, infer unstated identities or intent, or change a source signal's polarity automatically. If no comments were captured, continue without manufacturing a review.

When a selected platform item's meaning is materially carried by video, read [video-evidence-contract.md](references/video-evidence-contract.md). Keep discovery and media understanding as separate stages. Select no more than ten deduplicated representative URLs, run any optional video analyzer sequentially, prefer native subtitles before ASR, sample scenes before OCR, delete temporary frames, and merge derived transcript/OCR evidence without increasing trend sample counts. Never pass browser cookies or credentials through the Skill. A failed media analysis leaves the item as search-card evidence; a successful analysis requires semantic re-review before it can change relevance, evidence role, or topic assignment.

After merging usable video evidence, prepare and complete the Agent review before clustering or report generation. The Agent—not the user—creates `video-content-review.json`. Quote only exact queued subtitle, ASR, or OCR rows; summarize their decision relevance separately. The apply step validates provenance and completeness, does not change trend volume, and does not automatically overwrite the signal's existing relevance, evidence role, or topic:

```bash
python scripts/prepare_video_review.py --input video-enriched-signals.json --output video-review-queue.json
python scripts/apply_video_review.py --input video-enriched-signals.json --queue video-review-queue.json --review video-content-review.json --output video-reviewed-signals.json
```

Use `video-reviewed-signals.json` for subsequent clustering, scoring, and reporting. Never render unreviewed transcript or OCR rows in the human reading path. Show the Agent-reviewed plain-language media summary first. Keep original subtitle, ASR, or OCR excerpts under a collapsed “view original text” disclosure with plain-language channel labels, and retain the full machine-derived evidence in JSON audit data. Do not force a reader to interpret foreign-language OCR before understanding what the video adds.

Raw volume never proves research sufficiency. Before declaring the sampling contract complete, require relevant unique signals and per-layer relevant/direct signals in addition to observed, unique, detail, counterevidence, and review-coverage minima. A layer filled by career, course, vendor, or other off-task noise must trigger query rewriting and recovery even when the total count is high.

When a query returns no visible results, record an empty chunk with `can_continue: false`, empty result and signal arrays, the preserved raw artifact, and `stop_reason: zero_results`. Let the orchestrator store `completed_with_zero_results` and calculate the terminal contract decision. Never leave the query `in_progress` or generate a report from an `in_progress` snapshot.

Treat a timeout as a retry condition, not as proof that results ended. Treat continuation as exhausted only when the platform or DokoBot supplies explicit terminal evidence; visible-card count and first-screen completion are not terminal evidence. Let the orchestrator reduce the first timeout or unknown-continuation retry to one screen. When DokoBot reports an expired continuation session, restart the same query once from its original URL without `--session-id`, deduplicate already observed cards, and only then finalize it as partial if recovery fails again. Only platform-wide safety or access conditions such as captcha, rate limit, login expiry, permission prompts, or abnormal redirects may block the whole run immediately.

Start DokoBot reads with one screen per chunk. If a successful continuation returns no new card after the query already has results, record the empty continuation without inventing a zero-result stop; retry once and finalize that query as partial after a second consecutive empty continuation. Never create or execute a patched copy of the orchestrator inside a run directory. Preserve every card that was actually observed, but avoid requesting multiple screens in advance merely to fill the quota.

Never keep the only copy of evidence in browser memory. Let the append and normalization scripts calculate final counts; do not hand-maintain a separate total.

Do not append a path merely because it was requested. A successful capture, detail read, stdout/stderr log, and per-capture metadata entry must reference a file that actually exists. Reject report delivery when any recorded raw artifact is missing or when multiple executions reuse the same audit-log path.

Keep raw evidence unchanged. Mark every retained signal `support`, `counter`, or `neutral` for the shared scoring kernel, and add one Profile-specific `profile_evidence_role` from the frozen context during review. The two fields serve different purposes and must not overwrite each other. Distinguish opened direct posts, unopened search cards, summaries, profiles, and search snippets. A controlled-browser search result without an opened detail is `search_card`, never `direct_post`. A single run is a `signal snapshot`. Claim direction only from compatible repeated snapshots.

Also label every retained signal `semantic_relevance` as `direct`, `adjacent`, `weak`, or `unreviewed`. `standard` and `deep` runs must satisfy the per-layer observed, unique, and detail gates, plus direct subject-bridge evidence and relevance-review coverage. Total counts alone never complete the contract.

### 4. Normalize and score deterministically

Read [signal-schema.md](references/signal-schema.md), then run:

```bash
python scripts/normalize_signals.py --input raw-signals.json --output normalized-signals.json --platform x --source-mode controlled_capture
python scripts/prepare_comment_review.py --input normalized-signals.json --output comment-review-queue.json
python scripts/apply_comment_review.py --input normalized-signals.json --queue comment-review-queue.json --review comment-review.json --output comment-reviewed-signals.json
python scripts/calculate_evidence_index.py --input comment-reviewed-signals.json --output scored-signals.json
python scripts/detect_data_gaps.py --input scored-signals.json --output data-gaps.json
```

When the queue contains zero comments, skip `apply_comment_review.py` and use `normalized-signals.json` as the next input.

Try `python3`, `py`, or a documented bundled Python 3 runtime if `python` is unavailable. If no runtime exists, perform the schema-equivalent transformation locally and disclose that deterministic scripts were not executed.

Read [scoring-contract.md](references/scoring-contract.md). Report `observed_heat` and `evidence_confidence` separately. Use content publication time for freshness and topic-level independent authors for diffusion. Missing dimensions contribute zero; never redistribute weights. Cap confidence when the sampling contract is incomplete and show the raw value, capped value, and reason.

Use [engagement-weight-registry.json](references/engagement-weight-registry.json) for platform-specific interaction behavior weights. Preserve its version in scored output, treat candidate weights as calibration assumptions, and never compare raw engagement or weighted scores across platforms.

In human-facing reports, treat the two scores as grading aids, not as warnings. Show `observed_heat` and `evidence_confidence` with plain-language levels so the user can scan them directly. Keep raw confidence, cap calculations, and cap reasons inside a collapsed score explanation and JSON. Never phrase a confidence cap as though the trend score itself was reduced.

### 5. Form bounded opportunity hypotheses

Cluster semantically related signals without overwriting samples. Read [clustering-contract.md](references/clustering-contract.md). Create a clustering plan with explicit inclusion/exclusion rules and one auditable assignment for every signal, then run:

```bash
python scripts/audit_clusters.py --input normalized-signals.json --plan cluster-plan.json --output clustered-signals.json --research-context research-context.json
python scripts/calculate_evidence_index.py --input clustered-signals.json --output scored-signals.json
```

Do not treat a `topic_key` rewrite as semantic clustering. A failed or missing audit caps confidence and blocks `review_ready`. Create only differentiated opportunities supported by a concrete task transition. Treat opportunity targets as capacity, never as a quota. Do not split a coherent cluster or create extra cards merely to fill the first screen. A failed or missing cluster audit remains an exploratory topic and cannot produce an opportunity card. Emit at most one finding per eligible topic. Show one to three qualified finding cards in the main decision path when the evidence supports them; one card is valid when only one topic passes, while additional eligible topics must not be suppressed merely to force a single answer.

Exclude `unreviewed`, `reviewed-unclustered`, and keyword-collision topics from human topic lists and opportunity generation. In standard mode, only a topic with a passed cluster audit may generate an opportunity card, including a candidate card.

Give every cluster a concise reader-facing `title` in the report language that describes the shared task or outcome. Do not reuse a representative post headline, Markdown decoration, vendor slogan, or `topic_key`. The scorer must use the audited cluster title in JSON, Markdown, and HTML.

For `business_opportunity`, the existing opportunity-card contract remains supported. For every Profile, create `profile-findings.json` using [decision-profile-contract.md](references/decision-profile-contract.md), populate the selected Profile's exact report sections and action fields, then validate it:

```bash
python scripts/validate_profile_decisions.py --research-context research-context.json --signals scored-signals.json --findings profile-findings.json
```

When a topic has reviewed relevant comments, use their validated insights when writing the user task, objection, workaround, decision summary, or next validation action. The shared report generator automatically adds a compact reader-facing comment-evidence block to the matching topic card.

For brand sentiment, label a single run as a current issue snapshot. Never claim that an issue is spreading, rising, falling, or resolved over time without at least two compatible snapshots.

Support and counter references must be disjoint after URL normalization. A mixed or ambiguous source may be discussed in the reasoning, but it cannot occupy both evidence lists in one opportunity. Reclassify it once or leave the opportunity as a candidate until the conflict is resolved; never deliver a report with overlapping references.

Write every human-facing title, summary, section, and action for the inferred audience. For Chinese reports, state the user, concrete situation, meaning, and next action; avoid research/product shorthand such as “任务链”, “跨来源”, “受约束”, “作为入口”, “切口”, “副驾”, “中台”, “闭环”, “赋能”, “桥接”, or “守门层”. The shared generator rejects these terms in reader-facing findings; rewrite the source finding instead of relying on automatic word replacement. Preserve technical terms only in JSON audit fields or define them immediately when the intended audience is expert.

Mark `review_ready` only when all conditions pass:

- sampling contract completed;
- at least three independent signals and two independent direct authors;
- at least one direct source;
- at least one directly relevant subject-bridge source;
- semantic relevance reviewed for at least 80% of the topic signals;
- cluster audit passed when clustering was applied;
- evidence confidence at least 55;
- counterevidence was found or explicitly searched without a result;
- the topic-to-subject semantic link was reviewed;
- audience, task, boundary, support, and next validation action are concrete.

Otherwise keep the result `candidate` and list failed gates. Only a human may set `confirmed`.

### 6. Generate three output layers

Read [output-schema.md](references/output-schema.md), then run:

```bash
python scripts/generate_profile_report.py \
  --research-context research-context.json \
  --signals scored-signals.json \
  --findings profile-findings.json \
  --json-output profile-report.json \
  --markdown-output profile-report.md \
  --html-output profile-report.html
```

Use this shared visual renderer for all five modes. It changes the decision question, finding labels, report sections, action fields, and follow-up cadence from the frozen Profile. Keep the machine audit collapsed, but show one compact `Research basis` block immediately after the direct answer with the search-theme count, observed result count, deduplicated signal count, relevant signal count when reviewed, opened-detail count, counter-signal count, and a plain-language sampling status. Never make the reader open raw JSON to discover how much evidence was collected. Every action requires an intensity, execution condition, success or response metric, stop condition, and human boundary as defined by that Profile. The follow-up panel is a recommendation only; never claim that a scheduled task exists without explicit confirmation and an actual task-creation result. For backward-compatible `business_opportunity` delivery, the existing three-artifact generator remains accepted during migration:

```bash
python scripts/generate_opportunities.py \
  --subject subject.json \
  --signals scored-signals.json \
  --opportunities opportunities.json \
  --json-output trend-opportunities.json \
  --markdown-output trend-report.md \
  --html-output trend-report.html
python scripts/validate_report_artifacts.py \
  --json-report trend-opportunities.json \
  --markdown-report trend-report.md \
  --html-report trend-report.html
```

Omit `--opportunities` only for a cautious candidate-only fallback. Deliver the self-contained HTML as the primary human-readable result, Markdown as the concise portable report, and JSON as the audit record. Lead with one primary decision answer, then show one to three eligible finding cards in the main reading path; never pad the card count, never hide a second or third independently qualified topic to make the report look simpler, and keep any additional eligible items in secondary disclosure. Deeper evidence and excluded exploratory topics remain auditable. Match HTML interface language to the research subject. Always perform browser QA over temporary loopback HTTP; do not attempt `file://` first. Start a read-only server rooted at the run directory, inspect the subject, first screen, evidence sections, and console, then create `html-visual-qa.json` with `record_html_visual_qa.py`. Stop the server after inspection. Pass the receipt to final validation:

Keep the machine audit complete but deduplicate the visible reading path. Show the Profile's short `decision_answer` only in the top decision block, the finding's longer `decision_summary` only as the card explanation, and `evidence_boundary` only in that card's evidence disclosure. Suppress an exact Profile-section duplicate of a shared card field in human-readable HTML and Markdown; in brand sentiment, show one audience block instead of repeating `affected_audience`. Preserve all original fields unchanged in JSON and embedded audit data.

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory RUN_DIRECTORY
python scripts/record_html_visual_qa.py --html-report trend-report.html --output html-visual-qa.json --url http://127.0.0.1:8765/trend-report.html --title "VISIBLE PAGE TITLE" --subject-visible --first-screen-readable --evidence-sections-readable --console-error-count 0
python scripts/validate_report_artifacts.py --json-report trend-opportunities.json --markdown-report trend-report.md --html-report trend-report.html --visual-qa-receipt html-visual-qa.json
```

Keep raw status keys such as `blocked`, `candidate`, and failed gate identifiers in JSON only. Translate them into reader-facing evidence language in HTML, such as “待补采”, “候选”, and a concrete missing-evidence description. Never present an incomplete evidence contract as a software error.

Do not hand-edit generated HTML or Markdown. Regenerate all three formats from the same UTF-8 JSON inputs. The generator rejects suspected encoding corruption, and the artifact validator requires the HTML embedded payload to equal the standalone JSON exactly.

Do not create run-local parsers, signal sanitizers, ledger deduplicators, or patched orchestrators to make a report pass. Fix the reusable Skill script and rerun from preserved raw evidence. The artifact validator rejects known one-off repair scripts in a delivery directory.

Never present an evidence gap as a standalone problem for the user. Pair every visible limitation with what the current evidence can still support, what it cannot support yet, and a concrete resolution path. Lead with a decision-support block adapted to the inferred goal and general/expert audience. Prefer plain language for `general`; keep technical audit terms in collapsed details and JSON.

Do not dump per-signal limitation notes into the visible HTML or Markdown. Summarize them into at most four decision-impact categories with counts; retain the complete original notes only in JSON and the collapsed machine-readable audit section.

Do not repeat generic single-snapshot gaps such as velocity, freshness, or search demand under every topic. Keep these dimensions in JSON scoring audit and address the time-series gap once through the follow-up monitoring recommendation. Translate collection mode, subject type, evidence status, and topic status into the report language.

After a single-snapshot report, recommend an optional follow-up monitoring task that reuses the subject, platform, language, region, query layers, sampling contract, and output history. Suggest every three days for fast-moving platforms such as X, or weekly elsewhere, for four runs by default. Require user confirmation before creating any scheduled task or using authorized collection access. Append snapshots without overwriting history. If the Agent cannot schedule tasks, provide the reusable task instructions only.

## Preserve evidence boundaries

Label claims as platform fact, subject fact, user premise, model inference, or human confirmation. Keep stable links near supported claims. Report access failures and partial collection. Never fabricate unavailable content, comments, metrics, trends, compatibility, demand, revenue, or product capability.

## Operate safely

- Keep browser work read-only, sequential, bounded, permission-aware, and paced by the recorded conservative interval and batch cooldown.
- Stop on captcha, rate limits, login expiry, permission prompts, abnormal redirects, or repeated timeouts. Use only a platform-validated read-only `controlled_capture` adapter; use direct Chrome control to verify one failed or ambiguous read, not to bypass a platform restriction.
- Do not like, follow, comment, post, evade controls, or imitate people to bypass safeguards.
- Save run artifacts in the user's current working directory, never in the Skill folder.
- Do not package credentials, sessions, private data, customer material, internal brands, or proprietary conclusions.

Lead with the decision and evidence strength. Call single-run results `signal snapshots`; never present scores as predictions of virality or guaranteed market demand.
