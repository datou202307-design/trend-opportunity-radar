# Research Context Contract

Version: `research-context-v0.1`

Compile the user's simple request before collection. Freeze the result for the entire run.

Required fields:

- `research_intent`
- `profile_version`
- `subject`
- `platform`
- `language`
- `decision_question`
- `analysis_unit`
- `evidence_roles`
- `counterevidence_targets`
- `query_profile`
- `query_intents`
- `decision_thresholds`
- `action_contract`
- `report_profile`
- `report_sections`
- `assumptions`
- `source_prompt_sha256`

When intent or platform is materially ambiguous, return `status: clarification_required` with one concise question and do not start collection. Explicit mode selection overrides incidental words such as “opportunity.” The legacy phrase “analyze ... on ... for trend opportunities” defaults to `business_opportunity`.

Profile selection freezes executable M3 semantics. Use the selected query intents, Profile evidence roles, thresholds, action contract, and report sections without changing them mid-run.
