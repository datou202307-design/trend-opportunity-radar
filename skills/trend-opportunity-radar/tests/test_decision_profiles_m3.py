from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import apply_semantic_review
import decision_profiles
import generate_profile_report
import profile_decisions
import research_context
from orchestrate_dokobot_collection import validate_plan


class DecisionProfilesM3Test(unittest.TestCase):
    def context(self, intent: str) -> dict:
        return research_context.compile_context(
            "研究一个清晰主题。", intent=intent, platform="x", language="zh-CN",
            subject={"name": "测试主题", "subject_type": "idea", "summary": "跨模式测试"},
        )

    def test_reddit_platform_is_inferred_from_a_clear_chinese_request(self) -> None:
        context = research_context.compile_context(
            "分析面向忙碌家庭的 AI 膳食规划工具在 Reddit 英语社区的产品需求。",
            subject={"name": "AI 家庭膳食规划", "subject_type": "idea", "summary": "产品需求测试"},
        )
        self.assertEqual(context["status"], "ready")
        self.assertEqual(context["platform"], "reddit")
        self.assertEqual(context["research_intent"], "product_demand")

    def finding(self, context: dict, *, temporal_claim: str = "current_snapshot", snapshots: int = 1) -> dict:
        required_sections = context["report_sections"]
        action_fields = context["action_contract"]["required_fields"]
        action = {field: "用户可理解的测试值" for field in action_fields}
        return {
            "schema_version": profile_decisions.SCHEMA_VERSION,
            "research_intent": context["research_intent"],
            "profile_version": context["profile_version"],
            "findings": [{
                "id": "finding-1", "title": "用户可理解的发现", "topic_key": "topic-1",
                "analysis_unit_statement": "一个明确的分析单位", "decision_summary": "先做一次低风险验证。",
                "audience": "目标用户", "profile_evidence_roles": context["evidence_roles"][:2],
                "support_refs": ["https://x.example/1", "https://x.example/2"],
                "counter_refs": [], "counter_search_status": "searched_none_found", "direct_source_present": True,
                "conclusion_status": "review_ready", "evidence_boundary": "不代表市场规模或长期变化。",
                "temporal_claim": temporal_claim, "compatible_snapshot_count": snapshots,
                "recommended_actions": [action],
                "report_sections": {section: f"content for {section}" for section in required_sections},
            }],
        }

    def test_all_five_profiles_are_executable_and_complete(self) -> None:
        registry = decision_profiles.load_registry()
        self.assertEqual(registry["schema_version"], "decision-profile-registry-v0.2")
        self.assertTrue(all(item["implementation_status"] == "available" for item in registry["profiles"].values()))
        for intent in sorted(decision_profiles.INTENTS):
            with self.subTest(intent=intent):
                context = self.context(intent)
                research_context.validate_context(context)
                self.assertTrue(context["query_intents"])
                self.assertTrue(context["decision_thresholds"])
                self.assertTrue(context["action_contract"]["required_fields"])
                self.assertTrue(context["report_sections"])
                self.assertEqual(profile_decisions.validate_findings(self.finding(context), context, topic_keys={"topic-1"}), [])

    def test_non_default_query_plan_requires_allowed_profile_intents(self) -> None:
        context = self.context("content_opportunity")
        base = [
            {"id": "b1", "term": "audience question", "layer": "platform_baseline", "url": "https://x.com/a"},
            {"id": "c1", "term": "common mistakes", "layer": "category", "url": "https://x.com/b"},
            {"id": "s1", "term": "topic guide", "layer": "subject_bridge", "url": "https://x.com/c"},
        ]
        with self.assertRaises(SystemExit):
            validate_plan({"queries": base}, "standard", context)
        valid = [{**item, "query_intent": intent} for item, intent in zip(base, ("question", "misconception", "content_supply"))]
        self.assertEqual(len(validate_plan({"queries": valid}, "standard", context)), 3)
        valid[0]["query_intent"] = "complaint"
        with self.assertRaises(SystemExit):
            validate_plan({"queries": valid}, "standard", context)

    def test_semantic_review_preserves_kernel_polarity_and_adds_profile_role(self) -> None:
        context = self.context("competitor_users")
        extraction = {"signals": [{"content_id": "1", "semantic_relevance": "unreviewed", "evidence_role": "neutral", "topic_key": "unreviewed"}]}
        reviewed = apply_semantic_review.apply_review(extraction, {"reviews": [{
            "content_id": "1", "semantic_relevance": "direct", "evidence_role": "support",
            "profile_evidence_role": "switch_trigger", "topic_key": "migration-friction", "reason": "Describes why a user switched.",
        }]}, context)
        self.assertEqual(reviewed["signals"][0]["evidence_role"], "support")
        self.assertEqual(reviewed["signals"][0]["profile_evidence_role"], "switch_trigger")
        with self.assertRaises(SystemExit):
            apply_semantic_review.apply_review({"signals": [{"content_id": "2"}]}, {"reviews": [{
                "content_id": "2", "semantic_relevance": "direct", "evidence_role": "support",
                "profile_evidence_role": "unmet_need", "topic_key": "wrong-role", "reason": "Wrong profile role.",
            }]}, context)

    def test_brand_single_snapshot_cannot_claim_spread(self) -> None:
        context = self.context("brand_sentiment")
        errors = profile_decisions.validate_findings(self.finding(context, temporal_claim="spreading", snapshots=1), context, topic_keys={"topic-1"})
        self.assertTrue(any("single snapshot" in item for item in errors))
        self.assertEqual(profile_decisions.validate_findings(self.finding(context, temporal_claim="spreading", snapshots=2), context, topic_keys={"topic-1"}), [])

    def test_report_data_changes_with_selected_profile(self) -> None:
        snapshot = {"platform": "x", "collection": {"contract_status": "met"}, "topics": [{"topic_key": "topic-1", "cluster_audit": {"status": "passed"}}]}
        outputs = {}
        for intent in ("brand_sentiment", "product_demand"):
            context = self.context(intent)
            report = generate_profile_report.build_report(context, snapshot, self.finding(context))
            outputs[intent] = report
            self.assertEqual(report["research_context"]["report_sections"], context["report_sections"])
        self.assertNotEqual(outputs["brand_sentiment"]["research_context"]["report_sections"], outputs["product_demand"]["research_context"]["report_sections"])
        self.assertNotEqual(outputs["brand_sentiment"]["audit"]["profile_evidence_roles"], outputs["product_demand"]["audit"]["profile_evidence_roles"])

    def test_report_uses_short_profile_answer_instead_of_repeating_long_summary(self) -> None:
        context = self.context("brand_sentiment")
        payload = self.finding(context)
        payload["findings"][0]["decision_summary"] = "这是用于卡片内部解释依据的较长摘要。"
        payload["findings"][0]["report_sections"]["decision_answer"] = "先处理可复现问题。"
        snapshot = {"platform": "x", "collection": {"contract_status": "met"}, "topics": [{
            "topic_key": "topic-1", "cluster_audit": {"status": "passed"},
        }]}
        report = generate_profile_report.build_report(context, snapshot, payload)
        self.assertEqual(report["decision_answer"], "先处理可复现问题。")
        self.assertEqual(report["findings"][0]["decision_summary"], "这是用于卡片内部解释依据的较长摘要。")

    def test_report_rejects_answer_that_repeats_first_card(self) -> None:
        context = self.context("business_opportunity")
        payload = self.finding(context)
        repeated = "这是一个足够长的用户可见结论，它只是把第一张卡片的摘要原样重复了一遍，并没有提供更直接的决策答案。"
        payload["findings"][0]["decision_summary"] = repeated
        payload["findings"][0]["report_sections"]["decision_answer"] = repeated
        snapshot = {"platform": "x", "collection": {"contract_status": "met"}, "topics": [{
            "topic_key": "topic-1", "cluster_audit": {"status": "passed"},
        }]}
        with self.assertRaises(SystemExit):
            generate_profile_report.build_report(context, snapshot, payload)

    def test_profile_report_preserves_failed_and_unused_topics_for_audit(self) -> None:
        context = self.context("product_demand")
        snapshot = {"platform": "x", "collection": {"contract_status": "met"}, "topics": [
            {"topic_key": "topic-1", "title": "Selected", "cluster_audit": {"status": "passed"}},
            {"topic_key": "topic-2", "title": "Eligible but unused", "cluster_audit": {"status": "passed"}},
            {"topic_key": "topic-3", "title": "Keyword collision", "cluster_audit": {
                "status": "failed", "checks": {"member_count": False, "direct_source": False, "author_diversity": True},
            }},
        ]}
        report = generate_profile_report.build_report(context, snapshot, self.finding(context))
        self.assertEqual(report["audit"]["unused_eligible_topics"], ["topic-2"])
        self.assertEqual(report["excluded_topics"], [{
            "topic_key": "topic-3", "title": "Keyword collision", "exclusion_reason": "cluster_audit_failed",
            "failed_gates": ["direct_source", "member_count"],
        }])

    def test_visible_report_sections_remove_semantic_duplicates_without_changing_audit_data(self) -> None:
        brand = self.context("brand_sentiment")
        visible = generate_profile_report.visible_report_sections(
            brand["research_intent"], brand["report_sections"]
        )
        self.assertNotIn("decision_answer", visible)
        self.assertNotIn("evidence_boundary", visible)
        self.assertNotIn("affected_audience", visible)
        self.assertIn("issue_priority", visible)

        business = self.context("business_opportunity")
        business_visible = generate_profile_report.visible_report_sections(
            business["research_intent"], business["report_sections"]
        )
        self.assertNotIn("decision_answer", business_visible)
        self.assertNotIn("evidence_boundary", business_visible)
        self.assertIn("audience_and_task", business_visible)

        payload = self.finding(brand)
        snapshot = {"platform": "x", "collection": {"contract_status": "met"}, "topics": [{
            "topic_key": "topic-1", "cluster_audit": {"status": "passed"},
        }]}
        report = generate_profile_report.build_report(brand, snapshot, payload)
        self.assertIn("decision_answer", report["findings"][0]["report_sections"])
        self.assertIn("evidence_boundary", report["findings"][0]["report_sections"])
        self.assertIn("affected_audience", report["findings"][0]["report_sections"])

    def test_m4_visual_contract_changes_labels_and_exposes_follow_up_without_creating_it(self) -> None:
        snapshot = {"platform": "x", "collection": {"contract_status": "met", "stop_reason": "sampling_contract_met", "counts": {
            "query_count": 4, "observed_result_count": 77, "unique_sample_count": 73,
            "detail_open_count": 12, "counter_signal_count": 21,
        }}, "signals": [
            {"semantic_relevance": "direct", "evidence_role": "support"},
            {"semantic_relevance": "adjacent", "evidence_role": "counter"},
            {"semantic_relevance": "weak", "evidence_role": "neutral"},
        ], "topics": [{
            "topic_key": "topic-1", "cluster_audit": {"status": "passed"},
            "observed_heat": 32, "evidence_confidence": 54,
        }]}
        pages = {}
        for intent in ("brand_sentiment", "competitor_users", "content_opportunity", "product_demand", "business_opportunity"):
            context = self.context(intent)
            report = generate_profile_report.build_report(context, snapshot, self.finding(context))
            page = generate_profile_report.render_html(report)
            pages[intent] = page
            ui = generate_profile_report.PROFILE_UI[intent]["zh-CN"]
            self.assertIn(ui["question"], page)
            self.assertIn('id="raw"', page)
            self.assertIn("平台讨论强度 32/100", page)
            self.assertIn("这项判断的可靠度 54/100", page)
            self.assertIn("较弱", page)
            self.assertIn("中等", page)
            self.assertIn("本次研究基础", page)
            self.assertIn("本轮通过 4 个搜索主题，在 X 观察到 77 条可见结果", page)
            self.assertIn("其中 2 条与研究主题相关", page)
            self.assertIn("打开并核验 0 条详情", page)
            self.assertIn("检查 1 条不同意见或相反情况", page)
            self.assertIn("标准采样已完成", page)
            self.assertEqual(report["schema_version"], "profile-research-report-v0.3")
            self.assertEqual(report["collection_summary"], {
                "query_count": 4, "observed_result_count": 77, "unique_signal_count": 3,
                "relevant_signal_count": 2, "detail_open_count": 0,
                "counter_signal_count": 1, "sampling_status": "complete",
            })
            self.assertEqual(report["findings"][0]["score_summary"], {"observed_heat": 32, "evidence_confidence": 54})
            self.assertFalse(report["follow_up_recommendation"]["created"])
            self.assertTrue(report["follow_up_recommendation"]["requires_explicit_confirmation"])
            self.assertIn("intensity", report["findings"][0]["recommended_actions"][0])
            visible_page = page.split('<pre id="raw">', 1)[0]
            for raw_key in ("success_metric", "validation_metric", "audience_response_metric", "response_level", "target_segment", "stop_condition", "human_boundary"):
                self.assertNotIn(f"<dt>{raw_key}</dt>", visible_page)
            markdown = generate_profile_report.render_markdown(report)
            self.assertIn(ui["question"], markdown)
            self.assertIn("## 本次研究基础", markdown)
            self.assertIn("支持依据 1", markdown)
            action_keys = report["findings"][0]["recommended_actions"][0]
            for key in action_keys:
                if key not in {"action", "intensity", "condition"}:
                    self.assertIn(generate_profile_report.ACTION_FIELD_LABELS["zh-CN"][key], markdown)
        self.assertIn("当前需要关注的议题", pages["brand_sentiment"])
        self.assertIn("用户留下或切换的原因", pages["competitor_users"])
        self.assertIn("值得回应的受众问题", pages["content_opportunity"])
        self.assertIn("需要验证的真实任务", pages["product_demand"])
        self.assertNotEqual(pages["brand_sentiment"], pages["business_opportunity"])

    def test_collection_summary_uses_plain_bounded_snapshot_language(self) -> None:
        context = self.context("business_opportunity")
        context["platform"] = "xiaohongshu"
        snapshot = {"platform": "xiaohongshu", "collection": {"contract_status": "blocked", "counts": {
            "query_count": 3, "observed_result_count": 48, "unique_sample_count": 31,
            "detail_open_count": 8, "counter_signal_count": 3,
        }}, "topics": [{"topic_key": "topic-1", "cluster_audit": {"status": "passed"}}]}
        report = generate_profile_report.build_report(context, snapshot, self.finding(context))
        visible_page = generate_profile_report.render_html(report).split('<pre id="raw">', 1)[0]
        self.assertIn("在小红书观察到", visible_page)
        self.assertIn("本轮为有限快照", visible_page)
        self.assertNotIn("blocked", visible_page)

    def test_collection_summary_is_localized_in_english(self) -> None:
        context = research_context.compile_context(
            "Find a business opportunity in a clear topic.", intent="business_opportunity",
            platform="x", language="en",
            subject={"name": "Test topic", "subject_type": "idea", "summary": "English report test"},
        )
        snapshot = {"platform": "x", "collection": {"contract_status": "met", "stop_reason": "sampling_contract_met", "counts": {
            "query_count": 4, "observed_result_count": 72, "unique_sample_count": 60,
            "detail_open_count": 12, "counter_signal_count": 5,
        }}, "topics": [{"topic_key": "topic-1", "cluster_audit": {"status": "passed"}}]}
        report = generate_profile_report.build_report(context, snapshot, self.finding(context))
        page = generate_profile_report.render_html(report)
        self.assertIn("Research basis", page)
        self.assertIn("This run used 4 search themes and observed 72 visible results on X", page)
        self.assertIn("60 remained after deduplication", page)
        self.assertIn("12 detail pages were opened and verified", page)
        self.assertIn("The standard sampling requirement was met", page)

    def test_profile_report_never_invents_scores_when_topic_scores_are_missing(self) -> None:
        context = self.context("business_opportunity")
        snapshot = {"platform": "x", "collection": {"contract_status": "met"}, "topics": [{
            "topic_key": "topic-1", "cluster_audit": {"status": "passed"},
        }]}
        report = generate_profile_report.build_report(context, snapshot, self.finding(context))
        self.assertNotIn("score_summary", report["findings"][0])
        self.assertNotIn("平台讨论强度", generate_profile_report.render_html(report))

    def test_chinese_report_rejects_known_reader_facing_jargon(self) -> None:
        context = self.context("business_opportunity")
        payload = self.finding(context)
        payload["findings"][0]["decision_summary"] = "把跨来源整理作为入口，形成一条任务链。"
        snapshot = {"platform": "x", "collection": {"contract_status": "met"}, "topics": [{
            "topic_key": "topic-1", "cluster_audit": {"status": "passed"},
        }]}
        with self.assertRaisesRegex(SystemExit, "plain language"):
            generate_profile_report.build_report(context, snapshot, payload)

    def test_report_shows_only_reviewed_video_additions_in_plain_language(self) -> None:
        context = self.context("business_opportunity")
        snapshot = {
            "platform": "x",
            "collection": {"contract_status": "met", "stop_reason": "sampling_contract_met"},
            "video_evidence": {"semantic_review_status": "complete", "reviewed_count": 1, "relevant_reviewed_count": 1},
            "signals": [{
                "topic_key": "topic-1", "canonical_url": "https://x.example/video-1",
                "semantic_relevance": "direct", "evidence_role": "support",
                "content_evidence": {
                    "transcript": {"provenance": "asr", "segments": [{"text": "raw machine transcript"}]},
                    "visual_text": {"provenance": "ocr", "rows": [{"text": "raw OCR row"}]},
                    "semantic_review": {
                        "status": "reviewed", "content_format": "video", "usable_channels": ["asr", "ocr"],
                        "summary": "视频说明用户先完成三步设置。", "relevant_excerpt_count": 2,
                        "excerpts": [
                            {"channel": "asr", "text": "先完成一次最小测试", "semantic_relevance": "direct", "evidence_role": "support"},
                            {"channel": "ocr", "text": "三步设置", "semantic_relevance": "direct", "evidence_role": "support"},
                        ],
                    },
                },
            }],
            "topics": [{"topic_key": "topic-1", "cluster_audit": {"status": "passed"}}],
        }
        report = generate_profile_report.build_report(context, snapshot, self.finding(context))
        page = generate_profile_report.render_html(report)
        visible = page.split('<pre id="raw">', 1)[0]
        markdown = generate_profile_report.render_markdown(report)
        self.assertIn("核验 1 条视频内容", visible)
        self.assertIn("视频核验发现", visible)
        self.assertIn("视频说明用户先完成三步设置。", visible)
        self.assertIn("查看原始字幕或画面文字", visible)
        self.assertIn("语音转写（机器提取）", visible)
        self.assertIn("画面文字（机器提取）", markdown)
        self.assertIn("先完成一次最小测试", visible)
        self.assertLess(visible.index("视频说明用户先完成三步设置。"), visible.index("先完成一次最小测试"))
        self.assertNotIn("raw machine transcript", visible)
        self.assertNotIn("raw OCR row", visible)
        self.assertEqual(report["collection_summary"]["reviewed_video_count"], 1)
        self.assertEqual(report["collection_summary"]["relevant_video_count"], 1)


if __name__ == "__main__":
    unittest.main()
