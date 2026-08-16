from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from _common import as_text, load_data, now_iso, write_json
from research_context import load_context


VALID_FITS = {"core", "supporting", "counter"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply an explicit semantic clustering plan and audit cluster coherence gates.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--research-context")
    args = parser.parse_args()

    snapshot = load_data(args.input)
    plan = load_data(args.plan)
    context = load_context(Path(args.research_context).resolve()) if args.research_context else None
    signals = snapshot.get("signals", []) if isinstance(snapshot, dict) else []
    clusters = plan.get("clusters", []) if isinstance(plan, dict) else []
    if not isinstance(signals, list) or not isinstance(clusters, list) or not clusters:
        raise SystemExit("Input requires signals and plan requires a non-empty clusters array.")

    by_id = {as_text(item.get("signal_id")): item for item in signals if as_text(item.get("signal_id"))}
    seen: set[str] = set()
    audits: list[dict[str, Any]] = []
    for cluster in clusters:
        if not isinstance(cluster, dict):
            raise SystemExit("Each cluster must be an object.")
        key = as_text(cluster.get("topic_key"))
        title = as_text(cluster.get("title"))
        transition = as_text(cluster.get("analysis_unit_statement") or cluster.get("task_transition"))
        inclusion = as_text(cluster.get("inclusion_rule"))
        exclusion = as_text(cluster.get("exclusion_rule"))
        assignments = cluster.get("assignments", [])
        if not all((key, title, transition, inclusion, exclusion)) or not isinstance(assignments, list):
            raise SystemExit("Every cluster needs topic_key, title, task_transition, inclusion_rule, exclusion_rule, and assignments.")
        if len(title) > 120 or title == key or any(marker in title for marker in ("**", "__", "http://", "https://")):
            raise SystemExit("Cluster title must be a concise reader-facing topic label, not a key, URL, or source-card Markdown title.")
        members = []
        for assignment in assignments:
            signal_id = as_text((assignment or {}).get("signal_id")) if isinstance(assignment, dict) else ""
            fit = as_text((assignment or {}).get("fit")) if isinstance(assignment, dict) else ""
            reason = as_text((assignment or {}).get("reason")) if isinstance(assignment, dict) else ""
            transition_match = (assignment or {}).get("task_transition_match") if isinstance(assignment, dict) else None
            if signal_id not in by_id or signal_id in seen or fit not in VALID_FITS or not reason or not isinstance(transition_match, bool):
                raise SystemExit("Assignments need a unique known signal_id, valid fit, reason, and boolean task_transition_match.")
            seen.add(signal_id)
            by_id[signal_id]["topic_key"] = key
            members.append((by_id[signal_id], assignment))
        author_ids = {as_text((item[0].get("author") or {}).get("id")) for item in members if as_text((item[0].get("author") or {}).get("id"))}
        direct_count = sum(1 for item, _ in members if item.get("detail_captured") or item.get("source_type") in {"direct_post", "exported_item"})
        core_count = sum(1 for _, assignment in members if assignment["fit"] == "core")
        match_count = sum(1 for _, assignment in members if assignment["task_transition_match"])
        subject_bridge_count = sum(1 for item, _ in members if "subject_bridge" in {item.get("query_layer"), *(item.get("query_layers") or [])})
        checks = {
            "member_count": len(members) >= 3,
            "author_diversity": len(author_ids) >= 2,
            "direct_source": direct_count >= 1,
            "core_members": core_count >= 2,
            "task_transition_match": match_count / max(len(members), 1) >= 0.8,
            "subject_bridge_member": subject_bridge_count >= 1,
        }
        profile_roles = sorted({as_text(item.get("profile_evidence_role")) for item, _ in members if as_text(item.get("profile_evidence_role"))})
        if context:
            checks["profile_role_coverage"] = len(profile_roles) >= int(context["decision_thresholds"]["minimum_profile_roles"])
        audits.append({
            "topic_key": key,
            "title": title,
            "task_transition": transition,
            "analysis_unit": context["analysis_unit"] if context else "user_task_or_unmet_need",
            "analysis_unit_statement": transition,
            "profile_evidence_roles": profile_roles,
            "inclusion_rule": inclusion,
            "exclusion_rule": exclusion,
            "status": "passed" if all(checks.values()) else "failed",
            "checks": checks,
            "member_count": len(members),
            "author_count": len(author_ids),
            "direct_source_count": direct_count,
            "core_member_count": core_count,
            "task_transition_match_rate": round(match_count / max(len(members), 1), 3),
            "subject_bridge_member_count": subject_bridge_count,
            "fit_counts": dict(Counter(assignment["fit"] for _, assignment in members)),
            "assignments": assignments,
        })

    unassigned = sorted(set(by_id) - seen)
    if unassigned:
        raise SystemExit(f"Clustering plan must assign every signal exactly once; unassigned: {', '.join(unassigned[:10])}")
    snapshot["clustering"] = {
        "applied": True,
        "audited_at": now_iso(),
        "cluster_count": len(audits),
        "passed_count": sum(1 for item in audits if item["status"] == "passed"),
        "failed_count": sum(1 for item in audits if item["status"] == "failed"),
    }
    snapshot["cluster_audits"] = audits
    write_json(args.output, snapshot)


if __name__ == "__main__":
    main()
