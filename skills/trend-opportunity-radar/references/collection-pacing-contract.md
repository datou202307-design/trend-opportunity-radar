# Controlled read pacing contract

Apply `controlled-read-pacing-v0.1` to every live browser-backed search, detail, and separately requested comment read.

- Run at most one browser read at a time for a research run and browser profile. Never parallelize queries, details, comments, scrolling sessions, or fallback adapters.
- Keep the cadence transparent and deterministic. Pacing reduces platform load; it must not imitate random human behavior or bypass bot detection.
- Wait between reads: X and YouTube 10 seconds, Xiaohongshu search 15 seconds and detail/comment 20 seconds, TikTok pilot search 12 seconds. Use 10 seconds for an unlisted controlled-read platform until it is calibrated.
- After every five completed read requests, add a 30-second cooldown; use 45 seconds for Xiaohongshu.
- Count a retry and a separately requested comment read as new requests. Embedded replies returned by one detail response do not add a request.
- Start with one result screen or one bounded CLI request. Never pre-open multiple tabs or queue details in parallel to compensate for the cadence.
- Record the policy version, request index, interval, cooldown, and actual wait in capture metadata.
- Stop immediately on captcha, rate limit, login expiry, permission request, abnormal redirect, or repeated timeout. Waiting longer is not permission to retry a safety stop.

The intervals are conservative defaults, not evidence that a platform authorizes automated collection. Use stricter official limits when available.
