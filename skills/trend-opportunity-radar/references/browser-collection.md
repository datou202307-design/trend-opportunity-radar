# Controlled browser collection

Use this workflow after the user authorizes read-only collection and personally completes any required login. Chrome browser control, OpenCLI, and DokoBot are known implementations, not hard dependencies. Run `check_collection_adapter.py` and `select_collection_adapter.py`; a PATH lookup or one successful CLI read is never sufficient acceptance evidence. Follow [opencli-orchestration.md](opencli-orchestration.md) for OpenCLI X or Xiaohongshu, or [dokobot-orchestration.md](dokobot-orchestration.md) for DokoBot.

## Prepare

1. Read [sampling-contract.md](sampling-contract.md) and select `quick`, `standard`, or `deep`.
2. Confirm the browser can read rendered search and detail pages and stable links.
3. Initialize `raw-signals.json` as the sole collection ledger before the first query.
4. State the selected mode, source, target counts, and limitations in one sentence.

Default to `standard` for an opportunity report. Use `quick` only when the user asks for a quick scan, the source is public-web discovery, or access constraints prevent a standard run. Never label an untracked public-web selection as a completed standard collection.

## Collect safely

1. Reuse one browser session and process one query at a time. Preserve DokoBot continuation sessions and OpenCLI signed Xiaohongshu detail URLs.
2. Cover all three query layers; keep query definitions in the ledger.
3. Count visible result cards before filtering.
4. Record retained, discarded, and opened-detail counts for every query, then run `append_collection_result.py` before starting the next query.
5. Open details only for high-signal, non-duplicate results, within the selected contract.
6. Capture visible text, author, content time, metrics, stable URL, and source type exactly.
7. Mark each retained signal `support`, `counter`, or `neutral`.
8. Preserve representative objections and adoption barriers; do not merely search for confirmation.
9. Stop when the contract is met, useful new mechanisms cease appearing across two consecutive queries, or a safety/access condition occurs. Record the reason.

Do not repeatedly refresh, scan concurrently, scroll without a bound, simulate human randomness, or use low-quality items to fill a target.

## Bounded recovery

Use the selected adapter only for capabilities validated on the target platform. On Xiaohongshu, use OpenCLI for structured search and detail reads and DokoBot or direct Chrome control to verify ambiguous rendering. On X, use OpenCLI for structured Top/Latest search and thread detail, then DokoBot for rendered-page verification or fallback. After two repeated navigation or extraction timeouts across the selected path, stop retrying the same operation. Do not merge public-web discovery into controlled-capture counts.

## Stop immediately

Stop on captcha, rate limits, login expiry, permission requests, abnormal redirects, or repeated timeouts. Preserve the partial ledger and create a gap task. Never bypass the condition.

## Platform notes

- Xiaohongshu: separate search cards, details, comments, account conditions, and media availability. A public search page does not prove complete platform coverage.
- X: preserve the query operator, post URL, full visible text, author, publish time, and visible metrics. Label an unopened result as `search_card`; only an opened post detail or authorized API/export item qualifies as direct evidence. A profile or Grok trend summary is not a direct post. Browser results can be personalized and must not be labeled as Recent Search API data.
