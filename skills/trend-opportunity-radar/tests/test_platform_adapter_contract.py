from __future__ import annotations

import copy
import tempfile
import unittest
import json
import subprocess
from pathlib import Path

import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import platform_adapter_contract as contract
import parse_opencli_tiktok_search as tiktok_parser
import select_collection_adapter as selector
import _common as common


class PlatformAdapterContractTest(unittest.TestCase):
    def test_registry_validates_and_aliases_normalize(self) -> None:
        registry = contract.load_registry()
        self.assertEqual(registry["contract_version"], "platform-adapter-contract-v0.2")
        self.assertEqual(contract.normalize_platform("小红书", registry), "xiaohongshu")
        self.assertEqual(contract.normalize_platform("Twitter", registry), "x")
        self.assertEqual(contract.normalize_platform("油管", registry), "youtube")
        self.assertEqual(contract.normalize_platform("Tik Tok", registry), "tiktok")
        self.assertEqual(common.normalize_platform("TikTok"), "tiktok")
        self.assertEqual(common.normalize_platform("抖音"), "douyin")
        self.assertEqual(contract.platform_scope_status("youtube", "topic_research", registry), "validated")
        self.assertEqual(contract.platform_scope_status("youtube", "account_research", registry), "unsupported")

    def test_invalid_capability_shape_is_rejected(self) -> None:
        registry = contract.load_registry()
        broken = copy.deepcopy(registry)
        del broken["adapters"]["opencli"]["platforms"]["x"]["safety_stops"]
        with self.assertRaises(ValueError):
            contract.validate_registry(broken)

    def test_comment_capability_requires_a_bounded_limit(self) -> None:
        registry = contract.load_registry()
        broken = copy.deepcopy(registry)
        broken["adapters"]["opencli"]["platforms"]["xiaohongshu"]["comment_sample_limit"] = 50
        with self.assertRaises(ValueError):
            contract.validate_registry(broken)

    def test_platform_readiness_is_not_inferred_from_other_platform(self) -> None:
        status = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"x": True, "xiaohongshu": False}}
        self.assertTrue(contract.status_supports(status, "x"))
        self.assertFalse(contract.status_supports(status, "xiaohongshu"))
        route = selector.select_adapter("xiaohongshu", [status])
        self.assertFalse(route["ready"])
        self.assertEqual(route["rejected"][0]["reason"], "platform_not_validated")

    def test_unsupported_research_scope_cannot_select_a_live_adapter(self) -> None:
        status = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"youtube": True}}
        route = selector.select_adapter("youtube", [status], research_scope="account_research")
        self.assertFalse(route["ready"])
        self.assertEqual(route["release_status"], "unsupported")
        self.assertEqual(route["status"], "research_scope_not_live_supported")

    def test_pilot_scope_requires_explicit_opt_in(self) -> None:
        status = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"tiktok": True}}
        default_route = selector.select_adapter("tiktok", [status])
        self.assertFalse(default_route["ready"])
        self.assertEqual(default_route["release_status"], "pilot")
        pilot_route = selector.select_adapter("tiktok", [status], allow_pilot=True)
        self.assertTrue(pilot_route["ready"])
        self.assertEqual(pilot_route["adapter"], "opencli")

    def test_tiktok_selects_opencli_search_and_logged_in_dokobot_detail(self) -> None:
        opencli = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"tiktok": True}}
        dokobot = {"adapter": "dokobot", "ready": True, "status": "ready"}
        route = selector.select_adapter("tiktok", [dokobot, opencli], allow_pilot=True)
        self.assertEqual(route["adapter"], "opencli")
        self.assertEqual(route["detail_adapter"], "dokobot")
        self.assertTrue(route["detail_ready"])
        self.assertEqual(contract.adapter_capability("opencli", "tiktok")["search_builder"], "opencli_tiktok_search_v1")
        self.assertIsNone(contract.adapter_capability("opencli", "tiktok")["detail_builder"])
        self.assertEqual(contract.adapter_capability("dokobot", "tiktok")["detail_builder"], "dokobot_tiktok_detail_v1")
        self.assertEqual(contract.adapter_capability("dokobot", "tiktok")["comment_sample_limit"], 5)

    def test_tiktok_search_parser_keeps_only_stable_read_only_cards(self) -> None:
        records = [{
            "author": "synthetic.creator", "comments": 4,
            "desc": "A synthetic AI workflow example", "likes": 1200,
            "plays": 24000, "rank": 1, "shares": 33,
            "url": "https://www.tiktok.com/@synthetic.creator/video/7000000000000000001",
        }]
        parsed = tiktok_parser.parse_search_records(records, {"id": "q1", "term": "AI workflow", "layer": "category"}, "synthetic.json")
        self.assertEqual(parsed["observed_result_keys"], ["7000000000000000001"])
        signal = parsed["signals"][0]
        self.assertEqual(signal["metrics"]["views"], 24000)
        self.assertEqual(signal["metrics"]["shares"], 33)
        self.assertEqual(signal["published_at"], "")
        self.assertFalse(signal["detail_captured"])

    def test_existing_command_contract_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "raw.json"
            query = {"term": "meeting follow-up", "url": "https://x.com/search?q=meeting&f=live"}
            x_state = {"adapter": "opencli", "platform": "x", "mode": "standard"}
            x_search = contract.build_search_command(x_state, query, output, 1)
            self.assertEqual(x_search[:3], ["opencli", "twitter", "search"])
            self.assertIn("live", x_search)
            self.assertEqual(contract.build_detail_command(x_state, "https://x.com/a/status/1", output)[:3], ["opencli", "twitter", "thread"])

            xhs_state = {"adapter": "opencli", "platform": "xiaohongshu", "mode": "standard"}
            self.assertEqual(contract.build_search_command(xhs_state, query, output, 1)[:3], ["opencli", "xiaohongshu", "search"])
            self.assertEqual(contract.build_detail_command(xhs_state, "https://www.xiaohongshu.com/explore/1", output)[:3], ["opencli", "xiaohongshu", "note"])

            youtube_state = {"adapter": "opencli", "platform": "youtube", "mode": "standard"}
            youtube_query = {**query, "url": "https://www.youtube.com/results?search_query=meeting&sort=views&upload=month&type=video"}
            youtube_search = contract.build_search_command(youtube_state, youtube_query, output, 1)
            self.assertEqual(youtube_search[:3], ["opencli", "youtube", "search"])
            self.assertIn("--sort", youtube_search)
            self.assertIn("views", youtube_search)
            self.assertIn("--upload", youtube_search)
            self.assertIn("month", youtube_search)
            self.assertEqual(contract.build_detail_command(youtube_state, "https://www.youtube.com/watch?v=abc123", output)[:3], ["opencli", "youtube", "video"])

            tiktok_state = {"adapter": "opencli", "platform": "tiktok", "mode": "standard"}
            tiktok_search = contract.build_search_command(tiktok_state, query, output, 1)
            self.assertEqual(tiktok_search[:3], ["opencli", "tiktok", "search"])
            with self.assertRaises(ValueError):
                contract.build_detail_command(tiktok_state, "https://www.tiktok.com/@synthetic/video/1", output)

            tiktok_browser_state = {"adapter": "dokobot", "platform": "tiktok", "mode": "standard"}
            tiktok_detail = contract.build_detail_command(tiktok_browser_state, "https://www.tiktok.com/@synthetic/video/1", output)
            self.assertEqual(tiktok_detail[:2], ["dokobot", "read"])
            self.assertIn("--screens", tiktok_detail)

            doko_state = {"adapter": "dokobot", "platform": "x", "mode": "standard"}
            doko_search = contract.build_search_command(doko_state, {**query, "session_id": "abc"}, output, 1)
            self.assertEqual(doko_search[:2], ["dokobot", "read"])
            self.assertIn("--session-id", doko_search)

    def test_structured_import_is_cross_platform_but_not_live_capture(self) -> None:
        capability = contract.adapter_capability("structured_import", "youtube")
        self.assertIsNotNone(capability)
        self.assertEqual(capability["source_mode"], "customer_export")
        self.assertIsNone(capability["search_builder"])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                contract.build_search_command(
                    {"adapter": "structured_import", "platform": "youtube", "mode": "standard"},
                    {"term": "topic", "url": "https://example.com"}, Path(directory) / "raw.json", 1,
                )

    def test_structured_import_output_records_adapter_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            output = root / "normalized.json"
            source.write_text(json.dumps({"items": [{
                "id": "1", "platform": "youtube", "title": "A supplied signal",
                "url": "https://example.com/1", "published_at": "2026-08-13T00:00:00Z"
            }]}), encoding="utf-8")
            subprocess.run([
                sys.executable, str(SCRIPTS / "normalize_signals.py"), "--input", str(source),
                "--output", str(output), "--platform", "youtube", "--source-mode", "customer_export",
            ], check=True, capture_output=True, text=True)
            normalized = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(normalized["platform_adapter"]["adapter"], "structured_import")
            self.assertEqual(normalized["platform_adapter"]["contract_version"], "platform-adapter-contract-v0.2")
            self.assertFalse(normalized["platform_adapter"]["live_collection"])


if __name__ == "__main__":
    unittest.main()
