from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_tiktok_comment_enrichment as enrichment


class TikTokCommentEnrichmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.snapshot = {
            "platform": "tiktok",
            "signals": [{
                "signal_id": "tiktok:7000000000000000001",
                "content_id": "7000000000000000001",
                "canonical_url": "https://www.tiktok.com/@synthetic.creator/video/7000000000000000001",
                "detail_captured": True,
                "source_type": "direct_post",
                "author": {"id": "synthetic.creator", "handle": "@synthetic.creator"},
                "platform_facts": {
                    "representative_comments": [],
                    "representative_comment_count": 0,
                    "comment_sample_limit": 5,
                    "comment_capture_status": "unavailable",
                },
                "limitations": ["No representative comment text was visible in the bounded detail read."],
                "evidence_refs": [],
                "raw_artifacts": [],
            }],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def capture(self, request: dict, comments: list[dict] | None = None) -> dict:
        return {
            "schema_version": enrichment.CAPTURE_SCHEMA,
            "request_sha256": request["request_sha256"],
            "canonical_url": request["canonical_url"],
            "content_id": request["content_id"],
            "author_handle": request["author_handle"],
            "visible_comment_entry_count": 120,
            "comments": comments if comments is not None else [{
                "author_name": "synthetic.viewer",
                "text": "A synthetic visible comment",
                "likes": 4,
                "top_level_visible": True,
            }],
            "checks": {
                "stable_content_id": True,
                "author_path": True,
                "target_comments_panel": True,
                "top_level_visible_comments_only": True,
                "no_recommended_content": True,
                "no_write_actions": True,
            },
            "stop_reason": "",
        }

    def test_plan_freezes_one_verified_target(self) -> None:
        request = enrichment.build_request(self.snapshot)
        self.assertEqual(request["content_id"], "7000000000000000001")
        self.assertEqual(request["max_comments"], 5)
        self.assertEqual(request["request_sha256"], enrichment.request_hash(request))

    def test_plan_can_freeze_an_explicit_eligible_signal(self) -> None:
        other = copy.deepcopy(self.snapshot["signals"][0])
        other.update({
            "signal_id": "tiktok-7000000000000000002",
            "content_id": "7000000000000000002",
            "canonical_url": "https://www.tiktok.com/@second.synthetic/video/7000000000000000002",
            "author": {"id": "second.synthetic", "handle": "@second.synthetic"},
        })
        snapshot = {**self.snapshot, "signals": [self.snapshot["signals"][0], other]}
        request = enrichment.build_request(snapshot, "tiktok-7000000000000000002")
        self.assertEqual(request["content_id"], "7000000000000000002")

    def test_record_merges_visible_comments_without_changing_sample_volume(self) -> None:
        request = enrichment.build_request(self.snapshot)
        capture = self.capture(request)
        raw = self.root / "capture.json"
        raw.write_text(json.dumps(capture), encoding="utf-8")
        updated, receipt = enrichment.apply_capture(self.snapshot, request, capture, raw)
        comments = updated["signals"][0]["platform_facts"]["representative_comments"]
        self.assertEqual(len(comments), 1)
        self.assertEqual(receipt["status"], "captured")
        self.assertTrue(receipt["snapshot_mutated"])
        self.assertEqual(len(updated["signals"]), len(self.snapshot["signals"]))
        self.assertEqual(self.snapshot["signals"][0]["platform_facts"]["representative_comments"], [])

    def test_more_than_five_comments_is_rejected(self) -> None:
        request = enrichment.build_request(self.snapshot)
        row = {"author_name": "viewer", "text": "visible", "top_level_visible": True}
        capture = self.capture(request, [{**row, "author_name": f"viewer-{index}", "text": f"visible-{index}"} for index in range(6)])
        with self.assertRaises(SystemExit):
            enrichment.validate_capture(request, capture)

    def test_target_mismatch_is_blocked_without_mutating_snapshot(self) -> None:
        request = enrichment.build_request(self.snapshot)
        capture = self.capture(request)
        capture["canonical_url"] = "https://www.tiktok.com/@other.creator/video/7000000000000000002"
        raw = self.root / "mismatch.json"
        raw.write_text(json.dumps(capture), encoding="utf-8")
        updated, receipt = enrichment.apply_capture(self.snapshot, request, capture, raw)
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["stop_reason"], "content_mismatch")
        self.assertFalse(receipt["snapshot_mutated"])
        self.assertEqual(updated, self.snapshot)

    def test_unavailable_comments_leave_snapshot_unchanged(self) -> None:
        request = enrichment.build_request(self.snapshot)
        capture = self.capture(request, [])
        capture["visible_comment_entry_count"] = 0
        capture["stop_reason"] = "comments_unavailable"
        raw = self.root / "unavailable.json"
        raw.write_text(json.dumps(capture), encoding="utf-8")
        updated, receipt = enrichment.apply_capture(self.snapshot, request, capture, raw)
        self.assertEqual(receipt["status"], "unavailable")
        self.assertFalse(receipt["snapshot_mutated"])
        self.assertEqual(updated, self.snapshot)

    def test_capture_must_match_frozen_request_hash(self) -> None:
        request = enrichment.build_request(self.snapshot)
        capture = self.capture(request)
        capture["request_sha256"] = "0" * 64
        with self.assertRaises(SystemExit):
            enrichment.validate_capture(request, capture)


if __name__ == "__main__":
    unittest.main()
