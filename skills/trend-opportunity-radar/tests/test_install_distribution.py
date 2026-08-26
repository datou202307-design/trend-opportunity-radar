from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_NAME = "trend-opportunity-radar"
REPOSITORY = "datou202307-design/trend-opportunity-radar"


class InstallDistributionTest(unittest.TestCase):
    def test_claude_marketplace_points_to_the_canonical_skill(self) -> None:
        marketplace = json.loads(
            (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
        )
        plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(marketplace["name"], SKILL_NAME)
        self.assertEqual(len(marketplace["plugins"]), 1)
        self.assertEqual(marketplace["plugins"][0]["name"], SKILL_NAME)
        self.assertEqual(marketplace["plugins"][0]["source"], "./")
        self.assertEqual(plugin["name"], SKILL_NAME)
        self.assertEqual(plugin["version"], marketplace["plugins"][0]["version"])
        self.assertTrue((REPO_ROOT / "skills" / SKILL_NAME / "SKILL.md").is_file())
        self.assertTrue((REPO_ROOT / "skills" / SKILL_NAME / "scripts" / "trend_radar.py").is_file())

    def test_bilingual_readmes_lead_with_managed_installers(self) -> None:
        cross_agent_command = f"npx skills add {REPOSITORY} -g"
        marketplace_command = f"/plugin marketplace add {REPOSITORY}"
        install_command = f"/plugin install {SKILL_NAME}@{SKILL_NAME}"
        for filename in ("README.md", "README.zh-CN.md"):
            text = (REPO_ROOT / filename).read_text(encoding="utf-8")
            install_index = text.index("## Install") if filename == "README.md" else text.index("## 安装")
            release_index = text.index("Releases page") if filename == "README.md" else text.index("Releases 页面")
            self.assertIn(cross_agent_command, text)
            self.assertIn(marketplace_command, text)
            self.assertIn(install_command, text)
            self.assertLess(install_index, release_index)
            self.assertLess(text.index(cross_agent_command), release_index)
            self.assertIn("ZIP", text[install_index : release_index + 300])


if __name__ == "__main__":
    unittest.main()
