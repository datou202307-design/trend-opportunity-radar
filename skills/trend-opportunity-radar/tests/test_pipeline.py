from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_collection_adapter as adapter_check
import _common as common
import research_context
import generate_opportunities as opportunity_generator
import orchestrate_dokobot_collection as orchestrator
import parse_opencli_xhs_search as opencli_parser
import parse_opencli_x_search as opencli_x_parser
import parse_opencli_youtube_search as opencli_youtube_parser
import run_opencli_detail_backfill as opencli_detail_runner
import run_collection_capture as collection_capture_runner
import parse_dokobot_x_search as x_parser
import apply_semantic_review as semantic_reviewer
import apply_comment_review as comment_reviewer
import prepare_comment_review as comment_queue
import run_dokobot_capture as capture_runner
import run_dokobot_detail_backfill as detail_runner
import parse_dokobot_tiktok_detail as tiktok_detail_parser
import select_collection_adapter as adapter_selector
import validate_report_artifacts as report_validator
from generate_profile_report import collection_summary, finding_comment_evidence, visible_status


def run_script(name: str, *args: str) -> None:
    subprocess.run([sys.executable, str(SCRIPTS / name), *args], check=True, capture_output=True, text=True)


def run_script_json(name: str, *args: str) -> dict:
    completed = subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args], check=True, capture_output=True, text=True
    )
    return json.loads(completed.stdout)


