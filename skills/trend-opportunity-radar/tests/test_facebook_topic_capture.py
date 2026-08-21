from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_facebook_topic_capture as facebook
import merge_facebook_topic_snapshots as merger


class FacebookTopicCaptureTest(unittest.TestCase):
    def make_snapshot(self, layer: str, content_id: str = "1665370064521528") -> dict:
        url = f"https://www.facebook.com/reel/{content_id}/"
        return {
            "schema_version": "trend-signal-snapshot-v0.4",
            "platform": "facebook",
            "research_scope": "topic_research",
            "subject": "Synthetic family meal planning",
            "query": {"term": f"query {layer}", "layer": layer, "url": "https://www.facebook.com/search/posts/"},
            "raw_sample_count": 4,
            "collection": {"counts": {"observed_result_count": 4}, "repeatability": {"pass_count": 2, "overlap_jaccard": 0.5}, "terminal_reason": "visible_posts_results_exhausted"},
            "signals": [{
                "signal_id": f"facebook-{content_id}",
                "platform": "facebook",
                "canonical_url": url,
                "summary": "Synthetic visible result",
                "detail_captured": layer == "subject_bridge",
                "source_type": "direct_post" if layer == "subject_bridge" else "search_card",
                "query_terms": [f"query {layer}"],
                "query_layers": [layer],
                "evidence_refs": [url],
                "raw_artifacts": [],
            }],
        }

    def test_plan_freezes_posts_surface_and_read_only_actions(self) -> None:
        request = facebook.build_request("AI trip planning", "AI travel planner", "category")
        self.assertEqual(request["platform"], "facebook")
        self.assertIn("/search/posts/?q=", request["query_url"])
        self.assertIn("read_posts_search_results", request["allowed_actions"])
        self.assertIn("expand_exact_detail_comments_once", request["allowed_actions"])
        self.assertIn("use_home_feed", request["forbidden_actions"])
        self.assertIn("react", request["forbidden_actions"])

    def test_record_preserves_reactions_and_requires_detail_for_completion(self) -> None:
        request = facebook.build_request("AI trip planning", "AI travel planner", "category")
        url = "https://www.facebook.com/reel/1665370064521528/"
        capture = {
            "schema_version": facebook.CAPTURE_SCHEMA, "request_sha256": request["request_sha256"], "captured_at": "2026-08-20T00:00:00Z",
            "checks": {"posts_surface": True, "frozen_query_visible": True, "public_content_only": True, "no_home_feed": True, "no_mixed_search": True, "no_write_actions": True, "no_credential_export": True},
            "result_passes": [[url], [url]],
            "result_cards": [{"canonical_url": url, "author_name": "Synthetic Travel Page", "preview_text": "A synthetic public travel-planning example.", "observed_time_label": "1 day", "content_format": "reel", "reactions": 43, "comments": 9, "shares": 14}],
            "posts": [{"canonical_url": url, "author_name": "Synthetic Travel Page", "body_text": "A synthetic public travel-planning example with detail.", "observed_time_label": "1 day", "content_format": "reel", "reactions": 43, "comments": 9, "shares": 14, "representative_comments": [{"author_name": "Sample Reader", "text": "Does this work offline?", "top_level_visible": True}]}],
        }
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "capture.json"; raw.write_text(json.dumps(capture), encoding="utf-8")
            snapshot, receipt = facebook.build_snapshot(request, capture, raw)
        self.assertEqual(receipt["status"], "captured")
        self.assertEqual(snapshot["collection"]["counts"]["detail_open_count"], 1)
        self.assertEqual(snapshot["signals"][0]["metrics"]["reactions"], 43)
        self.assertIsNone(snapshot["signals"][0]["metrics"]["likes"])
        self.assertEqual(snapshot["signals"][0]["platform_facts"]["representative_comment_count"], 1)

    def test_mixed_search_or_personal_fields_are_rejected(self) -> None:
        request = facebook.build_request("AI trip planning", "AI travel planner", "category")
        capture = {"schema_version": facebook.CAPTURE_SCHEMA, "request_sha256": request["request_sha256"], "cookies": "forbidden", "result_passes": [[]], "checks": {}}
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / "capture.json"; raw.write_text(json.dumps(capture), encoding="utf-8")
            with self.assertRaises(SystemExit):
                facebook.build_snapshot(request, capture, raw)

    def test_merge_requires_three_layers_and_deduplicates_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for layer in ("platform_baseline", "category", "subject_bridge"):
                path = Path(temp) / f"{layer}.json"
                path.write_text(json.dumps(self.make_snapshot(layer)), encoding="utf-8")
                paths.append(path)
            merged = merger.merge_snapshots(paths)
        self.assertEqual(merged["raw_sample_count"], 12)
        self.assertEqual(merged["unique_sample_count"], 1)
        self.assertEqual(merged["collection"]["counts"]["detail_open_count"], 1)
        self.assertEqual(set(merged["signals"][0]["query_layers"]), {"platform_baseline", "category", "subject_bridge"})


if __name__ == "__main__":
    unittest.main()
