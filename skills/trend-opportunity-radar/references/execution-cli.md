# Unified execution entry point

Use `scripts/trend_radar.py` to start a run and diagnose one platform scope. It never installs software, changes credentials, logs in, or performs platform writes.

## Run the synthetic Demo

Use the Demo when a user wants to inspect a complete report before live collection:

```bash
python scripts/trend_radar.py demo --output-dir PATH/TO/DEMO --language en
```

The command produces `trend-report.html`, `trend-report.md`, `opportunities.json`, and `demo-manifest.json`. It is deterministic and idempotent: an identical rerun keeps the existing files, while a non-matching file in the destination stops the command instead of overwriting it. Every format marks the output as synthetic and not a live platform conclusion. The Demo calls the formal Profile report builder and renderers, but it does not create a live `run-manifest.json`, satisfy a sampling contract, or enter monitoring.

## Initialize the two minimum inputs

`init` persists a topic and platform without collecting anything:

```bash
python scripts/trend_radar.py init \
  --topic "AI support for small online shops" \
  --platform x \
  --output-dir PATH/TO/REQUEST

python scripts/trend_radar.py start \
  --request PATH/TO/REQUEST/research-request.json \
  --output-dir PATH/TO/RUN
```

The request file contains no platform data, credentials, session, or capability claim. `start --request` compiles it into the same frozen context and preflight flow as `start --prompt`; explicit command-line platform, intent, or language values may refine the initialized defaults but do not bypass validation.

## Start a run

```bash
python scripts/trend_radar.py start \
  --prompt "Analyze AI travel planning on X for content opportunities." \
  --output-dir PATH/TO/RUN
```

The command freezes `research-context.json`, creates and validates `subject.json`, writes a redacted `environment-doctor.json`, and returns `run-manifest.json` with exactly one current state and one next action.

`run-manifest.json` also includes `prerequisites`. Surface its message only when `required` is true. A ready environment deliberately returns an empty message so repeat users are not forced through setup instructions on every run.

Pass an adapter status only after the corresponding read-only preflight has actually run:

```bash
python scripts/check_collection_adapter.py \
  --adapter opencli \
  --platform x \
  --output PATH/TO/opencli-status.json \
  --require-ready
```

For OpenCLI, `--platform` must match the current research platform. Normal runs never probe unrelated platforms. The omitted-platform mode exists only for backward-compatible diagnostics.

```bash
python scripts/trend_radar.py start \
  --prompt "Analyze AI travel planning on X for content opportunities." \
  --status PATH/TO/opencli-status.json \
  --output-dir PATH/TO/RUN
```

Use `--allow-pilot` only after explicit user opt-in for a Beta or pilot platform. Repeating the identical start request is idempotent. Reusing the directory for a different request is rejected.

Current start states:

- `clarification_required`: ask the single generated question.
- `pilot_opt_in_required`: obtain explicit consent before a pilot live route.
- `preflight_required`: execute the platform's real read-only capability probe.
- `import_required`: use a compliant structured dataset or repair the diagnosed live capability.
- `query_plan_required`: generate the three frozen query layers, then continue with the platform adapter and shared orchestrator.

## Resume a run

After every completed stage, call the same deterministic entry point again:

```bash
python scripts/trend_radar.py resume --run-dir PATH/TO/RUN
```

`resume` inspects the frozen run in strict order and returns the first missing or stale required artifact. It will not advance past an in-progress sampling contract, an unreviewed retained signal, a missing or stale route proof, inconsistent report formats, or a failed/stale HTML visual-QA receipt. This makes the workflow independent of whether the host model remembers every internal step.

Resume states after query planning are `collection_required`, `semantic_review_required`, `normalization_required`, `cluster_plan_required`, `clustering_required`, `scoring_required`, `decision_synthesis_required`, `route_proof_required`, `report_required`, `visual_qa_required`, and `complete`. Execute only the returned `next_action`, create its listed `required_artifacts`, then call `resume` again. Do not infer completion from the existence of a later file.