class PipelineTest(unittest.TestCase):
    def test_comment_review_is_complete_auditable_and_does_not_change_trend_volume(self) -> None:
        snapshot = {
            "platform": "x",
            "raw_sample_count": 20,
            "signals": [{
                "signal_id": "signal-1", "topic_key": "shared-expense", "canonical_url": "https://x.com/a/status/1",
                "platform_facts": {"representative_comments": [
                    {"text": "We need a simpler way to split recurring bills", "likes": 3},
                    {"text": "A spreadsheet already works for us", "likes": 1},
                ]},
            }],
        }
        queue = comment_queue.build_queue(snapshot)
        self.assertEqual(queue["comment_count"], 2)
        review = {
            "schema_version": comment_reviewer.SCHEMA_VERSION,
            "queue_sha256": queue["queue_sha256"],
            "reviews": [
                {"comment_key": queue["comments"][0]["comment_key"], "category": "need", "semantic_relevance": "direct", "evidence_role": "support", "insight": "Users ask for simpler recurring-bill splitting.", "reason": "The commenter states the need directly."},
                {"comment_key": queue["comments"][1]["comment_key"], "category": "workaround", "semantic_relevance": "direct", "evidence_role": "counter", "insight": "Some users consider a spreadsheet sufficient.", "reason": "The commenter names an existing workaround."},
            ],
        }
        enriched = comment_reviewer.apply(snapshot, queue, review)
        self.assertEqual(enriched["raw_sample_count"], 20)
        self.assertEqual(enriched["comment_evidence"]["reviewed_count"], 2)
        self.assertEqual(enriched["comment_evidence"]["counter_count"], 1)
        topic = finding_comment_evidence(enriched, "shared-expense")
        self.assertEqual(topic["relevant_count"], 2)
        self.assertEqual(len(topic["insights"]), 2)
        basis = collection_summary(enriched)
        self.assertEqual(basis["reviewed_comment_count"], 2)

    def test_collection_summary_recomputes_detail_count_from_canonical_signals(self) -> None:
        snapshot = {
            "collection": {"counts": {"detail_open_count": 0}},
            "signals": [
                {"signal_id": "s1", "detail_captured": True, "semantic_relevance": "direct", "evidence_role": "support"},
                {"signal_id": "s2", "detail_captured": False, "semantic_relevance": "adjacent", "evidence_role": "counter"},
            ],
        }
        self.assertEqual(collection_summary(snapshot)["detail_open_count"], 1)

    def test_comment_review_rejects_missing_labels(self) -> None:
        snapshot = {"platform": "x", "signals": [{"signal_id": "s1", "platform_facts": {"representative_comments": [{"text": "Useful"}]}}]}
        queue = comment_queue.build_queue(snapshot)
        with self.assertRaises(SystemExit):
            comment_reviewer.apply(snapshot, queue, {
                "schema_version": comment_reviewer.SCHEMA_VERSION,
                "queue_sha256": queue["queue_sha256"],
                "reviews": [],
            })

    def test_collection_capture_never_overwrites_existing_raw_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            requested = Path(temp_dir) / "category-1-001.json"
            self.assertEqual(collection_capture_runner.immutable_raw_path(requested), requested)
            requested.write_text("first", encoding="utf-8")
            attempt_two = collection_capture_runner.immutable_raw_path(requested)
            self.assertEqual(attempt_two.name, "category-1-001-attempt-2.json")
            attempt_two.write_text("second", encoding="utf-8")
            self.assertEqual(
                collection_capture_runner.immutable_raw_path(requested).name,
                "category-1-001-attempt-3.json",
            )

    def test_opencli_capture_uses_same_common_location_resolution_as_preflight(self) -> None:
        from unittest.mock import patch

        with patch.object(collection_capture_runner.shutil, "which", return_value=None), patch.object(
            collection_capture_runner, "resolve_opencli", return_value=("C:/npm/opencli.cmd", "path_or_common_location", [])
        ), patch.object(collection_capture_runner, "executable_command", return_value=["node", "opencli.js", "xiaohongshu", "search"]):
            command = collection_capture_runner.resolve_opencli_command(["opencli", "xiaohongshu", "search"])
        self.assertEqual(command, ["node", "opencli.js", "xiaohongshu", "search"])

    def test_profile_statuses_are_reader_facing(self) -> None:
        self.assertEqual(visible_status("candidate", "zh-CN"), "待验证")
        self.assertEqual(visible_status("candidate", "en"), "Needs validation")
        self.assertNotIn("candidate", visible_status("candidate", "zh-CN"))

    def test_orchestrator_cli_output_is_legacy_console_safe(self) -> None:
        payload = {"action": "start_query", "query": "meeting tasks 📢"}
        rendered = json.dumps(payload, ensure_ascii=True, indent=2)
        rendered.encode("gbk")
        self.assertEqual(json.loads(rendered), payload)

    def test_dokobot_x_parser_is_mechanical_and_semantic_review_is_explicit(self) -> None:
        text = """# X
> https://x.com/search?q=interview
**Research Workflow Lab [1]** @researchflowlab [1]·Aug 10 [2]
Interview synthesis groups evidence into themes and decisions.
3 Replies 2 reposts 16 Likes 670 views [3]
---
**Synthetic Fan Account [4]** @syntheticfan [4]·Aug 9 [5]
An entertainment interview translation thread.
[1] https://x.com/researchflowlab
[2] https://x.com/researchflowlab/status/1111111111111111111
[3] https://x.com/researchflowlab/status/1111111111111111111/analytics
[4] https://x.com/syntheticfan
[5] https://x.com/syntheticfan/status/2222222222222222222
"""
        extraction = x_parser.parse_text(text, {"term": "interview synthesis", "layer": "category"})
        self.assertEqual(len(extraction["signals"]), 2)
        self.assertTrue(all(item["semantic_relevance"] == "unreviewed" for item in extraction["signals"]))
        reviewed = semantic_reviewer.apply_review(extraction, {"reviews": [
            {"content_id": "1111111111111111111", "semantic_relevance": "direct", "evidence_role": "support", "topic_key": "evidence-to-decisions", "reason": "Describes interview synthesis as an evidence-to-decision task."},
            {"content_id": "2222222222222222222", "semantic_relevance": "weak", "evidence_role": "neutral", "reason": "Entertainment interview is an off-task keyword collision."},
        ]})
        self.assertEqual(reviewed["signals"][0]["semantic_relevance"], "direct")
        self.assertEqual(reviewed["signals"][1]["semantic_relevance"], "weak")
        self.assertEqual(reviewed["semantic_review_audit"]["unreviewed_count"], 0)

    def test_semantic_review_cli_appends_query_specific_audit_ledger(self) -> None:
        ledger = self.root / "semantic-review-ledger.json"
        for query_id, content_id in (("baseline-1", "101"), ("category-1", "102")):
            extraction = self.write(f"{query_id}-extraction.json", {
                "query_id": query_id, "observed_result_keys": [content_id], "detail_open_keys": [],
                "signals": [{"content_id": content_id, "semantic_relevance": "unreviewed", "evidence_role": "neutral", "topic_key": "unreviewed"}],
            })
            review = self.write(f"{query_id}-semantic-review.json", {"reviews": [{
                "content_id": content_id, "semantic_relevance": "direct", "evidence_role": "support",
                "topic_key": "customer-risk-workflow", "reason": "Directly describes the reviewed task.",
            }]})
            run_script("apply_semantic_review.py", "--extraction", str(extraction), "--review", str(review),
                       "--output", str(self.root / f"{query_id}-reviewed-extraction.json"), "--audit-ledger", str(ledger))
        entries = json.loads(ledger.read_text(encoding="utf-8"))["entries"]
        self.assertEqual([item["query_id"] for item in entries], ["baseline-1", "category-1"])
        self.assertEqual(len({item["review"] for item in entries}), 2)

    def test_standard_report_excludes_unreviewed_topic_even_with_high_score(self) -> None:
        topic = {"topic_key": "unreviewed", "title": "Raw post title", "cluster_audit": {"status": "passed"},
                 "sample_count": 20, "unique_author_count": 20, "direct_source_count": 5,
                 "subject_bridge_direct_count": 2, "relevance_review_coverage": 1.0,
                 "evidence_confidence": 90, "observed_heat": 90, "data_coverage": 90,
                 "counter_signal_count": 2, "missing_fields": []}
        self.assertFalse(opportunity_generator.topic_is_eligible(topic, "standard"))

    def test_recovery_plan_accepts_only_one_query_per_round(self) -> None:
        state = {"mode": "standard", "queries": self.make_standard_query_plan()["queries"],
                 "snapshot": str(self.root / "missing-snapshot.json")}
        plan = {"queries": [
            {"id": "r1", "term": "customer pain", "layer": "category", "url": "https://x.example/r1"},
            {"id": "r2", "term": "agent handoff", "layer": "subject_bridge", "url": "https://x.example/r2"},
        ]}
        with self.assertRaises(SystemExit):
            orchestrator.validate_recovery_plan(plan, state)

    def test_query_ledger_preserves_relevance_yield_fields(self) -> None:
        signal = self.make_signal(1600)
        signal["semantic_relevance"] = "weak"
        query = self.write("yield-query.json", {
            "query_term": "broad phrase", "query_layer": "category", "observed_result_count": 20,
            "signals": [signal], "detail_open_count": 0, "relevant_signal_count": 0,
            "retention_rate": 0.05, "relevant_yield_rate": 0.0, "low_yield": True,
        })
        snapshot = self.root / "yield-raw.json"
        run_script("append_collection_result.py", "--snapshot", str(snapshot), "--query-result", str(query),
                   "--platform", "x", "--source-mode", "controlled_capture", "--mode", "standard")
        run = json.loads(snapshot.read_text(encoding="utf-8"))["collection"]["query_runs"][0]
        self.assertEqual(run["relevant_signal_count"], 0)
        self.assertEqual(run["relevant_yield_rate"], 0.0)
        self.assertTrue(run["low_yield"])

    def test_report_validator_rejects_run_local_repair_scripts(self) -> None:
        (self.root / "sanitize_signals.py").write_text("# one-off repair", encoding="utf-8")
        with self.assertRaises(SystemExit):
            report_validator.validate_collection_artifacts({"collection": {"query_runs": []}}, self.root)

    def test_detail_backfill_recording_is_idempotent(self) -> None:
        raw = self.root / "detail-idempotent.json"
        stdout = self.root / "detail-idempotent.stdout.txt"
        stderr = self.root / "detail-idempotent.stderr.txt"
        metadata = self.root / "detail-idempotent.capture.json"
        for path in (raw, stdout, stderr, metadata):
            path.write_text("{}", encoding="utf-8")
        signal = self.make_signal(1700)
        signal.update({"query_layer": "category", "semantic_relevance": "direct", "detail_captured": False})
        snapshot = self.write("idempotent-raw.json", {
            "platform": "x", "source_mode": "controlled_capture",
            "collection": {"mode": "standard", "counts": {"detail_open_count": 0}, "detail_backfills": []},
            "signals": [signal],
        })
        state = {"mode": "standard", "snapshot": str(snapshot), "detail_backfill_attempts": []}
        original_plan = orchestrator.detail_backfill_plan
        orchestrator.detail_backfill_plan = lambda _state: {"targets": [{"signal_key": orchestrator.signal_key(signal), "layer": "category"}], "required_detail_count": 1}
        payload = {"schema_version": "dokobot-detail-backfill-v0.2", "results": [{
            "signal_key": orchestrator.signal_key(signal), "success": False, "raw_artifact": str(raw), "stop_reason": "cli_error",
            "execution": {"stdout_artifact": str(stdout), "stderr_artifact": str(stderr), "metadata_artifact": str(metadata)},
        }]}
        try:
            orchestrator.record_detail_backfill(state, payload)
            state["detail_backfill_attempts"] = []
            orchestrator.record_detail_backfill(state, payload)
        finally:
            orchestrator.detail_backfill_plan = original_plan
        audits = json.loads(snapshot.read_text(encoding="utf-8"))["collection"]["detail_backfills"]
        self.assertEqual(len(audits), 1)

    def test_detail_backfill_closes_collection_terminal_state_when_contract_passes(self) -> None:
        raw = self.root / "detail-terminal.json"
        stdout = self.root / "detail-terminal.stdout.txt"
        stderr = self.root / "detail-terminal.stderr.txt"
        metadata = self.root / "detail-terminal.capture.json"
        for path in (raw, stdout, stderr, metadata):
            path.write_text("{}", encoding="utf-8")
        signal = self.make_signal(1750)
        signal.update({"query_layer": "category", "semantic_relevance": "direct", "detail_captured": False})
        snapshot = self.write("terminal-raw.json", {
            "platform": "x", "source_mode": "controlled_capture",
            "collection": {
                "mode": "standard", "stop_reason": "sampling_contract_unmet:detail_opens",
                "limitations": ["sampling_contract_unmet:detail_opens"],
                "counts": {"detail_open_count": 0}, "detail_backfills": [],
            },
            "signals": [signal],
        })
        state = {
            "mode": "standard", "snapshot": str(snapshot), "queries": [],
            "status": "blocked", "stop_reason": "sampling_contract_unmet:detail_opens",
            "detail_backfill_attempts": [],
        }
        original_plan = orchestrator.detail_backfill_plan
        original_checks = orchestrator.contract_checks
        orchestrator.detail_backfill_plan = lambda _state: {"targets": [{"signal_key": orchestrator.signal_key(signal), "layer": "category"}], "required_detail_count": 1}
        orchestrator.contract_checks = lambda _state: {"detail_opens": True, "all_other_gates": True}
        payload = {"schema_version": "dokobot-detail-backfill-v0.2", "results": [{
            "signal_key": orchestrator.signal_key(signal), "success": True, "raw_artifact": str(raw),
            "stop_reason": "", "signal": {"summary": "opened detail"},
            "execution": {"stdout_artifact": str(stdout), "stderr_artifact": str(stderr), "metadata_artifact": str(metadata)},
        }]}
        try:
            orchestrator.record_detail_backfill(state, payload)
        finally:
            orchestrator.detail_backfill_plan = original_plan
            orchestrator.contract_checks = original_checks
        updated = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["stop_reason"], "sampling_contract_met")
        self.assertEqual(updated["collection"]["stop_reason"], "sampling_contract_met")
        self.assertEqual(updated["collection"]["counts"]["detail_open_count"], 1)
        self.assertEqual(updated["signals"][0]["signal_id"], signal["id"])
        self.assertNotIn("sampling_contract_unmet:detail_opens", updated["collection"]["limitations"])

    def test_normalization_restores_platform_content_id_when_detail_lacks_signal_id(self) -> None:
        normalized = common.normalize_signal(
            {"platform": "tiktok", "content_id": "1234567890", "canonical_url": "https://www.tiktok.com/@creator/video/1234567890"},
            "tiktok", "controlled_capture", self.now.isoformat(),
        )
        self.assertEqual(normalized["signal_id"], "tiktok-1234567890")

    def test_normalization_removes_isolated_replacement_character_and_records_boundary(self) -> None:
        normalized = common.normalize_signal(
            {
                "platform": "tiktok",
                "content_id": "1234567890",
                "canonical_url": "https://www.tiktok.com/@creator/video/1234567890",
                "title": "Weekly budget plan \ufffd",
                "summary": "Weekly budget plan \ufffd",
            },
            "tiktok", "controlled_capture", self.now.isoformat(),
        )
        self.assertEqual(normalized["title"], "Weekly budget plan")
        self.assertEqual(normalized["summary"], "Weekly budget plan")
        self.assertTrue(any("replacement character" in item for item in normalized["limitations"]))

    def test_expansion_platform_names_are_inferred_without_reasking_the_user(self) -> None:
        prompts = {
            "使用 trend-opportunity-radar，分析家庭预算在 TikTok 英语市场的产品需求。": "tiktok",
            "分析年轻人在抖音平台的内容机会。": "douyin",
            "研究 Instagram 上的品牌舆情。": "instagram",
        }
        for prompt, expected in prompts.items():
            with self.subTest(expected=expected):
                context = research_context.compile_context(prompt)
                self.assertEqual(context["status"], "ready")
                self.assertEqual(context["platform"], expected)

    def test_detail_backfill_plan_deduplicates_a_signal_seen_in_multiple_layers(self) -> None:
        shared = self.make_signal(123)
        shared.update({
            "platform": "youtube", "content_id": "shared", "query_layer": "category",
            "semantic_relevance": "direct", "evidence_role": "support", "detail_captured": False,
        })
        shared["query_layers"] = ["category", "subject_bridge"]
        shared["canonical_url"] = "https://www.youtube.com/watch?v=shared"
        snapshot = self.write("raw-shared-detail.json", {
            "platform": "youtube",
            "signals": [shared],
            "collection": {"mode": "standard", "query_runs": [], "counts": {}},
        })
        state = {
            "snapshot": str(snapshot), "adapter": "opencli", "platform": "youtube", "mode": "standard",
            "detail_backfill_attempts": [],
        }
        original_recovery = orchestrator.recovery_diagnostics
        orchestrator.recovery_diagnostics = lambda _state: {
            "layer_deficits": {
                "platform_baseline": {"details": 0, "direct": 0},
                "category": {"details": 1, "direct": 0},
                "subject_bridge": {"details": 1, "direct": 1},
            },
            "global_deficits": {"details": 1},
        }
        try:
            plan = orchestrator.detail_backfill_plan(state)
        finally:
            orchestrator.recovery_diagnostics = original_recovery
        self.assertEqual(len(plan["targets"]), 1)
        self.assertEqual(plan["targets"][0]["signal_key"], orchestrator.signal_key(shared, "youtube"))

    def test_normalization_does_not_override_stale_blocked_stop_reason(self) -> None:
        signals = [self.make_signal(index) for index in range(30)]
        raw = {
            "collection": {
                "mode": "standard", "stop_reason": "sampling_contract_unmet:detail_opens",
                "query_runs": [{
                    "query_term": f"q-{index}",
                    "query_layer": ["platform_baseline", "category", "subject_bridge"][index % 3],
                    "observed_result_count": 10,
                } for index in range(6)],
                "counts": {"query_count": 6, "observed_result_count": 60, "detail_open_count": 30, "counter_signal_count": 3},
            }
        }
        collection = common.normalize_collection(raw, 30, 30, signals)
        self.assertEqual(collection["contract_status"], "blocked")

    def test_report_validator_rejects_met_report_with_blocked_state(self) -> None:
        report = {"collection": {"contract_status": "met", "stop_reason": "sampling_contract_unmet:detail_opens", "counts": {}}}
        with self.assertRaises(SystemExit):
            report_validator.validate_collection_state_consistency(report, self.root)

    def test_report_validator_rejects_detail_review_loss_and_counter_count_drift(self) -> None:
        self.write("raw-signals.json", {
            "collection": {"counts": {"detail_open_count": 1, "counter_signal_count": 1}, "stop_reason": ""},
            "signals": [{
                "detail_captured": True, "semantic_relevance": "direct",
                "evidence_role": "support", "topic_key": "topic-a",
            }],
        })
        report = {"collection": {"contract_status": "blocked", "counts": {"detail_open_count": 1, "counter_signal_count": 1}}}
        with self.assertRaises(SystemExit):
            report_validator.validate_collection_state_consistency(report, self.root)

    def test_report_validator_counts_unique_counter_signals(self) -> None:
        duplicate_counter = {
            "platform": "xiaohongshu",
            "content_id": "note-1",
            "evidence_role": "counter",
            "detail_captured": False,
        }
        self.write("raw-signals.json", {
            "platform": "xiaohongshu",
            "collection": {"counts": {"detail_open_count": 0, "counter_signal_count": 1}, "stop_reason": ""},
            "signals": [duplicate_counter, dict(duplicate_counter)],
        })
        report = {"platform": "xiaohongshu", "collection": {
            "contract_status": "blocked",
            "counts": {"detail_open_count": 0, "counter_signal_count": 1},
        }}
        report_validator.validate_collection_state_consistency(report, self.root)

    def test_report_validator_counts_duplicate_detail_rows_once(self) -> None:
        duplicate_detail = {
            "platform": "x", "content_id": "post-1", "detail_captured": True,
            "semantic_relevance": "direct", "semantic_review": {"status": "reviewed"},
            "evidence_role": "support", "topic_key": "topic-a",
        }
        self.write("raw-signals.json", {
            "platform": "x",
            "collection": {"counts": {"detail_open_count": 1, "counter_signal_count": 0}, "stop_reason": ""},
            "signals": [duplicate_detail, dict(duplicate_detail)],
        })
        report = {"platform": "x", "collection": {
            "contract_status": "blocked",
            "counts": {"detail_open_count": 1, "counter_signal_count": 0},
        }}
        report_validator.validate_collection_state_consistency(report, self.root)

    def test_report_validator_rejects_overlapping_support_and_counter_refs(self) -> None:
        report = {
            "subject": {"name": "Test"},
            "opportunities": [{
                "support_refs": ["https://x.example/status/1/"],
                "counter_refs": ["https://x.example/status/1"],
            }],
        }
        with self.assertRaises(SystemExit):
            report_validator.validate_report_contents(report, "Test")

    def test_next_repairs_stale_blocked_state_when_all_contract_checks_pass(self) -> None:
        snapshot = self.write("stale-blocked-raw.json", {
            "collection": {"stop_reason": "sampling_contract_unmet:detail_opens", "limitations": ["sampling_contract_unmet:detail_opens"]}
        })
        state = {"status": "blocked", "stop_reason": "sampling_contract_unmet:detail_opens", "snapshot": str(snapshot)}
        original_counts = orchestrator.snapshot_counts
        original_checks = orchestrator.contract_checks
        orchestrator.snapshot_counts = lambda _state: {"detail_open_count": 12}
        orchestrator.contract_checks = lambda _state: {"detail_opens": True, "all_other_gates": True}
        try:
            result = orchestrator.action(state)
        finally:
            orchestrator.snapshot_counts = original_counts
            orchestrator.contract_checks = original_checks
        updated = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(result["action"], "complete")
        self.assertEqual(state["status"], "complete")
        self.assertEqual(state["stop_reason"], "sampling_contract_met")
        self.assertEqual(updated["collection"]["stop_reason"], "sampling_contract_met")
        self.assertEqual(updated["collection"]["limitations"], [])

    def test_snapshot_counts_repairs_stale_detail_count_from_canonical_signals(self) -> None:
        signal = self.make_signal(1760)
        signal["detail_captured"] = True
        snapshot = self.write("stale-detail-count.json", {
            "collection": {"counts": {"detail_open_count": 0}}, "signals": [signal]
        })
        counts = orchestrator.snapshot_counts({"snapshot": str(snapshot)})
        updated = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(counts["detail_open_count"], 1)
        self.assertEqual(updated["collection"]["counts"]["detail_open_count"], 1)

    def test_orchestrator_uses_snapshot_platform_when_deduplicating_missing_platform_rows(self) -> None:
        signals = [self.make_signal(index) for index in range(17)]
        duplicate = dict(signals[0])
        duplicate.pop("platform")
        signals.append(duplicate)
        runs = [
            {"query_layer": layer, "observed_result_count": 20, "discarded_result_count": 0}
            for layer in ("platform_baseline", "category", "subject_bridge")
        ]
        snapshot = self.write("platform-fallback-raw.json", {
            "collection": {"query_runs": runs, "counts": {"unique_sample_count": 18}},
            "signals": signals,
        })
        state = {
            "snapshot": str(snapshot), "platform": "x", "mode": "standard",
            "queries": [
                {"status": "completed", "layer": layer}
                for layer in ("platform_baseline", "category", "subject_bridge")
            ],
        }
        counts = orchestrator.snapshot_counts(state)
        checks = orchestrator.contract_checks(state)
        self.assertEqual(counts["unique_sample_count"], 17)
        self.assertFalse(checks["relevant_unique_signals"])

    def test_search_budget_allows_exact_atomic_read_to_upper_bound(self) -> None:
        original_counts = orchestrator.snapshot_counts
        try:
            orchestrator.snapshot_counts = lambda _state: {"observed_result_count": 80}
            self.assertTrue(orchestrator.search_budget({"mode": "standard"})["may_start_search"])
            orchestrator.snapshot_counts = lambda _state: {"observed_result_count": 81}
            self.assertFalse(orchestrator.search_budget({"mode": "standard"})["may_start_search"])
        finally:
            orchestrator.snapshot_counts = original_counts

    def test_xiaohongshu_detail_runner_applies_interval_and_batch_cooldown(self) -> None:
        waits: list[int] = []
        first = opencli_detail_runner.throttle_before_detail("xiaohongshu", 0, waits.append)
        ordinary = opencli_detail_runner.throttle_before_detail("xiaohongshu", 1, waits.append)
        after_batch = opencli_detail_runner.throttle_before_detail("xiaohongshu", 5, waits.append)
        x_platform = opencli_detail_runner.throttle_before_detail("x", 5, waits.append)
        self.assertEqual(first["waited_seconds"], 0)
        self.assertEqual(ordinary["waited_seconds"], 20)
        self.assertEqual(after_batch["waited_seconds"], 65)
        self.assertEqual(after_batch["batch_cooldown_seconds"], 45)
        self.assertEqual(x_platform["waited_seconds"], 40)
        self.assertEqual(x_platform["max_parallel_reads"], 1)
        self.assertFalse(x_platform["randomized"])
        self.assertEqual(waits, [20, 65, 40])

    def test_query_read_count_preserves_serial_cadence_across_queries(self) -> None:
        state = {"queries": [
            {"capture_executions": [{"read_status": "success"}]},
            {"capture_executions": [{"read_status": "timeout"}, {"read_status": "success"}]},
            {"capture_executions": []},
        ]}
        self.assertEqual(collection_capture_runner.prior_query_read_count(state), 3)

    def test_reader_titles_translate_internal_jargon_for_general_audience(self) -> None:
        profile = {"language": "zh-CN", "audience": "general"}
        cases = {
            "多语言售后副驾：先准备动作，资金操作人工批准":
                "跨境电商多语言售后助手：自动准备处理方案，退款等资金操作交给人工确认",
            "跨时区多语言首轮处理队列":
                "先处理夜间和多语言售后，复杂问题再转人工",
            "售后 Agent 的政策与订单事实守门层":
                "售后 AI 助手回复前，先核对订单和政策",
        }
        for original, expected in cases.items():
            with self.subTest(original=original):
                title, replaced = opportunity_generator.reader_title({"title": original}, profile)
                self.assertEqual(title, expected)
                self.assertTrue(replaced)

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.now = datetime.now(timezone.utc)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, name: str, value: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def make_signal(self, index: int, role: str = "support", published_at: str | None = None) -> dict:
        return {
            "id": f"post-{index}",
            "platform": "x",
            "source_type": "direct_post",
            "evidence_role": role,
            "detail_captured": index < 12,
            "query_term": f"query-{index % 6}",
            "query_layer": ["platform_baseline", "category", "subject_bridge"][index % 3],
            "semantic_relevance": "direct",
            "topic_key": "topic-a",
            "title": "A repeated user task",
            "summary": f"Independent observation {index}",
            "url": f"https://x.example/status/{index}",
            "author_id": f"author-{index}",
            "published_at": published_at or (self.now - timedelta(days=index % 5)).isoformat(),
            "captured_at": self.now.isoformat(),
            "metrics_captured_at": self.now.isoformat(),
            "observed_content_count": 30,
            "search_result_count": 80,
            "views": 1000 + index * 10,
            "likes": 40 + index,
            "comments": 5,
            "shares": 3,
            "permission_scope": "public",
        }

    def test_standard_pipeline_and_html(self) -> None:
        raw = {
            "platform": "x",
            "collection": {
                "mode": "standard",
                "query_runs": [
                    {
                        "query_term": f"query-{index}",
                        "query_layer": ["platform_baseline", "category", "subject_bridge"][index % 3],
                        "observed_result_count": 10,
                        "retained_signal_count": 5,
                        "detail_open_count": 2,
                        "discarded_result_count": 5,
                    }
                    for index in range(6)
                ],
                "counts": {
                    "query_count": 6,
                    "observed_result_count": 60,
                    "detail_open_count": 12,
                    "counter_signal_count": 3,
                },
                "stop_reason": "",
            },
            "signals": [self.make_signal(index, "counter" if index >= 27 else "support") for index in range(30)],
        }
        subject = {
            "name": "独立工作流助手",
            "subject_type": "idea",
            "summary": "验证一个边界明确的工作流假设。",
            "facts": [],
            "hypotheses": [{"statement": "The workflow may be useful.", "origin": "user_premise"}],
            "audiences": ["independent professionals"],
        }
        opportunity = {
            "opportunities": [{
                "title": "Assist one repeated workflow",
                "topic_key": "topic-a",
                "audience": "independent professionals",
                "task_gap": "A repeated step is slow and inconsistent.",
                "subject_entry": "Draft a bounded recommendation for human review.",
                "expected_action": "Run five task-based interviews.",
                "support_refs": ["https://x.example/status/0"],
                "counter_refs": ["https://x.example/status/27"],
                "counter_review": "Some users prefer manual control.",
                "counter_search_status": "found",
                "semantic_review": "agent_reviewed",
                "risk_boundaries": ["Do not claim confirmed demand."],
                "missing_evidence": ["Willingness to adopt"],
            }]
        }
        raw_path = self.write("raw.json", raw)
        subject_path = self.write("subject.json", subject)
        opportunity_path = self.write("opportunities.json", opportunity)
        normalized = self.root / "normalized.json"
        scored = self.root / "scored.json"
        report_json = self.root / "report.json"
        report_md = self.root / "report.md"
        report_html = self.root / "report.html"
        run_script("normalize_signals.py", "--input", str(raw_path), "--output", str(normalized), "--platform", "x", "--source-mode", "controlled_capture")
        run_script("calculate_evidence_index.py", "--input", str(normalized), "--output", str(scored))
        scored_fixture = json.loads(scored.read_text(encoding="utf-8"))
        for topic in scored_fixture.get("topics", []):
            topic["cluster_audit"] = {"status": "passed", "title": "把重复任务变成可审核建议"}
        scored.write_text(json.dumps(scored_fixture, ensure_ascii=False, indent=2), encoding="utf-8")
        run_script(
            "generate_opportunities.py", "--subject", str(subject_path), "--signals", str(scored),
            "--opportunities", str(opportunity_path), "--json-output", str(report_json),
            "--markdown-output", str(report_md), "--html-output", str(report_html),
        )
        normalized_data = json.loads(normalized.read_text(encoding="utf-8"))
        scored_data = json.loads(scored.read_text(encoding="utf-8"))
        report = json.loads(report_json.read_text(encoding="utf-8"))
        page = report_html.read_text(encoding="utf-8")
        self.assertEqual(normalized_data["raw_sample_count"], 60)
        self.assertEqual(normalized_data["retained_sample_count"], 30)
        self.assertEqual(normalized_data["collection"]["contract_status"], "met")
        self.assertIn("observed_heat", scored_data["topics"][0])
        self.assertIn("evidence_confidence", scored_data["topics"][0])
        self.assertEqual(report["opportunities"][0]["evidence_status"], "review_ready")
        self.assertIn("查看采样与评分依据", page)
        self.assertIn("证据支撑", page)
        self.assertLess(page.index("机会卡片"), page.index("重点话题"))
        self.assertNotIn("What was actually collected", page)
        self.assertNotIn("<script src=", page)
        self.assertNotIn("<link rel=", page)

    def test_old_content_is_not_fresh_and_weak_topic_stays_candidate(self) -> None:
        signal = self.make_signal(1, published_at="2020-01-01T00:00:00Z")
        raw_path = self.write("raw.json", {"platform": "x", "signals": [signal]})
        subject_path = self.write("subject.json", {"name": "Idea", "subject_type": "idea", "summary": "Test"})
        opportunity_path = self.write("opportunities.json", {"opportunities": [{
            "title": "Weak opportunity", "topic_key": "topic-a", "audience": "users",
            "task_gap": "gap", "subject_entry": "entry", "expected_action": "test",
            "support_refs": [signal["url"]], "counter_refs": [],
            "counter_review": "Searched without finding a counterexample.",
            "counter_search_status": "searched_none_found", "semantic_review": "agent_reviewed",
            "risk_boundaries": ["candidate"], "missing_evidence": [],
        }]})
        normalized = self.root / "normalized.json"
        scored = self.root / "scored.json"
        report_json = self.root / "report.json"
        run_script("normalize_signals.py", "--input", str(raw_path), "--output", str(normalized), "--platform", "x", "--source-mode", "public_web")
        run_script("calculate_evidence_index.py", "--input", str(normalized), "--output", str(scored))
        run_script(
            "generate_opportunities.py", "--subject", str(subject_path), "--signals", str(scored),
            "--opportunities", str(opportunity_path), "--json-output", str(report_json),
            "--markdown-output", str(self.root / "report.md"),
        )
        scored_data = json.loads(scored.read_text(encoding="utf-8"))
        report = json.loads(report_json.read_text(encoding="utf-8"))
        self.assertEqual(scored_data["signals"][0]["evidence_index"]["dimensions"]["freshness"], 10.0)
        self.assertEqual(report["opportunities"][0]["evidence_status"], "candidate")
        self.assertIn("sampling_contract_completed", report["opportunities"][0]["failed_gates"])
        self.assertIn("minimum_independent_signals", report["opportunities"][0]["failed_gates"])

    def test_report_excludes_failed_clusters_and_duplicate_topic_opportunities(self) -> None:
        def topic(key: str, audit_status: str) -> dict:
            return {
                "topic_key": key, "title": key, "cluster_audit": {"status": audit_status},
                "sample_count": 3, "unique_author_count": 3, "direct_source_count": 2,
                "subject_bridge_direct_count": 1, "relevance_review_coverage": 1.0,
                "evidence_confidence": 54, "observed_heat": 30, "data_coverage": 65,
                "raw_evidence_confidence": 85, "confidence_cap": 54,
                "confidence_cap_reason": "sampling_contract_incomplete",
                "counter_signal_count": 1, "search_card_count": 1, "missing_fields": [],
            }

        scored = self.write("strict-scored.json", {
            "platform": "x", "collection": {
                "mode": "standard", "contract_status": "blocked", "counts": {},
                "contract_checks": {"queries": True, "layer_detail_opens": False},
                "layer_stats": {"platform_baseline": {"query_count": 2, "observed_result_count": 10, "unique_signal_count": 4, "detail_open_count": 0, "direct_relevance_count": 0}},
            },
            "signals": [
                {"limitations": [
                    "Search card only; full post context not opened.",
                    "Vendor framing; no independent customer outcome.",
                    "Broad commentary; not specific to small ecommerce teams.",
                    "ROI figures are unsourced and unverified.",
                    "Search card is truncated.",
                ]}
            ], "topics": [topic("passed-topic", "passed"), topic("failed-topic", "failed")],
        })
        subject = self.write("strict-subject.json", {
            "name": "English-market test subject", "subject_type": "idea", "summary": "Research an English-language market.",
            "communication": {"language": "zh-CN", "goal": "validate_business_opportunity", "audience": "general"},
        })

        def opportunity(title: str, key: str) -> dict:
            return {
                "title": title, "topic_key": key, "audience": "users", "task_gap": "gap",
                "subject_entry": "entry", "expected_action": "test", "support_refs": ["https://x.example/1"],
                "counter_refs": ["https://x.example/2"], "counter_review": "reviewed",
                "counter_search_status": "found", "semantic_review": "agent_reviewed",
                "risk_boundaries": ["bounded"], "missing_evidence": [],
            }

        proposals = self.write("strict-opportunities.json", {"opportunities": [
            opportunity("多语言售后副驾：先准备动作，资金操作人工批准", "passed-topic"),
            opportunity("Duplicate", "passed-topic"),
            opportunity("Failed cluster", "failed-topic"),
        ]})
        report_json = self.root / "strict-report.json"
        report_html = self.root / "strict-report.html"
        run_script(
            "generate_opportunities.py", "--subject", str(subject), "--signals", str(scored),
            "--opportunities", str(proposals), "--json-output", str(report_json),
            "--markdown-output", str(self.root / "strict-report.md"), "--html-output", str(report_html),
        )
        report = json.loads(report_json.read_text(encoding="utf-8"))
        visible_html = report_html.read_text(encoding="utf-8").split('<pre id="raw">', 1)[0]
        self.assertEqual(report["schema_version"], "trend-opportunity-report-v0.3")
        self.assertEqual([item["topic_key"] for item in report["topics"]], ["passed-topic"])
        self.assertEqual([item["title"] for item in report["opportunities"]], ["多语言售后副驾：先准备动作，资金操作人工批准"])
        self.assertEqual(report["opportunities"][0]["reader_title"], "跨境电商多语言售后助手：自动准备处理方案，退款等资金操作交给人工确认")
        self.assertEqual(report["opportunities"][0]["title_readability"]["status"], "rewritten")
        self.assertEqual(len(report["excluded_topics"]), 1)
        self.assertEqual(
            {item["exclusion_reason"] for item in report["excluded_opportunities"]},
            {"one_primary_opportunity_per_topic", "topic_not_eligible"},
        )
        visible_markdown = opportunity_generator.render_markdown(report)
        self.assertNotIn("已排除的探索性话题", visible_markdown)
        self.assertNotIn("Excluded exploratory topics", visible_markdown)
        self.assertIn("初步证据", visible_html)
        self.assertIn("各层采集情况", visible_html)
        self.assertIn("当前结论保持为候选，避免过度确定", visible_html)
        self.assertNotIn("blocked", visible_html)
        self.assertNotIn("Failed collection gates", visible_html)
        self.assertNotIn("sampling_contract_completed", visible_html)
        self.assertNotIn("Search card only; full post context not opened.", visible_html)
        self.assertIn("这里只展示影响判断的汇总", visible_html)
        self.assertLessEqual(visible_html.count('<li>'), 4)
        self.assertIn("Search card only; full post context not opened.", report["limitations"])
        self.assertEqual(len(report["limitation_summary"]), 4)
        self.assertTrue(report["monitoring_recommendation"]["recommended"])
        self.assertEqual(report["monitoring_recommendation"]["cadence"]["value"], 3)
        self.assertEqual(report["monitoring_recommendation"]["cadence"]["occurrences"], 4)
        self.assertIn("不得覆盖历史快照", report["monitoring_recommendation"]["automation_prompt"])
        self.assertIn("把这次快照变成趋势", visible_html)
        self.assertIn("每 3 天一次，连续 4 次", visible_html)
        self.assertEqual(report["communication"], {"language": "zh-CN", "goal": "validate_business_opportunity", "audience": "general"})
        self.assertIn("这次研究现在能帮你做什么决定", visible_html)
        self.assertIn("现在可以用于", visible_html)
        self.assertIn("建议的解决路径", visible_html)
        self.assertNotIn("尚缺趋势维度", visible_html)
        self.assertNotIn("当前数据还不够完整", visible_html)
        self.assertIn("30/100", visible_html)
        self.assertIn("弱信号", visible_html)
        self.assertIn("54/100", visible_html)
        self.assertIn("证据待补强", visible_html)
        self.assertIn("评分怎么看", visible_html)
        self.assertIn("证据质量计算值为 85", visible_html)
        self.assertNotIn("避免高估结论可靠性", visible_html)
        self.assertNotIn("各层详情页数量", visible_html)
        self.assertNotIn("补齐分层证据后可重新评估", visible_html)
        self.assertNotIn("多语言售后副驾", visible_html)
        self.assertIn("跨境电商多语言售后助手", visible_html)

    def test_search_card_is_downgraded_and_confidence_is_capped(self) -> None:
        signal = self.make_signal(20)
        signal["source_type"] = "direct_post"
        signal["detail_captured"] = False
        signal["limitations"] = ["search_card_only"]
        raw_path = self.write("raw.json", {"platform": "x", "signals": [signal]})
        normalized = self.root / "normalized.json"
        scored = self.root / "scored.json"
        run_script("normalize_signals.py", "--input", str(raw_path), "--output", str(normalized), "--platform", "x", "--source-mode", "controlled_capture")
        run_script("calculate_evidence_index.py", "--input", str(normalized), "--output", str(scored))
        normalized_data = json.loads(normalized.read_text(encoding="utf-8"))
        topic = json.loads(scored.read_text(encoding="utf-8"))["topics"][0]
        self.assertEqual(normalized_data["signals"][0]["source_type"], "search_card")
        self.assertEqual(topic["direct_source_count"], 0)
        self.assertEqual(topic["search_card_count"], 1)
        self.assertLessEqual(topic["evidence_confidence"], 45)
        self.assertGreaterEqual(topic["raw_evidence_confidence"], topic["evidence_confidence"])

    def test_stable_content_id_dedupe_merges_search_card_and_detail(self) -> None:
        card = self.make_signal(1)
        card.update({"detail_captured": False, "source_type": "search_card", "query_term": "broad", "query_layer": "platform_baseline"})
        detail = self.make_signal(1)
        detail.update({"detail_captured": True, "source_type": "direct_post", "query_term": "bridge", "query_layer": "subject_bridge", "summary": "Richer direct detail"})
        raw_path = self.write("duplicate.json", {"platform": "x", "signals": [card, detail]})
        normalized = self.root / "deduped.json"
        run_script("normalize_signals.py", "--input", str(raw_path), "--output", str(normalized), "--platform", "x", "--source-mode", "controlled_capture")
        data = json.loads(normalized.read_text(encoding="utf-8"))
        self.assertEqual(data["retained_sample_count"], 2)
        self.assertEqual(data["unique_sample_count"], 1)
        self.assertEqual(data["collection"]["counts"]["duplicate_count"], 1)
        signal = data["signals"][0]
        self.assertEqual(signal["source_type"], "direct_post")
        self.assertTrue(signal["detail_captured"])
        self.assertEqual(set(signal["query_layers"]), {"platform_baseline", "subject_bridge"})
        self.assertEqual(signal["merged_from_count"], 2)

    def test_cluster_audit_requires_explicit_assignments_and_passes_valid_plan(self) -> None:
        raw_path = self.write("cluster-input.json", {"platform": "x", "signals": [self.make_signal(index) for index in range(6)]})
        normalized = self.root / "cluster-normalized.json"
        clustered = self.root / "clustered.json"
        run_script("normalize_signals.py", "--input", str(raw_path), "--output", str(normalized), "--platform", "x", "--source-mode", "controlled_capture")
        normalized_data = json.loads(normalized.read_text(encoding="utf-8"))
        plan = self.write("cluster-plan.json", {"clusters": [{
            "topic_key": "workflow-transition",
            "title": "Workflow transition",
            "task_transition": "manual review to bounded assisted review",
            "inclusion_rule": "Signals describing the same review transition",
            "exclusion_rule": "Exclude unrelated automation claims",
            "assignments": [{
                "signal_id": item["signal_id"], "fit": "core" if index < 2 else "supporting",
                "reason": "Describes the shared review transition", "task_transition_match": True,
            } for index, item in enumerate(normalized_data["signals"])],
        }]})
        run_script("audit_clusters.py", "--input", str(normalized), "--plan", str(plan), "--output", str(clustered))
        data = json.loads(clustered.read_text(encoding="utf-8"))
        self.assertTrue(data["clustering"]["applied"])
        self.assertEqual(data["cluster_audits"][0]["status"], "passed")
        self.assertEqual({item["topic_key"] for item in data["signals"]}, {"workflow-transition"})
        scored = self.root / "cluster-scored.json"
        run_script("calculate_evidence_index.py", "--input", str(clustered), "--output", str(scored))
        self.assertEqual(json.loads(scored.read_text(encoding="utf-8"))["topics"][0]["title"], "Workflow transition")

        bad_plan = self.write("bad-cluster-title.json", {"clusters": [{
            **json.loads(plan.read_text(encoding="utf-8"))["clusters"][0],
            "title": "**Representative source post**",
        }]})
        rejected = subprocess.run(
            [sys.executable, str(SCRIPTS / "audit_clusters.py"), "--input", str(normalized), "--plan", str(bad_plan), "--output", str(self.root / "bad-cluster.json")],
            capture_output=True, text=True,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("reader-facing", rejected.stderr + rejected.stdout)

    def test_atomic_query_append_and_subject_validation(self) -> None:
        query_one = self.write("query-one.json", {
            "query_term": "designer pricing", "query_layer": "category", "observed_result_count": 4,
            "detail_open_count": 1, "signals": [self.make_signal(1), self.make_signal(2, "counter")],
        })
        query_two = self.write("query-two.json", {
            "query_term": "AI quote assistant", "query_layer": "subject_bridge", "observed_result_count": 3,
            "detail_open_count": 0, "signals": [self.make_signal(3)], "stop_reason": "visible_results_exhausted",
        })
        snapshot = self.root / "raw-signals.json"
        for query in (query_one, query_two):
            run_script(
                "append_collection_result.py", "--snapshot", str(snapshot), "--query-result", str(query),
                "--platform", "x", "--source-mode", "controlled_capture", "--mode", "standard",
            )
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(data["collection"]["counts"]["query_count"], 2)
        self.assertEqual(data["collection"]["counts"]["observed_result_count"], 7)
        self.assertEqual(data["collection"]["counts"]["retained_sample_count"], 3)
        self.assertEqual(data["collection"]["counts"]["counter_signal_count"], 1)
        self.assertEqual(len(data["collection"]["query_runs"]), 2)

        invalid_subject = self.write("invalid-subject.json", {
            "name": "Idea", "subject_type": "opportunity_hypothesis", "summary": "Test",
            "facts": [], "hypotheses": [], "audiences": [], "scenarios": [], "constraints": [], "source_refs": [],
        })
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_subject.py"), "--input", str(invalid_subject)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("subject_type must be one of", completed.stderr + completed.stdout)

    def make_standard_query_plan(self) -> dict:
        layers = ["platform_baseline", "category", "subject_bridge"] * 2
        return {
            "queries": [
                {
                    "id": f"query-{index}",
                    "term": f"term {index}",
                    "layer": layer,
                    "url": f"https://x.example/search?q={index}",
                }
                for index, layer in enumerate(layers)
            ]
        }

    def make_ready_adapter_status(self) -> Path:
        return self.write("adapter-status.json", {
            "schema_version": "collection-adapter-status-v0.1",
            "adapter": "dokobot",
            "status": "ready",
            "ready": True,
        })

    def test_dokobot_orchestrator_continues_and_meets_standard_contract(self) -> None:
        plan = self.write("query-plan.json", self.make_standard_query_plan())
        state = self.root / "collection-state.json"
        snapshot = self.root / "raw-signals.json"
        adapter_status = self.make_ready_adapter_status()
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(plan), "--adapter-status", str(adapter_status), "--platform", "x", "--mode", "standard",
        )
        self.assertEqual(action["action"], "start_query")
        self.assertEqual(action["dokobot_command"][0:2], ["dokobot", "read"])

        next_signal = 0
        for query_index in range(6):
            for chunk_index in range(2):
                raw_artifact = self.root / f"capture-{query_index}-{chunk_index}.json"
                raw_artifact.write_text("{}", encoding="utf-8")
                roles = ["counter" if next_signal + offset >= 57 else "support" for offset in range(5)]
                signals = [self.make_signal(next_signal + offset, role) for offset, role in enumerate(roles)]
                keys = [f"post-{next_signal + offset}" for offset in range(5)]
                next_signal += 5
                chunk = self.write(f"chunk-{query_index}-{chunk_index}.json", {
                    "query_id": f"query-{query_index}",
                    "session_id": f"session-{query_index}",
                    "can_continue": chunk_index == 0,
                    "observed_result_keys": keys,
                    "signals": signals,
                    "detail_open_keys": keys[:1],
                    "raw_artifact": str(raw_artifact),
                })
                action = run_script_json(
                    "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(chunk)
                )
                if chunk_index == 0:
                    self.assertEqual(action["action"], "continue_query")
                    self.assertIn("--session-id", action["dokobot_command"])

        self.assertEqual(action["action"], "complete")
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(data["collection"]["counts"]["query_count"], 6)
        self.assertEqual(data["collection"]["counts"]["observed_result_count"], 60)
        self.assertEqual(data["collection"]["counts"]["unique_sample_count"], 60)
        self.assertEqual(data["collection"]["counts"]["detail_open_count"], 12)
        self.assertEqual(data["collection"]["counts"]["counter_signal_count"], 3)

    def test_dokobot_orchestrator_replans_then_blocks_at_query_budget(self) -> None:
        plan = self.write("query-plan.json", self.make_standard_query_plan())
        state = self.root / "collection-state.json"
        snapshot = self.root / "raw-signals.json"
        adapter_status = self.make_ready_adapter_status()
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(plan), "--adapter-status", str(adapter_status), "--platform", "x", "--mode", "standard",
        )
        for query_index in range(6):
            raw_artifact = self.root / f"short-{query_index}.json"
            raw_artifact.write_text("{}", encoding="utf-8")
            chunk = self.write(f"short-chunk-{query_index}.json", {
                "query_id": f"query-{query_index}",
                "session_id": "",
                "can_continue": False,
                "observed_result_keys": [f"short-{query_index}-1", f"short-{query_index}-2"],
                "signals": [{**self.make_signal(100 + query_index), "semantic_relevance": "weak"}],
                "detail_open_keys": [],
                "raw_artifact": str(raw_artifact),
                "stop_reason": "visible_results_exhausted",
                "continuation_status": "exhausted",
                "terminal_evidence": "explicit_platform_end",
            })
            action = run_script_json(
                "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(chunk)
            )
        self.assertEqual(action["action"], "replan_queries")
        self.assertIn("observed_results", action["missing"])
        self.assertIn("unique_signals", action["missing"])
        self.assertEqual(action["recovery"]["query_budget_remaining"], 3)
        for query_index, layer in enumerate(["platform_baseline", "category", "subject_bridge"]):
            recovery = self.write(f"recovery-plan-{query_index}.json", {"queries": [
                {"id": f"recovery-{query_index}", "term": f"broader recovery {query_index}", "layer": layer,
                 "url": f"https://x.example/search?q=recovery-{query_index}"}
            ]})
            action = run_script_json(
                "orchestrate_dokobot_collection.py", "add-queries", "--state", str(state), "--plan", str(recovery)
            )
            raw_artifact = self.root / f"recovery-empty-{query_index}.json"
            raw_artifact.write_text("{}", encoding="utf-8")
            chunk = self.write(f"recovery-chunk-{query_index}.json", {
                "query_id": f"recovery-{query_index}", "session_id": "", "can_continue": False,
                "observed_result_keys": [], "signals": [], "detail_open_keys": [],
                "raw_artifact": str(raw_artifact), "stop_reason": "zero_results",
                "continuation_status": "exhausted", "terminal_evidence": "zero_results",
            })
            action = run_script_json(
                "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(chunk)
            )
        self.assertEqual(action["action"], "blocked")
        data = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertTrue(data["collection"]["stop_reason"].startswith("sampling_contract_unmet:"))

    def test_standard_observed_budget_stops_before_another_atomic_search(self) -> None:
        state = self.root / "budget-state.json"
        snapshot = self.root / "budget-raw.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("budget-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        for query_index in range(3):
            raw_artifact = self.root / f"budget-{query_index}.json"
            raw_artifact.write_text("{}", encoding="utf-8")
            signals = []
            for offset in range(3):
                signal = self.make_signal(1400 + query_index * 3 + offset)
                signal.update({"query_layer": ["platform_baseline", "category", "subject_bridge"][query_index], "semantic_relevance": "weak"})
                signals.append(signal)
            chunk = self.write(f"budget-chunk-{query_index}.json", {
                "query_id": f"query-{query_index}", "session_id": "", "can_continue": True,
                "observed_result_keys": [f"budget-{query_index}-{offset}" for offset in range(30)],
                "signals": signals, "detail_open_keys": [], "raw_artifact": str(raw_artifact),
            })
            action = run_script_json(
                "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(chunk)
            )
        self.assertEqual(action["action"], "blocked")
        self.assertTrue(action["stop_reason"].startswith("observed_budget_guard:"))
        self.assertEqual(action["counts"]["observed_result_count"], 90)
        self.assertFalse(action["search_budget"]["may_start_search"])
        state_data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(state_data["queries"][3]["status"], "pending")
        diagnostics = orchestrator.recovery_diagnostics(state_data)
        self.assertEqual(len(diagnostics["low_yield_queries"]), 3)
        self.assertTrue(all(item["reason"] == "high_volume_low_relevance" for item in diagnostics["low_yield_queries"]))

    def test_standard_accepts_three_layer_probe_plan(self) -> None:
        plan = {"queries": self.make_standard_query_plan()["queries"][:3]}
        validated = orchestrator.validate_plan(plan, "standard")
        self.assertEqual(len(validated), 3)
        self.assertEqual({item["layer"] for item in validated}, {"platform_baseline", "category", "subject_bridge"})

    def test_atomic_read_overshoot_is_preserved_and_audited(self) -> None:
        state = self.root / "overshoot-state.json"
        snapshot = self.root / "overshoot-raw.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("overshoot-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        state_data = json.loads(state.read_text(encoding="utf-8"))
        state_data["active_query"] = orchestrator.new_active_query(state_data["queries"][0])
        state_data["active_query"].update({
            "observed_result_keys": [f"seen-{index}" for index in range(105)],
            "signals": [], "raw_artifacts": [], "detail_open_keys": [],
        })
        state_data["queries"][0]["status"] = "in_progress"
        state.write_text(json.dumps(state_data), encoding="utf-8")
        orchestrator.finalize_active(state_data, state)
        audit = json.loads(snapshot.read_text(encoding="utf-8"))["collection"]["observed_budget_audit"]
        self.assertEqual(audit["observed_result_count"], 105)
        self.assertEqual(audit["atomic_overshoot"], 5)
        self.assertFalse(audit["truncated"])
        self.assertEqual(audit["reason"], "atomic_read_overshoot")

    def test_finalize_active_recovers_when_snapshot_append_preceded_state_write(self) -> None:
        snapshot = self.root / "recover-raw.json"
        state_path = self.root / "recover-state.json"
        active = orchestrator.new_active_query({
            "id": "bridge", "term": "AI travel planner", "layer": "subject_bridge",
            "url": "https://www.tiktok.com/search?q=AI%20travel%20planner",
        })
        active.update({
            "observed_result_keys": ["video-1"],
            "signals": [{"id": "video-1", "url": "https://www.tiktok.com/@demo/video/1", "semantic_relevance": "direct"}],
        })
        state = {
            "adapter": "opencli", "platform": "tiktok", "mode": "standard",
            "snapshot": str(snapshot), "active_query": active,
            "queries": [{"id": "bridge", "term": "AI travel planner", "layer": "subject_bridge", "status": "in_progress"}],
        }
        orchestrator.finalize_active(state, state_path)
        recovered_active = json.loads(json.dumps(active))
        state["active_query"] = recovered_active
        state["queries"][0]["status"] = "in_progress"
        orchestrator.finalize_active(state, state_path)
        saved = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["collection"]["query_runs"]), 1)
        self.assertEqual(saved["collection"]["counts"]["observed_result_count"], 1)
        self.assertEqual(state["queries"][0]["status"], "completed")
        self.assertIsNone(state["active_query"])

    def test_search_only_tiktok_hands_off_to_video_evidence_without_detail_command(self) -> None:
        layers = ["platform_baseline", "category", "subject_bridge"]
        signals = []
        for index in range(60):
            layer = layers[index // 20]
            signals.append({
                "id": f"video-{index}", "url": f"https://www.tiktok.com/@demo/video/{index}",
                "query_layer": layer, "semantic_relevance": "direct",
                "evidence_role": "counter" if index >= 54 else "support",
                "source_type": "search_card", "detail_captured": False,
            })
        snapshot = self.write("tiktok-search-only.json", {
            "schema_version": "trend-raw-snapshot-v0.2", "platform": "tiktok", "source_mode": "controlled_capture",
            "collection": {"mode": "standard", "query_runs": [
                {"query_term": layer, "query_layer": layer, "observed_result_count": 20, "retained_signal_count": 20,
                 "detail_open_count": 0, "discarded_result_count": 0}
                for layer in layers
            ], "counts": {}, "stop_reason": "collection_in_progress", "limitations": []},
            "signals": signals,
        })
        state = self.write("tiktok-search-only-state.json", {
            "schema_version": "collection-orchestrator-v0.2", "adapter": "opencli", "platform": "tiktok",
            "source_mode": "controlled_capture", "mode": "standard", "snapshot": str(snapshot),
            "plan": str(self.root / "plan.json"), "adapter_status": str(self.root / "adapter.json"),
            "capture_dir": str(self.root / "captures"), "screens_per_chunk": 1,
            "status": "in_progress", "stop_reason": "", "active_query": None,
            "queries": [
                {"id": f"q-{index}", "term": layer, "layer": layer, "url": "https://www.tiktok.com/search", "status": "completed"}
                for index, layer in enumerate(layers)
            ],
        })
        action = run_script_json("orchestrate_dokobot_collection.py", "next", "--state", str(state))
        self.assertEqual(action["action"], "blocked")
        self.assertEqual(action["handoff"], "video_evidence")
        self.assertIn("detail_enrichment_unavailable", action["stop_reason"])
        self.assertFalse(orchestrator.detail_backfill_plan(json.loads(state.read_text(encoding="utf-8")))["available"])

    def test_tiktok_detail_enhancement_uses_dokobot_after_opencli_search(self) -> None:
        snapshot = self.write("tiktok-enhanced-raw.json", {
            "platform": "tiktok", "source_mode": "controlled_capture",
            "collection": {"mode": "standard", "query_runs": [], "counts": {}, "stop_reason": "collection_in_progress"},
            "signals": [{
                "content_id": "7000000000000000001",
                "canonical_url": "https://www.tiktok.com/@synthetic.creator/video/7000000000000000001",
                "query_layer": "subject_bridge", "semantic_relevance": "direct", "evidence_role": "support",
                "title": "Synthetic travel planner example", "detail_captured": False,
            }],
        })
        state = {
            "adapter": "opencli", "detail_adapter": "dokobot", "platform": "tiktok", "mode": "standard",
            "snapshot": str(snapshot), "capture_dir": str(self.root / "captures"), "detail_backfill_attempts": [],
            "queries": [], "active_query": None,
        }
        original_recovery = orchestrator.recovery_diagnostics
        orchestrator.recovery_diagnostics = lambda _state: {
            "global_deficits": {"details": 1},
            "layer_deficits": {
                "platform_baseline": {"details": 0}, "category": {"details": 0},
                "subject_bridge": {"details": 1, "direct": 1},
            }
        }
        try:
            plan = orchestrator.detail_backfill_plan(state)
        finally:
            orchestrator.recovery_diagnostics = original_recovery
        self.assertTrue(plan["available"])
        self.assertEqual(len(plan["targets"]), 1)
        command = orchestrator.detail_capture_command(state, plan["targets"][0]["url"], self.root / "detail.txt")
        self.assertEqual(command[:2], ["dokobot", "read"])

    def test_attach_detail_adapter_reopens_only_recoverable_tiktok_detail_block(self) -> None:
        snapshot = self.write("attach-detail-raw.json", {
            "platform": "tiktok", "collection": {"stop_reason": "sampling_contract_unmet:detail_opens,detail_enrichment_unavailable", "limitations": []}, "signals": [],
        })
        selection_path = self.write("enhanced-selection.json", {
            "schema_version": "collection-adapter-selection-v0.2", "platform": "tiktok",
            "adapter": "opencli", "ready": True, "detail_adapter": "dokobot", "detail_ready": True,
            "detail_selected_preflight": {"adapter": "dokobot", "ready": True, "status": "ready"},
        })
        state = {
            "adapter": "opencli", "platform": "tiktok", "snapshot": str(snapshot),
            "status": "blocked", "stop_reason": "sampling_contract_unmet:detail_opens,detail_enrichment_unavailable",
        }
        orchestrator.attach_detail_adapter(state, selection_path, json.loads(selection_path.read_text(encoding="utf-8")))
        self.assertEqual(state["detail_adapter"], "dokobot")
        self.assertEqual(state["status"], "in_progress")
        self.assertEqual(len(state["adapter_enhancements"]), 1)
        saved = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(saved["collection"]["stop_reason"], "collection_in_progress")

    def test_tiktok_detail_parser_requires_stable_identity_and_bounds_visible_comments(self) -> None:
        target_url = "https://www.tiktok.com/@synthetic.creator/video/7000000000000000001"
        raw_text = """# TikTok - Make Your Day
> https://www.tiktok.com/@synthetic.creator/video/7000000000000000001

**1250**
**Like**
**Comments**
**12**
**Favorites**
**Add to Favorites**
**Share**
**31**
---
Synthetic Creator [8]
· 8-18

Build a flexible AI travel planner **more** #travel
---
Comments
Viewer One
I need to change the plan after booking
3 likes · 1d ago
---
Viewer Two
Spreadsheets already work for me
1 like · 2d ago
---
You may like
[8] https://www.tiktok.com/@synthetic.creator
"""
        raw = self.root / "tiktok-detail.txt"
        metadata = self.root / "detail.capture.json"
        stdout = self.root / "detail.stdout.txt"
        stderr = self.root / "detail.stderr.txt"
        for path in (raw, metadata, stdout, stderr):
            path.write_text(raw_text if path == raw else "{}", encoding="utf-8")
        parsed = tiktok_detail_parser.parse_tiktok_detail(raw_text, target_url, raw, metadata, stdout, stderr, "AI travel planner")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["content_id"], "7000000000000000001")
        self.assertEqual(parsed["metrics"]["likes"], 1250)
        self.assertEqual(parsed["metrics"]["comments"], 12)
        self.assertEqual(parsed["metrics"]["shares"], 31)
        self.assertEqual(parsed["platform_facts"]["representative_comment_count"], 2)
        mismatch = tiktok_detail_parser.parse_tiktok_detail(
            raw_text, "https://www.tiktok.com/@synthetic.creator/video/7999999999999999999",
            raw, metadata, stdout, stderr,
        )
        self.assertIsNone(mismatch)

    def test_dokobot_orchestrator_backfills_retained_details_before_reporting(self) -> None:
        signals = []
        layers = ["platform_baseline", "category", "subject_bridge"]
        for index in range(30):
            signal = self.make_signal(index, "counter" if index >= 27 else "support")
            layer = layers[index // 10]
            signal.update({
                "query_layer": layer,
                "query_term": f"{layer}-{index % 3}",
                "semantic_relevance": "direct",
                "semantic_review": {"status": "agent_reviewed", "reason": "Reviewed before detail backfill."},
                "detail_captured": layer != "platform_baseline" and index % 10 < 5,
            })
            signals.append(signal)
        query_runs = [
            {
                "query_term": f"{layer}-{index}", "query_layer": layer,
                "observed_result_count": 10, "retained_signal_count": 3,
                "detail_open_count": 0, "discarded_result_count": 7,
            }
            for layer in layers for index in range(3)
        ]
        snapshot = self.write("detail-backfill-snapshot.json", {
            "schema_version": "trend-raw-snapshot-v0.2", "platform": "x", "source_mode": "controlled_capture",
            "collection": {"mode": "standard", "query_runs": query_runs, "counts": {
                "query_count": 9, "observed_result_count": 90, "retained_sample_count": 30,
                "unique_sample_count": 30, "detail_open_count": 10, "counter_signal_count": 3,
            }, "stop_reason": "sampling_contract_unmet:detail_opens,layer_detail_opens", "limitations": []},
            "signals": signals,
        })
        state = self.write("detail-backfill-state.json", {
            "schema_version": "dokobot-collection-orchestrator-v0.1", "adapter": "dokobot", "platform": "x",
            "source_mode": "controlled_capture", "mode": "standard", "snapshot": str(snapshot),
            "plan": str(self.root / "plan.json"), "adapter_status": str(self.root / "adapter.json"),
            "capture_dir": str(self.root / "captures"), "screens_per_chunk": 3,
            "status": "blocked", "stop_reason": "sampling_contract_unmet:detail_opens,layer_detail_opens",
            "queries": [
                {"id": f"q-{index}", "term": run["query_term"], "layer": run["query_layer"], "url": f"https://x.example/search/{index}", "status": "completed"}
                for index, run in enumerate(query_runs)
            ],
            "active_query": None,
        })
        action = run_script_json("orchestrate_dokobot_collection.py", "next", "--state", str(state))
        self.assertEqual(action["action"], "backfill_details")
        self.assertEqual(action["required_detail_count"], 2)
        self.assertGreaterEqual(len(action["targets"]), 2)
        results = []
        for index, target in enumerate(action["targets"][:2]):
            raw_artifact = self.root / f"detail-{index}.json"
            raw_artifact.write_text("{}", encoding="utf-8")
            original = next(item for item in signals if item["url"] == target["url"])
            results.append({
                "signal_key": target["signal_key"], "success": True, "raw_artifact": str(raw_artifact),
                "signal": {"content_id": original["id"], "canonical_url": original["url"], "summary": "Full verified detail", "detail_captured": True, "source_type": "direct_post"},
            })
        result_path = self.write("detail-results.json", {"results": results})
        completed = run_script_json(
            "orchestrate_dokobot_collection.py", "record-details", "--state", str(state), "--results", str(result_path)
        )
        updated_snapshot = json.loads(snapshot.read_text(encoding="utf-8"))
        updated_state = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(completed["action"], "complete")
        self.assertEqual(updated_state["status"], "complete")
        self.assertEqual(updated_snapshot["collection"]["counts"]["detail_open_count"], 12)
        self.assertEqual(len(updated_snapshot["collection"]["detail_backfills"]), 2)
        enriched = [item for item in updated_snapshot["signals"] if item.get("summary") == "Full verified detail"]
        self.assertEqual(len(enriched), 2)
        self.assertTrue(all(item.get("semantic_review") for item in enriched))
        self.assertTrue(all(item.get("evidence_role") for item in enriched))
        self.assertTrue(all(item.get("topic_key") == "topic-a" for item in enriched))

    def test_dokobot_orchestrator_finalizes_zero_result_query_then_requests_recovery(self) -> None:
        plan_data = self.make_standard_query_plan()
        plan_data["queries"].append({
            "id": "bridge-zero",
            "term": "no matching results",
            "layer": "subject_bridge",
            "url": "https://x.example/search?q=zero",
        })
        plan = self.write("query-plan-zero.json", plan_data)
        state = self.root / "collection-state-zero.json"
        snapshot = self.root / "raw-signals-zero.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(plan), "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        for query_index in range(6):
            raw_artifact = self.root / f"pre-zero-{query_index}.json"
            raw_artifact.write_text("{}", encoding="utf-8")
            chunk = self.write(f"pre-zero-chunk-{query_index}.json", {
                "query_id": f"query-{query_index}",
                "session_id": "",
                "can_continue": False,
                "observed_result_keys": [f"pre-zero-{query_index}"],
            "signals": [{**self.make_signal(200 + query_index), "semantic_relevance": "weak"}],
                "detail_open_keys": [],
                "raw_artifact": str(raw_artifact),
                "stop_reason": "visible_results_exhausted",
                "continuation_status": "exhausted",
                "terminal_evidence": "explicit_platform_end",
            })
            action = run_script_json(
                "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(chunk)
            )
        self.assertEqual(action["query"]["id"], "bridge-zero")
        zero_artifact = self.root / "zero-results.json"
        zero_artifact.write_text("{}", encoding="utf-8")
        zero_chunk = self.write("zero-result-chunk.json", {
            "query_id": "bridge-zero",
            "session_id": "",
            "can_continue": False,
            "observed_result_keys": [],
            "signals": [],
            "detail_open_keys": [],
            "raw_artifact": str(zero_artifact),
            "stop_reason": "zero_results",
            "continuation_status": "exhausted",
            "terminal_evidence": "zero_results",
        })
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(zero_chunk)
        )
        self.assertEqual(action["action"], "replan_queries")
        state_data = json.loads(state.read_text(encoding="utf-8"))
        snapshot_data = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(state_data["status"], "in_progress")
        self.assertIsNone(state_data["active_query"])
        self.assertEqual(state_data["queries"][-1]["status"], "completed")
        self.assertEqual(state_data["queries"][-1]["completion_status"], "completed_with_zero_results")
        self.assertEqual(snapshot_data["collection"]["counts"]["query_count"], 7)
        self.assertEqual(snapshot_data["collection"]["query_runs"][-1]["observed_result_count"], 0)
        self.assertEqual(snapshot_data["collection"]["query_runs"][-1]["outcome"], "completed_with_zero_results")
        self.assertEqual(snapshot_data["collection"]["stop_reason"], "collection_in_progress")

    def test_recovery_queries_can_reopen_legacy_sampling_block(self) -> None:
        plan_data = self.make_standard_query_plan()
        plan_data["queries"].append({
            "id": "legacy-7", "term": "legacy narrow query", "layer": "subject_bridge",
            "url": "https://x.example/search?q=legacy-7",
        })
        state = self.root / "legacy-state.json"
        snapshot = self.root / "legacy-raw.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("legacy-plan.json", plan_data)), "--adapter-status", str(self.make_ready_adapter_status()),
            "--platform", "x", "--mode", "standard",
        )
        state_data = json.loads(state.read_text(encoding="utf-8"))
        state_data["queries"] = [{**query, "status": "completed"} for query in state_data["queries"]]
        state_data["active_query"] = None
        state_data["status"] = "blocked"
        state_data["stop_reason"] = "sampling_contract_unmet:observed_results"
        state.write_text(json.dumps(state_data), encoding="utf-8")
        recovery = self.write("legacy-recovery.json", {"queries": [
            {"id": "legacy-recovery-1", "term": "broader support pain", "layer": "category",
             "url": "https://x.example/search?q=legacy-recovery-1"},
        ]})
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "add-queries", "--state", str(state), "--plan", str(recovery)
        )
        self.assertEqual(action["action"], "start_query")
        self.assertEqual(action["query"]["id"], "legacy-recovery-1")
        self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["status"], "in_progress")

    def test_zero_result_chunk_requires_terminal_reason_and_reports_refuse_in_progress(self) -> None:
        plan = self.write("query-plan-invalid-zero.json", self.make_standard_query_plan())
        state = self.root / "collection-state-invalid-zero.json"
        snapshot = self.root / "raw-signals-invalid-zero.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(plan), "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        raw_artifact = self.root / "invalid-zero.json"
        raw_artifact.write_text("{}", encoding="utf-8")
        invalid = self.write("invalid-zero-chunk.json", {
            "query_id": "query-0", "session_id": "", "can_continue": True,
            "observed_result_keys": [], "signals": [], "detail_open_keys": [],
            "raw_artifact": str(raw_artifact), "stop_reason": "",
        })
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate_dokobot_collection.py"), "record-chunk", "--state", str(state), "--chunk", str(invalid)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("zero-result chunk", completed.stderr + completed.stdout)

        in_progress_raw = {
            "platform": "x",
            "collection": {
                "mode": "standard",
                "query_runs": [{"query_term": "q", "query_layer": "platform_baseline", "observed_result_count": 1}],
                "counts": {"query_count": 1, "observed_result_count": 1},
                "stop_reason": "collection_in_progress",
            },
            "signals": [self.make_signal(1)],
        }
        raw_path = self.write("in-progress-raw.json", in_progress_raw)
        normalized = self.root / "in-progress-normalized.json"
        scored = self.root / "in-progress-scored.json"
        run_script("normalize_signals.py", "--input", str(raw_path), "--output", str(normalized), "--platform", "x", "--source-mode", "controlled_capture")
        run_script("calculate_evidence_index.py", "--input", str(normalized), "--output", str(scored))
        self.assertEqual(json.loads(normalized.read_text(encoding="utf-8"))["collection"]["contract_status"], "in_progress")
        subject = self.write("in-progress-subject.json", {"name": "Idea", "subject_type": "idea", "summary": "Test"})
        report = subprocess.run(
            [sys.executable, str(SCRIPTS / "generate_opportunities.py"), "--subject", str(subject), "--signals", str(scored),
             "--json-output", str(self.root / "no-report.json"), "--markdown-output", str(self.root / "no-report.md")],
            capture_output=True, text=True,
        )
        self.assertNotEqual(report.returncode, 0)
        self.assertIn("still in_progress", report.stderr + report.stdout)

    def test_dokobot_timeout_retries_one_screen_then_continues_next_query(self) -> None:
        state = self.root / "timeout-state.json"
        snapshot = self.root / "timeout-raw.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("timeout-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        for attempt in range(2):
            artifact = self.root / f"timeout-{attempt}.json"
            artifact.write_text("{}", encoding="utf-8")
            chunk = self.write(f"timeout-chunk-{attempt}.json", {
                "query_id": "query-0", "read_status": "timeout", "session_id": "",
                "can_continue": False, "continuation_status": "unknown",
                "observed_result_keys": [], "signals": [], "detail_open_keys": [],
                "raw_artifact": str(artifact), "stop_reason": "",
            })
            action = run_script_json(
                "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(chunk)
            )
            if attempt == 0:
                self.assertEqual(action["action"], "start_query")
                screens_index = action["dokobot_command"].index("--screens")
                self.assertEqual(action["dokobot_command"][screens_index + 1], "1")
        self.assertEqual(action["action"], "start_query")
        self.assertEqual(action["query"]["id"], "query-1")
        state_data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(state_data["status"], "in_progress")
        self.assertEqual(state_data["queries"][0]["completion_status"], "completed_partial")
        snapshot_data = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(snapshot_data["collection"]["query_runs"][0]["stop_reason"], "repeated_timeout")

    def test_under_target_chunk_without_terminal_metadata_is_not_treated_as_exhausted(self) -> None:
        state = self.root / "unknown-continuation-state.json"
        snapshot = self.root / "unknown-continuation-raw.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("unknown-continuation-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        artifact = self.root / "unknown-continuation.json"
        artifact.write_text("{}", encoding="utf-8")
        chunk = self.write("unknown-continuation-chunk.json", {
            "query_id": "query-0", "read_status": "success", "session_id": "",
            "can_continue": False, "continuation_status": "unknown",
            "observed_result_keys": ["only-one"], "signals": [self.make_signal(500)],
            "detail_open_keys": [], "raw_artifact": str(artifact), "stop_reason": "visible_results_exhausted",
        })
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(chunk)
        )
        self.assertEqual(action["query"]["id"], "query-0")
        self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["queries"][0]["status"], "in_progress")
        second_artifact = self.root / "unknown-continuation-2.json"
        second_artifact.write_text("{}", encoding="utf-8")
        second_chunk = self.write("unknown-continuation-chunk-2.json", {
            "query_id": "query-0", "read_status": "success", "session_id": "",
            "can_continue": False, "continuation_status": "unknown",
            "observed_result_keys": ["only-two"], "signals": [self.make_signal(501)],
            "detail_open_keys": [], "raw_artifact": str(second_artifact), "stop_reason": "",
        })
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(second_chunk)
        )
        self.assertEqual(action["query"]["id"], "query-1")
        state_data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(state_data["queries"][0]["completion_status"], "completed_partial")
        self.assertEqual(state_data["queries"][1]["status"], "in_progress")

    def test_existing_results_allow_one_empty_continuation_then_finalize_partial(self) -> None:
        state = self.root / "empty-continuation-state.json"
        snapshot = self.root / "empty-continuation-raw.json"
        first_action = run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("empty-continuation-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        self.assertEqual(first_action["dokobot_command"][first_action["dokobot_command"].index("--screens") + 1], "1")
        first_raw = self.root / "empty-first.json"
        first_raw.write_text("first", encoding="utf-8")
        first = self.write("empty-first-chunk.json", {
            "query_id": "query-0", "read_status": "success", "session_id": "session-1",
            "can_continue": True, "continuation_status": "available",
            "observed_result_keys": ["first-card"], "signals": [self.make_signal(1200)],
            "detail_open_keys": [], "raw_artifact": str(first_raw), "stop_reason": "",
        })
        action = run_script_json("orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(first))
        for attempt in (1, 2):
            empty_raw = self.root / f"empty-{attempt}.json"
            empty_raw.write_text("empty page", encoding="utf-8")
            empty = self.write(f"empty-{attempt}-chunk.json", {
                "query_id": "query-0", "read_status": "success", "session_id": "session-1",
                "can_continue": True, "continuation_status": "available",
                "observed_result_keys": [], "signals": [], "detail_open_keys": [],
                "raw_artifact": str(empty_raw), "stop_reason": "",
            })
            action = run_script_json("orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(empty))
            if attempt == 1:
                self.assertEqual(action["query"]["id"], "query-0")
        self.assertEqual(action["query"]["id"], "query-1")
        state_data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(state_data["queries"][0]["completion_status"], "completed_partial")

    def test_capture_wrapper_parses_session_and_record_capture_prevents_metadata_override(self) -> None:
        state = self.root / "capture-state.json"
        snapshot = self.root / "capture-raw.json"
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("capture-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        raw_artifact = Path(action["raw_output"])
        raw_artifact.parent.mkdir(parents=True, exist_ok=True)
        raw_artifact.write_text("captured page", encoding="utf-8")
        metadata = capture_runner.build_metadata(
            "query-0", action["dokobot_command"], str(raw_artifact),
            "", "Written to page\nSession: 345394716372099073 (use --session-id to continue)\n", 0,
            "2026-08-11T00:00:00Z", "2026-08-11T00:00:01Z",
        )
        stdout_artifact = self.root / "capture-001.stdout.txt"
        stderr_artifact = self.root / "capture-001.stderr.txt"
        metadata_artifact = self.root / "capture-001.capture.json"
        stdout_artifact.write_text("", encoding="utf-8")
        stderr_artifact.write_text("Session: 345394716372099073", encoding="utf-8")
        metadata_artifact.write_text("{}", encoding="utf-8")
        metadata.update({
            "stdout_artifact": str(stdout_artifact),
            "stderr_artifact": str(stderr_artifact),
            "metadata_artifact": str(metadata_artifact),
        })
        metadata_path = self.write("capture-metadata.json", metadata)
        extraction = self.write("capture-extraction.json", {
            "observed_result_keys": [f"capture-{index}" for index in range(10)],
            "signals": [self.make_signal(600 + index) for index in range(10)],
            "detail_open_keys": [],
        })
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "record-capture", "--state", str(state),
            "--metadata", str(metadata_path), "--extraction", str(extraction),
        )
        self.assertEqual(action["query"]["id"], "query-1")
        self.assertEqual(metadata["session_id"], "345394716372099073")
        snapshot_data = json.loads(snapshot.read_text(encoding="utf-8"))
        self.assertEqual(snapshot_data["collection"]["query_runs"][0]["capture_executions"][0]["exit_code"], 0)

        bad_extraction = self.write("bad-capture-extraction.json", {
            "session_id": "forged", "observed_result_keys": [], "signals": [], "detail_open_keys": [],
        })
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate_dokobot_collection.py"), "record-capture", "--state", str(state),
             "--metadata", str(metadata_path), "--extraction", str(bad_extraction)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("cannot override", completed.stderr + completed.stdout)

    def test_windows_dokobot_shim_resolves_to_direct_node_entry(self) -> None:
        shim_root = self.root / "npm"
        entry = shim_root / "node_modules" / "@dokobot" / "cli" / "dist" / "cli" / "bin" / "dokobot.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("// test", encoding="utf-8")
        shim = shim_root / "dokobot.cmd"
        shim.write_text("@echo off", encoding="utf-8")
        node = shim_root / "node.exe"
        node.write_text("test", encoding="utf-8")
        original_which = capture_runner.shutil.which
        try:
            capture_runner.shutil.which = lambda name: str(shim) if name == "dokobot" else None
            command = capture_runner.resolve_execution_command([
                "dokobot", "read", "https://x.example/search?q=a&src=typed_query&f=live", "--local",
            ])
        finally:
            capture_runner.shutil.which = original_which
        self.assertEqual(command[0], str(node))
        self.assertEqual(command[1], str(entry))
        self.assertEqual(command[3], "https://x.example/search?q=a&src=typed_query&f=live")

    def test_windows_dokobot_shim_falls_back_to_appdata_npm(self) -> None:
        appdata = self.root / "AppData" / "Roaming"
        shim_root = appdata / "npm"
        entry = shim_root / "node_modules" / "@dokobot" / "cli" / "dist" / "cli" / "bin" / "dokobot.js"
        entry.parent.mkdir(parents=True)
        entry.write_text("// test", encoding="utf-8")
        shim = shim_root / "dokobot.cmd"
        shim.write_text("@echo off", encoding="utf-8")
        node = shim_root / "node.exe"
        node.write_text("test", encoding="utf-8")
        original_which = capture_runner.shutil.which
        original_appdata_root = capture_runner.windows_appdata_root
        try:
            capture_runner.shutil.which = lambda name: None
            capture_runner.windows_appdata_root = lambda: appdata
            command = capture_runner.resolve_execution_command(["dokobot", "read", "https://example.com"])
        finally:
            capture_runner.shutil.which = original_which
            capture_runner.windows_appdata_root = original_appdata_root
        self.assertEqual(command[:2], [str(node), str(entry)])

    def test_session_expiry_restarts_same_query_without_session_before_partial_failure(self) -> None:
        state = self.root / "session-restart-state.json"
        snapshot = self.root / "session-restart-raw.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("session-restart-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        first_raw = self.root / "session-first.json"
        first_raw.write_text("{}", encoding="utf-8")
        first = self.write("session-first-chunk.json", {
            "query_id": "query-0", "read_status": "success", "session_id": "expired-session",
            "can_continue": True, "continuation_status": "available",
            "observed_result_keys": ["first"], "signals": [self.make_signal(900)],
            "detail_open_keys": [], "raw_artifact": str(first_raw), "stop_reason": "",
        })
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(first)
        )
        self.assertIn("--session-id", action["dokobot_command"])
        failed_raw = self.root / "session-failed-not-created.json"
        expired = self.write("session-expired-chunk.json", {
            "query_id": "query-0", "read_status": "error", "session_id": "",
            "can_continue": False, "continuation_status": "unknown",
            "observed_result_keys": [], "signals": [], "detail_open_keys": [],
            "raw_artifact": str(failed_raw), "stop_reason": "session_expired",
        })
        action = run_script_json(
            "orchestrate_dokobot_collection.py", "record-chunk", "--state", str(state), "--chunk", str(expired)
        )
        self.assertEqual(action["query"]["id"], "query-0")
        self.assertNotIn("--session-id", action["dokobot_command"])
        self.assertEqual(action["dokobot_command"][action["dokobot_command"].index("--screens") + 1], "1")
        state_data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(state_data["active_query"]["session_restart_count"], 1)
        self.assertNotIn(str(failed_raw), state_data["active_query"]["raw_artifacts"])

    def test_capture_execution_paths_are_unique_per_raw_capture(self) -> None:
        metadata = self.root / "capture-metadata.json"
        first = capture_runner.execution_artifact_paths(metadata, self.root / "captures" / "q-001.json")
        second = capture_runner.execution_artifact_paths(metadata, self.root / "captures" / "q-002.json")
        self.assertEqual(len(set(first + second)), 6)
        self.assertTrue(str(first[0]).endswith("q-001.json.capture.json"))

    def test_recovery_plan_rejects_restacked_long_query(self) -> None:
        state = self.root / "wide-recovery-state.json"
        snapshot = self.root / "wide-recovery-raw.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("wide-recovery-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        state_data = json.loads(state.read_text(encoding="utf-8"))
        state_data["queries"] = [{**item, "status": "completed"} for item in state_data["queries"]]
        state_data["active_query"] = None
        state.write_text(json.dumps(state_data), encoding="utf-8")
        plan = self.write("restacked-recovery.json", {"queries": [{
            "id": "too-long", "term": "AI freelance designer client feedback tasks", "layer": "subject_bridge",
            "url": "https://x.example/search?q=too-long",
        }]})
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "orchestrate_dokobot_collection.py"), "add-queries", "--state", str(state), "--plan", str(plan)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("at most four words", completed.stderr + completed.stdout)

    def test_cluster_counter_assignment_is_reflected_in_topic_score(self) -> None:
        members = [self.make_signal(950), self.make_signal(951), self.make_signal(952)]
        for member in members:
            member["signal_id"] = member["id"]
        audit = {
            "status": "passed",
            "assignments": [
                {"signal_id": members[0]["id"], "fit": "counter"},
                {"signal_id": members[1]["id"], "fit": "core"},
                {"signal_id": members[2]["id"], "fit": "core"},
            ],
        }
        score = common.calculate_topic_index(
            members, collection={"contract_status": "met"}, cluster_audit=audit, clustering_applied=True
        )
        self.assertEqual(score["counter_signal_count"], 1)
        self.assertEqual(score["confidence_dimensions"]["counterevidence"], 100.0)

    def test_report_artifact_audit_rejects_missing_and_reused_execution_files(self) -> None:
        existing = self.root / "existing.txt"
        existing.write_text("evidence", encoding="utf-8")
        missing_result = {"collection": {"query_runs": [{"raw_artifacts": [str(self.root / "missing.json")]}]}}
        with self.assertRaises(SystemExit):
            report_validator.validate_collection_artifacts(missing_result, self.root)
        reused = {
            "collection": {"query_runs": [{"raw_artifacts": [str(existing)], "capture_executions": [
                {"stdout_artifact": str(existing), "stderr_artifact": str(existing), "metadata_artifact": str(existing)},
                {"stdout_artifact": str(existing), "stderr_artifact": str(existing), "metadata_artifact": str(existing)},
            ]}]}
        }
        with self.assertRaises(SystemExit):
            report_validator.validate_collection_artifacts(reused, self.root)

    def test_legacy_query_local_block_reopens_remaining_queries(self) -> None:
        state = self.root / "legacy-local-block-state.json"
        snapshot = self.root / "legacy-local-block-raw.json"
        run_script_json(
            "orchestrate_dokobot_collection.py", "init", "--state", str(state), "--snapshot", str(snapshot),
            "--plan", str(self.write("legacy-local-plan.json", self.make_standard_query_plan())),
            "--adapter-status", str(self.make_ready_adapter_status()), "--platform", "x", "--mode", "standard",
        )
        state_data = json.loads(state.read_text(encoding="utf-8"))
        state_data["queries"][0]["status"] = "completed"
        state_data["queries"][0]["completion_status"] = "completed_partial"
        state_data["active_query"] = None
        state_data["status"] = "blocked"
        state_data["stop_reason"] = "continuation_unresolved"
        state.write_text(json.dumps(state_data), encoding="utf-8")
        action = run_script_json("orchestrate_dokobot_collection.py", "next", "--state", str(state))
        self.assertEqual(action["action"], "start_query")
        self.assertEqual(action["query"]["id"], "query-1")
        self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["status"], "in_progress")

    def test_report_generation_rejects_mojibake_subject(self) -> None:
        subject = self.write("mojibake-subject.json", {
            "name": "°ïÖú¶ÀÁ¢¹ËÎÊ", "subject_type": "idea", "summary": "Test",
            "facts": [], "hypotheses": [], "audiences": [], "scenarios": [], "constraints": [], "source_refs": [],
        })
        signals = self.write("mojibake-signals.json", {
            "platform": "x", "collection": {"mode": "quick", "contract_status": "blocked"}, "signals": [], "topics": [],
        })
        completed = subprocess.run(
            [sys.executable, str(SCRIPTS / "generate_opportunities.py"), "--subject", str(subject),
             "--signals", str(signals), "--json-output", str(self.root / "bad.json"),
             "--markdown-output", str(self.root / "bad.md"), "--html-output", str(self.root / "bad.html")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("text integrity", completed.stderr + completed.stdout)

    def test_dokobot_adapter_preflight_distinguishes_ready_and_disconnected(self) -> None:
        probe_kwargs: list[dict[str, object]] = []

        def ready_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            probe_kwargs.append(kwargs)
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, "2.11.0\n", "")
            return subprocess.CompletedProcess(command, 0, "Local:\n  abc pid 1234, Chrome, ext 0.3.1\n", "")

        ready = adapter_check.diagnose_dokobot("dokobot", "test", runner=ready_runner)
        self.assertTrue(ready["ready"])
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["cli"]["version"], "2.11.0")
        self.assertTrue(all(item["encoding"] == "utf-8" for item in probe_kwargs))
        self.assertTrue(all(item["errors"] == "replace" for item in probe_kwargs))

        def disconnected_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            if command[-1] == "--version":
                return subprocess.CompletedProcess(command, 0, "2.11.0\n", "")
            return subprocess.CompletedProcess(command, 0, "Local:\n  No devices connected\n", "")

        disconnected = adapter_check.diagnose_dokobot("dokobot", "test", runner=disconnected_runner)
        self.assertFalse(disconnected["ready"])
        self.assertEqual(disconnected["status"], "browser_not_connected")

    def test_dokobot_adapter_preflight_does_not_confuse_sandbox_visibility_with_absence(self) -> None:
        hidden = adapter_check.diagnose_dokobot(
            "", "unresolved", ["permission_denied:C:\\Users\\example\\AppData\\Roaming\\npm\\dokobot.cmd"]
        )
        self.assertEqual(hidden["status"], "cli_not_visible")
        self.assertIn("standalone", " ".join(hidden["remediation"]))

    def test_opencli_preflight_and_platform_routing_are_capability_bounded(self) -> None:
        observed_timeouts: dict[str, list[int]] = {}

        def ready_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, "1.8.6\n", "")
            capability = "tiktok" if "tiktok" in command else command[1]
            observed_timeouts.setdefault(capability, []).append(int(kwargs["timeout"]))
            return subprocess.CompletedProcess(command, 0, '[{"field":"username","value":"tester"}]\n', "")

        opencli = adapter_check.diagnose_opencli("opencli", "test", runner=ready_runner)
        self.assertTrue(opencli["ready"])
        self.assertTrue(opencli["capabilities"]["xiaohongshu"])
        self.assertTrue(opencli["capabilities"]["x"])
        self.assertTrue(opencli["capabilities"]["youtube"])
        self.assertTrue(opencli["capabilities"]["tiktok"])
        self.assertEqual(opencli["diagnostics"]["identity_probes"]["tiktok"]["probe_type"], "identity_diagnostic_and_bounded_topic_search")
        self.assertEqual(opencli["diagnostics"]["identity_probes"]["tiktok"]["timeout_seconds"], 45)
        self.assertEqual(observed_timeouts["tiktok"], [15, 45])
        self.assertEqual(observed_timeouts["twitter"], [15])
        dokobot = {"adapter": "dokobot", "ready": True, "status": "ready"}
        xhs_route = adapter_selector.select_adapter("小红书", [dokobot, opencli])
        self.assertEqual(xhs_route["selected_adapter"], "opencli")
        x_route = adapter_selector.select_adapter("x", [dokobot, opencli])
        self.assertEqual(x_route["selected_adapter"], "opencli")

    def test_opencli_tiktok_preflight_does_not_confuse_identity_parser_failure_with_search_failure(self) -> None:
        calls: list[list[str]] = []

        def auth_required_runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
            calls.append(command)
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, "1.8.6\n", "")
            if "tiktok" in command and "whoami" in command:
                return subprocess.CompletedProcess(command, 77, "", "AUTH_REQUIRED: no owner user")
            if "tiktok" in command and "search" in command:
                return subprocess.CompletedProcess(command, 0, '[{"url":"https://www.tiktok.com/@tester/video/1"}]\n', "")
            return subprocess.CompletedProcess(command, 0, '[{"field":"username","value":"tester"}]\n', "")

        status = adapter_check.diagnose_opencli("opencli", "test", runner=auth_required_runner)
        tiktok_calls = [command for command in calls if "tiktok" in command]
        self.assertTrue(status["capabilities"]["tiktok"])
        self.assertEqual(len(tiktok_calls), 2)
        self.assertIn("whoami", tiktok_calls[0])
        self.assertIn("search", tiktok_calls[1])
        self.assertFalse(status["diagnostics"]["identity_probes"]["tiktok"]["identity_ok"])
        self.assertTrue(status["diagnostics"]["identity_probes"]["tiktok"]["search_attempted"])

    def test_opencli_x_parser_normalizes_metrics_and_keeps_search_evidence_unreviewed(self) -> None:
        raw = self.write("opencli-x-search.json", [{
            "id": "1234567890", "author": "builder", "text": "A long practical post about AI workflows.",
            "created_at": "2026-08-12T10:00:00Z", "likes": 42, "views": "12.5K",
            "url": "https://x.com/i/status/1234567890",
        }])
        parsed = opencli_x_parser.parse_file(raw, {"id": "q1", "term": "AI workflows", "layer": "category"})
        self.assertEqual(parsed["query_id"], "q1")
        self.assertEqual(parsed["observed_result_keys"], ["1234567890"])
        signal = parsed["signals"][0]
        self.assertEqual(signal["canonical_url"], "https://x.com/builder/status/1234567890")
        self.assertEqual(signal["metrics"]["views"], 12500)
        self.assertEqual(signal["summary"], "A long practical post about AI workflows.")
        self.assertEqual(signal["semantic_relevance"], "unreviewed")

    def test_text_integrity_accepts_valid_accented_languages(self) -> None:
        self.assertEqual(common.text_integrity_issues("ADIÓS, ¿cómo está? Très bien. ação útil."), [])
        self.assertTrue(common.text_integrity_issues("broken \ufffd text"))

    def test_opencli_x_detail_selects_original_thread_row_and_allows_missing_views(self) -> None:
        target = {"url": "https://x.com/builder/status/1234567890"}
        detail = opencli_detail_runner.x_detail([
            {"id": "999", "author": "reply", "text": "reply"},
            {"id": "1234567890", "author": "builder", "text": "complete body", "likes": 5, "retweets": 2},
        ], target)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["summary"], "complete body")
        self.assertIsNone(detail["metrics"]["views"])
        self.assertEqual(detail["metrics"]["shares"], 2)
        self.assertEqual(detail["platform_facts"]["representative_comment_count"], 1)
        self.assertEqual(detail["platform_facts"]["representative_comments"][0]["text"], "reply")

    def test_platform_specific_engagement_weights_are_versioned_and_not_shared(self) -> None:
        x_signal = {"platform": "x", "metrics": {"views": 1000, "comments": 10}}
        xhs_signal = {"platform": "xiaohongshu", "metrics": {"views": 1000, "comments": 10}}
        self.assertEqual(common.engagement_weights("x")["comments"], 2.0)
        self.assertEqual(common.engagement_weights("xiaohongshu")["comments"], 3.0)
        self.assertLess(
            common.signal_dimensions(x_signal)["engagement"],
            common.signal_dimensions(xhs_signal)["engagement"],
        )
        scored = common.calculate_index(x_signal)
        self.assertEqual(scored["engagement_weight_version"], "platform-engagement-weights-v0.1-candidate")
        self.assertEqual(scored["engagement_weights"]["shares"], 3.0)

    def test_opencli_youtube_search_and_detail_preserve_platform_facts(self) -> None:
        raw = self.write("opencli-youtube-search.json", [{
            "rank": 1,
            "title": "AI agents for small business",
            "channel": "Practical AI",
            "views": "56,423次观看",
            "duration": "24:52",
            "published": "5天前",
            "url": "https://www.youtube.com/watch?v=LVAHYV4Xrto",
        }])
        parsed = opencli_youtube_parser.parse_file(raw, {"id": "q1", "term": "AI agents", "layer": "category"})
        self.assertEqual(parsed["observed_result_keys"], ["LVAHYV4Xrto"])
        signal = parsed["signals"][0]
        self.assertEqual(signal["metrics"]["views"], 56423)
        self.assertEqual(signal["author"]["name"], "Practical AI")
        self.assertEqual(signal["platform_facts"]["duration"], "24:52")
        detail = opencli_detail_runner.youtube_detail([
            {"field": "title", "value": "AI agents for small business"},
            {"field": "channel", "value": "Practical AI"},
            {"field": "channelId", "value": "UC123"},
            {"field": "description", "value": "A detailed walkthrough."},
            {"field": "publishDate", "value": "2026-08-11T06:31:57-07:00"},
            {"field": "views", "value": "56423"},
            {"field": "likes", "value": "2000"},
            {"field": "subscribers", "value": "94.3万位订阅者"},
            {"field": "duration", "value": "1492s"},
        ])
        self.assertIsNotNone(detail)
        self.assertEqual(detail["metrics"]["likes"], 2000)
        self.assertEqual(detail["author"]["follower_count"], 943000)
        self.assertEqual(detail["platform_facts"]["duration_seconds"], 1492)
        self.assertNotIn("transcript", detail)

    def test_opencli_safety_stop_classifier_covers_platform_access_failures(self) -> None:
        cases = {
            "captcha challenge": "captcha",
            "429 too many requests": "rate_limit",
            "login_required": "login_expired",
            "403 access denied": "permission_prompt",
            "abnormal redirect loop": "abnormal_redirect",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                stop_reason, hard_stop = collection_capture_runner.classify_opencli_failure(message)
                self.assertEqual(stop_reason, "")
                self.assertEqual(hard_stop, expected)

    def test_opencli_youtube_comments_are_bounded_and_normalized(self) -> None:
        rows = [{
            "author": {"name": f"Viewer {index}"},
            "text": f"Comment {index}",
            "likes": "1.2K" if index == 0 else index,
            "replies": "3" if index == 0 else 0,
            "time": "2 days ago",
        } for index in range(14)]
        comments = opencli_detail_runner.youtube_comments(rows)
        self.assertEqual(len(comments), 10)
        self.assertEqual(comments[0]["author_name"], "Viewer 0")
        self.assertEqual(comments[0]["likes"], 1200)
        self.assertEqual(comments[0]["reply_count"], 3)
        self.assertEqual(comments[0]["observed_time_label"], "2 days ago")

    def test_opencli_xhs_comments_are_bounded_top_level_and_normalized(self) -> None:
        rows = [{
            "author": f"Reader {index}", "text": f"Comment {index}", "likes": "1.2万" if index == 0 else index,
            "time": "昨天", "is_reply": index == 2,
        } for index in range(8)]
        comments = opencli_detail_runner.xhs_comments(rows)
        self.assertEqual(len(comments), 5)
        self.assertEqual(comments[0]["likes"], 12000)
        self.assertNotIn("Comment 2", [item["text"] for item in comments])

    def test_opencli_xhs_comment_capture_preserves_limit_throttle_and_artifacts(self) -> None:
        detail_raw = self.root / "xhs-detail.json"
        target = {"signal_key": "xiaohongshu:abc", "url": "https://www.xiaohongshu.com/explore/abc?xsec_token=signed"}
        original_execute = opencli_detail_runner.execute
        opencli_detail_runner.execute = lambda _requested, _timeout: (
            0, json.dumps([{"author": "Reader", "text": "Useful", "likes": 3, "time": "1小时前"}]), "", False
        )
        throttle = {"request_index": 1, "interval_seconds": 20, "batch_cooldown_seconds": 0, "waited_seconds": 20}
        try:
            result = opencli_detail_runner.capture_xhs_comments(target, detail_raw, 30, throttle)
        finally:
            opencli_detail_runner.execute = original_execute
        self.assertEqual(result["sample_limit"], 5)
        self.assertEqual(result["comments"][0]["text"], "Useful")
        self.assertTrue(all(Path(item).is_file() for item in result["artifacts"]))
        metadata = json.loads(Path(result["metadata_artifact"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["throttle"]["waited_seconds"], 20)

    def test_normalization_preserves_bounded_youtube_platform_facts(self) -> None:
        signal = self.make_signal(1701)
        signal.update({
            "platform": "youtube",
            "platform_facts": {
                "representative_comments": [{"author_name": "Viewer", "text": "Useful", "likes": 2}],
                "representative_comment_count": 1,
                "comment_sample_limit": 10,
                "comment_capture_status": "complete",
            },
        })
        normalized = common.normalize_signal(signal, "youtube", "controlled_capture", self.now.isoformat())
        self.assertEqual(normalized["platform_facts"]["representative_comment_count"], 1)
        self.assertEqual(normalized["platform_facts"]["representative_comments"][0]["text"], "Useful")

    def test_normalization_preserves_author_name_for_platforms_without_search_author_id(self) -> None:
        signal = self.make_signal(1702)
        signal["author"] = {"name": "Practical AI"}
        signal.pop("author_id", None)
        normalized = common.normalize_signal(signal, "youtube", "controlled_capture", self.now.isoformat())
        self.assertEqual(normalized["author"]["name"], "Practical AI")

    def test_opencli_youtube_comment_capture_preserves_artifacts_and_hard_stop(self) -> None:
        detail_raw = self.root / "detail.json"
        target = {"signal_key": "youtube:abc", "url": "https://www.youtube.com/watch?v=abc"}
        original_execute = opencli_detail_runner.execute
        opencli_detail_runner.execute = lambda _requested, _timeout: (
            1, "", "429 too many requests", False
        )
        try:
            result = opencli_detail_runner.capture_youtube_comments(target, detail_raw, 30)
        finally:
            opencli_detail_runner.execute = original_execute
        self.assertEqual(result["hard_stop"], "rate_limit")
        self.assertEqual(result["comments"], [])
        self.assertEqual(len(result["artifacts"]), 4)
        self.assertTrue(all(Path(item).is_file() for item in result["artifacts"]))
        metadata = json.loads(Path(result["metadata_artifact"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["sample_limit"], 10)
        self.assertEqual(metadata["hard_stop"], "rate_limit")

    def test_opencli_xhs_parser_preserves_signed_detail_and_requires_semantic_review(self) -> None:
        raw = self.write("opencli-search.json", [{
            "rank": 1,
            "author": "Researcher",
            "author_url": "https://www.xiaohongshu.com/user/profile/author123?xsec_token=a",
            "likes": "1.3万",
            "title": "AI 工作流真实复盘",
            "url": "https://www.xiaohongshu.com/search_result/note123?xsec_token=signed&xsec_source=pc_search",
            "published_at": "2026-08-10",
        }])
        parsed = opencli_parser.parse_file(raw, {"id": "q1", "term": "AI 工作流", "layer": "category"})
        self.assertEqual(parsed["observed_result_keys"], ["note123"])
        signal = parsed["signals"][0]
        self.assertEqual(signal["metrics"]["likes"], 13000)
        self.assertTrue(signal["detail_access"]["token_present"])
        self.assertEqual(signal["semantic_relevance"], "unreviewed")

    def test_generic_orchestrator_routes_opencli_for_xiaohongshu_and_x(self) -> None:
        status = self.write("opencli-ready.json", {
            "schema_version": "collection-adapter-status-v0.2", "adapter": "opencli",
            "ready": True, "status": "ready", "capabilities": {"xiaohongshu": True, "x": True},
        })
        plan = self.write("xhs-plan.json", self.make_standard_query_plan())
        state = self.root / "xhs-state.json"
        action = run_script_json(
            "orchestrate_collection.py", "init", "--state", str(state), "--snapshot", str(self.root / "raw.json"),
            "--plan", str(plan), "--adapter-status", str(status), "--platform", "小红书", "--mode", "standard",
        )
        self.assertEqual(action["opencli_command"][:3], ["opencli", "xiaohongshu", "search"])
        self.assertNotIn("dokobot_command", action)
        xhs_state = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(xhs_state["platform_adapter_contract"], "platform-adapter-contract-v0.2")
        self.assertEqual(xhs_state["platform_adapter_registry"], "platform-adapter-registry-v0.2")
        x_action = run_script_json(
            "orchestrate_collection.py", "init", "--state", str(self.root / "x-state.json"),
            "--snapshot", str(self.root / "x-raw.json"), "--plan", str(plan), "--adapter-status", str(status),
            "--platform", "x", "--mode", "standard",
        )
        self.assertEqual(x_action["opencli_command"][:3], ["opencli", "twitter", "search"])
        self.assertIn("--product", x_action["opencli_command"])

    def test_standard_contract_rejects_high_volume_layer_without_direct_relevance(self) -> None:
        signals = [self.make_signal(index) for index in range(30)]
        for signal in signals:
            if signal["query_layer"] == "platform_baseline":
                signal["semantic_relevance"] = "adjacent"
        raw = {
            "collection": {
                "mode": "standard", "stop_reason": "sampling_contract_met",
                "query_runs": [{
                    "query_term": f"q-{index}",
                    "query_layer": ["platform_baseline", "category", "subject_bridge"][index % 3],
                    "observed_result_count": 10,
                } for index in range(6)],
                "counts": {"query_count": 6, "observed_result_count": 60, "detail_open_count": 12, "counter_signal_count": 3},
            }
        }
        collection = common.normalize_collection(raw, 30, 30, signals)
        self.assertFalse(collection["contract_checks"]["layer_direct_signals"])
        self.assertEqual(collection["contract_status"], "blocked")

    def test_global_relevant_deficit_produces_recovery_layer_guidance(self) -> None:
        signals = [self.make_signal(index) for index in range(30)]
        for signal in signals[12:]:
            signal["semantic_relevance"] = "weak"
        snapshot = self.write("global-relevance-raw.json", {
            "collection": {"counts": {
                "query_count": 6, "observed_result_count": 60, "unique_sample_count": 30,
                "detail_open_count": 12, "counter_signal_count": 3,
            }, "query_runs": [{
                "query_layer": ["platform_baseline", "category", "subject_bridge"][index % 3],
                "observed_result_count": 10,
            } for index in range(6)]},
            "signals": signals,
        })
        diagnostics = orchestrator.recovery_diagnostics({
            "mode": "standard", "snapshot": str(snapshot), "queries": [{} for _ in range(6)]
        })
        self.assertEqual(diagnostics["global_deficits"]["relevant"], 6)
        self.assertEqual(set(diagnostics["recommended_layers"]), {"platform_baseline", "category", "subject_bridge"})

    def test_volume_only_recovery_uses_terms_derived_from_successful_queries(self) -> None:
        signals = [self.make_signal(index) for index in range(30)]
        for signal in signals[-3:]:
            signal["evidence_role"] = "counter"
        snapshot = self.write("volume-recovery-raw.json", {
            "collection": {
                "counts": {"query_count": 3, "observed_result_count": 56, "unique_sample_count": 30, "detail_open_count": 12, "counter_signal_count": 3},
                "query_runs": [
                    {"query_term": "meeting follow-up", "query_layer": "platform_baseline", "observed_result_count": 18, "relevant_signal_count": 10, "relevant_yield_rate": 0.556},
                    {"query_term": "meeting action items", "query_layer": "category", "observed_result_count": 16, "relevant_signal_count": 11, "relevant_yield_rate": 0.688},
                    {"query_term": "AI meeting notes", "query_layer": "subject_bridge", "observed_result_count": 22, "relevant_signal_count": 9, "relevant_yield_rate": 0.409},
                ],
            },
            "signals": signals,
        })
        state = {"mode": "standard", "snapshot": str(snapshot), "queries": [{"id": f"q-{index}", "term": "seed", "url": f"https://x.test/{index}", "layer": layer, "status": "completed"} for index, layer in enumerate(["platform_baseline", "category", "subject_bridge"])]}
        diagnostics = orchestrator.recovery_diagnostics(state)
        self.assertTrue(diagnostics["volume_recovery"]["required"])
        self.assertIn("action items", diagnostics["volume_recovery"]["recommended_terms"])
        self.assertEqual(diagnostics["recommended_layers"][0], "category")
        rejected = {"queries": [{"id": "r-1", "term": "meeting owner deadline", "layer": "category", "url": "https://x.test/search?q=owner"}]}
        with self.assertRaises(SystemExit):
            orchestrator.validate_recovery_plan(rejected, state)
        accepted = {"queries": [{"id": "r-1", "term": "action items", "layer": "category", "url": "https://x.test/search?q=action-items"}]}
        self.assertEqual(orchestrator.validate_recovery_plan(accepted, state)[0]["term"], "action items")

    def test_volume_recovery_continues_with_shorter_proven_phrases(self) -> None:
        signals = [self.make_signal(index) for index in range(30)]
        for signal in signals[-3:]:
            signal["evidence_role"] = "counter"
        snapshot = self.write("progressive-volume-raw.json", {
            "collection": {
                "counts": {"query_count": 4, "observed_result_count": 50, "unique_sample_count": 30, "detail_open_count": 12, "counter_signal_count": 3},
                "query_runs": [
                    {"query_term": "food waste fridge", "query_layer": "platform_baseline", "observed_result_count": 20, "relevant_signal_count": 10},
                    {"query_term": "forgot food fridge", "query_layer": "category", "observed_result_count": 12, "relevant_signal_count": 6},
                    {"query_term": "fridge inventory app", "query_layer": "subject_bridge", "observed_result_count": 9, "relevant_signal_count": 7},
                    {"query_term": "fridge inventory", "query_layer": "platform_baseline", "observed_result_count": 9, "relevant_signal_count": 7},
                ],
            },
            "signals": signals,
        })
        state = {"mode": "standard", "snapshot": str(snapshot), "queries": [
            {"id": f"q-{index}", "term": f"seed-{index}", "url": f"https://x.test/{index}", "layer": layer}
            for index, layer in enumerate(("platform_baseline", "category", "subject_bridge", "subject_bridge"))
        ]}
        diagnostics = orchestrator.recovery_diagnostics(state)
        self.assertTrue(diagnostics["volume_recovery"]["required"])
        self.assertIn("food waste", diagnostics["volume_recovery"]["recommended_terms"])
        with self.assertRaises(SystemExit):
            orchestrator.validate_recovery_plan({"queries": [{
                "id": "invented", "term": "forgotten fridge food", "layer": "category", "url": "https://x.test/invented",
            }]}, state)

    def test_volume_recovery_derives_contiguous_chinese_phrase(self) -> None:
        signals = [self.make_signal(index) for index in range(30)]
        for signal in signals[-3:]:
            signal["evidence_role"] = "counter"
        snapshot = self.write("chinese-volume-recovery.json", {
            "collection": {
                "counts": {"query_count": 3, "observed_result_count": 57, "unique_sample_count": 30, "detail_open_count": 12, "counter_signal_count": 3},
                "query_runs": [
                    {"query_term": "AI自动剪视频", "query_layer": "subject_bridge", "observed_result_count": 19, "relevant_signal_count": 19},
                    {"query_term": "AI做视频", "query_layer": "platform_baseline", "observed_result_count": 19, "relevant_signal_count": 15},
                    {"query_term": "手机素材剪辑", "query_layer": "category", "observed_result_count": 19, "relevant_signal_count": 14},
                ],
            },
            "signals": signals,
        })
        state = {
            "mode": "standard", "platform": "xiaohongshu", "snapshot": str(snapshot),
            "queries": [
                {"id": "q1", "term": "AI自动剪视频", "url": "https://xhs.test/1", "layer": "subject_bridge", "status": "completed"},
                {"id": "q2", "term": "AI做视频", "url": "https://xhs.test/2", "layer": "platform_baseline", "status": "completed"},
                {"id": "q3", "term": "手机素材剪辑", "url": "https://xhs.test/3", "layer": "category", "status": "completed"},
            ],
        }
        diagnostics = orchestrator.recovery_diagnostics(state)
        self.assertTrue(diagnostics["volume_recovery"]["required"])
        self.assertIn("自动剪视频", diagnostics["volume_recovery"]["recommended_terms"])
        state.update({
            "status": "blocked",
            "stop_reason": "sampling_contract_unmet:observed_results,evidence_recovery_exhausted",
            "capture_dir": str(self.root / "captures"),
        })
        resumed = orchestrator.action(state)
        self.assertEqual(resumed["action"], "replan_queries")
        self.assertEqual(state["status"], "in_progress")

    def test_zero_result_query_is_low_yield(self) -> None:
        state = {"active_query": {
            "id": "zero", "term": "empty phrase", "layer": "category", "url": "https://x.test/zero",
            "observed_result_keys": [], "signals": [], "detail_open_keys": [], "raw_artifacts": [],
            "capture_executions": [], "stop_reason": "zero_results",
        }, "snapshot": str(self.root / "zero-raw.json"), "platform": "x", "mode": "standard", "queries": [
            {"id": "zero", "term": "empty phrase", "layer": "category", "url": "https://x.test/zero", "status": "in_progress"}
        ], "status": "in_progress", "stop_reason": "", "updated_at": ""}
        orchestrator.finalize_active(state, self.root / "zero-state.json", "zero_results")
        run = json.loads((self.root / ".trend-collection" / "query-zero.json").read_text(encoding="utf-8"))
        self.assertTrue(run["low_yield"])

    def test_report_validator_rejects_mojibake_collection_state_paths(self) -> None:
        self.write("collection-state.json", {"status": "blocked", "stop_reason": "", "snapshot": "C:/Documents/鏂囨梾鍏ㄩ摼璺惀閿€涓績/raw.json"})
        with self.assertRaises(SystemExit):
            report_validator.validate_collection_state_consistency({"collection": {"contract_status": "blocked"}}, self.root)

    def test_visual_qa_receipt_must_match_html_and_loopback(self) -> None:
        html_path = self.root / "report.html"
        html_path.write_text("<html>ok</html>", encoding="utf-8")
        digest = __import__("hashlib").sha256(html_path.read_bytes()).hexdigest()
        receipt = self.write("html-visual-qa.json", {
            "status": "passed", "url": "http://127.0.0.1:8765/report.html", "html_sha256": digest,
            "checks": {"subject_visible": True, "first_screen_readable": True, "evidence_sections_readable": True, "console_error_count": 0},
        })
        report_validator.validate_visual_qa(str(receipt), html_path)
        bad = self.write("bad-html-visual-qa.json", {
            "status": "passed", "url": "file:///report.html", "html_sha256": digest,
            "checks": {"subject_visible": True, "first_screen_readable": True, "evidence_sections_readable": True, "console_error_count": 0},
        })
        with self.assertRaises(SystemExit):
            report_validator.validate_visual_qa(str(bad), html_path)

    def test_dokobot_x_detail_parser_preserves_rendered_post_and_audit_refs(self) -> None:
        raw = self.root / "detail.txt"
        metadata = self.root / "detail.capture.json"
        stdout = self.root / "detail.stdout.txt"
        stderr = self.root / "detail.stderr.txt"
        text = """# X
> https://x.com/example/status/2031659089902649607
**Example Person [1]**
@example [1]
---
Teams are using customer feedback to prioritize the next product experiment.
---
5:10 PM · Mar 11, 2026 [2]·60 Views
---
2 Replies 7 Likes
"""
        parsed = detail_runner.parse_x_detail(text, "https://x.com/example/status/2031659089902649607", raw, metadata, stdout, stderr)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["content_id"], "2031659089902649607")
        self.assertEqual(parsed["author"]["handle"], "@example")
        self.assertEqual(parsed["metrics"]["likes"], 7)
        self.assertIn("customer feedback", parsed["summary"])

    def test_successful_detail_audit_without_execution_evidence_is_rejected(self) -> None:
        raw = self.root / "detail.json"
        raw.write_text("{}", encoding="utf-8")
        result = {"collection": {"detail_backfills": [{"success": True, "raw_artifact": str(raw)}]}}
        with self.assertRaises(SystemExit):
            report_validator.validate_collection_artifacts(result, self.root)
        normalized = common.normalize_collection({"collection": {
            "mode": "quick", "query_runs": [{"observed_result_count": 1}],
            "detail_backfills": result["collection"]["detail_backfills"],
        }}, 0, 0, [])
        self.assertEqual(len(normalized["detail_backfills"]), 1)

    def test_chinese_markdown_uses_reader_language_and_non_ranking_boundary(self) -> None:
        subject = {"name": "客户反馈优先级", "subject_type": "idea", "summary": "研究如何选择下一项产品实验", "communication": {"language": "zh-CN"}}
        result = {
            "generated_at": self.now.isoformat(), "subject": subject, "platform": "x",
            "collection": {"contract_status": "met", "mode": "standard", "counts": {}},
            "topics": [{
                "title": "Source title", "cluster_audit": {"title": "把反馈整理成产品决定"}, "status": "snapshot",
                "observed_heat": 30, "evidence_confidence": 80, "data_coverage": 50, "sample_count": 5,
                "unique_author_count": 4, "direct_source_count": 2, "counter_signal_count": 1,
                "missing_fields": ["velocity", "search_demand"],
            }], "excluded_topics": [], "opportunities": [], "excluded_opportunities": [],
            "limitation_summary": [], "monitoring_recommendation": {},
        }
        markdown = opportunity_generator.render_markdown(result)
        self.assertIn("## 一分钟结论", markdown)
        self.assertNotIn("## One-minute conclusion", markdown)
        self.assertIn("研究模式：标准研究", markdown)
        self.assertIn("主题类型：想法", markdown)
        self.assertIn("### 把反馈整理成产品决定", markdown)
        self.assertNotIn("尚未覆盖的趋势维度", markdown)
        decision = opportunity_generator.build_decision_support(subject, result["collection"], [], [{"evidence_status": "review_ready"}], "zh-CN")
        self.assertIn("选择下一步验证实验", decision["headline"])
        self.assertIn("不用于给机会排序", decision["headline"])


if __name__ == "__main__":
    unittest.main()
