# Platform Adapter Contract

Version: `platform-adapter-contract-v0.1`

Use this contract when adding or selecting a collection source. Keep platform mechanics out of Decision Profiles and research conclusions.

## Responsibilities

An adapter may:

- declare readiness for one platform and source mode;
- build a bounded search or detail-read request;
- preserve raw output and execution metadata;
- mechanically map visible fields into the common signal schema;
- report continuation, terminal evidence, and safety-stop reasons.

An adapter must not:

- decide semantic relevance, evidence role, topic membership, or a business conclusion;
- estimate missing platform metrics;
- translate one platform's raw engagement into another platform's scale;
- silently change source mode or claim readiness from another platform's login.

## Registry requirements

`platform-adapter-registry.json` is the executable registry. Every platform declares aliases, controlled-capture preference, and visible metric fields. Every adapter-platform capability declares:

- `capability_key`
- `search_builder`
- `detail_builder`
- optional `comment_builder` and bounded `comment_sample_limit`
- `search_parser`
- `detail_runner`
- `pagination`
- `terminal_evidence`
- `safety_stops`

Use `null` only when an operation is intentionally unsupported. Wildcard platform support is allowed only for non-live adapters such as structured import.

## Common extraction boundary

A successful mechanical extraction returns:

- `query_id`
- `observed_result_keys`
- `signals`
- `detail_open_keys`

Newly searched signals remain `semantic_relevance: unreviewed`. Semantic review is a separate, append-only step.

## Adding a platform

1. Add its aliases and metric fields.
2. Add at least one adapter capability or retain import-only support.
3. Implement and test registered builders and parsers.
4. Verify zero results, detail merge, safety stops, raw artifacts, and terminal state.
5. Do not call the platform live-supported until its real end-to-end acceptance passes.
