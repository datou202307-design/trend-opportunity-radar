from __future__ import annotations

import unittest
import subprocess
from unittest.mock import patch
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_facebook_opencli_capture as capture


class FacebookOpenCliCaptureTest(unittest.TestCase):
    def test_surface_requires_posts_url_query_identity_and_cards(self) -> None:
        query_url = "https://www.facebook.com/search/posts/?q=weekly%20meal%20prep"
        valid = capture.inspect_surface({
            "url": query_url,
            "title": "weekly meal prep - Search results | Facebook",
            "body_text": "Search results weekly meal prep",
        }, query_url, "weekly meal prep", 7)
        self.assertEqual(valid["state"], "results_visible")
        blank = capture.inspect_surface({"url": "about:blank", "title": "", "body_text": ""}, query_url, "weekly meal prep", 0)
        self.assertEqual(blank["state"], "surface_unreadable")

    def test_zero_results_requires_explicit_facebook_empty_state(self) -> None:
        query_url = "https://www.facebook.com/search/posts/?q=syntheticnone"
        shell = capture.inspect_surface({"url": query_url, "title": "syntheticnone - Search results | Facebook", "body_text": "Search results syntheticnone Filters"}, query_url, "syntheticnone", 0)
        self.assertEqual(shell["state"], "surface_unreadable")
        empty = capture.inspect_surface({"url": query_url, "title": "syntheticnone - Search results | Facebook", "body_text": "Search results syntheticnone No results found"}, query_url, "syntheticnone", 0)
        self.assertEqual(empty["state"], "explicit_empty")

    def test_surface_safety_stop_matrix_is_distinct_from_zero_results(self) -> None:
        query_url = "https://www.facebook.com/search/posts/?q=syntheticnone"
        cases = [
            ({"url": query_url, "title": "Security check", "body_text": "Confirm you're human CAPTCHA"}, "captcha"),
            ({"url": query_url, "title": "Facebook", "body_text": "Too many requests. Try again later."}, "rate_limit"),
            ({"url": "https://www.facebook.com/login/", "title": "Log into Facebook", "body_text": "", "password_input_count": 1}, "login_expired"),
            ({"url": "https://www.facebook.com/checkpoint/", "title": "Approval required", "body_text": "Please confirm your identity"}, "permission_prompt"),
            ({"url": query_url, "title": "Private group", "body_text": "This content is private"}, "private_content"),
            ({"url": "https://www.facebook.com/", "title": "Facebook", "body_text": "Home"}, "abnormal_redirect"),
        ]
        for raw, expected in cases:
            with self.subTest(expected=expected):
                surface = capture.inspect_surface(raw, query_url, "syntheticnone", 0)
                self.assertEqual(surface["state"], "safety_stop")
                self.assertEqual(surface["safety_stop"], expected)
                self.assertFalse(surface["explicit_empty"])

    def test_capture_payload_preserves_distinct_terminal_reasons(self) -> None:
        request = {"request_sha256": "abc", "query_term": "syntheticnone", "query_url": "https://www.facebook.com/search/posts/?q=syntheticnone"}
        unreadable = capture.capture_payload(request, [[], []], {}, [], 0, 10, 20, 10, True, page_probes=[{"state": "surface_unreadable", "query_identity": False}, {"state": "surface_unreadable", "query_identity": False}])
        self.assertEqual(unreadable["stop_reason"], "surface_unreadable")
        self.assertFalse(unreadable["checks"]["posts_surface"])
        verified = capture.capture_payload(request, [[], []], {}, [], 0, 10, 20, 10, True, page_probes=[{"state": "explicit_empty", "query_identity": True}, {"state": "explicit_empty", "query_identity": True}])
        self.assertEqual(verified["stop_reason"], "verified_zero_results")
        stopped = capture.capture_payload(request, [[]], {}, [], 0, 10, 20, 10, True, page_probes=[{"state": "safety_stop", "query_identity": False, "safety_stop": "captcha"}], forced_stop_reason="captcha")
        self.assertEqual(stopped["stop_reason"], "captcha")

    def test_non_json_navigation_result_is_allowed_when_not_requested(self) -> None:
        def runner(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 0, stdout="Scrolled down", stderr="")

        value = capture.run_cli("opencli", ["browser", "session", "scroll", "down"], 10, runner, expect_json=False)
        self.assertEqual(value, "Scrolled down")

    def test_eval_still_requires_json(self) -> None:
        def runner(*args, **kwargs):
            return subprocess.CompletedProcess(args[0], 0, stdout="not json", stderr="")

        with self.assertRaises(RuntimeError):
            capture.run_cli("opencli", ["browser", "session", "eval", "1"], 10, runner)

    def test_replacement_character_fragments_are_removed(self) -> None:
        self.assertEqual(capture.sanitize_visible_text("L&O Travel Design �� ��注"), "L&O Travel Design")

    def test_corrupt_detail_without_recoverable_time_is_rejected(self) -> None:
        url = "https://www.facebook.com/reel/1665370064521528/"
        detail = capture.normalize_detail(
            {"canonical_url": url, "description": "ҳ���޷���ʾ", "author_name": "ҳ���޷���ʾ", "observed_time_label": "1��"},
            url,
            {"preview_text": "Synthetic", "observed_time_label": "1��"},
        )
        self.assertIsNone(detail)

    def test_platform_unavailable_page_is_not_a_verified_detail(self) -> None:
        url = "https://www.facebook.com/permalink.php?story_fbid=synthetic"
        detail = capture.normalize_detail(
            {"canonical_url": url, "visible_text": "页面无法显示 这条链接可能已损坏，或页面已被移除。", "observed_time_label": "1天"},
            url,
        )
        self.assertIsNone(detail)

    def test_pacing_resumes_with_cooldown_after_five_reads(self) -> None:
        waits = []
        event = capture.pace_before_request(5, waits.append)
        self.assertEqual(waits, [30.0])
        self.assertEqual(event, {"request_index": 6, "wait_seconds": 30.0, "cooldown": True})

    def test_pacing_uses_interval_between_other_reads(self) -> None:
        waits = []
        event = capture.pace_before_request(2, waits.append)
        self.assertEqual(waits, [10.0])
        self.assertFalse(event["cooldown"])

    def test_shared_run_pacing_seed_overrides_a_new_query_capture(self) -> None:
        request = {"request_sha256": "abc", "max_posts": 5, "max_detail_posts": 1, "query_url": "https://www.facebook.com/search/posts/?q=test", "query_term": "test", "allowed_actions": ["expand_exact_detail_comments_once"]}
        result = capture.execute(request, "unused", "session", 0, 10, 20, 10, 45, sleeper=lambda _seconds: None, target_passes=0, include_details=False, pacing_seed_count=5, pacing_seed_events=[{"request_index": 5}])
        self.assertEqual(result["capture_audit"]["pacing"]["request_count"], 5)
        self.assertEqual(result["capture_audit"]["pacing"]["events"], [{"request_index": 5}])

    def test_detail_attempt_limit_never_exceeds_frozen_request_budget(self) -> None:
        urls = [f"https://www.facebook.com/reel/{value}/" for value in ("1111111111", "2222222222", "3333333333")]
        self.assertEqual(capture.select_detail_urls(urls, 2, attempt_limit=5), urls[:2])
        self.assertEqual(capture.select_detail_urls(urls, 3, attempt_limit=1), urls[:1])

    def test_detail_selection_is_bounded_to_frozen_first_pass(self) -> None:
        urls = [
            "https://www.facebook.com/reel/1111111111/",
            "https://www.facebook.com/reel/2222222222/",
            "https://www.facebook.com/reel/3333333333/",
        ]
        self.assertEqual(capture.select_detail_urls(urls, 2, ["3333333333", "1111111111"]), [urls[0], urls[2]])
        with self.assertRaises(RuntimeError):
            capture.select_detail_urls(urls, 2, ["9999999999"])
        with self.assertRaises(RuntimeError):
            capture.select_detail_urls(urls, 1, ["1111111111", "2222222222"])

    def test_metrics_require_number_and_semantic_button_label(self) -> None:
        metrics = capture.parse_metrics([
            {"label": "186 次回应", "text": "186"},
            {"label": "赞：119位用户", "text": "119"},
            {"label": "查看 9 条评论", "text": "9"},
            {"label": "14 次分享", "text": "14"},
            {"label": "赞", "text": ""},
        ])
        self.assertEqual(metrics, {"reactions": 186, "comments": 9, "shares": 14, "views": None})

    def test_reaction_subtype_is_not_misreported_as_total_reactions(self) -> None:
        metrics = capture.parse_metrics([{"label": "赞：119位用户", "text": "119"}, {"label": "119 likes", "text": "119"}])
        self.assertIsNone(metrics["reactions"])

    def test_card_normalization_keeps_reactions_separate_from_likes(self) -> None:
        card = capture.normalize_card({
            "canonical_url": "https://www.facebook.com/reel/1665370064521528/?tracking=1",
            "author_name": "Synthetic Travel Page", "preview_text": "Synthetic public post", "observed_time_label": "1 day",
            "button_labels": [{"label": "1.2K reactions", "text": "1.2K"}],
        })
        self.assertIsNotNone(card)
        self.assertEqual(card["reactions"], 1200)
        self.assertEqual(card["content_format"], "reel")

    def test_detail_identity_mismatch_is_rejected(self) -> None:
        detail = capture.normalize_detail({"canonical_url": "https://www.facebook.com/reel/9999999999/", "description": "Mismatch", "observed_time_label": "1 day"}, "https://www.facebook.com/reel/1665370064521528/")
        self.assertIsNone(detail)

    def test_detail_can_reuse_time_and_metrics_from_the_same_search_card(self) -> None:
        url = "https://www.facebook.com/reel/1665370064521528/"
        detail = capture.normalize_detail(
            {"canonical_url": url, "description": "Verified public detail body", "author_name": "Travel Page", "button_labels": []},
            url,
            {"observed_time_label": "2025年10月26日", "comments": 54, "shares": 101, "reactions": None, "views": None},
        )
        self.assertIsNotNone(detail)
        self.assertEqual(detail["observed_time_label"], "2025年10月26日")
        self.assertEqual(detail["comments"], 54)
        self.assertEqual(detail["shares"], 101)
        self.assertIsNone(detail["reactions"])

    def test_detail_keeps_only_five_unique_visible_top_level_comments(self) -> None:
        url = "https://www.facebook.com/reel/1665370064521528/"
        rows = [
            {"author_name": f"Reader {index}", "text": f"Visible comment {index}", "top_level_visible": True}
            for index in range(6)
        ]
        rows.insert(2, dict(rows[0]))
        rows.append({"author_name": "Hidden", "text": "Not visible", "top_level_visible": False})
        detail = capture.normalize_detail(
            {"canonical_url": url, "description": "Verified public detail", "observed_time_label": "1 day", "representative_comments": rows},
            url,
        )
        self.assertIsNotNone(detail)
        self.assertEqual(len(detail["representative_comments"]), 5)
        self.assertTrue(all(row["top_level_visible"] for row in detail["representative_comments"]))
        self.assertEqual(detail["representative_comments"][0]["text"], "Visible comment 0")

    def test_search_safety_stop_ends_before_a_second_pass(self) -> None:
        request = {"request_sha256": "abc", "max_posts": 5, "max_detail_posts": 1, "query_url": "https://www.facebook.com/search/posts/?q=test", "query_term": "test"}
        surface = {"state": "safety_stop", "query_identity": False, "canonical_card_count": 0, "explicit_empty": False, "safety_stop": "rate_limit"}
        with patch.object(capture, "collect_pass", return_value=([], {}, surface)) as mocked:
            result = capture.execute(request, "unused", "session", 0, 10, 20, 10, 45, sleeper=lambda _seconds: None, target_passes=2, include_details=False)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(result["stop_reason"], "rate_limit")
        self.assertEqual(result["capture_audit"]["pass_count"], 1)

    def test_checkpoint_payload_is_valid_after_first_pass(self) -> None:
        request = {"request_sha256": "abc", "query_term": "AI travel planner", "query_url": "https://www.facebook.com/search/posts/?q=AI%20travel%20planner"}
        url = "https://www.facebook.com/reel/1665370064521528/"
        card = {"canonical_url": url, "preview_text": "Synthetic", "author_name": "Page", "observed_time_label": "1 day", "content_format": "reel", "reactions": None, "comments": None, "shares": None, "views": None}
        payload = capture.capture_payload(request, [[url]], {url: card}, [], 0, 10, 20, 10, False)
        self.assertEqual(payload["capture_audit"]["pass_count"], 1)
        self.assertFalse(payload["capture_audit"]["terminal"])
        self.assertEqual(payload["result_cards"][0]["canonical_url"], url)

    def test_surface_probe_is_bounded_and_read_only(self) -> None:
        self.assertIn("body_text", capture.STATUS_JS)
        self.assertIn("slice(0,6000)", capture.STATUS_JS)
        self.assertNotIn("click(", capture.STATUS_JS)
        self.assertNotIn("fetch(", capture.STATUS_JS)
        self.assertIn("representative_comments", capture.DETAIL_JS)
        self.assertIn("slice(0,5)", capture.DETAIL_JS)
        self.assertNotIn("click(", capture.DETAIL_JS)

    def test_comment_trigger_is_one_bounded_read_only_expansion(self) -> None:
        self.assertEqual(capture.COMMENT_TRIGGER_JS.count("target.click()"), 1)
        self.assertIn("\\d", capture.COMMENT_TRIGGER_JS)
        self.assertIn("comments?", capture.COMMENT_TRIGGER_JS)
        self.assertNotIn("input", capture.COMMENT_TRIGGER_JS.casefold())
        self.assertNotIn("submit", capture.COMMENT_TRIGGER_JS.casefold())

    def test_detail_expands_comments_once_and_audits_the_result(self) -> None:
        url = "https://www.facebook.com/reel/1665370064521528/"
        request = {"request_sha256": "abc", "max_posts": 5, "max_detail_posts": 1, "query_url": "https://www.facebook.com/search/posts/?q=test", "query_term": "test", "allowed_actions": ["expand_exact_detail_comments_once"]}
        card = {"canonical_url": url, "preview_text": "Synthetic", "author_name": "Page", "observed_time_label": "1 day", "content_format": "reel", "reactions": None, "comments": 5, "shares": None, "views": None}
        initial = {"request_sha256": "abc", "result_passes": [[url]], "result_cards": [card], "posts": [], "page_probes": [{"state": "results_visible", "query_identity": True}], "capture_audit": {"metric_contract_version": capture.METRIC_CONTRACT, "pacing": {"request_count": 0, "events": []}}}
        before = {"canonical_url": url, "description": "Verified public detail", "observed_time_label": "1 day", "button_labels": [{"label": "5 comments", "text": "5"}], "representative_comments": []}
        after = dict(before)
        after["representative_comments"] = [{"author_name": "Reader", "text": "A visible question", "top_level_visible": True}]
        responses = iter(["opened", before, {"clicked": True, "label": "5 comments"}, after])
        with patch.object(capture, "run_cli", side_effect=lambda *args, **kwargs: next(responses)):
            result = capture.execute(request, "unused", "session", 0, 10, 20, 10, 45, sleeper=lambda _seconds: None, initial_capture=initial, target_passes=1, detail_only=True, detail_content_ids=["1665370064521528"])
        self.assertEqual(len(result["posts"]), 1)
        self.assertEqual(len(result["posts"][0]["representative_comments"]), 1)
        events = result["capture_audit"]["pacing"]["events"]
        self.assertEqual([event["kind"] for event in events], ["detail", "comment_expand_and_read"])
        self.assertEqual(events[0]["status"], "captured")
        self.assertEqual(events[0]["captured_comment_count"], 1)

    def test_legacy_request_does_not_gain_comment_expansion_permission(self) -> None:
        url = "https://www.facebook.com/reel/1665370064521528/"
        request = {"request_sha256": "abc", "max_posts": 5, "max_detail_posts": 1, "query_url": "https://www.facebook.com/search/posts/?q=test", "query_term": "test", "allowed_actions": ["read_visible_comments"]}
        card = {"canonical_url": url, "preview_text": "Synthetic", "author_name": "Page", "observed_time_label": "1 day", "content_format": "reel", "reactions": None, "comments": 5, "shares": None, "views": None}
        initial = {"request_sha256": "abc", "result_passes": [[url]], "result_cards": [card], "posts": [], "page_probes": [{"state": "results_visible", "query_identity": True}], "capture_audit": {"metric_contract_version": capture.METRIC_CONTRACT, "pacing": {"request_count": 0, "events": []}}}
        detail = {"canonical_url": url, "description": "Verified public detail", "observed_time_label": "1 day", "button_labels": [{"label": "5 comments", "text": "5"}], "representative_comments": []}
        responses = iter(["opened", detail])
        with patch.object(capture, "run_cli", side_effect=lambda *args, **kwargs: next(responses)) as mocked:
            result = capture.execute(request, "unused", "session", 0, 10, 20, 10, 45, sleeper=lambda _seconds: None, initial_capture=initial, target_passes=1, detail_only=True, detail_content_ids=["1665370064521528"])
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual([event["kind"] for event in result["capture_audit"]["pacing"]["events"]], ["detail"])
        self.assertEqual(result["posts"][0]["representative_comments"], [])

    def test_unavailable_detail_never_triggers_comment_expansion(self) -> None:
        url = "https://www.facebook.com/reel/1665370064521528/"
        request = {"request_sha256": "abc", "max_posts": 5, "max_detail_posts": 1, "query_url": "https://www.facebook.com/search/posts/?q=test", "query_term": "test", "allowed_actions": ["expand_exact_detail_comments_once"]}
        card = {"canonical_url": url, "preview_text": "Synthetic", "author_name": "Page", "observed_time_label": "1 day", "content_format": "reel", "reactions": None, "comments": 99, "shares": None, "views": None}
        initial = {"request_sha256": "abc", "result_passes": [[url]], "result_cards": [card], "posts": [], "page_probes": [{"state": "results_visible", "query_identity": True}], "capture_audit": {"metric_contract_version": capture.METRIC_CONTRACT, "pacing": {"request_count": 0, "events": []}}}
        unavailable = {"canonical_url": url, "page_text": "This content isn't available right now", "description": "", "button_labels": []}
        responses = iter(["opened", unavailable])
        with patch.object(capture, "run_cli", side_effect=lambda *args, **kwargs: next(responses)) as mocked:
            result = capture.execute(request, "unused", "session", 0, 10, 20, 10, 45, sleeper=lambda _seconds: None, initial_capture=initial, target_passes=1, detail_only=True, detail_content_ids=["1665370064521528"])
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual([event["kind"] for event in result["capture_audit"]["pacing"]["events"]], ["detail"])
        self.assertEqual(result["capture_audit"]["pacing"]["events"][0]["status"], "rejected")
        self.assertEqual(result["capture_audit"]["pacing"]["events"][0]["reason"], "content_unavailable")

    def test_runner_defaults_to_background_but_exposes_one_explicit_foreground_fallback(self) -> None:
        self.assertIn('choices=["background", "foreground"]', Path(capture.__file__).read_text(encoding="utf-8"))
        self.assertIn("--inspect-current-cards", Path(capture.__file__).read_text(encoding="utf-8"))

    def test_resume_capture_requires_the_same_frozen_request(self) -> None:
        request = {"request_sha256": "abc", "max_posts": 5, "max_detail_posts": 1, "query_url": "https://www.facebook.com/search/posts/?q=test", "query_term": "test"}
        with self.assertRaises(RuntimeError):
            capture.execute(request, "unused", "session", 0, 10, 20, 10, 45, initial_capture={"request_sha256": "different"}, target_passes=1, include_details=False)

    def test_resume_clears_legacy_reaction_values_without_total_evidence(self) -> None:
        url = "https://www.facebook.com/reel/1665370064521528/"
        request = {"request_sha256": "abc", "max_posts": 5, "max_detail_posts": 1, "query_url": "https://www.facebook.com/search/posts/?q=test", "query_term": "test"}
        legacy = {"request_sha256": "abc", "result_passes": [[url]], "result_cards": [{"canonical_url": url, "preview_text": "Synthetic", "reactions": 119}], "posts": [], "capture_audit": {}}
        result = capture.execute(request, "unused", "session", 0, 10, 20, 10, 45, sleeper=lambda _seconds: None, initial_capture=legacy, target_passes=1, include_details=False, detail_only=True)
        self.assertIsNone(result["result_cards"][0]["reactions"])
        self.assertEqual(result["capture_audit"]["metric_contract_version"], capture.METRIC_CONTRACT)


if __name__ == "__main__":
    unittest.main()
