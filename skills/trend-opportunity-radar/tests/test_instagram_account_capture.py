from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_instagram_browser_adapter as preflight
import run_instagram_account_capture as capture
import generate_instagram_account_report as report_generator


class InstagramAccountCaptureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = capture.build_request("synthetic.brand", max_posts=6, max_detail_posts=3)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def payload(self) -> dict:
        posts = []
        for index in range(3):
            posts.append({
                "canonical_url": f"https://www.instagram.com/reel/SYNTHETIC{index}/",
                "author_username": "synthetic.brand",
                "detail_captured": index < 2,
                "caption": f"Synthetic caption {index}" if index < 2 else "",
                "published_at": f"2026-08-1{index}T00:00:00Z" if index < 2 else "",
                "likes": 100 + index,
                "comments": 10 + index,
                "views": 1000 + index,
                "representative_comments": [{
                    "author_name": "synthetic.viewer",
                    "text": f"Synthetic visible comment {index}",
                    "likes": 2,
                    "top_level_visible": True,
                }] if index == 0 else [],
            })
        return {
            "schema_version": capture.CAPTURE_SCHEMA,
            "request_sha256": self.request["request_sha256"],
            "username": "synthetic.brand",
            "captured_at": "2026-08-19T00:00:00Z",
            "profile": {"display_name": "Synthetic Brand", "bio": "Synthetic fixture"},
            "posts": posts,
            "checks": {
                "profile_identity": True,
                "canonical_post_links": True,
                "public_fields_only": True,
                "no_follow_graph": True,
                "no_write_actions": True,
                "no_credential_export": True,
            },
            "stop_reason": "",
        }

    def test_plan_is_bounded_and_hashed(self) -> None:
        request = capture.build_request("@synthetic.brand", max_posts=99, max_detail_posts=99)
        self.assertEqual(request["username"], "synthetic.brand")
        self.assertEqual(request["max_posts"], 12)
        self.assertEqual(request["max_detail_posts"], 12)
        self.assertEqual(request["request_sha256"], capture.request_hash(request))

    def test_record_preserves_stable_identity_and_counts(self) -> None:
        payload = self.payload()
        raw = self.root / "capture.json"
        raw.write_text(json.dumps(payload), encoding="utf-8")
        snapshot, receipt = capture.build_snapshot(self.request, payload, raw)
        self.assertEqual(receipt["status"], "captured")
        self.assertEqual(snapshot["research_scope"], "account_research")
        self.assertEqual(snapshot["raw_sample_count"], 3)
        self.assertEqual(snapshot["collection"]["counts"]["detail_open_count"], 2)
        self.assertEqual(snapshot["signals"][0]["content_id"], "SYNTHETIC0")
        self.assertEqual(snapshot["signals"][0]["platform_facts"]["representative_comment_count"], 1)
        self.assertEqual(snapshot["signals"][2]["source_type"], "search_card")

    def test_account_mismatch_is_blocked(self) -> None:
        payload = self.payload()
        payload["posts"][0]["author_username"] = "other.brand"
        status, _, reason = capture.validate_capture(self.request, payload)
        self.assertEqual((status, reason), ("blocked", "content_mismatch"))

    def test_account_prefixed_browser_url_is_supported_and_checked(self) -> None:
        payload = self.payload()
        payload["posts"][0]["canonical_url"] = "https://www.instagram.com/synthetic.brand/reel/SYNTHETIC0/"
        status, posts, reason = capture.validate_capture(self.request, payload)
        self.assertEqual((status, reason), ("captured", ""))
        self.assertIn("/synthetic.brand/reel/", posts[0]["canonical_url"])
        payload["posts"][0]["canonical_url"] = "https://www.instagram.com/other.brand/reel/SYNTHETIC0/"
        self.assertEqual(capture.validate_capture(self.request, payload)[2], "content_mismatch")

    def test_follow_graph_and_credentials_are_rejected(self) -> None:
        for key in ("followers", "cookies"):
            payload = self.payload()
            payload[key] = 123
            with self.assertRaises(SystemExit):
                capture.validate_capture(self.request, payload)

    def test_comment_limit_is_enforced(self) -> None:
        payload = self.payload()
        row = {"author_name": "viewer", "text": "visible", "top_level_visible": True}
        payload["posts"][0]["representative_comments"] = [{**row, "author_name": f"viewer-{index}"} for index in range(6)]
        with self.assertRaises(SystemExit):
            capture.validate_capture(self.request, payload)

    def test_preflight_requires_links_detail_and_privacy_checks(self) -> None:
        probe = {
            "logged_in_session": True,
            "public_profile_accessible": True,
            "canonical_post_links": [f"https://www.instagram.com/reel/SYNTHETIC{index}/" for index in range(3)],
            "detail_probe": {"canonical_url": "https://www.instagram.com/reel/SYNTHETIC0/", "content_id": "SYNTHETIC0", "published_at": "2026-08-19T00:00:00Z", "caption": "Synthetic"},
            "no_follow_graph": True,
            "no_write_actions": True,
            "no_credential_export": True,
        }
        self.assertTrue(preflight.build_status(probe)["ready"])
        broken = copy.deepcopy(probe)
        broken["canonical_post_links"] = []
        self.assertFalse(preflight.build_status(broken)["ready"])

    def test_not_found_and_private_accounts_stop_without_signals(self) -> None:
        for reason in ("account_not_found", "private_account"):
            payload = self.payload()
            payload["stop_reason"] = reason
            status, posts, stop_reason = capture.validate_capture(self.request, payload)
            self.assertEqual((status, posts, stop_reason), ("blocked", [], reason))

    def test_account_report_keeps_account_scope_and_evidence_links(self) -> None:
        payload = self.payload()
        raw = self.root / "capture.json"
        raw.write_text(json.dumps(payload), encoding="utf-8")
        snapshot, _ = capture.build_snapshot(self.request, payload, raw)
        analysis = {
            "direct_answer": "A bounded synthetic answer.",
            "findings": [{
                "title": "Synthetic finding",
                "claim": "A synthetic evidence-bound claim.",
                "why_it_matters": "Synthetic reason.",
                "recommended_action": "Synthetic action.",
                "evidence_signal_ids": [snapshot["signals"][0]["signal_id"]],
            }],
        }
        report = report_generator.build(snapshot, analysis, "en")
        self.assertEqual(report["research_scope"], "account_research")
        self.assertEqual(report["research_basis"]["observed_post_count"], 3)
        self.assertEqual(report["findings"][0]["evidence_urls"], [snapshot["signals"][0]["canonical_url"]])
        rendered = report_generator.html_page(report)
        self.assertIn("viewport", rendered)
        self.assertNotIn("trend score", rendered.casefold())


if __name__ == "__main__":
    unittest.main()
