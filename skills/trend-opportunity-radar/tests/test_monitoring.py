from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from monitoring import append_snapshot, compare_monitor, create_monitor


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def completed_run(
    root: Path,
    name: str,
    *,
    generated_at: str,
    topics: list[dict],
    platform: str = "x",
    language: str = "zh-CN",
    query_suffix: str = "",
) -> Path:
    run_dir = root / name
    run_dir.mkdir()
    write_json(run_dir / "run-manifest.json", {
        "state": "complete", "mode": "standard", "platform": platform,
    })
    write_json(run_dir / "research-context.json", {
        "platform": platform,
        "research_intent": "product_demand",
        "profile_version": "product_demand_v1",
        "analysis_unit": "workflow_or_adoption_friction",
        "language": language,
        "market": "英语市场",
    })
    write_json(run_dir / "subject.json", {
        "name": "AI 个人预算",
        "subject_type": "idea",
        "summary": "帮助普通人管理预算",
    })
    write_json(run_dir / "query-plan.json", {
        "queries": [
            {"layer": "platform_baseline", "query": "budgeting pain" + query_suffix},
            {"layer": "category", "query": "personal finance app"},
            {"layer": "subject_bridge", "query": "AI budget assistant"},
        ]
    })
    normalized_topics = []
    for topic in topics:
        normalized_topics.append({
            "topic_key": topic["topic_key"],
            "title": topic.get("title", topic["topic_key"]),
            "observed_heat": topic.get("observed_heat", 50),
            "evidence_confidence": topic.get("evidence_confidence", 70),
            "sample_count": topic.get("sample_count", 12),
            "counter_signal_count": topic.get("counter_signal_count", 2),
            "score_version": "trend-evidence-v0.5.0-candidate",
            "engagement_weight_version": "x-v0.1-candidate",
            "cluster_audit": {"status": topic.get("audit_status", "passed")},
        })
    write_json(run_dir / "scored-signals.json", {
        "generated_at": generated_at,
        "unique_sample_count": 36,
        "collection": {"counts": {
            "observed_result_count": 60,
            "unique_sample_count": 36,
            "detail_open_count": 12,
            "counter_signal_count": 3,
        }},
        "topics": normalized_topics,
    })
    write_json(run_dir / "profile-findings.json", {
        "findings": [{"id": "test-one", "title": "先验证一个具体任务"}],
    })
    write_json(run_dir / "profile-report.json", {
        "generated_at": generated_at,
        "summary": "测试报告",
        "topics": normalized_topics,
    })
    return run_dir


class MonitoringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.baseline = completed_run(
            self.root,
            "baseline",
            generated_at="2026-08-20T00:00:00Z",
            topics=[
                {"topic_key": "pause", "title": "付款前暂停", "observed_heat": 30},
                {"topic_key": "leak", "title": "发现消费漏洞", "observed_heat": 40},
                {"topic_key": "old", "title": "旧信号", "observed_heat": 50},
                {"topic_key": "invalid", "audit_status": "failed"},
            ],
        )
        self.monitor_dir = self.root / "monitor"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_create_freezes_baseline_without_claiming_a_schedule(self) -> None:
        state = create_monitor(self.baseline, self.monitor_dir)
        self.assertEqual(state["cadence"]["days"], 3)
        self.assertEqual(state["cadence"]["target_snapshot_count"], 4)
        self.assertFalse(state["safety"]["external_schedule_created"])
        self.assertTrue(state["safety"]["requires_explicit_scheduler_confirmation"])
        self.assertEqual(len(state["snapshots"]), 1)
        self.assertEqual(len(state["snapshots"][0]["topics"]), 3)
        self.assertTrue((self.monitor_dir / "frozen-query-plan.json").is_file())

        repeated = create_monitor(self.baseline, self.monitor_dir)
        self.assertEqual(repeated, state)

    def test_append_is_compatible_newer_and_idempotent(self) -> None:
        create_monitor(self.baseline, self.monitor_dir)
        current = completed_run(
            self.root,
            "current",
            generated_at="2026-08-23T00:00:00Z",
            topics=[
                {"topic_key": "pause", "title": "付款前暂停", "observed_heat": 38},
                {"topic_key": "leak", "title": "发现消费漏洞", "observed_heat": 38},
                {"topic_key": "new", "title": "新信号", "observed_heat": 45},
            ],
        )
        state = append_snapshot(self.monitor_dir, current)
        self.assertEqual(len(state["snapshots"]), 2)
        before = (self.monitor_dir / "monitor.json").read_bytes()
        repeated = append_snapshot(self.monitor_dir, current)
        self.assertEqual(len(repeated["snapshots"]), 2)
        self.assertEqual((self.monitor_dir / "monitor.json").read_bytes(), before)

    def test_append_rejects_query_drift(self) -> None:
        create_monitor(self.baseline, self.monitor_dir)
        drifted = completed_run(
            self.root,
            "drifted",
            generated_at="2026-08-23T00:00:00Z",
            query_suffix=" changed",
            topics=[{"topic_key": "pause"}],
        )
        with self.assertRaisesRegex(ValueError, "query_plan_sha256"):
            append_snapshot(self.monitor_dir, drifted)

    def test_compare_requires_two_snapshots(self) -> None:
        create_monitor(self.baseline, self.monitor_dir)
        with self.assertRaisesRegex(ValueError, "At least two"):
            compare_monitor(self.monitor_dir)

    def test_compare_classifies_visible_movement_and_writes_three_formats(self) -> None:
        create_monitor(self.baseline, self.monitor_dir)
        current = completed_run(
            self.root,
            "current",
            generated_at="2026-08-23T00:00:00Z",
            topics=[
                {"topic_key": "pause", "title": "付款前暂停", "observed_heat": 38},
                {"topic_key": "leak", "title": "发现消费漏洞", "observed_heat": 38},
                {"topic_key": "new", "title": "新信号", "observed_heat": 45},
            ],
        )
        append_snapshot(self.monitor_dir, current)
        result = compare_monitor(self.monitor_dir)
        self.assertEqual([x["topic_key"] for x in result["movement"]["strengthened"]], ["pause"])
        self.assertEqual([x["topic_key"] for x in result["movement"]["persistent"]], ["leak"])
        self.assertEqual([x["topic_key"] for x in result["movement"]["new"]], ["new"])
        self.assertEqual([x["topic_key"] for x in result["movement"]["disappeared"]], ["old"])
        self.assertEqual(result["movement"]["weakened"], [])
        for name in ("monitor-compare.json", "monitor-compare.md", "monitor-compare.html"):
            self.assertTrue((self.monitor_dir / name).is_file(), name)
        rendered = (self.monitor_dir / "monitor-compare.html").read_text(encoding="utf-8")
        self.assertIn("不证明需求增长", rendered)
        self.assertNotIn("总分", rendered)

    def test_four_snapshot_cycle_stops_at_the_frozen_target(self) -> None:
        state = create_monitor(self.baseline, self.monitor_dir)
        self.assertEqual(state["status"], "active")
        for index, day in enumerate((23, 26, 29), start=2):
            run = completed_run(
                self.root,
                f"snapshot-{index}",
                generated_at=f"2026-08-{day:02d}T00:00:00Z",
                topics=[{"topic_key": "pause", "observed_heat": 30 + index}],
            )
            state = append_snapshot(self.monitor_dir, run)
        self.assertEqual(len(state["snapshots"]), 4)
        self.assertEqual(state["status"], "complete")
        overflow = completed_run(
            self.root,
            "snapshot-5",
            generated_at="2026-09-01T00:00:00Z",
            topics=[{"topic_key": "pause", "observed_heat": 40}],
        )
        with self.assertRaisesRegex(ValueError, "reached its target"):
            append_snapshot(self.monitor_dir, overflow)


if __name__ == "__main__":
    unittest.main()
