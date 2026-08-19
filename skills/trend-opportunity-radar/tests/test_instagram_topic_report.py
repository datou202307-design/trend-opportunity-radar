from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_instagram_topic_report as generator
import run_instagram_topic_capture as capture


class InstagramTopicReportTest(unittest.TestCase):
    def test_bounded_report_leads_with_decision_support_and_counts(self) -> None:
        request = capture.build_request("Synthetic planning", "syntheticplanning", "category", 6, 2)
        payload = {
            "schema_version": capture.CAPTURE_SCHEMA,
            "request_sha256": request["request_sha256"],
            "hashtag": "syntheticplanning",
            "displayed_post_count_label": "10K posts",
            "result_passes": [[f"https://www.instagram.com/p/SYNTHETIC{i}/" for i in range(6)]],
            "posts": [{"canonical_url": "https://www.instagram.com/p/SYNTHETIC0/", "author_username": "synthetic.creator", "caption": "Synthetic planning difficulty", "published_at": "2026-08-19T00:00:00Z", "likes": 10, "comments": 2, "representative_comments": []}],
            "checks": {"hashtag_identity": True, "canonical_post_links": True, "public_fields_only": True, "no_account_search_proxy": True, "no_personalized_explore_feed": True, "no_write_actions": True, "no_credential_export": True},
            "stop_reason": "",
        }
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "raw.json"
            raw.write_text(json.dumps(payload), encoding="utf-8")
            snapshot, _ = capture.build_snapshot(request, payload, raw)
            snapshot["signals"][0]["semantic_relevance"] = "direct"
            analysis = {
                "direct_answer": "A bounded answer.", "can_support": "A narrow test.", "cannot_support": "Demand strength.", "resolution": "Collect the other layers.",
                "findings": [{"title": "Planning coordination", "claim": "A bounded claim.", "why_it_matters": "It names a task.", "recommended_action": "Test one workflow.", "status": "candidate", "evidence_signal_ids": [snapshot["signals"][0]["signal_id"]]}],
            }
            report = generator.build(snapshot, analysis, "en")
            self.assertEqual(report["research_basis"]["observed_post_count"], 6)
            self.assertEqual(report["research_basis"]["sampling_status"], "bounded")
            self.assertEqual(report["research_basis"]["relevant_post_count"], 1)
            rendered = generator.html_page(report)
            self.assertIn("viewport", rendered)
            self.assertIn("What this can support now", rendered)
            self.assertNotIn("traceback", rendered.casefold())


if __name__ == "__main__":
    unittest.main()
