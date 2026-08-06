---
name: trend-opportunity-radar
description: Analyze a research topic on one platform for evidence-backed trend opportunities. Use when the user asks to analyze a product, business opportunity, idea, problem, audience need, or project on Xiaohongshu, X, or another single platform; collect or import platform signals; calculate an evidence heat index with data coverage; identify topic-to-subject opportunities, counterevidence, risks, and missing-data tasks; or compare compatible snapshots without claiming viral prediction.
---

# Trend Opportunity Radar

Analyze a research topic on one platform. Treat products as fact-bound subjects and business opportunities or ideas as hypotheses to validate.

## Start with minimum input

Require only:

1. A comprehensible research topic.
2. One target platform.

Accept a product file or URL, a business opportunity, an early idea, a user problem, an audience need, or a project description. Infer language, region, audience, query terms, time window, source mode, sample size, and output paths when safe. State material assumptions in the result instead of asking the user to fill technical fields.

Use this canonical invocation pattern:

`Analyze [research topic] on [platform] for trend opportunities.`

Ask one concise question only when the topic or platform cannot be determined, browser or paid-API authorization is required, or a choice would materially change the result. Never ask for passwords, cookies, session data, or tokens in chat.

## Follow the workflow

### 1. Build the subject brief

Create a UTF-8 JSON object with:

- `name`
- `subject_type`: `product`, `opportunity`, `idea`, `problem`, or `project`
- `summary`
- `facts`: sourced statements only
- `hypotheses`: user premises and model inferences
- `audiences`
- `scenarios`
- `constraints`
- `source_refs`

For an opportunity or idea, never move a statement from `hypotheses` to `facts` without external evidence or explicit human confirmation.

### 2. Select one evidence source

Use the best available mode in this order:

1. `authorized_api`
2. `customer_export`
3. `controlled_capture`
4. `public_web`
5. `historical_snapshot`

Read [platform-adapters.md](references/platform-adapters.md) before selecting a source. For a logged-in or dynamic browser, also read [browser-collection.md](references/browser-collection.md).

Do not combine multiple platforms into one heat list or score. Run separate analyses when the user requests multiple platforms.

### 3. Collect and preserve signals

Keep raw evidence unchanged. Record query term, query layer, source mode, capture time, stable URL, visible metrics, author conditions, limitations, and permission scope.

Use three query layers:

- `platform_baseline`: platform-native attention and language
- `category`: the task, problem, audience, or category
- `subject_bridge`: direct terms connecting the topic to the research subject

Collect counterexamples and adoption barriers, not only supporting results. A single capture is a `snapshot`; claim rising, stable, or falling only from comparable repeated snapshots using the same platform, source, query definition, and time window.

### 4. Normalize deterministically

Read [signal-schema.md](references/signal-schema.md). Normalize JSON or CSV input:

```bash
python scripts/normalize_signals.py --input raw-signals.json --output normalized-signals.json --platform x --source-mode controlled_capture
```

The script uses only the Python standard library, normalizes common metric aliases, creates stable deduplication hashes, and rejects multi-platform snapshots.

Use an available Python 3 interpreter. If `python` is unavailable, try `python3`, `py`, or a documented bundled runtime before asking the user; if no Python runtime exists, perform the schema-equivalent transformation with the Agent's available local tools and disclose that deterministic scripts were not executed.

### 5. Calculate evidence heat

Read [scoring-contract.md](references/scoring-contract.md), then run:

```bash
python scripts/calculate_evidence_index.py --input normalized-signals.json --output scored-signals.json
```

Treat the index as evidence strength and observed heat, not viral prediction. Missing dimensions contribute zero; never redistribute missing weights to manufacture a full score. Always show `data_coverage`, `score_version`, `missing_fields`, source mode, and limitations.

### 6. Form opportunity hypotheses

Cluster semantically related signals without overwriting original samples. For each proposed opportunity, provide:

- `title`
- `topic_key`
- `audience`
- `task_gap`
- `subject_entry`
- `expected_action`
- `support_refs`
- `counter_refs`
- `risk_boundaries`
- `missing_evidence`

Pass five gates before marking a hypothesis review-ready:

1. Audience relevance
2. Task continuity within one or two steps
3. Subject truth or explicit hypothesis boundary
4. At least one platform evidence reference plus counterevidence review
5. A concrete next validation action

If semantic evidence is insufficient, keep the opportunity as a candidate instead of filling gaps with generic advice.

### 7. Generate data-gap tasks and report

```bash
python scripts/detect_data_gaps.py --input scored-signals.json --output data-gaps.json
python scripts/generate_opportunities.py --subject subject.json --signals scored-signals.json --opportunities opportunities.json --json-output trend-opportunities.json --markdown-output trend-report.md
```

Omit `--opportunities` only when a cautious generic fallback is acceptable. Read [output-schema.md](references/output-schema.md) before final delivery.

## Preserve evidence boundaries

Label statements as one of:

- platform fact
- subject fact
- user premise
- model inference
- human confirmation

Keep stable links near the claims they support. Report access failures and partial captures. Do not fabricate unavailable content, comments, metrics, trends, compatibility, revenue, demand, or product capability.

## Operate safely

- Keep browser collection read-only, single-threaded, small-batch, and depth-limited.
- Stop on captcha, rate limits, login expiry, permission prompts, abnormal redirects, or repeated timeouts.
- Do not like, follow, comment, post, evade controls, or imitate human behavior to bypass safeguards.
- Store run data in the user's current working directory, not inside this skill folder.
- Do not package credentials, sessions, private customer data, or proprietary case conclusions.

## Deliver the outcome

Lead with:

1. Research topic and assumptions
2. Platform heat topics
3. Trend × research topic opportunities
4. Supporting and counterevidence
5. Risks and boundaries
6. Recommended validation actions
7. Data gaps and recollection tasks

Call single-capture results `signal snapshots`. Never present the score as a prediction of future virality or guaranteed market demand.
