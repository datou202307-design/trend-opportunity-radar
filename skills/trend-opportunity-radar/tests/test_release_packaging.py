from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "tools" / "package_skill_release.py"
SPEC = importlib.util.spec_from_file_location("package_skill_release", MODULE_PATH)
assert SPEC and SPEC.loader
package_skill_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package_skill_release)


class ReleasePackagingTest(unittest.TestCase):
    def test_package_contains_installable_skill_and_excludes_tests_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = package_skill_release.package_release(REPO_ROOT, Path(directory), "v9.9.9-candidate")
            archive_path = Path(directory) / result["archive"]
            with zipfile.ZipFile(archive_path) as archive:
                names = archive.namelist()
                self.assertIn("trend-opportunity-radar/SKILL.md", names)
                self.assertIn("trend-opportunity-radar/agents/openai.yaml", names)
                self.assertIn("trend-opportunity-radar/assets/demo/signals.json", names)
                self.assertIn("trend-opportunity-radar/LICENSE", names)
                self.assertIn("trend-opportunity-radar/INSTALL.txt", names)
                self.assertFalse(any("/tests/" in name for name in names))
                self.assertFalse(any("__pycache__" in name or name.endswith(".pyc") for name in names))
                self.assertFalse(any(".agents" in name for name in names))
            manifest_path = Path(directory) / "trend-opportunity-radar-v9.9.9-candidate.manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["archive_sha256"], package_skill_release.sha256_bytes(archive_path.read_bytes()))

    def test_package_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            one = package_skill_release.package_release(REPO_ROOT, Path(first), "v9.9.9-candidate")
            two = package_skill_release.package_release(REPO_ROOT, Path(second), "v9.9.9-candidate")
            self.assertEqual(one["archive_sha256"], two["archive_sha256"])

    def test_invalid_version_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(package_skill_release.PackageError):
                package_skill_release.package_release(REPO_ROOT, Path(directory), "latest")


if __name__ == "__main__":
    unittest.main()

