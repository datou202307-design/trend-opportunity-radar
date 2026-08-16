from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m0"
INTENTS = {
    "business_opportunity",
    "brand_sentiment",
    "competitor_users",
    "content_opportunity",
    "product_demand",
}
PLATFORMS = {"x", "xiaohongshu"}


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class M0ContractTest(unittest.TestCase):
    def test_intent_eval_has_minimum_coverage_and_backward_compatibility(self) -> None:
        payload = load_fixture("intent-cases.json")
        cases = payload["cases"]
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))

        clear_counts = Counter(
            case["expected_intent"]
            for case in cases
            if not case["clarification_required"]
        )
        for intent in INTENTS:
            self.assertGreaterEqual(clear_counts[intent], 3)

        default_case = next(case for case in cases if case["id"] == "backward-compatible-default")
        self.assertEqual(default_case["expected_intent"], "business_opportunity")
        self.assertFalse(default_case["clarification_required"])
        self.assertTrue(any(case["clarification_required"] for case in cases))

    def test_acceptance_matrix_is_complete_and_balanced(self) -> None:
        payload = load_fixture("acceptance-matrix.json")
        cases = payload["cases"]
        self.assertEqual(set(payload["profiles"]), INTENTS)
        self.assertEqual(set(payload["platforms"]), PLATFORMS)
        self.assertEqual(len(cases), 30)
        self.assertEqual(len({case["id"] for case in cases}), 30)

        pair_counts = Counter((case["intent"], case["platform"]) for case in cases)
        live_counts = Counter(
            (case["intent"], case["platform"])
            for case in cases
            if case["execution"] == "live_e2e"
        )
        replay_counts = Counter(
            (case["intent"], case["platform"])
            for case in cases
            if case["execution"] == "snapshot_replay"
        )
        for intent in INTENTS:
            for platform in PLATFORMS:
                pair = (intent, platform)
                self.assertEqual(pair_counts[pair], 3)
                self.assertEqual(live_counts[pair], 1)
                self.assertEqual(replay_counts[pair], 2)

        allowed_statuses = {"pending", "completed_bounded", "passed", "failed"}
        self.assertTrue(all(case["status"] in allowed_statuses for case in cases))
        completed = next(case for case in cases if case["id"] == "pd-x-01")
        self.assertEqual(completed["status"], "completed_bounded")
        self.assertTrue(completed["acceptance_result"]["report_generated"])
        self.assertTrue(completed["acceptance_result"]["decision_profile_validated"])
        self.assertTrue(all(case["topic"].strip() for case in cases))

    def test_business_opportunity_golden_contract_is_profile_ready(self) -> None:
        payload = load_fixture("business-opportunity-golden.json")
        self.assertEqual(payload["expected_default_intent"], "business_opportunity")
        self.assertEqual(
            set(payload["required_query_layers"]),
            {"platform_baseline", "category", "subject_bridge"},
        )
        self.assertEqual(set(payload["required_report_formats"]), {"json", "markdown", "html"})
        self.assertEqual(
            payload["required_collection_terminal"],
            {"contract_status": "met", "stop_reason": "sampling_contract_met"},
        )
        self.assertIn("decision_support", payload["required_report_keys"])
        self.assertIn("evidence_status", payload["required_opportunity_keys"])
        self.assertIn("topic_key", payload["forbidden_reader_terms"])


if __name__ == "__main__":
    unittest.main()
