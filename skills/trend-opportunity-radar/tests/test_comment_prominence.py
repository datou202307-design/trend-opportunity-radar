from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import apply_comment_review
import comment_prominence
import derive_comment_demand_topics
import generate_profile_report
import prepare_comment_review


class CommentProminenceTest(unittest.TestCase):
    def test_comment_topic_requires_cross_post_recurrence_not_one_popular_comment(self) -> None:
        rows = [
            {"comment_key": "c1", "signal_key": "p1", "commenter_key": "u1", "source_url": "https://example.com/1", "demand_topic_key": "manual-handoff", "category": "pain", "semantic_relevance": "direct", "evidence_role": "support", "insight": "Manual handoff causes delays.", "prominence": {"tier": "high"}, "query_layers": ["category"]},
            {"comment_key": "c2", "signal_key": "p2", "commenter_key": "u2", "source_url": "https://example.com/2", "demand_topic_key": "manual-handoff", "category": "need", "semantic_relevance": "direct", "evidence_role": "support", "insight": "Users want handoffs to retain context.", "prominence": {"tier": "low"}, "query_layers": ["subject_bridge"]},
            {"comment_key": "c3", "signal_key": "p3", "commenter_key": "u3", "source_url": "https://example.com/3", "demand_topic_key": "one-thread", "category": "objection", "semantic_relevance": "direct", "evidence_role": "counter", "insight": "One objection attracted discussion.", "prominence": {"tier": "high"}, "query_layers": ["category"]},
        ]
        topics = {item["topic_key"]: item for item in derive_comment_demand_topics.derive(rows)}
        self.assertEqual(topics["manual-handoff"]["status"], "eligible_comment_demand")
        self.assertEqual(topics["manual-handoff"]["independent_parent_count"], 2)
        self.assertEqual(topics["one-thread"]["status"], "salient_single_thread")
        self.assertFalse(topics["one-thread"]["qualification"]["passed"])

    def test_cross_post_recurrence_without_commenter_identity_is_not_qualified_demand(self) -> None:
        common = {"demand_topic_key": "missing-export", "category": "need", "semantic_relevance": "direct", "evidence_role": "support", "prominence": {"tier": "medium"}}
        topics = derive_comment_demand_topics.derive([
            {**common, "comment_key": "c1", "signal_key": "p1", "insight": "Users need an export."},
            {**common, "comment_key": "c2", "signal_key": "p2", "insight": "Export remains missing."},
        ])
        self.assertEqual(topics[0]["status"], "cross_post_recurrence_unverified_commenters")
        self.assertEqual(topics[0]["independent_commenter_count"], 0)
        self.assertEqual(topics[0]["independent_comment_record_count"], 2)

    def test_legacy_review_remains_replayable_without_demand_topics(self) -> None:
        snapshot = {"platform": "x", "signals": [{"signal_id": "s1", "platform_facts": {"representative_comments": [{"text": "Need this", "likes": 5}]}}]}
        queue = prepare_comment_review.build_queue(snapshot)
        review = {"schema_version": apply_comment_review.LEGACY_SCHEMA_VERSION, "queue_sha256": queue["queue_sha256"], "reviews": [
            {"comment_key": queue["comments"][0]["comment_key"], "category": "need", "semantic_relevance": "direct", "evidence_role": "support", "insight": "A need is stated.", "reason": "Visible text."}
        ]}
        result = apply_comment_review.apply(snapshot, queue, review)
        self.assertEqual(result["comment_demand_topics"], [])

    def test_current_review_requires_topic_key_for_relevant_comment(self) -> None:
        snapshot = {"platform": "x", "signals": [{"signal_id": "s1", "platform_facts": {"representative_comments": [{"text": "Need this"}]}}]}
        queue = prepare_comment_review.build_queue(snapshot)
        review = {"schema_version": apply_comment_review.SCHEMA_VERSION, "queue_sha256": queue["queue_sha256"], "reviews": [
            {"comment_key": queue["comments"][0]["comment_key"], "category": "need", "semantic_relevance": "direct", "evidence_role": "support", "insight": "A need is stated.", "reason": "Visible text."}
        ]}
        with self.assertRaises(SystemExit):
            apply_comment_review.apply(snapshot, queue, review)

    def test_likes_and_replies_create_bounded_within_detail_prominence(self) -> None:
        rows = comment_prominence.annotate_comments([
            {"text": "Popular reaction", "likes": 100, "reply_count": 0},
            {"text": "Deep discussion", "likes": 1, "reply_count": 20},
            {"text": "Metrics unavailable"},
        ])
        self.assertEqual(max(row["prominence"]["score"] for row in rows), 100)
        self.assertGreater(rows[1]["prominence"]["score"], 0)
        self.assertEqual(rows[2]["prominence"]["tier"], "unmeasured")
        self.assertEqual(rows[0]["prominence"]["meaning"], "platform_visibility_not_credibility")

    def test_counter_and_neutral_views_survive_more_popular_support(self) -> None:
        rows = [
            {"comment_key": "support-high", "semantic_relevance": "direct", "evidence_role": "support", "category": "need", "insight": "Popular need", "prominence": {"score": 100}},
            {"comment_key": "support-next", "semantic_relevance": "direct", "evidence_role": "support", "category": "pain", "insight": "Another popular need", "prominence": {"score": 90}},
            {"comment_key": "counter-low", "semantic_relevance": "direct", "evidence_role": "counter", "category": "workaround", "insight": "A low-engagement workaround", "prominence": {"score": 5}},
            {"comment_key": "neutral-low", "semantic_relevance": "adjacent", "evidence_role": "neutral", "category": "question", "insight": "An unresolved question", "prominence": {"score": 2}},
        ]
        selected = comment_prominence.select_diverse_insights(rows, limit=4)
        self.assertEqual([row["comment_key"] for row in selected[:3]], ["support-high", "counter-low", "neutral-low"])

    def test_review_queue_and_summary_preserve_prominence_audit(self) -> None:
        snapshot = {
            "platform": "x",
            "signals": [{
                "signal_id": "x:synthetic-1",
                "topic_key": "synthetic-topic",
                "canonical_url": "https://x.com/synthetic/status/1",
                "platform_facts": {"representative_comments": [
                    {"text": "This solves the repeated task", "likes": 20, "reply_count": 2},
                    {"text": "The manual workaround is enough", "likes": 1, "reply_count": 0},
                ]},
            }],
        }
        queue = prepare_comment_review.build_queue(snapshot)
        self.assertEqual(queue["prominence_version"], comment_prominence.VERSION)
        self.assertEqual(queue["comments"][0]["prominence"]["score"], 100)
        review = {
            "schema_version": apply_comment_review.SCHEMA_VERSION,
            "queue_sha256": queue["queue_sha256"],
            "reviews": [
                {"comment_key": queue["comments"][0]["comment_key"], "category": "positive_outcome", "semantic_relevance": "direct", "evidence_role": "support", "demand_topic_key": "repeated-task", "insight": "The task was completed more easily.", "reason": "The visible text states the outcome."},
                {"comment_key": queue["comments"][1]["comment_key"], "category": "workaround", "semantic_relevance": "direct", "evidence_role": "counter", "demand_topic_key": "repeated-task", "insight": "A manual workaround may be sufficient.", "reason": "The visible text names the workaround."},
            ],
        }
        result = apply_comment_review.apply(snapshot, queue, review)
        evidence = result["comment_evidence"]
        self.assertEqual(evidence["prominence_version"], comment_prominence.VERSION)
        self.assertEqual(evidence["prominence_coverage_count"], 2)
        self.assertEqual(evidence["insight_selection"][1]["evidence_role"], "counter")
        self.assertEqual(result["signals"][0]["platform_facts"]["representative_comments"][0]["likes"], 20)

    def test_report_level_summary_preserves_counter_across_multiple_posts(self) -> None:
        snapshot = {"signals": [
            {
                "topic_key": "topic-1",
                "canonical_url": "https://example.com/1",
                "platform_facts": {"comment_analysis": {
                    "status": "reviewed", "reviewed_count": 3, "relevant_count": 3, "support_count": 3, "counter_count": 0,
                    "category_counts": {"need": 3}, "prominence_coverage_count": 3, "high_prominence_relevant_count": 2,
                    "insight_selection": [
                        {"insight": "Popular support A", "evidence_role": "support", "category": "need"},
                        {"insight": "Popular support B", "evidence_role": "support", "category": "need"},
                    ],
                }},
            },
            {
                "topic_key": "topic-1",
                "canonical_url": "https://example.com/2",
                "platform_facts": {"comment_analysis": {
                    "status": "reviewed", "reviewed_count": 1, "relevant_count": 1, "support_count": 0, "counter_count": 1,
                    "category_counts": {"workaround": 1}, "prominence_coverage_count": 1, "high_prominence_relevant_count": 0,
                    "insight_selection": [
                        {"insight": "Low-engagement counterexample", "evidence_role": "counter", "category": "workaround"},
                    ],
                }},
            },
        ]}
        evidence = generate_profile_report.finding_comment_evidence(snapshot, "topic-1")
        self.assertIn("Low-engagement counterexample", evidence["insights"])
        self.assertEqual(evidence["counter_count"], 1)


if __name__ == "__main__":
    unittest.main()
