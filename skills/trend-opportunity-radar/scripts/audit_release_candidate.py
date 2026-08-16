from __future__ import annotations

import argparse
from itertools import product
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json


COMPLETE_STATUSES = {"completed", "completed_bounded", "passed"}


def _case_passed(item: dict[str, Any]) -> bool:
    result = item.get("acceptance_result") or {}
    return (
        item.get("status") in COMPLETE_STATUSES
        and result.get("report_generated") is True
        and result.get("decision_profile_validated") is True
        and result.get("visual_qa") == "passed"
    )


def audit(matrix: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    platforms = [str(value) for value in matrix.get("platforms", [])]
    profiles = [str(value) for value in matrix.get("profiles", [])]
    policy = matrix.get("execution_policy") or {}
    cases = [item for item in matrix.get("cases", []) if isinstance(item, dict)]
    replay_cases = [item for item in replay.get("cases", []) if isinstance(item, dict)]
    required_live = int(policy.get("live_e2e_per_profile_platform") or 0)
    required_diverse_replays = int(policy.get("snapshot_replay_per_profile_platform") or 0)
    coverage = []
    gaps = []
    for intent, platform in product(profiles, platforms):
        matching = [item for item in cases if item.get("intent") == intent and item.get("platform") == platform]
        live_passed = sum(1 for item in matching if item.get("execution") == "live_e2e" and _case_passed(item))
        diverse_replays_passed = sum(
            1 for item in matching
            if item.get("execution") == "snapshot_replay" and _case_passed(item)
        )
        code_replays_passed = sum(
            1 for item in replay_cases
            if item.get("intent") == intent and item.get("platform") == platform and item.get("status") == "passed"
        )
        row = {
            "intent": intent,
            "platform": platform,
            "live_e2e": {"passed": live_passed, "required": required_live},
            "latest_code_replay": {"passed": code_replays_passed, "required": 1},
            "diverse_topic_snapshot_replay": {"passed": diverse_replays_passed, "required": required_diverse_replays},
        }
        coverage.append(row)
        if live_passed < required_live:
            gaps.append(f"{intent}/{platform}: live_e2e {live_passed}/{required_live}")
        if code_replays_passed < 1:
            gaps.append(f"{intent}/{platform}: latest_code_replay {code_replays_passed}/1")
        if diverse_replays_passed < required_diverse_replays:
            gaps.append(
                f"{intent}/{platform}: diverse_topic_snapshot_replay "
                f"{diverse_replays_passed}/{required_diverse_replays}"
            )
    return {
        "schema_version": "trend-release-audit-v0.1",
        "generated_at": now_iso(),
        "release_target": matrix.get("release_target"),
        "status": "ready" if not gaps else "blocked",
        "distinction": {
            "latest_code_replay": "Re-runs an existing real snapshot through the candidate code and proves upgrade compatibility.",
            "diverse_topic_snapshot_replay": "Uses a different topic snapshot and proves cross-topic generality. Code replay never counts toward this gate.",
        },
        "coverage": coverage,
        "gaps": gaps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a Trend Opportunity Radar release candidate without inflating replay coverage.")
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--code-replay-results", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = audit(load_data(args.matrix), load_data(args.code_replay_results))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    print(f"Release candidate status: {result['status']}; gaps: {len(result['gaps'])}")


if __name__ == "__main__":
    main()
