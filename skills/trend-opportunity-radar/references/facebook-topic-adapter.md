# Facebook Posts Topic Adapter Beta

This adapter supports bounded `topic_research` only through an explicit Facebook Posts search surface in a user-authorized logged-in browser. It does not turn Facebook's home Feed, generic mixed search, Pages, Groups, friends, notifications, Marketplace, or Reels recommendations into a reproducible topic sample.

## Contract

1. Freeze one exact query for each of `platform_baseline`, `category`, and `subject_bridge`, and construct `https://www.facebook.com/search/posts/?q=<encoded query>` before browser work.
2. Confirm that the visible page is a Posts search result for the frozen query. Reject a redirect to login, home Feed, generic search, a Group, or another content surface.
3. Confirm that the frozen query identity is visible and that the Posts surface exposes canonical result cards. A filter-only skeleton or zero parsed cards without an explicit Facebook empty-state message is a collection failure, not a zero-result conclusion.
4. Retain at most 20 unique canonical public identities per query. Supported candidates may be ordinary posts, public Reels, public photos, or other formats, but the content format must be observed rather than inferred from the URL.
5. Record one or two paced passes and preserve their overlap. Facebook ranking is session-, locale-, and personalization-dependent; a bounded result is not an exhaustive or chronological corpus.
6. Open at most 5 retained public details sequentially. Verify the same content identity and author route, then preserve visible text, publication label or time, content format, reactions, comments, shares, and views when present. If a verified detail shows a positive comment total but no visible comment bodies, the executor may activate that exact detail's numeric Comment control once, wait at the shared Facebook pacing interval, and perform at most one additional delayed read. Preserve no more than 5 explicitly visible top-level comments; never focus a composer, type, reply, react, or follow recommendation content.
7. Keep reaction count separate from reaction type. A displayed comment total is an interaction metric, not captured comment text. Missing fields remain null and are never estimated.
8. Send result cards and details through semantic and counterevidence review. A keyword match or high interaction count cannot by itself establish demand, sentiment, or an opportunity.

OpenCLI's built-in `facebook search` is a useful read-only capability diagnostic, but it currently describes a mixed people/Page/post search and exposes no Posts-only option. Its output must not enter the topic ledger unless the adapter independently proves the result came from the frozen Posts search surface.

Before a live run, save one redacted capability probe from the exact authorized browser surface and validate it. The probe contains only the query URL and visible identity checks, canonical public links, one matching detail identity, boolean safety checks, and no page body beyond the bounded detail field used for capability proof:

```bash
python scripts/check_facebook_topic_adapter.py \
  --probe facebook-preflight-probe.json \
  --output facebook-status.json \
  --require-ready
```

Pass `facebook-status.json` to `trend_radar.py doctor` or `start`. Do not hand-edit a ready status and do not treat generic Facebook mixed search as the Posts-only probe.

Freeze each read before browser work and validate the redacted capture afterward:

```bash
python scripts/run_facebook_topic_capture.py plan --subject "AI travel planning" --query "AI travel planner" --query-layer category --output facebook-request.json
python scripts/run_facebook_topic_capture.py record --request facebook-request.json --capture facebook-capture.json --output raw-signals.json --receipt facebook-receipt.json
```

After all three frozen layers have valid receipts, merge their snapshots before semantic review:

```bash
python scripts/merge_facebook_topic_snapshots.py --snapshot raw-signals-baseline.json --snapshot raw-signals-category.json --snapshot raw-signals-bridge.json --mode standard --output raw-signals.json
```

When the logged-in OpenCLI Browser Bridge is available, `scripts/run_facebook_opencli_capture.py` executes two paced Posts-only result passes, parses engagement only from buttons that contain both a number and a platform semantic label, and attempts bounded details sequentially. It never maps a bare adjacent number to reactions, comments, shares, or views.

Use the background browser window first. If the frozen Posts URL is correct but the bounded surface probe repeatedly returns only the search-filter skeleton and no result cards, retry once in the user-visible foreground window with `--window foreground`. This is a rendering fallback, not permission to browse the home Feed or perform interactions. Preserve the failed probe and the successful window mode in the capture audit.

Each formal pass uses its own controlled session and stores a redacted page probe containing only URL/query identity, canonical card count, explicit-empty evidence, and terminal state. Two empty passes become `verified_zero_results` only when both show the exact query on the Posts surface plus an explicit Facebook empty-state message. Otherwise record `surface_unreadable`, preserve any successful companion pass, and recover internally. Attribute failures only to the controller actually executed; an OpenCLI failure cannot be presented as proof that the Browser plugin is missing.

