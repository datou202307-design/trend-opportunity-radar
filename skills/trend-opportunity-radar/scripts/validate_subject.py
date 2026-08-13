from __future__ import annotations

import argparse

from _common import as_text, load_data, text_integrity_issues


SUBJECT_TYPES = {"product", "opportunity", "idea", "problem", "project"}
COMMUNICATION_LANGUAGES = {"auto", "zh-CN", "en", "bilingual"}
RESEARCH_GOALS = {"validate_business_opportunity", "validate_product_demand", "discover_content_opportunities", "understand_trend", "general_research"}
AUDIENCE_LEVELS = {"general", "expert"}


def validate_subject(subject: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(subject, dict):
        return ["Subject must be a JSON object."]
    errors.extend(text_integrity_issues(subject))
    for field in ("name", "summary"):
        if not as_text(subject.get(field)):
            errors.append(f"Subject requires a non-empty {field}.")
    if subject.get("subject_type") not in SUBJECT_TYPES:
        errors.append(f"subject_type must be one of: {', '.join(sorted(SUBJECT_TYPES))}.")
    for field in ("facts", "hypotheses", "audiences", "scenarios", "constraints", "source_refs"):
        if not isinstance(subject.get(field, []), list):
            errors.append(f"{field} must be an array.")
    communication = subject.get("communication", {})
    if communication and not isinstance(communication, dict):
        errors.append("communication must be an object when supplied.")
    elif isinstance(communication, dict):
        if communication.get("language", "auto") not in COMMUNICATION_LANGUAGES:
            errors.append(f"communication.language must be one of: {', '.join(sorted(COMMUNICATION_LANGUAGES))}.")
        if communication.get("goal", "general_research") not in RESEARCH_GOALS:
            errors.append(f"communication.goal must be one of: {', '.join(sorted(RESEARCH_GOALS))}.")
        if communication.get("audience", "general") not in AUDIENCE_LEVELS:
            errors.append(f"communication.audience must be one of: {', '.join(sorted(AUDIENCE_LEVELS))}.")
    for index, fact in enumerate(subject.get("facts", []) if isinstance(subject.get("facts", []), list) else []):
        if not isinstance(fact, dict) or not as_text(fact.get("statement")):
            errors.append(f"facts[{index}] requires statement and source_refs.")
        elif not isinstance(fact.get("source_refs"), list) or not fact.get("source_refs"):
            errors.append(f"facts[{index}] requires at least one source reference.")
    for index, hypothesis in enumerate(subject.get("hypotheses", []) if isinstance(subject.get("hypotheses", []), list) else []):
        if isinstance(hypothesis, str) and hypothesis.strip():
            continue
        if not isinstance(hypothesis, dict) or not as_text(hypothesis.get("statement")):
            errors.append(f"hypotheses[{index}] must be text or an object with statement.")
        elif hypothesis.get("origin") not in {"user_premise", "model_inference"}:
            errors.append(f"hypotheses[{index}].origin must be user_premise or model_inference.")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the research subject contract before collection.")
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    subject = load_data(args.input)
    errors = validate_subject(subject)
    if errors:
        raise SystemExit("Subject validation failed:\n- " + "\n- ".join(errors))
    print("Subject is valid.")


if __name__ == "__main__":
    main()
