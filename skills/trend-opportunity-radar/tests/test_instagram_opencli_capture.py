from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_instagram_opencli_capture as capture


class InstagramOpenCliCaptureTest(unittest.TestCase):
    @staticmethod
    def request() -> dict:
        return {
            "request_sha256": "synthetic-hash",
            "hashtag": "travelplanning",
            "query_url": "https://www.instagram.com/explore/search/keyword/?q=%23travelplanning",
            "max_posts": 24,
            "max_detail_posts": 6,
        }

    def test_surface_requires_target_identity_before_accepting_results(self) -> None:
        query = "https://www.instagram.com/explore/search/keyword/?q=%23travelplanning"
        valid = capture.inspect_surface({
            "url": query,
            "visible_hashtag": "#travelplanning",
            "post_link_count": 24,
            "explicit_empty": False,
        }, query, "travelplanning")
        self.assertEqual(valid["state"], "results_visible")
        blank = capture.inspect_surface({
            "url": "about:blank",
            "visible_hashtag": "",
            "post_link_count": 0,
            "explicit_empty": False,
        }, query, "travelplanning")
        self.assertEqual(blank["state"], "surface_unreadable")

    def test_zero_results_requires_explicit_platform_empty_state(self) -> None:
        query = "https://www.instagram.com/explore/search/keyword/?q=%23syntheticnone"
        unproven = capture.inspect_surface({
            "url": query,
            "visible_hashtag": "#syntheticnone",
            "post_link_count": 0,
            "explicit_empty": False,
        }, query, "syntheticnone")
        self.assertEqual(unproven["state"], "surface_unreadable")
        proven = capture.inspect_surface({
            "url": query,
            "visible_hashtag": "#syntheticnone",
            "post_link_count": 0,
            "explicit_empty": True,
        }, query, "syntheticnone")
        self.assertEqual(proven["state"], "explicit_empty")

    def test_execute_marks_unreadable_surface_instead_of_zero_results(self) -> None:
        def fake_cli(_path, args, _timeout, _runner):
            if "eval" in args:
                return {"url": "about:blank", "visible_hashtag": "", "post_link_count": 0, "explicit_empty": False}
            return {}
        with patch.object(capture, "run_cli", side_effect=fake_cli):
            result = capture.execute(self.request(), "opencli", "instagram-test", 0, 1, 10, 3, 30, sleeper=lambda _: None)
        self.assertEqual(result["stop_reason"], "surface_unreadable")
        self.assertEqual(result["capture_audit"]["controller"], "opencli_browser")

    def test_execute_accepts_only_two_explicit_empty_passes_as_verified_zero(self) -> None:
        def fake_cli(_path, args, _timeout, _runner):
            if "eval" in args:
                return {
                    "url": self.request()["query_url"],
                    "visible_hashtag": "#travelplanning",
                    "post_link_count": 0,
                    "explicit_empty": True,
                }
            return {}
        with patch.object(capture, "run_cli", side_effect=fake_cli):
            result = capture.execute(self.request(), "opencli", "instagram-test", 0, 1, 10, 3, 30, sleeper=lambda _: None)
        self.assertEqual(result["stop_reason"], "verified_zero_results")

    def test_detail_parser_keeps_public_fields_and_bounded_comments(self) -> None:
        parsed = capture.parse_detail({
            "canonical_url": "https://www.instagram.com/p/SYNTHETIC001/?utm_source=test",
            "og_title": "Synthetic Creator on Instagram: \"A weekly family meal plan\"",
            "description": "1,234 likes, 56 comments - synthetic.creator on August 20, 2026: \"A weekly family meal plan\".",
            "published_at": "2026-08-20T00:00:00Z",
            "comments": [{"author_username": "synthetic.viewer", "text": "How many meals?", "published_at": "2026-08-20T01:00:00Z"}],
        })
        self.assertEqual(parsed["canonical_url"], "https://www.instagram.com/p/SYNTHETIC001/")
        self.assertEqual(parsed["author_username"], "synthetic.creator")
        self.assertEqual(parsed["likes"], 1234)
        self.assertEqual(parsed["comments"], 56)
        self.assertTrue(parsed["representative_comments"][0]["top_level_visible"])
        self.assertNotIn("cookie", parsed)

    def test_non_post_url_is_rejected(self) -> None:
        self.assertEqual(capture.canonical_url("https://www.instagram.com/explore/"), "")


if __name__ == "__main__":
    unittest.main()