By default, `resume` directly runs safe deterministic stages when their required inputs already exist: normalization, materializing an explicit cluster plan, cluster auditing, scoring, frozen-route proof, and three-format report generation. It stops before semantic review, authoring the cluster configuration, decision synthesis, browser collection, and visual QA because those stages require model judgment, a live authorized environment, or actual visual inspection. Use `--no-execute` to inspect the next state without running deterministic stages. For a frozen split-adapter route, repeat `--receipt role=PATH` with each required secondary receipt.

Every passed stage writes an immutable SHA-256 receipt under `.trend-radar-receipts/`. Re-running `resume` is idempotent: completed deterministic outputs are not regenerated. If an upstream or output artifact changes after its receipt is recorded, the run stops instead of silently blessing the changed chain; create a new run or perform an explicitly reviewed migration rather than deleting audit receipts.

During collection, `wait_for_cooldown` means the active query and evidence ledger are preserved after a platform rate limit. Do not restart the run or repeat completed queries. Invoke the orchestrator again after `retry_not_before`; it resumes the same query.

`start` is the stable front door, not permission to collect. It prepares the run and routes the next authorized step. `resume` is the required continuation gate. Collection remains bounded by the platform adapter, sampling contract, pacing ledger, and safety stops.

## Monitor compatible completed runs

After a run reaches `complete`, use the monitoring subcommands to freeze a baseline, append newer compatible completed runs, and compare the latest two snapshots:

```bash
python scripts/trend_radar.py monitor create --run-dir PATH/TO/RUN --monitor-dir PATH/TO/MONITOR
python scripts/trend_radar.py monitor append --monitor-dir PATH/TO/MONITOR --run-dir PATH/TO/NEW-RUN
python scripts/trend_radar.py monitor compare --monitor-dir PATH/TO/MONITOR
```

Read [monitoring.md](monitoring.md) for the compatibility, cadence, idempotency, scheduling, stop, and interpretation contract. These commands do not create a scheduled task.

## Prove the frozen route before reporting

After collection, detail backfill, comment or media enrichment, and semantic review have produced the final signal snapshot, bind that exact file to the frozen route:

```bash
python scripts/prove_collection_route.py \
  --manifest PATH/TO/RUN/run-manifest.json \
  --signals PATH/TO/RUN/scored-signals.json \
  --output PATH/TO/RUN/route-execution-proof.json \
  --require-passed
```

When search and detail use the same registered adapter, the immutable final signal ledger can prove both roles. For a split route, provide the actual secondary adapter artifact, for example `--receipt detail=PATH/TO/DETAIL-RECEIPT.json`. Comments and media require a matching role receipt only when their evidence is present in the final snapshot.

The proof binds the request, frozen route, adapter roles, final signals hash, evidence counts, and receipt hashes. `generate_profile_report.py` automatically enforces it whenever `research-context.json` belongs to a unified live run. A missing or stale proof is an internal incomplete state, not a platform conclusion and not a user-facing research limitation. Historical snapshot replay and explicit structured import remain compatible when no frozen live route is present.

## Diagnose a platform

```bash
python scripts/trend_radar.py doctor --platform x --language en
python scripts/trend_radar.py doctor --platform facebook --allow-pilot --status PATH/TO/facebook-status.json --language zh-CN
```

Use `--require-live` when automation must stop unless a live adapter is ready. Without it, the command reports the structured-import fallback.

Platform-specific browser probes are validated before their status is passed to doctor. For example:

```bash
python scripts/check_instagram_topic_adapter.py --probe instagram-probe.json --output instagram-status.json
python scripts/check_facebook_topic_adapter.py --probe facebook-probe.json --output facebook-status.json --require-ready
```

The user-facing doctor output intentionally excludes CLI paths, raw stdout/stderr, cookies, browser state, and internal diagnostics. Preserve those only in the adapter's restricted preflight artifact when needed for audit.

## Python runtime

Try `python3`, `py`, or `python`. A host Agent may use its documented bundled Python 3 runtime. Do not install Python automatically. If no Python 3 runtime is available, report the missing deterministic runtime and do not claim that the scripts executed.
