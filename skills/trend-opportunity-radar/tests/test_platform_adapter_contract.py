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
import select_collection_adapter as selector


class PlatformAdapterContractTest(unittest.TestCase):
    def test_registry_validates_and_aliases_normalize(self) -> None:
        registry = contract.load_registry()
        self.assertEqual(registry["contract_version"], "platform-adapter-contract-v0.1")
        self.assertEqual(contract.normalize_platform("小红书", registry), "xiaohongshu")
        self.assertEqual(contract.normalize_platform("Twitter", registry), "x")

    def test_invalid_capability_shape_is_rejected(self) -> None:
        registry = contract.load_registry()
        broken = copy.deepcopy(registry)
        del broken["adapters"]["opencli"]["platforms"]["x"]["safety_stops"]
        with self.assertRaises(ValueError):
            contract.validate_registry(broken)

    def test_platform_readiness_is_not_inferred_from_other_platform(self) -> None:
        status = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"x": True, "xiaohongshu": False}}
        self.assertTrue(contract.status_supports(status, "x"))
        self.assertFalse(contract.status_supports(status, "xiaohongshu"))
        route = selector.select_adapter("xiaohongshu", [status])
        self.assertFalse(route["ready"])
        self.assertEqual(route["rejected"][0]["reason"], "platform_not_validated")

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
            self.assertEqual(normalized["platform_adapter"]["contract_version"], "platform-adapter-contract-v0.1")
            self.assertFalse(normalized["platform_adapter"]["live_collection"])


if __name__ == "__main__":
    unittest.main()
