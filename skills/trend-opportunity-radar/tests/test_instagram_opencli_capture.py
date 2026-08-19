from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_instagram_opencli_capture as capture


class InstagramOpenCliCaptureTest(unittest.TestCase):
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