Facebook may return fuzzy, personalized, or otherwise irrelevant fallback cards for a frozen low-yield query instead of a stable empty page. Release acceptance therefore does not require a live random query to produce an explicit empty state. It requires at least two frozen low-yield probes, preserved query identity on every probe, zero false `verified_zero_results` classifications, and semantic exclusion of every irrelevant fallback card from demand or opportunity evidence. If an explicit empty state does appear, it still requires two independent matching passes. This validates false-zero protection without turning platform ranking behavior into a brittle test fixture.

The live executor classifies CAPTCHA, rate limiting, expired login, permission checkpoints, private content, and abnormal redirects separately from zero results and stops before a second read. Detail pacing events record whether the target was captured, rejected, unavailable, or safety-stopped, plus the actual captured-comment count. A platform unavailable page is an ordinary rejected detail and may be replaced within the frozen budget; it is not a zero-result or login conclusion.

On environments with a short command lifetime, run the two search passes and detail stage separately with `--target-passes 1 --skip-details`, then `--resume-capture ... --target-passes 2 --skip-details`, and finally `--resume-capture ... --detail-only`. Every stage validates the same frozen request hash and writes an immediately reusable checkpoint. Do not repeat a completed pass merely because a later stage stopped.

The checkpoint also persists `controlled-read-pacing-v0.1` request counts and events. A resumed stage continues the prior count, waits at least 10 seconds between Facebook search or detail reads, and applies a 30-second cooldown before request 6, 11, and later five-read boundaries. Splitting a run must never reset pacing. For a three-layer study, pass the same run-level `--pacing-state facebook-pacing-state.json` to every query and detail invocation so changing capture files cannot reset the shared count.

The capture may contain only visible public fields and must match `facebook-posts-browser-capture-v0.1`. A successful search with no verified detail records an auditable partial snapshot but does not complete the Beta study. The registry route intentionally remains `pilot` so callers must opt in explicitly and pass a live logged-in browser preflight.

Use `--detail-attempt-limit N` to stage representative detail reads without changing the frozen request. The stage limit may only reduce the request's `max_detail_posts`; a later resume may raise the stage limit up to that frozen maximum and skips already verified identities.

Use repeated `--detail-content-id ID` options when semantic triage needs representative, non-duplicate authors rather than the first ranked cards. Every ID must already exist in the frozen first pass, and the selected count cannot exceed the request's detail budget. This option never authorizes an arbitrary Facebook URL.

The first live three-layer pilot for ordinary travelers using AI produced 3/3 category results, 6/5 platform-baseline results, and 5/5 subject-bridge results across two passes. Four same-identity public details remained after rejecting one Facebook “page unavailable” surface. Explicitly labelled comment and share totals were retained; total reactions remained null where the page exposed only a reaction subtype. This proves the read, repeat, detail, semantic-metric, checkpoint, and deterministic record path, but 14 layer-level results and 4 details remain below the standard study threshold and do not make Facebook a validated platform.

Beta acceptance includes three different real topics: one complete 60-result standard run, one 55-result bounded candidate run, and one 44-result household-electricity run. The latest run retained 40 unique signals, reviewed 40/40 for relevance, found 31 direct or adjacent signals, opened 13 deduplicated details, and reviewed 23/23 captured comments with 7 relevant feedback rows. Its JSON, Markdown, and HTML report produced three eligible decision cards and passed desktop plus 390px loopback-browser QA with no horizontal overflow or console errors. Together with two frozen low-yield false-zero probes, the safety-stop fault matrix, and a real five-comment expansion, this is sufficient for an explicit logged-in-browser Beta, not for `validated` or anonymous support.

OpenCLI navigation and scroll commands may return successful plain text or an empty body rather than JSON; only evaluator commands are required to return JSON. A Facebook error surface such as “page unavailable”, “link may be broken”, or “content is not available” is never a verified detail, even when the search card supplied a date and interaction total.

Stop safely on CAPTCHA, rate limiting, expired login, permission prompts, abnormal redirects, private content, content mismatch, or two consecutive timeouts for the same read. Preserve verified search evidence after a detail failure, but keep the run incomplete until at least one retained public detail is verified.

Never read the user's home Feed as topic evidence. Never read friends, notifications, private Groups, Marketplace, Messenger, saved items, or account relationship graphs. Never join a Group, add or follow a person, react, like, comment, share, publish, save, or export cookies, browser profiles, credentials, tokens, or session state.
