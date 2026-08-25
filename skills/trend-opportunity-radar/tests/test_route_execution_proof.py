from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import prove_collection_route as proof
import select_collection_adapter as selector


class CollectionRouteExecutionProofTest(unittest.TestCase):
    def write(self, path: Path, payload: dict) -> Path:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def facebook_route(self) -> dict:
        status = {
            "adapter": "facebook_posts_browser_capture",
            "ready": True,
            "status": "ready",
            "capabilities": {"facebook": True},
        }
        return selector.select_adapter("facebook", [status], allow_pilot=True)["collection_route"]

    def facebook_signals(self) -> dict:
        return {
            "platform": "facebook",
            "platform_adapter": {"adapter": "facebook_posts_browser_capture", "live_collection": True},
            "signals": [{
                "signal_id": "facebook:synthetic-101",
                "content_id": "synthetic-101",
                "detail_captured": True,
                "source_type": "direct_post",
                "representative_comments": [],
            }],
        }

    def test_same_adapter_live_snapshot_proves_search_and_detail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.write(root / "run-manifest.json", {
                "request_sha256": "request-1",
                "collection_route": self.facebook_route(),
            })
            signals = self.write(root / "scored-signals.json", self.facebook_signals())
            result = proof.build_proof(manifest, signals)
            self.assertEqual(result["status"], "passed")
            self.assertEqual(set(result["roles"]), {"search", "detail"})
            self.assertEqual(result["roles"]["search"]["runner"], "run_facebook_opencli_capture.py")

    def test_nested_detail_comments_require_and_prove_comment_role(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            opencli = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"youtube": True}}
            route = selector.select_adapter("youtube", [opencli], allow_pilot=True)["collection_route"]
            manifest = self.write(root / "run-manifest.json", {"request_sha256": "request-comments", "collection_route": route})
            signals = self.write(root / "scored-signals.json", {
                "platform": "youtube",
                "platform_adapter": {"adapter": "opencli", "live_collection": True},
                "signals": [{
                    "signal_id": "youtube:synthetic-comments",
                    "detail_captured": True,
                    "source_type": "direct_video",
                    "platform_facts": {"representative_comments": [{"text": "Please export action items."}]},
                }],
            })
            result = proof.build_proof(manifest, signals)
            self.assertEqual(set(result["roles"]), {"search", "detail", "comments"})
            self.assertEqual(result["roles"]["comments"]["evidence_count"], 1)

    def test_adapter_mismatch_cannot_be_proved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.write(root / "run-manifest.json", {
                "request_sha256": "request-1",
                "collection_route": self.facebook_route(),
            })
            payload = self.facebook_signals()
            payload["platform_adapter"]["adapter"] = "public_web"
            signals = self.write(root / "scored-signals.json", payload)
            with self.assertRaisesRegex(ValueError, "frozen search route"):
                proof.build_proof(manifest, signals)

    def test_split_adapter_route_requires_the_real_detail_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            opencli = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"tiktok": True}}
            dokobot = {"adapter": "dokobot", "ready": True, "status": "ready"}
            route = selector.select_adapter("tiktok", [opencli, dokobot], allow_pilot=True)["collection_route"]
            manifest = self.write(root / "run-manifest.json", {"request_sha256": "request-2", "collection_route": route})
            signals = self.write(root / "scored-signals.json", {
                "platform": "tiktok",
                "platform_adapter": {"adapter": "opencli", "live_collection": True},
                "signals": [{"signal_id": "tiktok:synthetic-201", "detail_captured": True, "source_type": "direct_video"}],
            })
            with self.assertRaisesRegex(ValueError, "detail receipt artifact"):
                proof.build_proof(manifest, signals)
            detail = self.write(root / "detail-receipt.json", {"platform": "tiktok", "adapter": "dokobot", "status": "captured"})
            result = proof.build_proof(manifest, signals, {"detail": detail})
            self.assertEqual(result["roles"]["detail"]["adapter"], "dokobot")

    def test_split_receipt_change_invalidates_an_existing_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            opencli = {"adapter": "opencli", "ready": True, "status": "ready", "capabilities": {"tiktok": True}}
            dokobot = {"adapter": "dokobot", "ready": True, "status": "ready"}
            route = selector.select_adapter("tiktok", [opencli, dokobot], allow_pilot=True)["collection_route"]
            manifest = self.write(root / "run-manifest.json", {"request_sha256": "request-4", "collection_route": route})
            signals = self.write(root / "scored-signals.json", {
                "platform": "tiktok",
                "platform_adapter": {"adapter": "opencli", "live_collection": True},
                "signals": [{"signal_id": "tiktok:synthetic-301", "detail_captured": True, "source_type": "direct_video"}],
            })
            detail = self.write(root / "detail-receipt.json", {"platform": "tiktok", "adapter": "dokobot", "status": "captured"})
            proof_path = self.write(root / "route-execution-proof.json", proof.build_proof(manifest, signals, {"detail": detail}))
            self.assertEqual(proof.validate_proof(manifest, signals, proof_path)["status"], "passed")
            self.write(detail, {"platform": "tiktok", "adapter": "dokobot", "status": "changed"})
            with self.assertRaisesRegex(ValueError, "has changed"):
                proof.validate_proof(manifest, signals, proof_path)

    def test_report_gate_rejects_missing_and_stale_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = self.write(root / "research-context.json", {"status": "ready"})
            manifest = self.write(root / "run-manifest.json", {
                "request_sha256": "request-3",
                "collection_route": self.facebook_route(),
            })
            signals = self.write(root / "scored-signals.json", self.facebook_signals())
            with self.assertRaisesRegex(ValueError, "execution proof is required"):
                proof.enforce_report_gate(context, signals)
            passed = proof.build_proof(manifest, signals)
            self.write(root / "route-execution-proof.json", passed)
            self.assertEqual(proof.enforce_report_gate(context, signals)["status"], "passed")
            payload = self.facebook_signals()
            payload["signals"].append({"signal_id": "facebook:synthetic-102", "detail_captured": True, "source_type": "direct_post"})
            self.write(signals, payload)
            with self.assertRaisesRegex(ValueError, "missing, stale"):
                proof.enforce_report_gate(context, signals)

    def test_historical_replay_without_live_manifest_remains_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            context = self.write(root / "research-context.json", {"status": "ready"})
            signals = self.write(root / "scored-signals.json", self.facebook_signals())
            self.assertIsNone(proof.enforce_report_gate(context, signals))


if __name__ == "__main__":
    unittest.main()
