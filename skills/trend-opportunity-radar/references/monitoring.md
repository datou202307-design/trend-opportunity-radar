# Compatible snapshot monitoring

Use monitoring only after a research run reaches `complete`. Monitoring repeats the same constrained study; it is not a background scraper and does not predict demand or virality.

## Create a cycle

```bash
python scripts/trend_radar.py monitor create \
  --run-dir PATH/TO/COMPLETED-RUN \
  --monitor-dir PATH/TO/MONITOR
```

The command freezes the subject, platform, research intent, Decision Profile, analysis unit, language, market, mode, exact query plan, score version, and engagement-weight version. X and TikTok default to a three-day cadence; other platforms default to seven days. The default cycle contains four snapshots including the baseline.

This command records a cadence recommendation but does not create an operating-system, Codex, or third-party scheduled task. Set up a schedule only after the user explicitly confirms it and the scheduling tool reports success. Never copy browser sessions, cookies, tokens, or raw live data into the Skill or scheduler payload.

## Append a completed snapshot

Run a new study through `start` and `resume` until it is complete, preserving the frozen monitoring inputs. Then append it:

```bash
python scripts/trend_radar.py monitor append \
  --monitor-dir PATH/TO/MONITOR \
  --run-dir PATH/TO/NEW-COMPLETED-RUN
```

The new run must be newer and exactly compatible with the frozen fields. A duplicate snapshot is skipped without changing monitor state. A changed subject, query plan, language, market, Profile, analysis unit, mode, score version, or engagement-weight version starts a new monitoring cycle; never force unlike snapshots into one time comparison.

`monitor.json` is the persistent state and `monitor-runs.jsonl` is the append-only execution log. Stop after the target snapshot count, on access or rate-limit errors, or when compatibility fails. Do not turn a collection failure into a zero-result snapshot.

## Compare the latest two snapshots

```bash
python scripts/trend_radar.py monitor compare \
  --monitor-dir PATH/TO/MONITOR
```

At least two compatible snapshots are required. The command generates `monitor-compare.json`, `monitor-compare.md`, and `monitor-compare.html`. It compares audited topic identities and describes only:

- new in the current snapshot;
- more visible in the current snapshot;
- persistent;
- less visible in the current snapshot;
- not observed again.

An observed-heat change of at least five points is the candidate threshold for “more visible” or “less visible.” Evidence confidence remains separate. Never total or average platforms, and never rewrite snapshot differences as demand growth, causality, market size, or future performance.

Inspect the generated HTML over loopback HTTP on desktop and mobile before delivery. Keep the plain-language summary and action implications visible; keep exact hashes, compatibility fields, and machine state in the expandable audit or JSON.
