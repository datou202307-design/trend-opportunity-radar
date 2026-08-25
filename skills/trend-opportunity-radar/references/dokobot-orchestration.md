# DokoBot collection orchestration

Use DokoBot as a read-only `controlled_capture` adapter. It may be the primary search adapter on a registered platform or a separately preflighted detail enhancer after another adapter performed search. Let the deterministic state file choose the next action; never treat one page read or one curated result list as a completed sample.

## Preflight the adapter

Run the read-only diagnostic before preparing the query plan:

```bash
python scripts/check_collection_adapter.py \
  --adapter dokobot \
  --output adapter-status.json
```

Proceed only when `status` is `ready`. Distinguish these failures:

- `cli_not_found`: no executable was resolved;
- `cli_not_visible`: a sandbox could not inspect a common installation location;
- `cli_permission_denied`: the entry point exists but execution was denied;
- `cli_timeout` or `cli_error`: the entry point did not respond correctly;
- `browser_not_connected`: the CLI works but no local Chrome/Edge device is connected.

PATH discovery is not final evidence in a sandbox. For the first three statuses, run `dokobot --version` and `dokobot doko list` as separate, explicitly authorized commands once. If they succeed, rerun `check_collection_adapter.py --require-ready` with the required read/execute approval and use its output; do not hand-edit `adapter-status.json`. If they fail, follow the adapter degradation order. Do not auto-install, copy cookies, or request credentials in chat.

## Prepare a query plan

Create `query-plan.json` with platform-native search URLs. Standard mode allows 3–9 total queries. Start with one probe in each layer; add only orchestrator-requested recovery queries:

```json
{
  "queries": [
    {"id": "baseline-1", "term": "...", "layer": "platform_baseline", "url": "https://..."},
    {"id": "category-1", "term": "...", "layer": "category", "url": "https://..."},
    {"id": "bridge-1", "term": "...", "layer": "subject_bridge", "url": "https://..."}
  ]
}
```

Initialize and request the next action:

```bash
python scripts/orchestrate_dokobot_collection.py init \
  --state collection-state.json \
  --snapshot raw-signals.json \
  --plan query-plan.json \
  --adapter-status adapter-status.json \
  --platform x \
  --mode standard
```

The returned `dokobot_command` is an audit preview. For live collection, execute it through the deterministic wrapper so DokoBot's console-only session metadata is not lost:

```bash
python scripts/run_dokobot_capture.py \
  --state collection-state.json \
  --metadata-output capture-metadata.json
```

The wrapper preserves the raw page output, stdout, stderr, exit state, timeout state, requested-command hash, and `Session:` value. Each numbered capture gets its own `.capture.json`, `.stdout.txt`, and `.stderr.txt` files beside the raw output. `capture-metadata.json` is only the current handoff pointer; do not hand-edit it or treat it as the historical log.

## Record every capture chunk

Convert only visible results from the wrapper's `raw_artifact` into `capture-extraction.json`:

```json
{
  "observed_result_keys": ["stable-post-url-or-platform-id"],
  "signals": [],
  "detail_open_keys": []
}
```

- Count every newly visible result card in `observed_result_keys`, including discarded cards.
- Use a stable platform ID or canonical URL as the key; otherwise use a deterministic hash of author, text, and visible time.
- Put retained structured evidence in `signals`. Do not invent fields absent from the raw output.
- Add a key to `detail_open_keys` only after opening and reading the direct detail page.
- Never place `query_id`, session, continuation, timeout, raw-artifact, stop, or execution fields in the extraction file. `record-capture` rejects attempts to override wrapper metadata.
- The wrapper treats a returned `Session:` value as continuation available. Absence of a session remains unknown unless explicit terminal evidence exists; it is never inferred from a short list.

Record the chunk:

```bash
python scripts/orchestrate_dokobot_collection.py record-capture \
  --state collection-state.json \
  --metadata capture-metadata.json \
  --extraction capture-extraction.json
```

If a successful raw capture contains no visible result cards and explicit terminal evidence is available, preserve it and use the compatibility `record-chunk` path with that evidence. Otherwise leave continuation unknown and let the wrapper-driven retry policy decide; never invent a zero-result terminal state.

```json
{
  "query_id": "bridge-3",
  "read_status": "success",
  "session_id": "",
  "can_continue": false,
  "continuation_status": "exhausted",
  "terminal_evidence": "zero_results",
  "observed_result_keys": [],
  "signals": [],
  "detail_open_keys": [],
  "raw_artifact": "captures/bridge-3-001.json",
  "stop_reason": "zero_results",
  "hard_stop": ""
}
```

