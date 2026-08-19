# Instagram known-account research pilot

Instagram live collection is limited to `account_research`. The user must supply one known public brand, competitor, or creator username. `topic_research` remains unsupported because account search and personalized Explore recommendations are not a reproducible topic sample.

## Environment

- A user-authorized, already signed-in browser session that the Agent can control read-only.
- A browser controller capable of reading rendered DOM and public metadata. Chrome control is the tested implementation; an equivalent controller may satisfy the same capture contract.
- No cookie, token, password, browser profile, or session export. The Skill never packages login state.

OpenCLI may confirm account discovery or public profile fields, but its current recent-post output omits stable post URLs and truncates captions. It is therefore auxiliary only and must not supply canonical evidence identity.

## Frozen workflow

1. Freeze one username and a bounded budget:

```bash
python scripts/run_instagram_account_capture.py plan --username example.account --max-posts 12 --max-detail-posts 6 --output instagram-request.json
```

2. In the authorized browser, open exactly `profile_url`. Confirm the visible username. Read at most `max_posts` unique anchors whose canonical path is `/p/{shortcode}/`, `/reel/{shortcode}/`, or the account-prefixed equivalent `/{username}/p|reel/{shortcode}/` returned by the current web UI.
3. Open at most `max_detail_posts` of those frozen links sequentially. Preserve the exact canonical URL, visible account name, caption, ISO publication time, and only metrics explicitly shown by the page metadata or visible interface. Read at most five visible top-level comments per opened post. Do not expand reply trees.
4. Save a capture matching `instagram-account-browser-capture-v0.1`. Set all six checks to `true` only after observing them. Never include Followers, Following, cookies, storage, headers, tokens, passwords, or session identifiers.
5. Record and normalize atomically:

```bash
python scripts/run_instagram_account_capture.py record --request instagram-request.json --capture instagram-capture.json --output raw-signals.json --receipt instagram-receipt.json
```

The recorder rejects account mismatch, malformed or duplicate shortcodes, excess posts/details/comments, missing detail identity, follow-graph fields, credentials, and any capture that cannot assert no write action.

## Safety and evidence boundary

- Maximum browser concurrency is one. Wait at least 15 seconds between profile/detail reads and add a 30-second cooldown after five reads.
- Stop on CAPTCHA, rate limiting, login loss, private/not-found account, permissions, abnormal redirect, or content mismatch. Do not retry around a safety stop.
- Likes, comments, views, dates, captions, and visible comments are platform facts. Content themes, audience interpretation, sentiment, opportunity, and recommendations are model inferences that require evidence links.
- Followers/Following are outside this pilot. Do not use the follow graph as a proxy for competitor users.
- A single account snapshot describes recent visible content supply and response. It does not establish platform-wide demand, trend growth, reach, market size, or causality.
- Promotion requires two different public accounts, zero/private/error paths, fixed-account repeatability, three report formats, and desktop/mobile loopback acceptance. Until then the registry remains `pilot`.
