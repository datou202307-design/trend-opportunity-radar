from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workspace import build_workspace


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def make_run(root: Path, name: str, *, complete: bool, follow_up: bool = False) -> Path:
    run = root / name
    write_json(run / "run-manifest.json", {
        "schema_version": "trend-radar-run-v0.1",
        "request_sha256": name * 8,
        "state": "complete" if complete else "semantic_review_required",
        "platform": "x",
        "next_action": "复核现有信号" if not complete else "",
        "updated_at": "2026-08-24T00:00:00Z",
    })
    write_json(run / "research-context.json", {
        "platform": "x",
        "research_intent": "product_demand",
        "language": "zh-CN",
    })
    write_json(run / "subject.json", {"name": f"{name} 研究主题", "summary": "合成主题"})
    if complete:
        write_json(run / "profile-report.json", {
            "generated_at": "2026-08-24T00:00:00Z",
            "decision_answer": "先验证一个具体使用场景。",
            "follow_up_recommendation": {"recommended": follow_up, "created": False},
        })
        (run / "profile-report.html").write_text("<html><body>synthetic report</body></html>", encoding="utf-8")
    return run


def make_monitor(root: Path, run: Path) -> Path:
    monitor = root / "monitor-one"
    write_json(monitor / "monitor.json", {
        "schema_version": "trend-monitor-v0.1",
        "monitor_id": "synthetic-monitor",
        "status": "active",
        "compatibility": {"platform": "x"},
        "cadence": {"target_snapshot_count": 4},
        "safety": {
            "external_schedule_created": False,
            "requires_explicit_scheduler_confirmation": True,
        },
        "snapshots": [{
            "run_dir": str(run.resolve()),
            "observed_at": "2026-08-20T00:00:00Z",
            "topics": [{"title": "合成主题一"}],
        }],
        "next_run_after": "2026-08-23T00:00:00Z",
    })
    return monitor


class WorkspaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.complete = make_run(self.root, "complete", complete=True, follow_up=True)
        self.open_run = make_run(self.root, "open", complete=False)
        self.monitor = make_monitor(self.root, self.complete)
        self.output = self.root / "workspace"
        self.now = datetime(2026, 8, 25, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_builds_local_action_index_without_raw_content_or_absolute_paths(self) -> None:
        payload = build_workspace(self.root, self.output, language="zh-CN", now=self.now)
        self.assertEqual(payload["counts"], {
            "runs": 2,
            "completed_runs": 1,
            "open_runs": 1,
            "monitors": 1,
            "due_monitors": 1,
            "actions": 2,
        })
        self.assertEqual([item["kind"] for item in payload["actions"]], ["monitor_due", "continue_run"])
        self.assertFalse(payload["monitors"][0]["external_schedule_created"])
        self.assertNotIn("已安排", payload["actions"][0]["body"])
        self.assertTrue(payload["privacy"]["local_only"])
        self.assertFalse(payload["privacy"]["contains_raw_platform_content"])
        rendered = (self.output / "workspace.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), rendered)
        self.assertNotIn("synthetic report", rendered)
        self.assertTrue((self.output / "index.html").is_file())
        html_text = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertIn("持续观察", html_text)
        self.assertIn("未创建外部调度", html_text)
        self.assertIn("查看继续用语", html_text)
        self.assertNotIn("复制给 Agent", html_text)
        self.assertIn("<span>你的研究，</span><span>下一步做什么</span>", html_text)
        self.assertEqual(len(list((self.output / "summary-cards").glob("*.html"))), 1)
        summary = next((self.output / "summary-cards").glob("*.html")).read_text(encoding="utf-8")
        self.assertNotIn("<script", summary)

    def test_completed_unmonitored_run_is_a_decision_not_a_created_monitor(self) -> None:
        second = make_run(self.root, "unmonitored", complete=True, follow_up=True)
        payload = build_workspace(self.root, self.output, language="zh-CN", now=self.now)
        actions = [item for item in payload["actions"] if item["kind"] == "consider_monitoring"]
        self.assertEqual(len(actions), 1)
        self.assertIn(second.name, actions[0]["source"]["relative_dir"])
        self.assertIn("尚未创建监测或定时任务", actions[0]["body"])

    def test_real_external_schedule_state_is_displayed_separately(self) -> None:
        state_path = self.monitor / "monitor.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["safety"]["external_schedule_created"] = True
        write_json(state_path, state)
        payload = build_workspace(self.root, self.output, language="zh-CN", now=self.now)
        due = next(item for item in payload["actions"] if item["kind"] == "monitor_due")
        self.assertIn("外部调度记录为已创建", due["body"])
        rendered = (self.output / "index.html").read_text(encoding="utf-8")
        self.assertIn("已创建外部调度", rendered)

    def test_repeated_build_is_byte_stable(self) -> None:
        first = build_workspace(self.root, self.output, language="zh-CN", now=self.now)
        before = {
            path.relative_to(self.output).as_posix(): path.read_bytes()
            for path in self.output.rglob("*") if path.is_file()
        }
        second = build_workspace(self.root, self.output, language="zh-CN", now=self.now)
        after = {
            path.relative_to(self.output).as_posix(): path.read_bytes()
            for path in self.output.rglob("*") if path.is_file()
        }
        self.assertEqual(first, second)
        self.assertEqual(before, after)

    def test_output_is_bound_to_the_first_workspace_root(self) -> None:
        narrow = self.root / "nested-root"
        make_run(narrow, "nested-run", complete=False)
        bound_output = narrow / "workspace"
        build_workspace(narrow, bound_output, language="zh-CN", now=self.now)
        with self.assertRaisesRegex(ValueError, "different workspace"):
            build_workspace(self.root, bound_output, language="zh-CN", now=self.now)

    def test_output_must_stay_inside_indexed_root(self) -> None:
        outside = Path(self.temp.name + "-outside")
        with self.assertRaisesRegex(ValueError, "inside the indexed root"):
            build_workspace(self.root, outside, language="zh-CN", now=self.now)


if __name__ == "__main__":
    unittest.main()