The orchestrator records a genuine zero-result query as `completed_with_zero_results`. A query that twice lacks usable continuation metadata or twice times out is recorded as `completed_partial`, then the next planned query starts. If a continuation read says `Session not found or expired`, the orchestrator first clears the session and restarts the same query once from its original URL with one screen. It deduplicates cards already observed before the expired session and records `session_recovery_failed` only if the fresh restart also fails. These are query-level limitations, not platform-wide stops.

Call `run_dokobot_capture.py` again whenever the next action is `continue_query` or `start_query`; always follow the returned `query.id`. The orchestrator finalizes each query at its bounded target, after explicit terminal evidence, or as partial after its local retry limit, then atomically appends it to `raw-signals.json` and continues the plan.

## Review before recovery

After the initial three layers finish, the orchestrator returns `review_signals` whenever retained signals are still mechanically unreviewed. Review the canonical snapshot with `apply_semantic_review.py`, write the reviewed snapshot to a new file, and pass `--state collection-state.json` so the tool verifies the input identity, preserves snapshot history, and advances the run to that reviewed output. Invoke `next` again after review. The orchestrator must never interpret `unreviewed` as irrelevant or spend recovery-query budget before this step. Never hand-edit the state snapshot path.

## Recover low-yield plans

When the initial plan ends below the contract and query budget remains, the orchestrator returns `replan_queries` instead of `blocked`. Its `recovery` object lists remaining query budget, deficient layers, per-layer deficits, and rewrite rules. Create a new plan containing only non-duplicative queries and add it:

```bash
python scripts/orchestrate_dokobot_collection.py add-queries \
  --state collection-state.json \
  --plan recovery-query-plan.json
```

Rewrite stacked queries into one platform-native problem, outcome, or workflow phrase at a time. Use at most four words in a recovery term. Cover as many distinct deficient layers as the remaining query slots permit, and add a failure, objection, or human-handoff query when counterevidence is low. The command rejects long restacked terms, duplicate IDs/terms/URLs, plans beyond the remaining budget, and plans that leave coverable deficient layers untouched.
It may also reopen an older `blocked` state when the stop reason is `sampling_contract_unmet:*` with unused query budget, or when a legacy `continuation_unresolved`/`repeated_timeout` state still has planned queries pending. Safety or access blocks cannot be reopened this way.

Before spending another query or finalizing `blocked`, the orchestrator may return `backfill_details` when retained signals already contain eligible detail URLs. For X, execute the deterministic runner; do not hand-author successful detail records:

```bash
python scripts/run_dokobot_detail_backfill.py \
  --state collection-state.json \
  --results-output detail-results.json
```

Each attempt preserves the raw page, console stdout/stderr, execution metadata, exact command hash, and either the mechanically extracted post or an exact stop reason. Successful details merge into the canonical snapshot by stable content identity without increasing query, observed, or unique counts. `record-details` remains available only for imported compatibility fixtures. Continue calling `next` until the contract is complete, no eligible retained link remains, or a safety/access stop requires user action.

For an explicitly enabled TikTok pilot, OpenCLI may remain the frozen search adapter while DokoBot is frozen as `detail_adapter`. The runner requires the requested content ID and author route to match the rendered page, records the resolved `video|photo` format, preserves visible publication and interaction fields, and retains at most five comment bodies only when they are actually visible in the bounded read. A comment total without comment bodies remains a metric. A mixed recommendation page, missing target block, changed content identity, captcha, login request, or abnormal redirect never counts as a successful detail.

## Obey the terminal decision

- `complete`: all sampling minima and layer coverage passed.
- `review_signals`: collected evidence needs semantic review before recovery or detail decisions.
- `replan_queries`: the current plan ended below a minimum but lawful query budget remains.
- `blocked`: the total query budget ended below a minimum or a platform-wide safety/access stop occurred. A single query's missing session or repeated timeout does not immediately block the run.

Do not replace `blocked` with a smaller mode, pad weak signals, or manually edit totals. `collection-state.json` is transient control state; `raw-signals.json.collection` remains the only canonical collection ledger.

The ledger and report validator reject missing raw files and missing execution evidence. Failed reads may legitimately have no raw page output, but their immutable per-capture metadata and stdout/stderr must exist; do not add the requested raw path to `raw_artifacts` when the CLI never created it. Every execution must use distinct audit paths.

Do not normalize, cluster, or render a report while the normalized collection status is `in_progress`. Finalize every active query first, including zero-result queries.
