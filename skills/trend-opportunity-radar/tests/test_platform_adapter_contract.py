from __future__ import annotations

import copy
import tempfile
import unittest
import json
import subprocess
from pathlib import Path

import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import platform_adapter_contract as contract
import check_reddit_mcp_adapter as reddit_preflight
import check_instagram_browser_adapter as instagram_preflight
import parse_opencli_tiktok_search as tiktok_parser
import parse_reddit_mcp_posts as reddit_parser
import apply_reddit_public_detail_backfill as reddit_detail
import select_collection_adapter as selector
import _common as common


class PlatformAdapterContractTest(unittest.TestCase):
    def test_registry_validates_and_aliases_normalize(self) -> None:
        registry = contract.load_registry()
        self.assertEqual(registry["contract_version"], "platform-adapter-contract-v0.2")
        self.assertEqual(contract.normalize_platform("小红书", registry), "xiaohongshu")
        self.assertEqual(contract.normalize_platform("Twitter", registry), "x")
        self.assertEqual(contract.normalize_platform("油管", registry), "youtube")
        self.assertEqual(contract.normalize_platform("Tik Tok", registry), "tiktok")
        self.assertEqual(contract.normalize_platform("Reddit", registry), "reddit")
        self.assertEqual(contract.normalize_platform("INS", registry), "instagram")
        self.assertEqual(common.normalize_platform("TikTok"), "tiktok")
        self.assertEqual(common.normalize_platform("抖音"), "douyin")
        self.assertEqual(common.normalize_platform("Instagram"), "instagram")
        self.assertEqual(contract.platform_scope_status("youtube", "topic_research", registry), "validated")
        self.assertEqual(contract.platform_scope_status("youtube", "account_research", registry), "unsupported")

    def test_invalid_capability_shape_is_rejected(self) -> None:
        registry = contract.load_registry()
        broken = copy.deepcopy(registry)
        del broken["adapters"]["opencli"]["platforms"]["x"]["safety_stops"]
        with self.assertRaises(ValueError):
            contract.validate_registry(broken)

    def test_comment_capability_requires_a_bounded_limit(self) -> None:
        registry = contract.load_registry()
        broken = copy.deepcopy(registry)
        broken["adapters"]["opencli"]["platforms"]["xiaohongshu"]["comment_sample_limit"] = 50
        with self.assertRaises(ValueError):
            contract.validate_registry(broken)

    def test_platform_readiness_is_not_inferred_from_other_platform(self) -> None:
        status = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"x": True, "xiaohongshu": False}}
        self.assertTrue(contract.status_supports(status, "x"))
        self.assertFalse(contract.status_supports(status, "xiaohongshu"))
        route = selector.select_adapter("xiaohongshu", [status])
        self.assertFalse(route["ready"])
        self.assertEqual(route["rejected"][0]["reason"], "platform_not_validated")

    def test_unsupported_research_scope_cannot_select_a_live_adapter(self) -> None:
        status = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"youtube": True}}
        route = selector.select_adapter("youtube", [status], research_scope="account_research")
        self.assertFalse(route["ready"])
        self.assertEqual(route["release_status"], "unsupported")
        self.assertEqual(route["status"], "research_scope_not_live_supported")

    def test_pilot_scope_requires_explicit_opt_in(self) -> None:
        status = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"tiktok": True}}
        default_route = selector.select_adapter("tiktok", [status])
        self.assertFalse(default_route["ready"])
        self.assertEqual(default_route["release_status"], "pilot")
        pilot_route = selector.select_adapter("tiktok", [status], allow_pilot=True)
        self.assertTrue(pilot_route["ready"])
        self.assertEqual(pilot_route["adapter"], "opencli")

    def test_tiktok_selects_opencli_search_and_logged_in_dokobot_detail(self) -> None:
        opencli = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"tiktok": True}}
        dokobot = {"adapter": "dokobot", "ready": True, "status": "ready"}
        route = selector.select_adapter("tiktok", [dokobot, opencli], allow_pilot=True)
        self.assertEqual(route["adapter"], "opencli")
        self.assertEqual(route["detail_adapter"], "dokobot")
        self.assertTrue(route["detail_ready"])
        self.assertEqual(contract.adapter_capability("opencli", "tiktok")["search_builder"], "opencli_tiktok_search_v1")
        self.assertIsNone(contract.adapter_capability("opencli", "tiktok")["detail_builder"])
        self.assertEqual(contract.adapter_capability("dokobot", "tiktok")["detail_builder"], "dokobot_tiktok_detail_v1")
        self.assertEqual(contract.adapter_capability("dokobot", "tiktok")["comment_sample_limit"], 5)

    def test_reddit_validated_route_preserves_authorized_api_source(self) -> None:
        status = {"adapter": "reddit_research_mcp", "ready": True, "status": "ready", "capabilities": {"reddit": True}}
        route = selector.select_adapter("reddit", [status])
        self.assertTrue(route["ready"])
        self.assertEqual(route["adapter"], "reddit_research_mcp")
        self.assertEqual(route["source_mode"], "authorized_api")

    def test_instagram_scopes_use_separate_explicit_pilot_adapters(self) -> None:
        status = {"adapter": "browser_readonly_capture", "ready": True, "status": "ready", "capabilities": {"instagram": True}}
        topic_status = {"adapter": "instagram_hashtag_browser_capture", "ready": True, "status": "ready", "capabilities": {"instagram": True}}
        self.assertFalse(selector.select_adapter("instagram", [topic_status], research_scope="topic_research")["ready"])
        topic_route = selector.select_adapter("instagram", [topic_status], research_scope="topic_research", allow_pilot=True)
        self.assertTrue(topic_route["ready"])
        self.assertEqual(topic_route["adapter"], "instagram_hashtag_browser_capture")
        self.assertFalse(selector.select_adapter("instagram", [status], research_scope="account_research")["ready"])
        route = selector.select_adapter("instagram", [status], research_scope="account_research", allow_pilot=True)
        self.assertTrue(route["ready"])
        self.assertEqual(route["adapter"], "browser_readonly_capture")
        self.assertEqual(route["source_mode"], "controlled_capture")

    def test_instagram_hashtag_adapter_allows_only_topic_read_operations(self) -> None:
        for operation in ("read_hashtag_results", "read_canonical_post_links", "read_post_detail", "read_visible_comments"):
            self.assertTrue(contract.adapter_operation_allowed("instagram_hashtag_browser_capture", operation))
        for operation in ("read_account_search_as_topic", "read_personalized_explore_feed", "follow_account", "like_post"):
            self.assertFalse(contract.adapter_operation_allowed("instagram_hashtag_browser_capture", operation))

    def test_reddit_operation_allowlist_blocks_comments_batches_and_feed_writes(self) -> None:
        for operation in ("discover_subreddits", "search_subreddit", "fetch_posts"):
            self.assertTrue(contract.adapter_operation_allowed("reddit_research_mcp", operation))
        for operation in ("fetch_comments", "fetch_multiple", "create_feed", "update_feed", "delete_feed"):
            self.assertFalse(contract.adapter_operation_allowed("reddit_research_mcp", operation))
        with self.assertRaises(ValueError):
            contract.build_mcp_search_request(
                {"adapter": "reddit_research_mcp", "platform": "reddit"},
                {"operation": "fetch_comments", "term": "AI travel planning", "subreddit": "travel"},
            )

    def test_reddit_request_builder_is_bounded_and_requires_a_discovered_community(self) -> None:
        state = {"adapter": "reddit_research_mcp", "platform": "reddit"}
        discovery = contract.build_mcp_search_request(state, {"operation": "discover_subreddits", "term": "AI travel planning", "limit": 99})
        self.assertEqual(discovery["arguments"]["limit"], 5)
        search = contract.build_mcp_search_request(state, {
            "operation": "search_subreddit", "term": "AI travel planning", "subreddit": "r/travel", "limit": 99,
        })
        self.assertEqual(search["arguments"]["subreddit"], "travel")
        self.assertEqual(search["arguments"]["limit"], 20)
        with self.assertRaises(ValueError):
            contract.build_mcp_search_request(state, {"operation": "search_subreddit", "term": "AI travel planning"})

    def test_reddit_public_permalink_backfill_upgrades_only_matching_search_card(self) -> None:
        snapshot = {"collection": {"counts": {}, "detail_backfills": []}, "signals": [{
            "content_id": "abc123", "platform": "reddit", "source_type": "search_card", "detail_captured": False,
            "canonical_url": "https://reddit.com/r/travel/comments/abc123/example/", "summary": "",
            "evidence_refs": [], "limitations": ["The post body was not returned by this operation; conclusions use the title and post-level metadata only."],
        }]}
        backfill = {"entries": [{"content_id": "abc123", "canonical_url": "https://www.reddit.com/r/travel/comments/abc123/example/",
                                  "body_text": "A bounded synthetic post body.", "body_text_kind": "agent_summary",
                                  "captured_at": "2026-08-19T00:00:00Z", "source_mode": "public_web"}]}
        result = reddit_detail.apply_backfill(snapshot, backfill, "synthetic-detail.json")
        signal = result["signals"][0]
        self.assertTrue(signal["detail_captured"])
        self.assertEqual(signal["source_type"], "direct_post")
        self.assertEqual(signal["detail_source_mode"], "public_web")
        self.assertEqual(signal["detail_text_kind"], "agent_summary")
        self.assertEqual(result["collection"]["counts"]["detail_open_count"], 1)
        self.assertNotIn("post body was not returned", " ".join(signal["limitations"]))

    def test_reddit_parser_keeps_score_separate_from_likes_and_uses_permalink(self) -> None:
        payload = {"results": [{
            "id": "abc123", "title": "Synthetic planning question", "author": "sample_user",
            "subreddit": "travel", "score": 42, "created_utc": 1700000000,
            "url": "https://example.com/external", "num_comments": 8, "upvote_ratio": 0.91,
            "permalink": "/r/travel/comments/abc123/synthetic_planning_question/",
        }]}
        parsed = reddit_parser.parse_search_records(payload, {
            "id": "q1", "term": "AI travel planning", "layer": "category", "intent": "task", "operation": "search_subreddit",
        }, "synthetic.json")
        signal = parsed["signals"][0]
        self.assertEqual(signal["signal_id"], "reddit-abc123")
        self.assertEqual(signal["canonical_url"], "https://www.reddit.com/r/travel/comments/abc123/synthetic_planning_question/")
        self.assertIsNone(signal["metrics"]["likes"])
        self.assertEqual(signal["metrics"]["comments"], 8)
        self.assertEqual(signal["platform_facts"]["reddit_score"], 42)
        self.assertEqual(signal["platform_facts"]["upvote_ratio"], 0.91)
        self.assertFalse(signal["detail_captured"])
        self.assertEqual(parsed["query_term"], "AI travel planning")
        self.assertEqual(parsed["query_layer"], "category")
        self.assertEqual(parsed["query_intent"], "task")
        self.assertEqual(signal["query_intent"], "task")
        self.assertEqual(parsed["observed_result_count"], 1)
        self.assertEqual(parsed["retained_signal_count"], 1)
        self.assertEqual(parsed["raw_artifacts"], ["synthetic.json"])

    def test_reddit_preflight_requires_only_the_safe_read_operations(self) -> None:
        status = reddit_preflight.build_status({"operations": [
            {"name": "discover_subreddits"}, {"name": "search_subreddit"}, {"name": "fetch_posts"},
            {"name": "fetch_comments"}, {"name": "create_feed"},
        ]})
        self.assertTrue(status["ready"])
        self.assertEqual(status["comment_collection"], "disabled")
        self.assertIn("fetch_comments", status["enforced_operation_denylist"])
        missing = reddit_preflight.build_status({"operations": [{"name": "search_subreddit"}]})
        self.assertFalse(missing["ready"])
        self.assertIn("discover_subreddits", missing["missing_operations"])

    def test_reddit_preflight_reads_operation_names_from_discovery_map_keys(self) -> None:
        status = reddit_preflight.build_status({"operations": {
            "discover_subreddits": "Find communities",
            "search_subreddit": "Search posts",
            "fetch_posts": "Fetch a bounded listing",
            "fetch_comments": "Forbidden by the Skill",
        }})
        self.assertTrue(status["ready"])
        self.assertEqual(status["missing_operations"], [])
        self.assertEqual(status["discovered_required_operations"], [
            "discover_subreddits", "fetch_posts", "search_subreddit",
        ])

    def test_tiktok_search_parser_keeps_only_stable_read_only_cards(self) -> None:
        records = [{
            "author": "synthetic.creator", "comments": 4,
            "desc": "A synthetic AI workflow example", "likes": 1200,
            "plays": 24000, "rank": 1, "shares": 33,
            "url": "https://www.tiktok.com/@synthetic.creator/video/7000000000000000001",
        }]
        parsed = tiktok_parser.parse_search_records(records, {"id": "q1", "term": "AI workflow", "layer": "category"}, "synthetic.json")
        self.assertEqual(parsed["observed_result_keys"], ["7000000000000000001"])
        signal = parsed["signals"][0]
        self.assertEqual(signal["metrics"]["views"], 24000)
        self.assertEqual(signal["metrics"]["shares"], 33)
        self.assertEqual(signal["published_at"], "")
        self.assertFalse(signal["detail_captured"])

    def test_existing_command_contract_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "raw.json"
            query = {"term": "meeting follow-up", "url": "https://x.com/search?q=meeting&f=live"}
            x_state = {"adapter": "opencli", "platform": "x", "mode": "standard"}
            x_search = contract.build_search_command(x_state, query, output, 1)
            self.assertEqual(x_search[:3], ["opencli", "twitter", "search"])
            self.assertIn("live", x_search)
            self.assertEqual(contract.build_detail_command(x_state, "https://x.com/a/status/1", output)[:3], ["opencli", "twitter", "thread"])

            xhs_state = {"adapter": "opencli", "platform": "xiaohongshu", "mode": "standard"}
            self.assertEqual(contract.build_search_command(xhs_state, query, output, 1)[:3], ["opencli", "xiaohongshu", "search"])
            self.assertEqual(contract.build_detail_command(xhs_state, "https://www.xiaohongshu.com/explore/1", output)[:3], ["opencli", "xiaohongshu", "note"])

            youtube_state = {"adapter": "opencli", "platform": "youtube", "mode": "standard"}
            youtube_query = {**query, "url": "https://www.youtube.com/results?search_query=meeting&sort=views&upload=month&type=video"}
            youtube_search = contract.build_search_command(youtube_state, youtube_query, output, 1)
            self.assertEqual(youtube_search[:3], ["opencli", "youtube", "search"])
            self.assertIn("--sort", youtube_search)
            self.assertIn("views", youtube_search)
            self.assertIn("--upload", youtube_search)
            self.assertIn("month", youtube_search)
            self.assertEqual(contract.build_detail_command(youtube_state, "https://www.youtube.com/watch?v=abc123", output)[:3], ["opencli", "youtube", "video"])

            tiktok_state = {"adapter": "opencli", "platform": "tiktok", "mode": "standard"}
            tiktok_search = contract.build_search_command(tiktok_state, query, output, 1)
            self.assertEqual(tiktok_search[:3], ["opencli", "tiktok", "search"])
            with self.assertRaises(ValueError):
                contract.build_detail_command(tiktok_state, "https://www.tiktok.com/@synthetic/video/1", output)

            tiktok_browser_state = {"adapter": "dokobot", "platform": "tiktok", "mode": "standard"}
            tiktok_detail = contract.build_detail_command(tiktok_browser_state, "https://www.tiktok.com/@synthetic/video/1", output)
            self.assertEqual(tiktok_detail[:2], ["dokobot", "read"])
            self.assertIn("--screens", tiktok_detail)

            doko_state = {"adapter": "dokobot", "platform": "x", "mode": "standard"}
            doko_search = contract.build_search_command(doko_state, {**query, "session_id": "abc"}, output, 1)
            self.assertEqual(doko_search[:2], ["dokobot", "read"])
            self.assertIn("--session-id", doko_search)

    def test_structured_import_is_cross_platform_but_not_live_capture(self) -> None:
        capability = contract.adapter_capability("structured_import", "youtube")
        self.assertIsNotNone(capability)
        self.assertEqual(capability["source_mode"], "customer_export")
        self.assertIsNone(capability["search_builder"])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                contract.build_search_command(
                    {"adapter": "structured_import", "platform": "youtube", "mode": "standard"},
                    {"term": "topic", "url": "https://example.com"}, Path(directory) / "raw.json", 1,
                )

    def test_structured_import_output_records_adapter_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            output = root / "normalized.json"
            source.write_text(json.dumps({"items": [{
                "id": "1", "platform": "youtube", "title": "A supplied signal",
                "url": "https://example.com/1", "published_at": "2026-08-13T00:00:00Z"
            }]}), encoding="utf-8")
            subprocess.run([
                sys.executable, str(SCRIPTS / "normalize_signals.py"), "--input", str(source),
                "--output", str(output), "--platform", "youtube", "--source-mode", "customer_export",
            ], check=True, capture_output=True, text=True)
            normalized = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(normalized["platform_adapter"]["adapter"], "structured_import")
            self.assertEqual(normalized["platform_adapter"]["contract_version"], "platform-adapter-contract-v0.2")
            self.assertFalse(normalized["platform_adapter"]["live_collection"])


if __name__ == "__main__":
    unittest.main()
