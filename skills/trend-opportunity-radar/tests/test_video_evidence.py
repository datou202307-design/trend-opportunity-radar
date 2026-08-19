from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_video_evidence as runner
import video_evidence as video
import check_video_evidence_runtime as runtime_check
import prepare_video_review as video_queue
import apply_video_review as video_reviewer


def signal(index: int, *, author: str, layer: str, relevance: str = "direct", role: str = "support") -> dict:
    return {
        "signal_id": f"synthetic-{index}",
        "platform": "tiktok",
        "source_type": "search_card",
        "detail_captured": False,
        "content_id": f"700000000000000000{index}",
        "canonical_url": f"https://www.tiktok.com/@{author}/video/700000000000000000{index}",
        "query_layer": layer,
        "query_layers": [layer],
        "semantic_relevance": relevance,
        "evidence_role": role,
        "metrics": {"views": 1000 * index, "likes": 100 * index, "comments": 10, "shares": 5, "saves": None},
        "author": {"id": author, "name": author},
        "evidence_refs": [],
        "limitations": ["The adapter did not provide publication time or an independent detail read; the item remains search-card evidence."],
    }


class VideoEvidenceTest(unittest.TestCase):
    def test_selection_is_bounded_deterministic_and_author_diverse(self) -> None:
        snapshot = {"schema_version": "trend-signal-snapshot-v0.4", "platform": "tiktok", "signals": [
            signal(1, author="alpha", layer="category"),
            signal(2, author="alpha", layer="subject_bridge"),
            signal(3, author="beta", layer="platform_baseline", role="counter"),
        ]}
        first = video.select_candidates(snapshot, 2)
        second = video.select_candidates(snapshot, 2)
        self.assertEqual([item["signal_key"] for item in first["candidates"]], [item["signal_key"] for item in second["candidates"]])
        self.assertEqual(first["selected_count"], 2)
        self.assertEqual(len({item["author"] for item in first["candidates"]}), 2)
        self.assertEqual({item["evidence_role"] for item in first["candidates"]}, {"support", "counter"})

    def test_analyzer_command_is_pinned_and_bounded(self) -> None:
        command = video.analyzer_command("https://example.com/video/1", Path("frames"))
        self.assertIn("mcp-video-analyzer@0.8.0", command)
        self.assertEqual(command[command.index("--max-frames") + 1], "8")
        self.assertNotIn("aiSummary", command[command.index("--fields") + 1])
        self.assertEqual(video.analyzer_arguments("https://example.com/video/1", Path("frames"))[0], "analyze")

    def test_normalization_keeps_channels_and_provenance_separate(self) -> None:
        candidate = video.select_candidates({"platform": "tiktok", "signals": [signal(1, author="alpha", layer="subject_bridge")]}, 1)["candidates"][0]
        raw = {
            "metadata": {"title": "Synthetic clip", "duration": 31, "uploader": "alpha"},
            "transcript": {"source": "native_subtitle", "language": "en", "segments": [{"start": 0, "end": 2, "text": "Spoken claim"}]},
            "ocrResults": [{"time": 1.5, "text": "Visible price", "confidence": 0.9}],
            "frames": [{"time": "0:01", "filePath": "temporary.jpg"}],
            "warnings": [],
        }
        normalized = video.normalize_result(raw, candidate, "synthetic-analyzer.json")
        evidence = normalized["content_evidence"]
        self.assertEqual(evidence["transcript"]["provenance"], "native_subtitle")
        self.assertEqual(evidence["visual_text"]["provenance"], "ocr")
        self.assertEqual(evidence["metadata"]["duration_seconds"], 31.0)
        self.assertFalse(evidence["keyframes"][0]["artifact_retained"])
        self.assertEqual(evidence["keyframes"][0]["timestamp_seconds"], 1.0)
        self.assertEqual(evidence["metadata"]["content_format_detected"], "video")
        self.assertNotIn("filePath", json.dumps(evidence))

    def test_normalization_filters_corrupt_ocr_but_preserves_analyzer_reference(self) -> None:
        candidate = video.select_candidates({"platform": "tiktok", "signals": [signal(1, author="alpha", layer="subject_bridge")]}, 1)["candidates"][0]
        normalized = video.normalize_result({
            "ocrResults": [{"time": 0, "text": "MÃE broken"}, {"time": 1, "text": "Create Trip"}],
        }, candidate, "raw-analyzer.json")
        evidence = normalized["content_evidence"]
        self.assertEqual([item["text"] for item in evidence["visual_text"]["rows"]], ["Create Trip"])
        self.assertIn("Filtered 1 OCR row", " ".join(evidence["limitations"]))
        self.assertEqual(evidence["raw_artifact"], "raw-analyzer.json")

    def test_merge_enriches_detail_without_changing_sample_counts(self) -> None:
        original = signal(1, author="alpha", layer="subject_bridge")
        snapshot = {"platform": "tiktok", "raw_sample_count": 60, "unique_sample_count": 40, "signals": [original]}
        candidate = video.select_candidates(snapshot, 1)["candidates"][0]
        normalized = video.normalize_result({"transcript": [{"text": "Actual spoken content"}]}, candidate, "synthetic.json")
        merged = video.merge_results(snapshot, {"attempted_count": 1, "results": [normalized]})
        self.assertEqual(merged["raw_sample_count"], 60)
        self.assertEqual(merged["unique_sample_count"], 40)
        self.assertTrue(merged["signals"][0]["detail_captured"])
        self.assertEqual(merged["signals"][0]["source_type"], "direct_post")
        self.assertTrue(merged["video_evidence"]["semantic_rereview_required"])

    def test_four_media_shapes_keep_format_and_evidence_boundaries(self) -> None:
        candidate = video.select_candidates({"platform": "tiktok", "signals": [signal(1, author="alpha", layer="subject_bridge")]}, 1)["candidates"][0]
        native = video.normalize_result({
            "transcript": {"source": "native_subtitle", "segments": [{"text": "Native caption fact"}]},
            "frames": [{"time": 1}],
        }, candidate, "native.json")
        spoken = video.normalize_result({
            "transcript": [{"text": "Locally transcribed speech"}],
            "warnings": ["Whisper local ASR was used"],
            "frames": [{"time": 1}],
        }, candidate, "spoken.json")
        text_led = video.normalize_result({
            "ocrResults": [{"time": 2, "text": "Visible workflow step"}],
            "frames": [{"time": 2}],
        }, candidate, "text-led.json")
        slideshow = video.normalize_result({
            "metadata": {"title": "Photo slideshow"},
            "warnings": ["Requested format does not contain any stream"],
        }, candidate, "slideshow.json")
        self.assertEqual(native["content_evidence"]["transcript"]["provenance"], "native_subtitle")
        self.assertEqual(spoken["content_evidence"]["transcript"]["provenance"], "asr")
        self.assertEqual(text_led["content_evidence"]["visual_text"]["provenance"], "ocr")
        self.assertTrue(native["success"] and spoken["success"] and text_led["success"])
        self.assertFalse(slideshow["success"])
        self.assertEqual(slideshow["content_evidence"]["metadata"]["content_format_detected"], "audio_or_slideshow")

    def test_keyframes_without_text_do_not_promote_a_detail(self) -> None:
        original = signal(1, author="alpha", layer="subject_bridge")
        snapshot = {"platform": "tiktok", "signals": [original]}
        candidate = video.select_candidates(snapshot, 1)["candidates"][0]
        normalized = video.normalize_result({"frames": [{"time": 1}]}, candidate, "frames-only.json")
        self.assertFalse(normalized["success"])
        merged = video.merge_results(snapshot, {"attempted_count": 1, "results": [normalized]})
        self.assertFalse(merged["signals"][0]["detail_captured"])
        self.assertEqual(merged["signals"][0]["source_type"], "search_card")

    def test_video_semantic_review_is_complete_exact_and_does_not_change_counts(self) -> None:
        original = signal(1, author="alpha", layer="subject_bridge")
        original["topic_key"] = "topic-a"
        snapshot = {"platform": "tiktok", "raw_sample_count": 60, "unique_sample_count": 40, "signals": [original]}
        candidate = video.select_candidates(snapshot, 1)["candidates"][0]
        normalized = video.normalize_result({
            "transcript": {"source": "native_subtitle", "segments": [{"start": 0, "text": "Prefix A concrete spoken result with extra noise"}]},
            "ocrResults": [{"time": 1, "text": "Three setup steps"}],
            "frames": [{"time": 1}],
        }, candidate, "synthetic.json")
        enriched = video.merge_results(snapshot, {"attempted_count": 1, "results": [normalized]})
        queue = video_queue.build_queue(enriched)
        review = {
            "schema_version": video_reviewer.SCHEMA_VERSION,
            "queue_sha256": queue["queue_sha256"],
            "reviews": [{
                "signal_key": queue["items"][0]["signal_key"],
                "content_format": "video",
                "usable_channels": ["native_subtitle", "ocr"],
                "summary": "The video shows a result and the setup needed to reach it.",
                "excerpts": [
                    {"channel": "native_subtitle", "text": "A concrete spoken result", "timestamp_seconds": 0, "semantic_relevance": "direct", "evidence_role": "support", "reason": "It states the result."},
                    {"channel": "ocr", "text": "Three setup steps", "timestamp_seconds": 1, "semantic_relevance": "direct", "evidence_role": "support", "reason": "The frame states the setup count."},
                ],
                "limitations": ["One short clip cannot establish market prevalence."],
            }],
        }
        reviewed = video_reviewer.apply(enriched, queue, review)
        self.assertEqual(reviewed["raw_sample_count"], 60)
        self.assertEqual(reviewed["unique_sample_count"], 40)
        self.assertFalse(reviewed["video_evidence"]["semantic_rereview_required"])
        self.assertEqual(reviewed["video_evidence"]["reviewed_count"], 1)
        self.assertEqual(reviewed["signals"][0]["content_evidence"]["semantic_review"]["status"], "reviewed")

        bad = json.loads(json.dumps(review))
        bad["reviews"][0]["excerpts"][0]["text"] = "A sentence the video never contained"
        with self.assertRaises(SystemExit):
            video_reviewer.apply(enriched, queue, bad)

    def test_irrelevant_media_text_does_not_promote_search_card_after_review(self) -> None:
        original = signal(1, author="alpha", layer="subject_bridge")
        original["topic_key"] = "topic-a"
        snapshot = {"platform": "tiktok", "raw_sample_count": 1, "unique_sample_count": 1, "signals": [original]}
        candidate = video.select_candidates(snapshot, 1)["candidates"][0]
        normalized = video.normalize_result({
            "transcript": {"source": "asr", "segments": [{"start": 0, "text": "Unrelated song lyric"}]},
            "warnings": ["Transcript generated via Whisper fallback"],
        }, candidate, "music.json")
        enriched = video.merge_results(snapshot, {"attempted_count": 1, "results": [normalized]})
        self.assertTrue(enriched["signals"][0]["detail_captured"])
        queue = video_queue.build_queue(enriched)
        review = {
            "schema_version": video_reviewer.SCHEMA_VERSION,
            "queue_sha256": queue["queue_sha256"],
            "reviews": [{
                "signal_key": queue["items"][0]["signal_key"], "content_format": "audio",
                "usable_channels": ["asr"], "summary": "Only unrelated music was available.",
                "excerpts": [{"channel": "asr", "text": "Unrelated song lyric", "timestamp_seconds": 0,
                              "semantic_relevance": "weak", "evidence_role": "neutral", "reason": "Not about the topic."}],
                "limitations": ["No relevant media text."],
            }],
        }
        reviewed = video_reviewer.apply(enriched, queue, review)
        self.assertFalse(reviewed["signals"][0]["detail_captured"])
        self.assertEqual(reviewed["signals"][0]["source_type"], "search_card")
        self.assertEqual(reviewed["video_evidence"]["relevant_reviewed_count"], 0)

    def test_failed_result_does_not_promote_search_card(self) -> None:
        original = signal(1, author="alpha", layer="subject_bridge")
        snapshot = {"platform": "tiktok", "signals": [original]}
        merged = video.merge_results(snapshot, {"attempted_count": 1, "results": [{"signal_key": video.signal_key(original), "success": False}]})
        self.assertFalse(merged["signals"][0]["detail_captured"])
        self.assertEqual(merged["signals"][0]["source_type"], "search_card")

    def test_runner_removes_cookie_environment(self) -> None:
        old_cookie = os.environ.get("YTDLP_COOKIES")
        old_browser = os.environ.get("YTDLP_COOKIES_FROM_BROWSER")
        old_api_key = os.environ.get("OPENAI_API_KEY")
        try:
            os.environ["YTDLP_COOKIES"] = "secret-cookie-file"
            os.environ["YTDLP_COOKIES_FROM_BROWSER"] = "chrome"
            os.environ["OPENAI_API_KEY"] = "secret-cloud-key"
            environment = runner.safe_child_environment()
            self.assertNotIn("YTDLP_COOKIES", environment)
            self.assertNotIn("YTDLP_COOKIES_FROM_BROWSER", environment)
            self.assertNotIn("OPENAI_API_KEY", environment)
            runtime_environment = runner.safe_child_environment(Path("isolated-bin"))
            self.assertTrue(runtime_environment["PATH"].startswith("isolated-bin"))
            local_asr = runner.safe_child_environment(
                Path("isolated-bin"), Path("whisper.exe"), "tiny", "en", Path("model-cache")
            )
            self.assertEqual(local_asr["WHISPER_MODEL"], "tiny")
            self.assertEqual(local_asr["HF_HOME"], "model-cache")
        finally:
            if old_cookie is None:
                os.environ.pop("YTDLP_COOKIES", None)
            else:
                os.environ["YTDLP_COOKIES"] = old_cookie
            if old_browser is None:
                os.environ.pop("YTDLP_COOKIES_FROM_BROWSER", None)
            else:
                os.environ["YTDLP_COOKIES_FROM_BROWSER"] = old_browser
            if old_api_key is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old_api_key

    def test_dry_run_is_sequential_and_does_not_invoke_runtime(self) -> None:
        plan = video.select_candidates({"platform": "tiktok", "signals": [signal(1, author="alpha", layer="category")]}, 1)
        with tempfile.TemporaryDirectory() as directory:
            result = runner.run_plan(plan, Path(directory), 60, dry_run=True)
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["max_concurrency"], 1)
        self.assertEqual(result["attempted_count"], 1)
        self.assertNotIn(plan["candidates"][0]["url"], json.dumps(result))

    def test_zero_success_is_not_reported_complete(self) -> None:
        self.assertEqual(runner.classify_failure("npm warn cleanup EPERM"), "runtime_install_error")
        empty = runner.run_plan({"candidates": []}, Path(tempfile.gettempdir()), 60, dry_run=False)
        self.assertEqual(empty["status"], "failed")

    def test_timeout_and_malformed_output_are_preserved_as_failed_attempts(self) -> None:
        plan = video.select_candidates({"platform": "tiktok", "signals": [signal(1, author="alpha", layer="category")]}, 1)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(runner.shutil, "which", return_value="npx.cmd"):
            with mock.patch.object(runner.subprocess, "run", side_effect=subprocess.TimeoutExpired(["npx"], 30)):
                timed_out = runner.run_plan(plan, Path(directory) / "timeout", 30)
            with mock.patch.object(runner.subprocess, "run", return_value=SimpleNamespace(stdout="not-json", stderr="", returncode=0)):
                malformed = runner.run_plan(plan, Path(directory) / "malformed", 30)
        self.assertEqual(timed_out["status"], "failed")
        self.assertEqual(timed_out["results"][0]["status"], "timeout")
        self.assertEqual(malformed["status"], "failed")
        self.assertEqual(malformed["results"][0]["status"], "malformed_analyzer_output")

    def test_runtime_preflight_does_not_claim_douyin(self) -> None:
        status = runtime_check.inspect_runtime(None, None, None)
        self.assertFalse(status["capabilities"]["douyin"])
        self.assertFalse(status["security"]["cloud_api_keys_forwarded"])


if __name__ == "__main__":
    unittest.main()
