from __future__ import annotations

import argparse
from pathlib import Path

from _common import load_data, now_iso, write_json


def subject_name(subject: dict) -> str:
    return str(subject.get("name") or subject.get("title") or subject.get("summary") or "Untitled research topic").strip()


def statement(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("statement") or value.get("summary") or value)
    return str(value)


def fallback_opportunity(topic: dict, subject: dict) -> dict:
    name = subject_name(subject)
    audience = (subject.get("audiences") or ["people discussing this platform topic"])[0]
    return {
        "title": f"Validate the connection between {topic.get('title')} and {name}",
        "topic_key": topic.get("topic_key"),
        "audience": audience,
        "task_gap": "The platform signal exists, but the user's concrete unresolved task has not yet been verified.",
        "subject_entry": f"Test whether {name} can address one step in that task without extending unverified claims.",
        "expected_action": "Run a small evidence-gathering or user test before creating formal content.",
        "support_refs": topic.get("evidence_refs", []),
        "counter_refs": [],
        "counter_review": "",
        "risk_boundaries": ["Treat this as a candidate hypothesis, not a confirmed market conclusion."],
        "missing_evidence": ["Counterevidence review has not been completed.", *topic.get("missing_fields", [])],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate opportunity gates and render a standalone report.")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--signals", required=True)
    parser.add_argument("--opportunities")
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()
    subject = load_data(args.subject)
    snapshot = load_data(args.signals)
    supplied = load_data(args.opportunities) if args.opportunities else []
    if isinstance(supplied, dict):
        supplied = supplied.get("opportunities", [])
    opportunities = supplied or [fallback_opportunity(topic, subject) for topic in snapshot.get("topics", [])]
    for item in opportunities:
        gates = {
            "audience_relevance": bool(item.get("audience")),
            "task_continuity": bool(item.get("task_gap") and item.get("subject_entry")),
            "subject_boundary": bool(item.get("risk_boundaries")),
            "supporting_evidence": bool(item.get("support_refs")),
            "counterevidence_review": bool(item.get("counter_refs") or item.get("counter_review")),
            "concrete_action": bool(item.get("expected_action")),
        }
        item["gates"] = gates
        item["evidence_status"] = "review_ready" if all(gates.values()) else "candidate"
    result = {
        "schema_version": "trend-opportunity-report-v0.1",
        "generated_at": now_iso(),
        "subject": subject,
        "platform": snapshot.get("platform"),
        "topics": snapshot.get("topics", []),
        "opportunities": opportunities,
        "limitations": list(dict.fromkeys(limit for signal in snapshot.get("signals", []) for limit in signal.get("limitations", []))),
    }
    write_json(args.json_output, result)
    lines = [
        f"# Trend opportunities: {subject_name(subject)} on {snapshot.get('platform') or 'unspecified platform'}",
        "",
        f"Generated: {result['generated_at']}",
        "",
        "## Research topic and assumptions",
        "",
        f"- Subject type: {subject.get('subject_type', 'unspecified')}",
        f"- Summary: {subject.get('summary', '')}",
    ]
    lines.extend([f"- Fact: {statement(item)}" for item in subject.get("facts", [])] or ["- Facts: none supplied"])
    lines.extend([f"- Hypothesis: {statement(item)}" for item in subject.get("hypotheses", [])] or ["- Hypotheses: none supplied"])
    lines.extend([
        "",
        "## Platform heat",
        "",
    ])
    for topic in result["topics"]:
        lines.extend([
            f"### {topic.get('title')}",
            "",
            f"- Status: {topic.get('status')}",
            f"- Evidence heat index: {topic.get('heat_index')}/100",
            f"- Data coverage: {topic.get('data_coverage')}%",
            f"- Samples: {topic.get('sample_count')}",
            f"- Missing fields: {', '.join(topic.get('missing_fields', [])) or 'none'}",
            "",
        ])
    lines.extend(["## Trend × research topic opportunities", ""])
    for item in opportunities:
        lines.extend([
            f"### {item.get('title', 'Untitled opportunity')}",
            "",
            f"- Evidence status: {item['evidence_status']}",
            f"- Audience: {item.get('audience', '')}",
            f"- Task gap: {item.get('task_gap', '')}",
            f"- Topic entry: {item.get('subject_entry', '')}",
            f"- Next action: {item.get('expected_action', '')}",
            f"- Supporting evidence: {'; '.join(item.get('support_refs', [])) or 'none listed'}",
            f"- Counterevidence: {'; '.join(item.get('counter_refs', [])) or item.get('counter_review', 'not reviewed')}",
            f"- Risk boundaries: {'; '.join(item.get('risk_boundaries', []))}",
            f"- Missing evidence: {'; '.join(item.get('missing_evidence', [])) or 'none listed'}",
            "",
        ])
    lines.extend(["## Supporting and counterevidence", ""])
    for item in opportunities:
        lines.append(f"- {item.get('title', 'Untitled opportunity')} — support: {'; '.join(item.get('support_refs', [])) or 'none listed'}")
        lines.append(f"- {item.get('title', 'Untitled opportunity')} — counterevidence: {'; '.join(item.get('counter_refs', [])) or item.get('counter_review', 'not reviewed')}")
    lines.extend(["", "## Risks and boundaries", ""])
    risks = list(dict.fromkeys(risk for item in opportunities for risk in item.get("risk_boundaries", [])))
    lines.extend([f"- {risk}" for risk in risks] or ["- No risk boundaries supplied; keep all opportunities as candidates."])
    lines.extend(["", "## Recommended validation actions", ""])
    actions = list(dict.fromkeys(item.get("expected_action", "") for item in opportunities if item.get("expected_action")))
    lines.extend([f"- {action}" for action in actions] or ["- Define one observable validation action before promotion."])
    lines.extend(["", "## Data gaps and recollection tasks", ""])
    gaps = list(dict.fromkeys(
        [gap for topic in result["topics"] for gap in topic.get("missing_fields", [])]
        + [gap for item in opportunities for gap in item.get("missing_evidence", [])]
    ))
    lines.extend([f"- {gap}" for gap in gaps] or ["- No declared gaps; still review source limitations before confirmation."])
    lines.append("")
    if result["limitations"]:
        lines.extend(["## Limitations", ""] + [f"- {item}" for item in result["limitations"]] + [""])
    target = Path(args.markdown_output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
