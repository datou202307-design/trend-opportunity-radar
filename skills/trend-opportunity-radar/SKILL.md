---
name: trend-opportunity-radar
description: Analyze one research topic on one platform as a constrained, evidence-backed decision study. Use to find business opportunities, monitor brand sentiment, study competitor users, find content opportunities, validate product demand, organize local research runs, or compare compatible completed snapshots without predicting virality.
---

# Trend Opportunity Radar

Turn one topic's platform signals into a decision answer, reviewable evidence, and a concrete next validation action. Treat product facts as facts and ideas, opportunities, demand, and trend direction as hypotheses until evidence supports them.

## Minimum input

Require only a comprehensible research topic and one platform. The subject may be a product, brand, competitor, problem, business opportunity, idea, audience need, or project.

Default invocation:

`Analyze [research topic] on [platform] for trend opportunities.`

Infer the report language from the request language. Infer the decision goal, audience, region, time window, and collection mode when safe. Ask one concise question only when the topic or platform is indeterminate, the intended decision is materially ambiguous, or login/paid access needs authorization. Never request passwords, cookies, sessions, or tokens in chat.

## Preview safely before live research

When the user asks to try, preview, evaluate, or understand the output before connecting a platform, generate the bundled synthetic Demo:

```bash
python scripts/trend_radar.py demo --output-dir PATH/TO/DEMO --language en
```

Use `--language zh-CN` for Chinese. The Demo requires no platform login or adapter and must preserve its synthetic marker in JSON, Markdown, HTML, and `demo-manifest.json`. It reuses the formal report generator but is never platform evidence, a completed live run, or proof that the sample subject has real demand. Do not remove the marker or mix Demo artifacts into monitoring or platform comparison.

For a first live study that should persist the two minimum inputs, initialize a request:

```bash
python scripts/trend_radar.py init --topic "TOPIC" --platform PLATFORM --output-dir PATH/TO/REQUEST
python scripts/trend_radar.py start --request PATH/TO/REQUEST/research-request.json --output-dir PATH/TO/RUN
```

`init` saves no platform content or login state. It feeds the same `start` entry point below; it does not bypass preflight, sampling, review, or report gates.

## Start through the unified entry point

Read [execution-cli.md](references/execution-cli.md), then start the run:

```bash
python scripts/trend_radar.py start \
  --prompt "ORIGINAL USER REQUEST" \
  --output-dir PATH/TO/RUN
```

Use `python3`, `py`, `python`, or a documented bundled Python 3 runtime. Do not install a runtime or adapter without authorization.

Follow the single `state` and `next_action` in `run-manifest.json`:

- Ask the generated question for `clarification_required`.
- Obtain explicit user opt-in before adding `--allow-pilot`.
- For `preflight_required`, run the selected platform's actual read-only capability probe, then restart with its status file.
- For `import_required`, use a lawful structured dataset or resolve the named login/connection action.
- For `query_plan_required`, continue with the frozen context and collection workflow below.

After producing the required artifact for any state, run:

```bash
python scripts/trend_radar.py resume --run-dir PATH/TO/RUN
```

Execute only the returned `next_action`, create the listed `required_artifacts`, and call `resume` again. Do not skip ahead because a later artifact happens to exist, and do not claim delivery until the manifest state is `complete`. `resume` is the deterministic guard against weaker host models omitting collection, full semantic review, route proof, report consistency, or browser visual QA.

Allow `resume` to run its safe deterministic stages by default. It must stop for live collection, full semantic review, cluster configuration, decision synthesis, and real browser visual QA. Do not delete or edit `.trend-radar-receipts/` to force progress: those immutable hashes prove which inputs and outputs actually passed each stage. Use `--no-execute` only for diagnosis.

