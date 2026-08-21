from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_instagram_topic_report as generator
import merge_instagram_topic_snapshots as merger
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
            self.assertEqual(report["schema_version"], "instagram-topic-research-report-v0.2")
            self.assertEqual(report["platform_native_context"]["platform"], "instagram")
            rendered = generator.html_page(report)
            self.assertIn("viewport", rendered)
            self.assertIn("What this can support now", rendered)
            self.assertIn("How to read this platform evidence", rendered)
            self.assertIn("content supply, not search demand", rendered)
            self.assertNotIn("traceback", rendered.casefold())

    def test_standard_multi_layer_snapshot_can_meet_sampling_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            layers = ("platform_baseline", "category", "subject_bridge")
            for layer_index, layer in enumerate(layers):
                request = capture.build_request("Family meal planning", f"mealplanning{layer_index}", layer, 24, 6)
                links = [f"https://www.instagram.com/p/L{layer_index}ITEM{item}/" for item in range(24)]
                payload = {
                    "schema_version": capture.CAPTURE_SCHEMA,
                    "request_sha256": request["request_sha256"],
                    "hashtag": request["hashtag"],
                    "displayed_post_count_label": "50K posts",
                    "result_passes": [links, links],
                    "result_cards": [{"canonical_url": url, "author_username": f"creator{layer_index}_{item}", "preview_text": f"Meal planning preview {layer_index} {item}"} for item, url in enumerate(links)],
                    "posts": [{"canonical_url": links[item], "author_username": f"creator{layer_index}_{item}", "caption": f"Meal planning detail {layer_index} {item}", "published_at": "2026-08-19T00:00:00Z", "likes": 10, "comments": 2, "representative_comments": []} for item in range(6)],
                    "checks": {"hashtag_identity": True, "canonical_post_links": True, "public_fields_only": True, "no_account_search_proxy": True, "no_personalized_explore_feed": True, "no_write_actions": True, "no_credential_export": True},
                    "stop_reason": "",
                }
                raw = root / f"capture-{layer_index}.json"
                raw.write_text(json.dumps(payload), encoding="utf-8")
                snapshot, _ = capture.build_snapshot(request, payload, raw)
                path = root / f"snapshot-{layer_index}.json"
                path.write_text(json.dumps(snapshot), encoding="utf-8")
                paths.append(path)
            merged = merger.merge_snapshots(paths)
            for index, signal in enumerate(merged["signals"]):
                signal["semantic_relevance"] = "direct" if index % 5 else "adjacent"
                signal["evidence_role"] = "counter" if index in {0, 24, 48} else "support"
            analysis = {
                "direct_answer": "The evidence supports a bounded validation test.",
                "can_support": "A concrete prototype test.",
                "cannot_support": "Guaranteed demand.",
                "resolution": "Repeat weekly.",
                "findings": [{"title": "Meal planning friction", "claim": "Families describe recurring planning friction.", "why_it_matters": "It is a repeated task.", "recommended_action": "Test one weekly workflow.", "status": "review_ready", "evidence_signal_ids": [merged["signals"][1]["signal_id"]]}],
            }
            report = generator.build(merged, analysis, "en")
            self.assertEqual(report["research_basis"]["query_count"], 3)
            self.assertEqual(report["research_basis"]["sampling_status"], "complete")
            self.assertEqual(report["research_basis"]["repeat_pass_count"], 2)
            self.assertEqual(report["research_basis"]["repeat_overlap_jaccard"], 1.0)
            self.assertTrue(all(report["research_basis"]["sampling_checks"].values()))


if __name__ == "__main__":
    unittest.main()
