from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "tools" / "build_case_gallery.py"
SPEC = importlib.util.spec_from_file_location("build_case_gallery", MODULE_PATH)
assert SPEC and SPEC.loader
build_case_gallery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_case_gallery)


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.scripts: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(str(values["href"]))
        if tag == "script":
            self.scripts.append(values)


class CaseGalleryTest(unittest.TestCase):
    def test_builds_five_bilingual_synthetic_cases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = build_case_gallery.build(output)
            pages = sorted(output.rglob("*.html"))
            self.assertEqual(result["case_count"], 5)
            self.assertEqual(result["page_count"], 12)
            self.assertEqual(len(pages), 12)
            self.assertTrue((output / ".nojekyll").exists())
            for page in pages:
                text = page.read_text(encoding="utf-8")
                self.assertIn('data-synthetic="true"', text)
                self.assertTrue("Synthetic example" in text or "合成示例" in text)
                self.assertNotIn("google-analytics", text.casefold())
                self.assertNotIn("gtag(", text.casefold())
                parser = LinkParser()
                parser.feed(text)
                self.assertEqual(parser.scripts, [])

    def test_case_pages_have_utm_links_and_evidence_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_case_gallery.build(output)
            for page in list((output / "cases").glob("*.html")) + list((output / "zh-CN" / "cases").glob("*.html")):
                text = page.read_text(encoding="utf-8")
                self.assertIn("utm_source=github_pages", text)
                self.assertIn("utm_medium=case_gallery", text)
                self.assertIn("utm_campaign=v0.13_case_gallery", text)
                self.assertTrue("What could overturn the decision" in text or "什么情况会推翻判断" in text)
                self.assertTrue("Smallest next test" in text or "最小下一步测试" in text)

    def test_internal_html_and_stylesheet_links_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_case_gallery.build(output)
            for page in output.rglob("*.html"):
                parser = LinkParser()
                parser.feed(page.read_text(encoding="utf-8"))
                for link in parser.links:
                    if link.startswith(("http://", "https://", "#")):
                        continue
                    target = (page.parent / link.split("#", 1)[0]).resolve()
                    self.assertTrue(target.exists(), f"Broken link in {page}: {link}")
                css_marker = 'rel="stylesheet" href="'
                text = page.read_text(encoding="utf-8")
                css_link = text.split(css_marker, 1)[1].split('"', 1)[0]
                self.assertTrue((page.parent / css_link).resolve().exists())

    def test_each_language_hub_routes_to_its_own_case_pages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_case_gallery.build(output)
            for hub in (output / "index.html", output / "zh-CN" / "index.html"):
                parser = LinkParser()
                parser.feed(hub.read_text(encoding="utf-8"))
                case_links = [link for link in parser.links if link.startswith("cases/")]
                self.assertEqual(len(case_links), 5)
                for link in case_links:
                    self.assertTrue((hub.parent / link).resolve().exists())

    def test_gallery_schema_rejects_missing_decision_mode(self) -> None:
        source = json.loads(build_case_gallery.DATA_PATH.read_text(encoding="utf-8"))
        source["cases"] = source["cases"][:-1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            with self.assertRaises(ValueError):
                build_case_gallery.load_gallery(path)


if __name__ == "__main__":
    unittest.main()