Treat `collection_route` as an execution contract, not a tool suggestion. Keep its research surface and its search, detail, comment, and media roles separate. Execute each available role through the frozen adapter and runner, and preserve the matching receipt. Do not replace a ready route with generic browsing, public-web search, or another installed collector merely because it is easier. A different live executor requires a new successful preflight and a newly frozen route; structured import must be explicit. Never issue a standard live report when the evidence ledger does not match the frozen route or its required receipts.

After the final reviewed signal snapshot is frozen, run `scripts/prove_collection_route.py` as documented in [execution-cli.md](references/execution-cli.md). The standard report generator automatically rejects a unified live run whose proof is missing, stale, adapter-mismatched, or bound to different signals. Do not hand-author, repair, or reinterpret the proof; resolve the named collection role and rerun the deterministic command.

If `prerequisites.required` is true, show its one concise `message` before asking the user to restore the browser, platform login, read-only adapter, or connected service. Do not show a generic setup warning when it is false. Re-run the same start request after the user completes the named action; never ask them to repeat the research topic.

Never infer readiness from PATH lookup, an installed extension, a browser tab, or login appearance. A successful redacted read probe is required for the capability the run will use. Keep recoverable adapter diagnostics internal unless the user must restore login, connect a browser, approve a narrow read, or choose import fallback.

## Route only the relevant instructions

Always read:

- [research-context.md](references/research-context.md) and [decision-profile-contract.md](references/decision-profile-contract.md) for the selected decision goal.
- [platform-adapters.md](references/platform-adapters.md) and [platform-adapter-registry.json](references/platform-adapter-registry.json) for capability and release status.
- [sampling-contract.md](references/sampling-contract.md) before collection.

Then read only the references needed by this run:

- OpenCLI on X, Xiaohongshu, YouTube, or TikTok: [opencli-orchestration.md](references/opencli-orchestration.md).
- DokoBot collection or detail fallback: [dokobot-orchestration.md](references/dokobot-orchestration.md).
- Dynamic or signed-in browser work: [browser-collection.md](references/browser-collection.md) and [collection-pacing-contract.md](references/collection-pacing-contract.md).
- Instagram Hashtag topic research: [instagram-hashtag-topic-adapter.md](references/instagram-hashtag-topic-adapter.md).
- Instagram known-account pilot: [instagram-account-adapter.md](references/instagram-account-adapter.md).
- Facebook Posts topic Beta: [facebook-topic-adapter.md](references/facebook-topic-adapter.md).
- Reddit topic research through a connected third-party MCP: [reddit-mcp-adapter.md](references/reddit-mcp-adapter.md).
- TikTok visible-comment enhancement: [tiktok-comment-enrichment.md](references/tiktok-comment-enrichment.md).
- Video, subtitle, ASR, or OCR evidence: [video-evidence-contract.md](references/video-evidence-contract.md).

Chrome control, OpenCLI, DokoBot, and third-party MCP services are optional adapters, not bundled dependencies or evidence of official platform authorization.

## Collect one platform with an immutable ledger

Use one platform per run. Cross-platform work consists of completed independent reports; never mix samples or scores during collection.

Create three query layers from the frozen Decision Profile:

- `platform_baseline`: platform-native attention and language.
- `category`: the audience task, problem, or category.
- `subject_bridge`: the concrete failure, outcome, objection, or capability connecting the subject to the platform signal.

Create `raw-signals.json` before searching. Count observed cards before filtering and separately record retained signals, duplicates, opened details, discarded results, independent authors, direct sources, counter signals, and query terminal states. Search cards remain `search_card` until their matching detail is opened and verified.

Use `scripts/orchestrate_collection.py` for the deterministic query loop. Start `standard` mode unless the user explicitly requests a quick scan or a lawful source constraint requires `quick`; use `deep` only when the source can support it. Do not silently downgrade.

