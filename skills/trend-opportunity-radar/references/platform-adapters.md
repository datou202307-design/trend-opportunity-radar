# Platform adapters

Read [platform-adapter-contract.md](platform-adapter-contract.md) before adding or changing an adapter. `platform-adapter-registry.json` is the executable capability registry; validate it with `python scripts/validate_platform_adapters.py`. Decision Profiles declare needed signals and evidence, never adapter commands.

Choose the strongest lawful source available. Preserve the selected source mode in every signal.

## Authorized API

Use an official platform or licensed provider API. Read credentials only from the local environment or the platform's secure authorization flow. Set request, page, sample, cost, and timeout limits. Record rate-limit state and raw snapshot hashes without credentials.

## Customer export

Accept JSON or CSV exported by the user. Preserve the original file and import time. Do not label an export as live data. Normalize column aliases with `normalize_signals.py`.

## Controlled capture

Use a user-authorized logged-in Chrome session, OpenCLI, DokoBot, an in-app browser, or an equivalent dynamic browser capability. Treat tool names as optional adapters, not required dependencies. Follow [browser-collection.md](browser-collection.md).

Run a non-mutating preflight for every considered adapter and select by recorded platform capability. For Xiaohongshu and X, prefer validated OpenCLI for structured search and retained details, then DokoBot for rendered-page verification; follow [opencli-orchestration.md](opencli-orchestration.md). The neutral orchestrator, not any single CLI call, owns query progression, raw-output retention, atomic ledger writes, detail recovery, and contract completion.

Browser capture may collect Xiaohongshu, X, or another platform the user can lawfully access. It remains `controlled_capture`, not an official API. Personalized ranking, incomplete metrics, access limits, and capture depth must be disclosed.

## Public web

Use public search engines or indexable pages for topic discovery and stable evidence links. Public-web evidence can establish that a signal exists, but cannot substitute for platform-native search position, comments, account distribution, or complete engagement metrics.

## Historical snapshot

Use archived evidence for its recorded time window only. Preserve the original date and limitations. Do not describe it as current or real-time.

## Degradation order

`authorized_api → customer_export → controlled_capture → public_web → historical_snapshot → gap task`

Never silently change modes. Preserve the last successful snapshot when a recollection attempt fails.
