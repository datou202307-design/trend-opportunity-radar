# Clustering contract

Clustering is a semantic review step, not a text-label rewrite. Preserve every normalized signal and assign it exactly once.

Create `cluster-plan.json` with this shape:

```json
{
  "clusters": [
    {
      "topic_key": "stable-topic-key",
      "title": "Concise task or outcome label in the report language",
      "analysis_unit_statement": "The concrete issue, experience, question, task, or transition shared by members",
      "inclusion_rule": "What evidence belongs",
      "exclusion_rule": "What superficially similar evidence does not belong",
      "assignments": [
        {
          "signal_id": "signal-...",
          "fit": "core|supporting|counter",
          "reason": "Why this signal belongs under the same task transition",
          "task_transition_match": true
        }
      ]
    }
  ]
}
```

`audit_clusters.py` rejects unknown, duplicate, or unassigned signals. A cluster passes only with at least three members, two authors, one direct source, two core members, an 80% task-transition match rate, and one subject-bridge member. Failed or missing audits cap topic evidence confidence at 54 and block `review_ready`.

When a frozen research context is supplied, the audit also checks that the cluster covers the Profile's minimum number of distinct `profile_evidence_role` values. `task_transition` remains a backwards-compatible alias for business-opportunity fixtures; new multi-Profile runs use `analysis_unit_statement`.

The audit verifies explicit provenance and deterministic gates; it does not prove semantic truth. Keep questionable members as `supporting` or `counter`, or split the cluster. Never split a coherent cluster to fill a display target. Failed or missing audits remain excluded exploratory topics and cannot back decision findings.

Write every cluster `title` for the report reader and summarize the members' shared task or outcome. Do not reuse a representative post headline, vendor slogan, URL, Markdown-formatted phrase, or raw `topic_key`. The audited title is the canonical topic title for JSON, Markdown, and HTML.
