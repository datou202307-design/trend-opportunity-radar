# Unified execution entry point

Use `scripts/trend_radar.py` to start a run and diagnose one platform scope. It never installs software, changes credentials, logs in, or performs platform writes.

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

During collection, `wait_for_cooldown` means the active query and evidence ledger are preserved after a platform rate limit. Do not restart the run or repeat completed queries. Invoke the orchestrator again after `retry_not_before`; it resumes the same query.

`start` is the stable front door, not permission to collect. It prepares the run and routes the next authorized step. Collection remains bounded by the platform adapter, sampling contract, pacing ledger, and safety stops.

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
