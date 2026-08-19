from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_instagram_topic_adapter as preflight
import run_instagram_topic_capture as capture


class InstagramTopicCaptureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = capture.build_request("Synthetic planning subject", "#syntheticplanning", "category", 12, 3)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def payload(self) -> dict:
        links = [f"https://www.instagram.com/p/SYNTHETIC{i}/" for i in range(8)]
        return {
            "schema_version": capture.CAPTURE_SCHEMA,
            "request_sha256": self.request["request_sha256"],
            "hashtag": "syntheticplanning",
            "query_url": self.request["query_url"],
            "captured_at": "2026-08-19T00:00:00Z",
            "displayed_post_count_label": "12K posts",
            "result_passes": [links, links[:7] + ["https://www.instagram.com/reel/SYNTHETIC8/"]],
            "posts": [{
                "canonical_url": links[index],
                "author_username": f"synthetic.creator{index}",
                "caption": f"Synthetic topic caption {index} #syntheticplanning",
                "published_at": f"2026-08-1{index}T00:00:00Z",
                "likes": 100 + index,
                "comments": 10 + index,
                "views": 1000 + index,
                "representative_comments": [{"author_name": "synthetic.viewer", "text": "Synthetic visible response", "top_level_visible": True}] if index == 0 else [],
            } for index in range(2)],
            "checks": {
                "hashtag_identity": True,
                "canonical_post_links": True,
                "public_fields_only": True,
                "no_account_search_proxy": True,
                "no_personalized_explore_feed": True,
                "no_write_actions": True,
                "no_credential_export": True,
            },
            "stop_reason": "",
        }

    def test_plan_freezes_explicit_hashtag_and_limits(self) -> None:
        request = capture.build_request("Subject", "#Synthetic_Tag", "subject_bridge", 99, 99)
        self.assertEqual(request["hashtag"], "synthetic_tag")
        self.assertIn("%23synthetic_tag", request["query_url"])
        self.assertEqual(request["max_posts"], 24)
        self.assertEqual(request["max_detail_posts"], 24)
        self.assertEqual(request["request_sha256"], capture.request_hash(request))

    def test_spaces_and_unknown_query_layers_are_rejected(self) -> None:
        with self.assertRaises(SystemExit):
            capture.build_request("Subject", "two words", "category")
        with self.assertRaises(SystemExit):
            capture.build_request("Subject", "oneword", "unknown")

    def test_record_separates_observed_links_details_and_hashtag_volume(self) -> None:
        payload = self.payload()
        raw = self.root / "capture.json"
        raw.write_text(json.dumps(payload), encoding="utf-8")
        snapshot, receipt = capture.build_snapshot(self.request, payload, raw)
        self.assertEqual(receipt["status"], "captured")
        self.assertEqual(snapshot["research_scope"], "topic_research")
        self.assertEqual(snapshot["raw_sample_count"], 8)
        self.assertEqual(snapshot["collection"]["counts"]["detail_open_count"], 2)
        self.assertEqual(snapshot["signals"][0]["semantic_relevance"], "pending_review")
        self.assertEqual(snapshot["signals"][0]["platform_facts"]["displayed_hashtag_volume_label"], "12K posts")
        self.assertIsNotNone(receipt["repeatability"]["overlap_jaccard"])

    def test_mismatched_hashtag_and_non_observed_detail_are_blocked(self) -> None:
        payload = self.payload()
        payload["hashtag"] = "different"
        self.assertEqual(capture.validate_capture(self.request, payload)[3], "content_mismatch")
        payload = self.payload()
        payload["posts"][0]["canonical_url"] = "https://www.instagram.com/p/NOTOBSERVED/"
        self.assertEqual(capture.validate_capture(self.request, payload)[3], "content_mismatch")

    def test_credentials_and_write_safety_mismatches_are_rejected(self) -> None:
        payload = self.payload()
        payload["cookies"] = "forbidden"
        with self.assertRaises(SystemExit):
            capture.validate_capture(self.request, payload)
        payload = self.payload()
        payload["checks"]["no_write_actions"] = False
        self.assertEqual(capture.validate_capture(self.request, payload)[3], "content_mismatch")

    def test_preflight_requires_hashtag_links_detail_and_safe_read_checks(self) -> None:
        probe = {
            "logged_in_session": True,
            "hashtag": "syntheticplanning",
            "query_url": self.request["query_url"],
            "canonical_post_links": [f"https://www.instagram.com/p/SYNTHETIC{i}/" for i in range(6)],
            "detail_probe": {"canonical_url": "https://www.instagram.com/p/SYNTHETIC0/", "content_id": "SYNTHETIC0", "published_at": "2026-08-19T00:00:00Z", "caption": "Synthetic"},
            "no_account_search_proxy": True,
            "no_personalized_explore_feed": True,
            "no_write_actions": True,
            "no_credential_export": True,
        }
        self.assertTrue(preflight.build_status(probe)["ready"])
        broken = copy.deepcopy(probe)
        broken["canonical_post_links"] = []
        self.assertFalse(preflight.build_status(broken)["ready"])


if __name__ == "__main__":
    unittest.main()
