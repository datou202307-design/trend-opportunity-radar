# Controlled browser collection

Use this workflow only after the user explicitly authorizes read-only collection and has completed any required login personally.

## Capability check

Confirm the environment can:

- control an existing authorized browser session;
- read JavaScript-rendered search and detail pages;
- extract visible text, metrics, timestamps, authors, and stable links;
- preserve a structured snapshot in the current working directory.

Chrome browser control and DokoBot are known implementations, not hard dependencies.

## Safe workflow

1. Record platform, query, query layer, locale, time, and intended page depth.
2. Reuse one tab when practical.
3. Read one query at a time.
4. Read the visible search results before opening details.
5. Open at most two details per query by default.
6. Expand to at most five only when additional high-signal, non-duplicate mechanisms remain visible.
7. Record visible metrics exactly as shown; use `null` when unavailable.
8. Record representative counterexamples and access limitations.
9. Close or leave the session without changing platform state.

Do not use low-interaction items to fill a quota. Do not repeatedly refresh, scan concurrently, scroll without a bound, or simulate human randomness.

## Stop conditions

Stop immediately on captcha, rate-limit warnings, login expiry, permission requests, abnormal redirects, or repeated timeouts. Preserve collected evidence and create a gap task. Never attempt to bypass the condition.

## Platform notes

- Xiaohongshu: separate visible search cards, details, comments, account conditions, and media availability. A public search page does not prove complete platform coverage.
- X: capture query, post URL, text, author, time, and visible public metrics. Browser results can be personalized or incomplete and must not be labeled as Recent Search API data.

