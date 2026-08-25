from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "tools" / "snapshot_github_traffic.py"
SPEC = importlib.util.spec_from_file_location("snapshot_github_traffic", MODULE_PATH)
assert SPEC and SPEC.loader
snapshot_github_traffic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot_github_traffic)


def fixture_api(endpoint: str):
    responses = {
        "repos/example/radar": {
            "full_name": "example/radar",
            "html_url": "https://github.com/example/radar",
            "description": "Synthetic repository",
            "created_at": "2026-08-01T00:00:00Z",
            "updated_at": "2026-08-25T00:00:00Z",
            "stargazers_count": 3,
            "forks_count": 1,
            "subscribers_count": 2,
            "open_issues_count": 0,
            "topics": ["agent-skills"],
            "has_discussions": True,
            "private": False,
            "owner": {"login": "should-not-be-copied"},
        },
        "repos/example/radar/traffic/views": {
            "count": 20,
            "uniques": 8,
            "views": [{"timestamp": "2026-08-24T00:00:00Z", "count": 20, "uniques": 8}],
        },
        "repos/example/radar/traffic/clones": {
            "count": 7,
            "uniques": 4,
            "clones": [{"timestamp": "2026-08-24T00:00:00Z", "count": 7, "uniques": 4}],
        },
        "repos/example/radar/traffic/popular/referrers": [
            {"referrer": "github.com", "count": 4, "uniques": 2}
        ],
        "repos/example/radar/traffic/popular/paths": [
            {"path": "/example/radar", "title": "example/radar", "count": 9, "uniques": 5}
        ],
        "repos/example/radar/releases?per_page=100": [
            {
                "tag_name": "v0.1.0",
                "published_at": "2026-08-20T00:00:00Z",
                "prerelease": True,
                "assets": [{"name": "radar.zip", "download_count": 6, "uploader": {"login": "ignored"}}],
            }
        ],
    }
    if endpoint not in responses:
        raise AssertionError(f"Unexpected endpoint: {endpoint}")
    return responses[endpoint]


class GitHubTrafficSnapshotTest(unittest.TestCase):
    def test_collects_only_bounded_repository_metrics(self) -> None:
        snapshot = snapshot_github_traffic.collect_snapshot(
            "example/radar",
            api_get=fixture_api,
            captured_at=datetime(2026, 8, 25, 2, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(snapshot["traffic"]["views"]["uniques"], 8)
        self.assertEqual(snapshot["traffic"]["release_downloads"][0]["assets"][0]["download_count"], 6)
        serialized = json.dumps(snapshot)
        self.assertNotIn("should-not-be-copied", serialized)
        self.assertNotIn("uploader", serialized)
        self.assertIn("not verified installations or users", serialized)

    def test_save_is_idempotent_on_the_same_utc_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            captured_at = datetime(2026, 8, 25, 2, 0, tzinfo=timezone.utc)
            first_path, first_status = snapshot_github_traffic.save_snapshot(
                "example/radar", output_dir, api_get=fixture_api, captured_at=captured_at
            )
            self.assertEqual(first_status, "captured")
            self.assertTrue(first_path and first_path.exists())

            def must_not_run(endpoint: str):
                raise AssertionError(f"API should not be called during same-day skip: {endpoint}")

            second_path, second_status = snapshot_github_traffic.save_snapshot(
                "example/radar", output_dir, api_get=must_not_run, captured_at=captured_at
            )
            self.assertEqual(second_status, "skipped_same_utc_date")
            self.assertEqual(second_path, first_path)

    def test_api_failure_writes_no_partial_snapshot_or_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            def fails_after_repository(endpoint: str):
                if endpoint == "repos/example/radar":
                    return fixture_api(endpoint)
                raise snapshot_github_traffic.SnapshotError("synthetic API failure")

            with self.assertRaises(snapshot_github_traffic.SnapshotError):
                snapshot_github_traffic.save_snapshot(
                    "example/radar",
                    output_dir,
                    api_get=fails_after_repository,
                    captured_at=datetime(2026, 8, 25, 2, 0, tzinfo=timezone.utc),
                )
            self.assertEqual(list(output_dir.glob("*.json")), [])

    def test_rejects_impossible_unique_count(self) -> None:
        def invalid_api(endpoint: str):
            value = fixture_api(endpoint)
            if endpoint.endswith("traffic/views"):
                return {**value, "count": 2, "uniques": 5}
            return value

        with self.assertRaisesRegex(snapshot_github_traffic.SnapshotError, "smaller than uniques"):
            snapshot_github_traffic.collect_snapshot("example/radar", api_get=invalid_api)


if __name__ == "__main__":
    unittest.main()

