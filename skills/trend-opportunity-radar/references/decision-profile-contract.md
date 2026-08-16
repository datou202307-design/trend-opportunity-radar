# Decision Profile contract

Version: `profile-decision-findings-v0.1`

Keep platform facts and the shared evidence polarity unchanged. Add `profile_evidence_role` during semantic review to describe what a signal means for the selected decision. A signal therefore retains:

- `evidence_role`: shared `support|counter|neutral` polarity used by collection and scoring;
- `profile_evidence_role`: one role allowed by the frozen Decision Profile;
- original source, text, time, metrics, platform, and audit trail.

Every query in a non-default Profile must declare one allowed `query_intent`. Query layers remain `platform_baseline`, `category`, and `subject_bridge`; intent describes why the query exists and never changes platform collection mechanics.

Create `profile-findings.json` with `schema_version`, frozen `research_intent`, frozen `profile_version`, and `findings`. Each finding must include:

- `id`, `title`, `topic_key`, `analysis_unit_statement`, `decision_summary`, `audience`;
- `profile_evidence_roles`, disjoint `support_refs` and `counter_refs`, `counter_search_status`, `direct_source_present`;
- `conclusion_status`, `evidence_boundary`, `temporal_claim`, `compatible_snapshot_count`;
- at least one `recommended_actions` item containing every field required by the selected Profile;
- a `report_sections` object containing exactly the selected Profile's required sections.

Run:

```bash
python scripts/validate_profile_decisions.py --research-context research-context.json --signals scored-signals.json --findings profile-findings.json
```

Do not promote a finding to `review_ready` until its Profile thresholds pass. Only a human may set `confirmed`. For brand sentiment, use `current_snapshot` for a single run; `spreading`, `rising`, `falling`, and `resolved_over_time` require at least two compatible snapshots.
