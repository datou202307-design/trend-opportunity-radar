# Evidence heat scoring contract

Version: `evidence-heat-index-v0.1`

The index measures observable evidence strength and heat inside one platform. It does not predict virality, revenue, product-market fit, or future demand.

| Dimension | Weight | Minimum evidence |
| --- | ---: | --- |
| Content volume | 20 | Observed qualifying content count |
| Engagement | 25 | Views or visible interactions |
| Velocity | 25 | Comparable current/previous window or growth rate |
| Diffusion | 15 | Stable author identity plus observed content count |
| Search demand | 10 | Search volume, result count, or rank |
| Freshness | 5 | Metrics capture time |

Rules:

- Score every available dimension from 0–100.
- Multiply each score by its fixed weight.
- Give missing dimensions zero contribution.
- Do not redistribute missing weights.
- Report coverage as the sum of weights with usable evidence.
- Mark coverage below 40 as `sparse`, 40–74 as `partial`, and 75 or above as `complete`.
- Keep the score version, dimension scores, missing fields, capture time, and source mode.
- Compare scores only inside the same platform and compatible source/query/time-window contract.
- A single snapshot remains `snapshot`, regardless of a high numeric index.

