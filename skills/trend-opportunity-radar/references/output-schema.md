# Output schema

Deliver a Markdown report and machine-readable JSON.

## Subject

```json
{
  "name": "...",
  "subject_type": "product|opportunity|idea|problem|project",
  "summary": "...",
  "facts": [{"statement": "...", "source_refs": []}],
  "hypotheses": [{"statement": "...", "origin": "user_premise|model_inference"}],
  "audiences": [],
  "scenarios": [],
  "constraints": [],
  "source_refs": []
}
```

## Opportunity

```json
{
  "title": "...",
  "topic_key": "...",
  "audience": "...",
  "task_gap": "...",
  "subject_entry": "...",
  "expected_action": "...",
  "support_refs": [],
  "counter_refs": [],
  "counter_review": "Required when counter_refs is empty",
  "risk_boundaries": [],
  "missing_evidence": [],
  "gates": {},
  "evidence_status": "candidate|review_ready|confirmed|rejected"
}
```

Only a human may promote `review_ready` to `confirmed`. Keep facts, user premises, model inferences, and human confirmations distinguishable.

## Markdown order

1. Research topic and assumptions
2. Platform heat
3. Trend × research topic opportunities
4. Supporting and counterevidence
5. Risks and boundaries
6. Recommended validation actions
7. Data gaps and recollection tasks

Use `signal snapshot` when comparable time-series evidence is absent. Place stable links next to supported claims.
