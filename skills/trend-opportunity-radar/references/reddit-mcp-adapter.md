# Reddit Research MCP adapter

Use this reference for the validated `reddit_research_mcp` `topic_research` route. It is a third-party authorized API route, not an official Reddit adapter and not a browser-session adapter.

## Safe capability boundary

Allow only `discover_subreddits`, `search_subreddit`, and `fetch_posts`. Do not call `fetch_comments`, `fetch_multiple`, or any Feed operation. The upstream comment-tree response can exceed its nominal limit, and Feed operations mutate third-party state. Never package OAuth state, service tokens, Reddit credentials, cookies, or saved responses.

The hosted service receives research queries and subreddit names. Require the user to approve and connect it through their own Agent environment before the first live run. A self-hosted instance remains the user's separate deployment responsibility.

## Validated workflow

1. Ask the connected MCP server to discover its operations. Save the redacted response and validate it:

   `python scripts/check_reddit_mcp_adapter.py --discovery reddit-mcp-operations.json --output reddit-mcp-status.json --require-ready`

2. Select Reddit after the connected service passes the read-only preflight:

   `python scripts/select_collection_adapter.py --platform reddit --research-scope topic_research --status reddit-mcp-status.json --output adapter-selection.json --require-ready`

3. For each frozen query, build a bounded discovery request with `build_mcp_search_request`. Execute it through the Agent's connected MCP tool, not through an invented shell command. Keep at most five discovered communities and record why each community is relevant.

4. Search one discovered subreddit at a time with `search_subreddit`, a maximum limit of 20, and an explicit time filter. Keep requests sequential. Save every raw response before parsing it:

   `python scripts/parse_reddit_mcp_posts.py --input reddit-q1-r-example.json --output reddit-q1-r-example-extraction.json --query-id q1 --query-term "..." --query-layer category --operation search_subreddit`

5. Append each extraction to the canonical ledger through the normal atomic recorder. Count every returned post before semantic filtering. Deduplicate by Reddit post ID across communities and query layers.

6. Use `fetch_posts` only for a bounded community feed when the research question genuinely needs `new`, `hot`, `top`, or `rising` context. It is not a replacement for a frozen keyword query. Do not interpret fewer than the requested limit as proof that Reddit is exhausted.

7. Search results do not provide a post-specific detail operation. Select representative canonical Reddit permalinks from the retained search cards and open them sequentially with the Agent's public web reader. Save only bounded post text, visible timestamps, stable URLs, and explicitly reviewed comment excerpts; never read or export browser cookies. Apply the saved detail records with:

   `python scripts/apply_reddit_public_detail_backfill.py --input normalized-signals.json --backfill reddit-public-details.json --output detail-signals.json`

   Keep the search source as `authorized_api` and record the detail source as `public_web`. A successful public permalink read may upgrade the matching search card to `direct_post`; a search result, related-post recommendation, or failed page read may not.

## Evidence semantics

- Preserve `score` as `platform_facts.reddit_score`; it is not a like or visible upvote count.
- Preserve `upvote_ratio` separately. Do not infer positive-vote totals.
- Preserve `num_comments` as the post's displayed comment total. It does not mean comment text was collected.
- Use the Reddit permalink as the canonical evidence URL. Preserve an external linked URL only as a platform fact.
- Keep views, likes, saves, and shares unavailable unless a future verified adapter exposes them.
- Search results without a fetched body remain `search_card`. Do not upgrade them to verified details.
- Treat community discovery as a navigation aid. Its vector index freshness and hosted-service availability are third-party constraints, not Reddit trend facts.

The validated scope is limited to bounded topic research through a user-connected service: three query layers, sequential community searches, independent semantic review, counterevidence, audited public-permalink details, and local reports. Comments remain disabled, fewer-than-limit results do not prove exhaustion, and every live run must rediscover and save the permitted operation schemas before collection.
