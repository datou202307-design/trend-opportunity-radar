from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
REPOSITORY = "datou202307-design/trend-opportunity-radar"


class AdoptionOnboardingTest(unittest.TestCase):
    def test_bilingual_quick_start_preserves_three_real_routes_and_commands(self) -> None:
        expectations = {
            "README.md": (
                "## Start in 60 seconds",
                "Already installed",
                "Managed installer",
                "Manual fallback",
                "Use trend-opportunity-radar to analyze",
                "assets/adoption-flow.gif",
            ),
            "README.zh-CN.md": (
                "## 60 秒开始",
                "已经安装",
                "一句安装",
                "手动回退",
                "使用 trend-opportunity-radar，分析",
                "assets/adoption-flow.zh-CN.gif",
            ),
        }
        install_command = f"npx skills add {REPOSITORY} -g"
        workspace_command = "trend_radar.py workspace --root ./trend-research --output-dir ./trend-research/workspace"
        for filename, required in expectations.items():
            text = (REPO_ROOT / filename).read_text(encoding="utf-8")
            quick_start_index = text.index(required[0])
            scenario_heading = "## Five research scenarios" if filename == "README.md" else "## 五种研究场景"
            self.assertLess(quick_start_index, text.index(scenario_heading))
            for value in required:
                self.assertIn(value, text)
            self.assertIn(install_command, text)
            self.assertIn(workspace_command, text)
            self.assertIn("does not" if filename == "README.md" else "不会", text[quick_start_index : text.index(scenario_heading)])

    def test_workflow_visuals_are_local_accessible_and_complete(self) -> None:
        expected_labels = {
            "adoption-flow.svg": ("Define", "Collect", "Review", "Report", "Continue"),
            "adoption-flow.zh-CN.svg": ("输入问题", "平台采集", "证据审查", "本地报告", "再次行动"),
        }
        for filename, labels in expected_labels.items():
            svg = (REPO_ROOT / "assets" / filename).read_text(encoding="utf-8")
            self.assertIn('viewBox="0 0 1280 260"', svg)
            self.assertIn("<title", svg)
            self.assertIn("<desc", svg)
            self.assertNotIn("foreignObject", svg)
            self.assertNotRegex(svg, re.compile(r'href="https?://', re.IGNORECASE))
            for label in labels:
                self.assertIn(label, svg)

        for filename in ("adoption-flow.gif", "adoption-flow.zh-CN.gif"):
            data = (REPO_ROOT / "assets" / filename).read_bytes()
            self.assertEqual(data[:6], b"GIF89a")
            self.assertGreaterEqual(data.count(b"\x21\xF9\x04"), 5)
            self.assertLess(len(data), 500_000)

    def test_external_acceptance_requires_three_uncoached_records(self) -> None:
        text = (REPO_ROOT / "docs" / "adoption-onboarding-test.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^\| T[123] \|", text, flags=re.MULTILINE)), 3)
        for field in (
            "Installed successfully",
            "Agent invoked the Skill",
            "Auto-invoked from plain request",
            "First report completed",
            "Reopened via workspace",
            "First blocking step",
            "Would use again",
        ):
            self.assertIn(field, text)
        self.assertIn("without developer coaching", text)
        self.assertIn("do not commit names", text)


if __name__ == "__main__":
    unittest.main()
