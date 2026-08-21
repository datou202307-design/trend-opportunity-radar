from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m0"
sys.path.insert(0, str(SCRIPTS))

import decision_profiles
import research_context


class ResearchContextTest(unittest.TestCase):
    def test_profile_registry_contains_five_versioned_profiles(self) -> None:
        registry = decision_profiles.load_registry()
        self.assertEqual(len(registry["profiles"]), 5)
        self.assertEqual(registry["profiles"]["business_opportunity"]["implementation_status"], "available")
        self.assertTrue(all(profile["version"].endswith("_v1") for profile in registry["profiles"].values()))

    def test_m0_intent_cases_compile_to_expected_decision(self) -> None:
        cases = json.loads((FIXTURES / "intent-cases.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(case=case["id"]):
                compiled = research_context.compile_context(case["prompt"])
                if case["clarification_required"]:
                    self.assertEqual(compiled["status"], "clarification_required")
                    self.assertTrue(compiled["clarification_question"])
                    self.assertLessEqual(compiled["clarification_question"].count("？") + compiled["clarification_question"].count("?"), 1)
                else:
                    self.assertEqual(compiled["status"], "ready")
                    self.assertEqual(compiled["research_intent"], case["expected_intent"])
                    self.assertEqual(compiled["platform"], case["expected_platform"])
                    research_context.validate_context(compiled)

    def test_explicit_selection_overrides_ambiguous_prompt(self) -> None:
        compiled = research_context.compile_context(
            "研究 Notion AI 的情况。", intent="competitor_users", platform="x", language="zh-CN"
        )
        self.assertEqual(compiled["status"], "ready")
        self.assertEqual(compiled["research_intent"], "competitor_users")
        self.assertEqual(compiled["profile_version"], "competitor_users_v1")
        self.assertEqual(compiled["profile_implementation_status"], "available")

    def test_youtube_platform_is_inferred_without_confusing_the_business_intent(self) -> None:
        compiled = research_context.compile_context("分析 AI Agent 教程在 YouTube 的内容机会。")
        self.assertEqual(compiled["status"], "ready")
        self.assertEqual(compiled["platform"], "youtube")
        self.assertEqual(compiled["research_intent"], "content_opportunity")

    def test_quoted_subject_is_frozen_without_invocation_or_platform_wrapper(self) -> None:
        compiled = research_context.compile_context(
            "使用 trend-opportunity-radar，分析“普通上班族如何用 AI 管理个人财务和日常开支”在小红书中文市场的内容机会。"
        )
        self.assertEqual(compiled["subject"]["name"], "普通上班族如何用 AI 管理个人财务和日常开支")
        self.assertEqual(compiled["subject"]["summary"], "普通上班族如何用 AI 管理个人财务和日常开支")

    def test_english_quoted_subject_is_frozen_without_request_wrapper(self) -> None:
        compiled = research_context.compile_context(
            'Use trend-opportunity-radar to analyze "AI meal planning for busy families" on Reddit for content opportunities.'
        )
        self.assertEqual(compiled["subject"]["name"], "AI meal planning for busy families")

    def test_expansion_platform_names_are_inferred_without_reasking_the_user(self) -> None:
        cases = [
            ("在 TikTok 英语市场验证 AI 备餐规划的产品需求。", "tiktok"),
            ("分析家庭旅行计划在抖音的商业机会。", "douyin"),
            ("分析品牌在 Instagram 的内容机会。", "instagram"),
            ("分析 AI 旅行规划在 Facebook 的趋势机会。", "facebook"),
        ]
        for prompt, expected in cases:
            with self.subTest(platform=expected):
                compiled = research_context.compile_context(prompt)
                self.assertEqual(compiled["status"], "ready")
                self.assertEqual(compiled["platform"], expected)

    def test_explicit_english_market_is_frozen(self) -> None:
        compiled = research_context.compile_context("分析小企业 AI Agent 在 YouTube 英语市场的商业机会。")
        self.assertEqual(compiled["market"], "英语市场")

    def test_context_hash_is_stable_and_profile_version_is_validated(self) -> None:
        first = research_context.compile_context("分析整理手机照片在小红书的趋势机会。")
        second = research_context.compile_context("分析整理手机照片在小红书的趋势机会。")
        self.assertEqual(first["source_prompt_sha256"], second["source_prompt_sha256"])
        broken = dict(first)
        broken["profile_version"] = "wrong_v1"
        with self.assertRaises(ValueError):
            research_context.validate_context(broken)

    def test_orchestrator_freezes_research_context_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = research_context.compile_context("分析 AI meeting follow-up 在 X 的趋势机会。")
            context_path = root / "research-context.json"
            context_path.write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")
            status = root / "status.json"
            status.write_text(json.dumps({
                "adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"x": True}
            }), encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(json.dumps({"queries": [
                {"id": "b1", "term": "meeting", "layer": "platform_baseline", "url": "https://x.com/search?q=meeting"},
                {"id": "c1", "term": "follow-up", "layer": "category", "url": "https://x.com/search?q=follow-up"},
                {"id": "s1", "term": "AI notes", "layer": "subject_bridge", "url": "https://x.com/search?q=ai-notes"}
            ]}), encoding="utf-8")
            state = root / "state.json"
            subprocess.run([
                sys.executable, str(SCRIPTS / "orchestrate_collection.py"), "init",
                "--state", str(state), "--snapshot", str(root / "raw.json"), "--plan", str(plan),
                "--adapter-status", str(status), "--research-context", str(context_path),
                "--platform", "x", "--mode", "standard",
            ], check=True, capture_output=True, text=True)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["research_intent"], "business_opportunity")
            self.assertEqual(saved["decision_profile_version"], "business_opportunity_v1")
            self.assertEqual(saved["source_prompt_sha256"], context["source_prompt_sha256"])

    def test_orchestrator_rejects_context_platform_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = research_context.compile_context("分析手机照片在小红书的趋势机会。")
            context_path = root / "context.json"
            context_path.write_text(json.dumps(context, ensure_ascii=False), encoding="utf-8")
            status = root / "status.json"
            status.write_text(json.dumps({"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"x": True}}), encoding="utf-8")
            plan = root / "plan.json"
            plan.write_text(json.dumps({"queries": [
                {"id": "b1", "term": "a", "layer": "platform_baseline", "url": "https://x.com/a"},
                {"id": "c1", "term": "b", "layer": "category", "url": "https://x.com/b"},
                {"id": "s1", "term": "c", "layer": "subject_bridge", "url": "https://x.com/c"}
            ]}), encoding="utf-8")
            completed = subprocess.run([
                sys.executable, str(SCRIPTS / "orchestrate_collection.py"), "init",
                "--state", str(root / "state.json"), "--snapshot", str(root / "raw.json"), "--plan", str(plan),
                "--adapter-status", str(status), "--research-context", str(context_path), "--platform", "x",
            ], capture_output=True, text=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("does not match", completed.stderr)


if __name__ == "__main__":
    unittest.main()
