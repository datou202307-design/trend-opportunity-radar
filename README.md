# Trend Opportunity Radar

An independent, brand-neutral agent Skill for analyzing evidence-backed trend opportunities for a research topic on one platform.

Current status: **v0.1 candidate**. This is a trend-research workflow, not a viral-content or traffic prediction system.

## What it does

- Accepts a product, business opportunity, idea, user problem, audience need, or project as the research topic.
- Analyzes one platform at a time, including X, Xiaohongshu, and adapter-defined platforms.
- Imports user-provided data or collects authorized, read-only browser and API signals.
- Normalizes evidence, source links, capture times, metrics, and limitations.
- Calculates an evidence heat index without hiding missing data.
- Generates topic-to-subject opportunities, counterevidence, risks, validation actions, and recollection tasks.
- Separates platform facts, user premises, model inferences, and human confirmation.
- Produces Markdown and machine-readable JSON.

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

The agent should infer safe defaults for language, region, audience, query terms, time window, source mode, and sample size. It should ask only when the topic or platform is missing, authentication is required, or a choice would materially change the result.

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

Chrome, DokoBot, or an equivalent controlled browser is optional. Users are responsible for platform terms, account permissions, and lawful data access. Credentials, cookies, and tokens must never be included in Skill inputs or outputs.

## Important boundaries

- Do not mix heat scores from different platforms.
- Label browser-derived X data as controlled capture, not API data.
- Use `signal snapshot` when comparable time-series evidence is absent.
- Treat products as fact-bound subjects and ideas or opportunities as hypotheses.
- Only a human may promote `review_ready` evidence to `confirmed`.
- Do not claim that the evidence heat index predicts future virality, traffic, demand, or revenue.

## Repository layout

```text
skills/trend-opportunity-radar/
├── SKILL.md
├── agents/openai.yaml
├── scripts/
└── references/
```

## License

MIT License. See [LICENSE](LICENSE).
