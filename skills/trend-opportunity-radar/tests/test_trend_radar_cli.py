from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import trend_radar
import check_facebook_topic_adapter


def ready_opencli(*platforms: str) -> dict:
    return {
        "schema_version": "collection-adapter-status-v0.2",
        "adapter": "opencli",
        "ready": True,
        "status": "ready",
        "checked_at": "2026-08-21T00:00:00Z",
        "capabilities": {platform: True for platform in platforms},
    }


class TrendRadarDoctorTest(unittest.TestCase):
    def test_facebook_redacted_probe_can_enable_only_the_posts_topic_route(self) -> None:
        status = check_facebook_topic_adapter.build_status({
            "logged_in_session": True,
            "query_url": "https://www.facebook.com/search/posts/?q=meal%20planning",
            "query": "meal planning",
            "query_identity_visible": True,
            "posts_only_surface": True,
            "canonical_public_post_links": ["https://www.facebook.com/example/posts/synthetic-101"],
            "detail_probe": {
                "canonical_url": "https://www.facebook.com/example/posts/synthetic-101",
                "content_id": "synthetic-101",
                "published_at": "2026-08-20T00:00:00Z",
            },
            "no_personal_surfaces": True,
            "no_write_actions": True,
            "no_credential_export": True,
        })
        self.assertTrue(status["ready"])
        blocked = trend_radar.build_doctor_report("facebook", [status], language="en")
        self.assertEqual(blocked["state"], "pilot_opt_in_required")
        ready = trend_radar.build_doctor_report("facebook", [status], allow_pilot=True, language="en")
        self.assertEqual(ready["state"], "ready_live")
        self.assertEqual(ready["live"]["search_adapter"], "facebook_posts_browser_capture")

    def test_facebook_probe_rejects_generic_search_or_missing_detail(self) -> None:
        status = check_facebook_topic_adapter.build_status({
            "logged_in_session": True,
            "query_url": "https://www.facebook.com/search/top/?q=meal%20planning",
            "query": "meal planning",
            "query_identity_visible": True,
            "posts_only_surface": False,
            "canonical_public_post_links": ["https://www.facebook.com/example/posts/synthetic-101"],
            "no_personal_surfaces": True,
            "no_write_actions": True,
            "no_credential_export": True,
        })
        self.assertFalse(status["ready"])
        self.assertIn("posts_search_url", status["missing_checks"])
        self.assertIn("detail_identity", status["missing_checks"])

    def test_validated_platform_without_preflight_requests_real_probe(self) -> None:
        report = trend_radar.build_doctor_report("x", [], language="en")
        self.assertEqual(report["state"], "preflight_required")
        self.assertFalse(report["live"]["ready"])
        self.assertTrue(report["structured_import"]["ready"])
        self.assertEqual(report["checked_adapters"], [])

    def test_ready_status_selects_live_adapter_without_raw_diagnostics(self) -> None:
        status = ready_opencli("x")
        status["cli"] = {"path": "C:/private/local/opencli.cmd"}
        status["diagnostics"] = {"stderr": "private machine output"}
        status["capabilities"]["local_path"] = "C:/private/capability"
        report = trend_radar.build_doctor_report("x", [status], language="en")
        self.assertEqual(report["state"], "ready_live")
        self.assertEqual(report["live"]["search_adapter"], "opencli")
        rendered = json.dumps(report)
        self.assertNotIn("C:/private", rendered)
        self.assertNotIn("private machine output", rendered)

    def test_pilot_requires_explicit_opt_in(self) -> None:
        status = ready_opencli("tiktok")
        blocked = trend_radar.build_doctor_report("tiktok", [status], language="en")
        self.assertEqual(blocked["state"], "pilot_opt_in_required")
        allowed = trend_radar.build_doctor_report("tiktok", [status], allow_pilot=True, language="en")
        self.assertEqual(allowed["state"], "ready_live")

    def test_unsupported_live_scope_keeps_import_path(self) -> None:
        report = trend_radar.build_doctor_report("youtube", [], research_scope="account_research", language="en")
        self.assertEqual(report["state"], "import_only")
        self.assertTrue(report["structured_import"]["ready"])


