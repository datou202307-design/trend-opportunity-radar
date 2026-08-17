# Trend evidence scoring contract

Version: `trend-evidence-v0.5.0-candidate`

Report two separate values. Neither predicts virality, revenue, market size, product-market fit, or future demand.

## Observed heat

| Dimension | Weight | Rule |
| --- | ---: | --- |
| Content volume | 20 | Topic-level qualifying sample volume |
| Engagement | 25 | Median visible engagement signal; do not let one viral item define the topic |
| Velocity | 25 | Comparable windows only |
| Diffusion | 15 | Unique direct-post authors at topic level |
| Search demand | 10 | Visible result count, rank, or authorized search measure |
| Freshness | 5 | Content publication time, never metrics capture time |

Calculate the engagement dimension with the versioned, platform-specific behavior weights in `engagement-weight-registry.json`. Do not use one platform's behavior weights for another platform. The initial values are candidate calibration rules, not proven causal values: X weights durable private intent and distribution more than likes; Xiaohongshu weights comments, collections, and shares more than likes; YouTube weights comments more than likes. Preserve the registry version in scored output. Compare engagement only within the same platform and compatible capture contract.

## Evidence confidence

| Dimension | Weight |
| --- | ---: |
| Sample sufficiency | 25 |
| Independent author diversity | 20 |
| Source quality | 20 |
| Field coverage | 20 |
| Counterevidence coverage | 15 |

Prefer direct API/export/browser-captured posts over platform summaries, profiles, and search snippets. Missing dimensions contribute zero and weights are never redistributed. Report all dimension values, coverage, missing fields, source mix, sample count, independent authors, direct sources, and counter signals.

Treat controlled-browser search cards without an opened detail as `search_card`, not `direct_post`. Score their source quality below verified details. When the sampling contract is `partial` or `blocked`, cap topic evidence confidence at 54; cap an untracked run at 45. Preserve the uncapped value and cap reason for audit. In the human report, use both scores primarily for fast grading: show each as `score/100 + plain-language level`. Put the uncapped calculation and cap reason inside a collapsed scoring explanation; do not turn the cap into a prominent warning or imply that observed heat itself was discounted.

Compare values only inside the same platform and compatible source, query, locale, and time-window contract. A single run remains a `snapshot` regardless of score.
