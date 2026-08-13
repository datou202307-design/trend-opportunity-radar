# Trend Opportunity Radar

An independent, brand-neutral agent Skill for analyzing evidence-backed trend opportunities for a research topic on one platform.

Current status: **v0.6.0 candidate**. This is a platform-signal and opportunity-research workflow, not a viral-content or traffic prediction system.

## What it does

- Accepts a product, business opportunity, idea, user problem, audience need, or project as the research topic.
- Analyzes one platform at a time, including X, Xiaohongshu, and adapter-defined platforms.
- Imports user-provided data or collects authorized, read-only browser and API signals.
- Normalizes evidence, source links, capture times, metrics, and limitations.
- Uses explicit quick, standard, and deep sampling contracts with a collection ledger.
- Atomically persists each completed query into one canonical raw snapshot.
- Orchestrates DokoBot query progression, session continuation, raw-output retention, and sampling gates.
- Distinguishes successful reads, timeouts, continuation availability, and explicit result exhaustion; first-screen completion or a timed-out read can no longer finalize a query as exhausted.
- Captures DokoBot's console-only session metadata through a deterministic wrapper, preserves immutable per-capture audit files, and restarts an expired continuation once before marking a query partial.
- Diagnoses missing, sandbox-hidden, permission-denied, broken, or browser-disconnected DokoBot environments before collection.
- Separates observed heat from evidence confidence without hiding missing data.
- Downgrades unopened browser search cards and caps confidence for incomplete collection.
- Deduplicates the same platform content across search-card and detail captures while preserving query and source provenance.
- Enforces per-layer observed, unique, detail, semantic-relevance, and subject-bridge evidence gates.
- Requires an explicit, auditable semantic clustering plan before clustered topics can become review-ready.
- Finalizes zero-result queries as auditable ledger entries and refuses to render reports from in-progress collection state.
- Requests short, non-duplicative recovery queries across as many deficient layers as the remaining collection budget permits.
- Excludes failed clusters and duplicate same-topic opportunity cards instead of padding the report to a visual quota.
- Keeps raw audit states in JSON while rendering incomplete evidence as localized research-status guidance rather than a software error.
- Condenses per-signal limitation notes into no more than four decision-impact summaries in human-facing reports while preserving the complete audit list in JSON.
- Recommends an optional, portable follow-up monitoring task so single snapshots can become comparable time series without overwriting history or pretending an automation was created.
- Adapts report language and decision framing to the user's request, research goal, and audience, and pairs every visible evidence gap with current value, boundaries, and a concrete resolution path.
- Backfills eligible retained detail links before reporting, without spending search-query budget, and keeps recoverable internal sampling gates out of human-facing reports.
- Applies a general-audience title readability gate, preserving the audit title while replacing unexplained product jargon with concrete reader-facing language.
- Generates topic-to-subject opportunities, counterevidence, risks, validation actions, and recollection tasks.
- Separates platform facts, user premises, model inferences, and human confirmation.
- Produces a self-contained local HTML report, concise Markdown, and machine-readable JSON.
- Rejects likely encoding corruption and verifies that HTML, Markdown, and JSON were generated from one mutually consistent UTF-8 result.

## Minimum input

Only two inputs are required:

1. A comprehensible research topic.
2. One target platform.

Example prompt:

```text
Use $trend-opportunity-radar to analyze the trend opportunities for an AI assistant that fills last-minute restaurant tables on X.
```

Chinese invocation:

```text
分析研究主题在某平台的趋势机会。
```

The agent should infer safe defaults for language, region, audience, query terms, time window, source mode, and collection mode. Standard research targets 60–100 observed result cards, 30–50 unique retained signals, 12–18 opened details, and at least three counter signals. Targets guide reproducibility and must never be filled with weak evidence.

## Install

Copy the Skill directory into your agent's Skill directory:

```text
skills/trend-opportunity-radar/
```

For Codex, place `trend-opportunity-radar` under `$CODEX_HOME/skills/` and restart or reload the agent session. Other agents may adapt `SKILL.md`, the reference contracts, and the Python scripts to their Skill or tool format.

The bundled scripts use the Python standard library. Python 3.10 or later is recommended.

## Data access

No live-data connector is required. The workflow supports:

- user-uploaded JSON or CSV;
- public web signals;
- controlled, read-only browser capture;
- authorized platform APIs;
- historical snapshots.

Chrome, DokoBot, or an equivalent controlled browser is optional. When DokoBot is available, the bundled orchestrator treats it as a first-class read-only adapter and blocks rather than silently downgrading an undersized run. Users are responsible for platform terms, account permissions, and lawful data access. Credentials, cookies, and tokens must never be included in Skill inputs or outputs.

## Important boundaries

- Do not mix heat scores from different platforms.
- Label browser-derived X data as controlled capture, not API data.
- Use `signal snapshot` when comparable time-series evidence is absent.
- Do not mark an opportunity `review_ready` when its sampling contract is incomplete.
- Do not treat global sample totals as sufficient when any query layer fails its quality gates.
- Do not interpret evidence confidence as business attractiveness or infer trend direction from one snapshot.
- Do not maintain a second hand-edited collection ledger beside `raw-signals.json`.
- Treat products as fact-bound subjects and ideas or opportunities as hypotheses.
- Only a human may promote `review_ready` evidence to `confirmed`.
- Do not claim that the evidence heat index predicts future virality, traffic, demand, or revenue.

## Third-party compatibility

DokoBot, OpenCLI, Chrome, X, and Xiaohongshu are optional third-party tools or platforms and are not bundled with this repository. Their names identify compatibility targets only; no affiliation, endorsement, account access, or permission is implied. Use each integration only with lawful access and in accordance with its applicable terms.

## Repository layout

```text
skills/trend-opportunity-radar/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
├── references/
└── tests/
```

## License

MIT License. See [LICENSE](LICENSE).

## Release safety

This repository contains synthetic fixtures only. It does not package captured platform data, browser sessions, credentials, customer material, internal brands, or machine-specific run artifacts. Before publishing a change, run:

```text
python tools/audit_open_source_release.py
python tools/validate_skill.py skills/trend-opportunity-radar
python -m unittest discover -s skills/trend-opportunity-radar/tests -v
```