Collect sequentially with the shared pacing ledger across query boundaries. Preserve every completed query and resume from its checkpoint. A platform rate limit pauses the active query, saves a `retry_not_before` time, and resumes that same query only after the cooldown; it must not finalize an empty query or require the user to re-enter the topic or log in again. Do not repeat successful queries, exceed the frozen query budget, run browser reads in parallel, or invent additional searches merely to fill a quota. A timeout, blank shell, wrong redirect, parser miss, or connection loss is not a zero-result finding. Only a verified target identity plus an explicit platform empty state can support zero results.

Every retained signal requires independent semantic review as `direct`, `adjacent`, or `weak`, plus shared `support`, `counter`, or `neutral` direction and the selected Profile's evidence role. Reviews must state a concrete reason. Unreviewed signals cannot satisfy sampling gates or generate findings. When the orchestrator returns `review_signals`, review the existing snapshot before any recovery query; never treat `unreviewed` as irrelevant.

The 80% standard and 90% deep coverage thresholds guide collection recovery only. Before a standard or deep run can complete or generate its formal report, every retained signal—including signals added by recovery queries—must have completed semantic review.

If the orchestrator requests detail backfill, exhaust eligible retained identities using the selected adapter before reporting. Comments are bounded qualitative evidence attached to an opened detail: they never increase the trend sample count and must be reviewed before informing a finding. Keep raw evidence unchanged and keep the only copy outside browser memory.

When visible comment likes or reply counts exist, apply the candidate prominence and diversity rule in [comment-evidence-contract.md](references/comment-evidence-contract.md). Use engagement to surface more visible discussion while preserving support, counter, neutral, and category diversity. Never equate popular comments with truthful, representative, or credible comments.

Treat reviewed comments as a separate demand-discovery layer. Assign the same stable `demand_topic_key` only when comments describe materially the same need, pain, question, workaround, intent, objection, outcome, or comparison. `apply_comment_review.py` may mark a topic `eligible_comment_demand` only after it recurs across at least two independent parent posts and two identified independent commenters; this may become a finding candidate in any of the five research Profiles. Cross-post recurrence without captured commenter identity remains `cross_post_recurrence_unverified_commenters`, a visible validation candidate rather than a qualified conclusion. A high-engagement comment in one thread is only `salient_single_thread`: surface it as an attitude or validation hypothesis, never as broad demand. Comment-derived topics do not increase post trend volume, and their support/counter direction must remain visible.

## Normalize, score, and form findings

Read [signal-schema.md](references/signal-schema.md), [comment-evidence-contract.md](references/comment-evidence-contract.md), [scoring-contract.md](references/scoring-contract.md), and [clustering-contract.md](references/clustering-contract.md). Use the deterministic scripts rather than hand-maintained totals:

```bash
python scripts/normalize_signals.py --input raw-signals.json --output normalized-signals.json --platform PLATFORM --source-mode SOURCE_MODE
python scripts/prepare_comment_review.py --input normalized-signals.json --output comment-review-queue.json
python scripts/calculate_evidence_index.py --input REVIEWED_SIGNALS.json --output scored-signals.json
python scripts/detect_data_gaps.py --input scored-signals.json --output data-gaps.json
python scripts/audit_clusters.py --input normalized-signals.json --plan cluster-plan.json --output clustered-signals.json --research-context research-context.json
python scripts/validate_profile_decisions.py --research-context research-context.json --signals scored-signals.json --findings profile-findings.json
```

Apply comment review when the queue is non-empty. Run the clustering audit before a topic can generate a finding. Keep support and counter references disjoint after URL normalization.

After comment review, read `comment_demand_topics` before drafting findings. Use eligible recurring comment topics to sharpen the user task, unmet need, objection, message angle, competitor gap, or validation action required by the selected Profile. Do not silently omit eligible topics; either incorporate them into a qualified finding or explain in the audit why they were not decision-relevant. Keep `salient_single_thread` items in the report's validation layer rather than promoting them to conclusions.

Report `observed_heat` and `evidence_confidence` separately. Missing dimensions contribute zero; never redistribute their weights. Platform engagement weights are calibration assumptions, not cross-platform exchange rates. A single snapshot cannot establish growth, decline, virality, market demand, traffic, revenue, or causality.