class TrendRadarStartTest(unittest.TestCase):
    def make_args(self, output: Path, **overrides: object) -> argparse.Namespace:
        values = {
            "prompt": "分析 AI 旅行规划在 X 的内容机会。",
            "output_dir": str(output),
            "intent": "",
            "platform": "",
            "language": "",
            "subject": None,
            "research_scope": "topic_research",
            "status": [],
            "allow_pilot": False,
            "mode": "standard",
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_start_freezes_context_subject_and_single_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status_path = root / "opencli-status.json"
            status_path.write_text(json.dumps(ready_opencli("x")), encoding="utf-8")
            run_dir = root / "run"
            manifest = trend_radar.start_run(self.make_args(run_dir, status=[str(status_path)]))
            self.assertEqual(manifest["state"], "query_plan_required")
            self.assertEqual(manifest["research_intent"], "content_opportunity")
            self.assertEqual(manifest["platform"], "x")
            self.assertTrue((run_dir / "research-context.json").exists())
            self.assertTrue((run_dir / "subject.json").exists())
            self.assertTrue((run_dir / "environment-doctor.json").exists())
            self.assertTrue((run_dir / "run-manifest.json").exists())

    def test_start_is_idempotent_for_same_request_and_rejects_different_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            first = trend_radar.start_run(self.make_args(run_dir))
            second = trend_radar.start_run(self.make_args(run_dir))
            self.assertEqual(first["request_sha256"], second["request_sha256"])
            with self.assertRaisesRegex(ValueError, "different research request"):
                trend_radar.start_run(self.make_args(run_dir, prompt="分析不同主题在 X 的内容机会。"))

    def test_same_run_advances_after_a_real_preflight_status_is_added(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            first = trend_radar.start_run(self.make_args(run_dir))
            self.assertEqual(first["state"], "preflight_required")
            status_path = root / "opencli-status.json"
            status_path.write_text(json.dumps(ready_opencli("x")), encoding="utf-8")
            second = trend_radar.start_run(self.make_args(run_dir, status=[str(status_path)]))
            self.assertEqual(second["state"], "query_plan_required")
            self.assertEqual(second["created_at"], first["created_at"])

    def test_clarification_can_be_resolved_in_the_same_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            first = trend_radar.start_run(self.make_args(run_dir, prompt="研究 AI 工具。"))
            self.assertEqual(first["state"], "clarification_required")
            second = trend_radar.start_run(self.make_args(
                run_dir,
                prompt="研究 AI 工具。",
                intent="content_opportunity",
                platform="x",
                language="zh-CN",
            ))
            self.assertEqual(second["state"], "preflight_required")
            self.assertEqual(second["research_intent"], "content_opportunity")

    def test_sampling_mode_cannot_change_after_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            trend_radar.start_run(self.make_args(run_dir))
            with self.assertRaisesRegex(ValueError, "sampling mode is frozen"):
                trend_radar.start_run(self.make_args(run_dir, mode="quick"))

    def test_subject_cannot_change_after_context_is_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            trend_radar.start_run(self.make_args(run_dir))
            changed_subject = root / "changed-subject.json"
            changed_subject.write_text(json.dumps({
                "name": "Different subject",
                "subject_type": "idea",
                "summary": "A different subject",
                "facts": [],
                "hypotheses": [],
                "audiences": [],
                "scenarios": [],
                "constraints": [],
                "source_refs": [],
                "communication": {"language": "zh-CN", "goal": "general_research", "audience": "general"},
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "subject is frozen"):
                trend_radar.start_run(self.make_args(run_dir, subject=str(changed_subject)))

    def test_ambiguous_request_stops_with_one_clarification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            manifest = trend_radar.start_run(self.make_args(run_dir, prompt="研究 AI 工具。"))
            self.assertEqual(manifest["state"], "clarification_required")
            self.assertIsNone(manifest["subject"])
            self.assertLessEqual(str(manifest["next_action"]).count("？"), 1)

    def test_cli_doctor_returns_nonzero_when_live_is_required(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "trend_radar.py"),
                "doctor",
                "--platform",
                "x",
                "--require-live",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["state"], "preflight_required")

    def test_cli_chinese_output_is_lossless_on_legacy_console(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "trend_radar.py"),
                "doctor",
                "--platform",
                "facebook",
                "--language",
                "zh-CN",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            check=True,
        )
        payload = json.loads(completed.stdout)
        self.assertIn("明确同意", payload["next_action"])


if __name__ == "__main__":
    unittest.main()
