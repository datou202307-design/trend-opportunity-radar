# Sampling contract

Choose a mode before collection and record actual counts. Targets guide a reproducible run; never add weak evidence merely to fill a quota.

| Mode | Queries | Observed result cards | Unique retained signals | Detail pages | Counter signals | Opportunity target | Use |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `quick` | 3–5 | 20–40 | 8–15 | 4–8 | ≥2 | 1–3 | Decide whether deeper research is justified |
| `standard` | 3–9 | 60–100 | 30–50 | 12–18 | ≥3 | 3–5 | Default reviewable opportunity research |
| `deep` | 9–15 | 100–300 | 80–200 | 20–40 | ≥8 | 5–8 | API/export research and repeated comparison |

Use one initial probe query in each of `platform_baseline`, `category`, and `subject_bridge` for `standard`. Treat nine as the total query budget, not the size of the initial plan: start with three and add only non-duplicative recovery queries for deficient layers. Stop when every volume and quality gate passes. Before starting another search, reserve the expected size of one atomic read against the 100-result upper bound; never truncate cards that were actually visible. A final atomic read may still cross the bound and must be preserved and identified as an atomic overshoot. Recovery queries must cover as many distinct deficient layers as the remaining budget permits, use no more than four words, and remove stacked qualifiers rather than restating the full subject. Use `deep` only with an authorized API, customer export, or another source that can lawfully sustain the volume. Require at least two comparable snapshots before describing direction.

## Canonical collection ledger

Use `raw-signals.json.collection` as the only canonical ledger. Do not maintain a separate `collection-ledger.json`; derived reports and gap tasks must read the canonical raw snapshot.

Store the following object next to raw `signals`:

```json
{
  "collection": {
    "mode": "standard",
    "query_runs": [
      {
        "query_term": "...",
        "query_layer": "category",
        "observed_result_count": 12,
        "retained_signal_count": 5,
        "detail_open_count": 2,
        "discarded_result_count": 7,
        "stop_reason": ""
      }
    ],
    "counts": {
      "query_count": 6,
      "observed_result_count": 72,
      "detail_open_count": 14,
      "counter_signal_count": 4
    },
    "stop_reason": "",
    "limitations": []
  }
}
```

Count every visible result card once in `observed_result_count`, including results later discarded. Count selected records before deduplication in `retained_sample_count`; let the normalization script calculate retained, duplicate, discarded, and unique counts. Record why evidence was discarded in query-level notes when the reason is material.

After every query, write that query's retained signals and counts to a temporary `query-result.json`, then atomically append it:

```bash
python scripts/append_collection_result.py --snapshot raw-signals.json --query-result query-result.json --platform x --source-mode controlled_capture --mode standard
```

Never keep the only copy of collected evidence in browser memory. The append script rejects duplicate query definitions and recomputes all snapshot counts from query runs and signals.

A query that lawfully returns zero visible results still belongs in `query_runs` with `observed_result_count: 0`, `retained_signal_count: 0`, a concrete stop reason, and `outcome: completed_with_zero_results`. Zero is evidence about query yield, not permission to fabricate cards or leave the collection state unfinished.

Mark the run `blocked` instead of lowering targets silently when a captcha, rate limit, login expiry, insufficient results, or another stop condition prevents completion. A partial run remains useful as a `signal snapshot`, but it cannot alone produce a review-ready opportunity.

## Per-layer quality gates

Global totals are necessary but insufficient. Apply these minimums to each of `platform_baseline`, `category`, and `subject_bridge`:

Relevant unique signals must also reach 4 / 18 / 48 globally in quick / standard / deep mode. `Relevant` means `direct` or `adjacent`; each layer's `direct` minimum prevents a numerically large but off-task result set from completing the contract.

| Mode | Queries/layer | Observed/layer | Unique/layer | Relevant/layer | Direct/layer | Details/layer | Direct subject-bridge evidence | Relevance reviewed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `quick` | 1 | 4 | 2 | 1 | 0 | 0 | 0 | 0% |
| `standard` | 1 | 8 | 4 | 4 | 2 | 2 | 2 | 80% |
| `deep` | 3 | 15 | 8 | 8 | 3 | 3 | 3 | 90% |

Direct subject-bridge evidence must have `semantic_relevance: direct` and either an opened detail or a direct/exported source. A query count may be complete while its layer quality is blocked.
