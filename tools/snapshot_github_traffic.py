from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "github-traffic-snapshot-v0.1"
STATE_VERSION = "github-traffic-state-v0.1"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class SnapshotError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SnapshotError(f"Expected a JSON object in {path}.")
    return value


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    temp_path.replace(path)


def sha256_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def gh_api(endpoint: str) -> Any:
    completed = subprocess.run(
        ["gh", "api", "--method", "GET", endpoint],
        capture_output=True,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    if completed.returncode != 0:
        message = stderr or "GitHub CLI returned a non-zero exit code."
        raise SnapshotError(f"GitHub API request failed for {endpoint}: {message}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"GitHub API returned invalid JSON for {endpoint}.") from exc


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnapshotError(f"Expected {label} to be a JSON object.")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SnapshotError(f"Expected {label} to be a JSON array.")
    return value


def validate_traffic_counter(value: Any, label: str) -> dict[str, Any]:
    counter = require_object(value, label)
    count = counter.get("count")
    uniques = counter.get("uniques")
    if not isinstance(count, int) or not isinstance(uniques, int) or count < 0 or uniques < 0:
        raise SnapshotError(f"{label} count and uniques must be non-negative integers.")
    if count < uniques:
        raise SnapshotError(f"{label} count cannot be smaller than uniques.")
    series_key = "views" if label == "views" else "clones"
    series = require_list(counter.get(series_key), f"{label}.{series_key}")
    for index, item in enumerate(series):
        row = require_object(item, f"{label}.{series_key}[{index}]")
        if not isinstance(row.get("timestamp"), str):
            raise SnapshotError(f"{label}.{series_key}[{index}] is missing timestamp.")
        if not isinstance(row.get("count"), int) or not isinstance(row.get("uniques"), int):
            raise SnapshotError(f"{label}.{series_key}[{index}] has invalid counters.")
    return {"count": count, "uniques": uniques, series_key: series}


def compact_ranked_rows(value: Any, label: str, allowed_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    rows = require_list(value, label)
    compact: list[dict[str, Any]] = []
    for index, item in enumerate(rows):
        row = require_object(item, f"{label}[{index}]")
        if not isinstance(row.get("count"), int) or not isinstance(row.get("uniques"), int):
            raise SnapshotError(f"{label}[{index}] has invalid counters.")
        compact.append({key: row.get(key) for key in allowed_keys if key in row})
    return compact


def collect_snapshot(
    repo: str,
    *,
    api_get: Callable[[str], Any] = gh_api,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    if not REPO_PATTERN.fullmatch(repo):
        raise SnapshotError("Repository must use the owner/name form.")
    captured = captured_at or utc_now()
    prefix = f"repos/{repo}"

    # Fetch every required response before building or writing a snapshot. A failed
    # request therefore cannot leave a partial result that looks complete.
    repository = require_object(api_get(prefix), "repository")
    views = validate_traffic_counter(api_get(f"{prefix}/traffic/views"), "views")
    clones = validate_traffic_counter(api_get(f"{prefix}/traffic/clones"), "clones")
    referrers = compact_ranked_rows(
        api_get(f"{prefix}/traffic/popular/referrers"),
        "popular_referrers",
        ("referrer", "count", "uniques"),
    )
    paths = compact_ranked_rows(
        api_get(f"{prefix}/traffic/popular/paths"),
        "popular_paths",
        ("path", "title", "count", "uniques"),
    )
    releases = require_list(api_get(f"{prefix}/releases?per_page=100"), "releases")

    release_downloads: list[dict[str, Any]] = []
    for index, item in enumerate(releases):
        release = require_object(item, f"releases[{index}]")
        assets = require_list(release.get("assets", []), f"releases[{index}].assets")
        release_downloads.append(
            {
                "tag_name": release.get("tag_name"),
                "published_at": release.get("published_at"),
                "prerelease": bool(release.get("prerelease")),
                "assets": [
                    {
                        "name": require_object(asset, "release asset").get("name"),
                        "download_count": require_object(asset, "release asset").get("download_count"),
                    }
                    for asset in assets
                ],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "captured_at": iso_utc(captured),
        "repository": {
            "full_name": repository.get("full_name", repo),
            "html_url": repository.get("html_url"),
            "description": repository.get("description"),
            "created_at": repository.get("created_at"),
            "updated_at": repository.get("updated_at"),
            "stargazers_count": repository.get("stargazers_count"),
            "forks_count": repository.get("forks_count"),
            "subscribers_count": repository.get("subscribers_count"),
            "open_issues_count": repository.get("open_issues_count"),
            "topics": repository.get("topics", []),
            "has_discussions": repository.get("has_discussions"),
        },
        "traffic": {
            "views": views,
            "clones": clones,
            "popular_referrers": referrers,
            "popular_paths": paths,
            "release_downloads": release_downloads,
        },
        "interpretation_limits": [
            "GitHub traffic covers a rolling window and is not permanent analytics.",
            "Clones are repository retrieval signals, not verified installations or users.",
            "This snapshot contains repository-level GitHub data only; it does not collect Skill prompts or report content.",
        ],
    }


def save_snapshot(
    repo: str,
    output_dir: Path,
    *,
    state_path: Path | None = None,
    force: bool = False,
    api_get: Callable[[str], Any] = gh_api,
    captured_at: datetime | None = None,
) -> tuple[Path | None, str]:
    captured = captured_at or utc_now()
    date_key = captured.astimezone(timezone.utc).date().isoformat()
    state_file = state_path or output_dir / "state.json"
    state = read_json(state_file)
    if state and state.get("last_successful_date") == date_key and not force:
        previous = state.get("last_snapshot")
        return (output_dir / previous if isinstance(previous, str) else None), "skipped_same_utc_date"

    snapshot = collect_snapshot(repo, api_get=api_get, captured_at=captured)
    if force:
        timestamp = captured.astimezone(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        filename = f"github-traffic-{timestamp}.json"
    else:
        filename = f"github-traffic-{date_key}.json"
    output_path = output_dir / filename
    if output_path.exists():
        raise SnapshotError(f"Refusing to overwrite existing snapshot: {output_path}")

    digest = sha256_json(snapshot)
    next_state = {
        "schema_version": STATE_VERSION,
        "repository": repo,
        "last_successful_date": date_key,
        "last_captured_at": snapshot["captured_at"],
        "last_snapshot": filename,
        "last_snapshot_sha256": digest,
    }
    atomic_write_json(output_path, snapshot)
    try:
        atomic_write_json(state_file, next_state)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    return output_path, "captured"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Save an idempotent, repository-level GitHub Traffic snapshot using the authenticated gh CLI."
    )
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name form.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Local directory for snapshots and state.")
    parser.add_argument("--state", type=Path, help="Optional state file outside the output directory.")
    parser.add_argument("--force", action="store_true", help="Take an additional timestamped snapshot on the same UTC date.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        path, status = save_snapshot(
            args.repo,
            args.output_dir.resolve(),
            state_path=args.state.resolve() if args.state else None,
            force=args.force,
        )
    except SnapshotError as exc:
        print(f"GitHub Traffic snapshot failed: {exc}", file=sys.stderr)
        return 1
    if status.startswith("skipped"):
        print(f"No snapshot written: {status} ({path or 'no previous path recorded'}).")
    else:
        print(f"GitHub Traffic snapshot written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