Show one to three qualified findings when the evidence supports them. One is valid; never pad the count. Each finding must name the audience, concrete situation or task, why it matters, supporting and counter evidence, an executable validation action, success metric, stop condition, and human boundary. Only a human may mark a finding confirmed.

## Generate and verify the report

Read [output-schema.md](references/output-schema.md), then generate JSON, Markdown, and self-contained HTML from the same inputs:

```bash
python scripts/generate_profile_report.py \
  --research-context research-context.json \
  --signals scored-signals.json \
  --findings profile-findings.json \
  --json-output profile-report.json \
  --markdown-output profile-report.md \
  --html-output profile-report.html
```

Lead with the direct decision answer and up to three concrete actions. Show the qualified findings next. Put the collection basis, platform-reading guidance, recurring comment topics, exact score values, source evidence, formulas, machine states, and raw audit fields behind progressive disclosure or in JSON. Visible score labels should communicate plain-language grades; retain exact audited values in the expandable evidence layer.

Use platform-native interpretation without changing shared gates:

- Facebook emphasizes verified public-post discussion, user experiences, objections, and reviewed visible comments.
- Instagram emphasizes Post/Reel/Carousel formats, captions, verified media or visual evidence, and then comments. Displayed Hashtag volume describes visible content supply, not search demand or trend growth.
- Video platforms distinguish search-card facts from verified subtitle, ASR, OCR, and visual evidence.

Write in the user's language and for their likely expertise. Prefer concrete people, situations, meaning, and next actions over research or product shorthand. Never expose adapter paths, internal state keys, or a collection repair task as though it were the user's responsibility. Pair every visible limitation with what current evidence still supports, what it cannot support, and the concrete resolution path.

Validate all three artifacts and inspect HTML through temporary loopback HTTP on desktop and a narrow mobile viewport. Confirm the title, first screen, research basis, findings, evidence sections, console, and absence of horizontal overflow. Do not hand-edit generated HTML or Markdown; fix the reusable generator and regenerate.

## Compare or monitor without overstating trend

For a cross-platform comparison, require completed reports with the same subject, research intent, Profile version, analysis unit, and report language. Keep each platform's collection basis, heat, and confidence separate; never total, average, normalize, or rank them. Use `scripts/generate_platform_comparison.py` and link back to the original reports.

After a single snapshot, recommend optional repeated collection when time change matters: every three days for fast-moving platforms such as X or TikTok, or weekly elsewhere, for four runs by default. Read [monitoring.md](references/monitoring.md), then use `trend_radar.py monitor create`, `append`, and `compare`. Reuse the frozen subject, platform, Profile, analysis unit, language, region, exact query plan, sampling mode, and scoring versions. Never claim monitoring exists until the user confirms it and task creation succeeds.

When the user wants to revisit or organize multiple existing runs, read [workspace.md](references/workspace.md) and build the local research workspace. Treat `run-manifest.json` and `monitor.json` as the sources of truth. Never infer that a scheduled task exists from a cadence recommendation or due date, and never upload workspace contents by default.

## Safety and delivery boundaries

- Prefer `authorized_api → customer_export → controlled_capture → public_web → historical_snapshot`.
- Keep browser work read-only, bounded, sequential, permission-aware, and paced. Stop on CAPTCHA, rate limits, login expiry, permission prompts, abnormal redirects, private content, or repeated timeouts.
- Never like, follow, vote, comment, post, save, publish, evade controls, imitate people to bypass safeguards, or silently borrow an unprobed browser session.
- Save run artifacts in the user's working directory, never inside the Skill.
- Do not package credentials, sessions, private data, customer material, internal brands, live captures, or proprietary conclusions.
- Deliver HTML as the primary human report, Markdown as the portable summary, and JSON as the audit record.

Call every one-run result a signal snapshot. Lead with the decision and evidence strength, not with the research system's limitations.
