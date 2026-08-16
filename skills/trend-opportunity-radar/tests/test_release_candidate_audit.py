from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_release_candidate


class ReleaseCandidateAuditTest(unittest.TestCase):
    def matrix(self, replay_status: str = "completed") -> dict:
        return {
            "release_target": "candidate",
            "platforms": ["x"],
            "profiles": ["product_demand"],
            "execution_policy": {"live_e2e_per_profile_platform": 1, "snapshot_replay_per_profile_platform": 2},
            "cases": [
                {"intent": "product_demand", "platform": "x", "execution": "live_e2e", "status": "completed", "acceptance_result": {"report_generated": True, "decision_profile_validated": True, "visual_qa": "passed"}},
                {"intent": "product_demand", "platform": "x", "execution": "snapshot_replay", "status": replay_status, "acceptance_result": {"report_generated": True, "decision_profile_validated": True, "visual_qa": "passed"}},
                {"intent": "product_demand", "platform": "x", "execution": "snapshot_replay", "status": replay_status, "acceptance_result": {"report_generated": True, "decision_profile_validated": True, "visual_qa": "passed"}},
            ],
        }

    def replay(self) -> dict:
        return {"cases": [{"intent": "product_demand", "platform": "x", "status": "passed"}]}

    def test_ready_requires_live_code_replay_and_two_diverse_topics(self) -> None:
        result = audit_release_candidate.audit(self.matrix(), self.replay())
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["gaps"], [])

    def test_code_replay_does_not_satisfy_diverse_topic_gate(self) -> None:
        result = audit_release_candidate.audit(self.matrix("pending"), self.replay())
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(any("diverse_topic_snapshot_replay 0/2" in item for item in result["gaps"]))


if __name__ == "__main__":
    unittest.main()
