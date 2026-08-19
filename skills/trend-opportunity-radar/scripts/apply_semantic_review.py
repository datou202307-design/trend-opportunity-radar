from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Any

from _common import as_text, load_data, write_json
from research_context import load_context


RELEVANCE = {"direct", "adjacent", "weak"}
ROLES = {"support", "counter", "neutral"}


def apply_review(extraction: Any, review: Any, context: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(extraction, dict) or not isinstance(extraction.get("signals"), list):
        raise SystemExit("Extraction requires a signals array.")
    items = review.get("reviews") if isinstance(review, dict) else None
    if not isinstance(items, list) or not items:
        raise SystemExit("Semantic review requires a non-empty reviews array.")
    known = {as_text(item.get("content_id")): item for item in extraction["signals"] if isinstance(item, dict)}
    reviewed: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise SystemExit("Every semantic review must be an object.")
        key = as_text(item.get("content_id"))
        relevance = as_text(item.get("semantic_relevance"))
        role = as_text(item.get("evidence_role"))
        reason = as_text(item.get("reason"))
        topic_key = as_text(item.get("topic_key"))
        profile_role = as_text(item.get("profile_evidence_role"))
        if key not in known or key in reviewed:
            raise SystemExit("Semantic review must reference one unique extracted content_id.")
        if relevance not in RELEVANCE or role not in ROLES or not reason:
            raise SystemExit("Every review requires semantic_relevance, evidence_role, and a concrete reason.")
        if relevance in {"direct", "adjacent"} and (not topic_key or topic_key in {"unreviewed", "excluded-keyword-collision"}):
            raise SystemExit("Direct and adjacent reviews require a meaningful provisional topic_key for later cluster audit.")
        if context and relevance in {"direct", "adjacent"} and profile_role not in set(context["evidence_roles"]):
            raise SystemExit("Direct and adjacent reviews require a profile_evidence_role allowed by the frozen research context.")
        signal = known[key]
        signal["semantic_relevance"] = relevance
        signal["evidence_role"] = role
        if profile_role:
            signal["profile_evidence_role"] = profile_role
        signal["semantic_review"] = {"status": "agent_reviewed", "reason": reason}
        if relevance == "weak":
            signal["topic_key"] = "excluded-keyword-collision"
        else:
            signal["topic_key"] = topic_key
        reviewed.add(key)
    extraction["semantic_review_audit"] = {
        "reviewed_count": len(reviewed),
        "unreviewed_count": len(known) - len(reviewed),
        "review_file_required": True,
    }
    return extraction


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply an explicit semantic review to mechanically extracted platform cards.")
    parser.add_argument("--extraction", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-ledger", required=True)
    parser.add_argument("--research-context")
    args = parser.parse_args()
    extraction_path = Path(args.extraction).resolve()
    review_path = Path(args.review).resolve()
    output_path = Path(args.output).resolve()
    extraction = load_data(str(extraction_path))
    query_id = as_text(extraction.get("query_id")) if isinstance(extraction, dict) else ""
    if not query_id or query_id.casefold() not in review_path.stem.casefold() or query_id.casefold() not in output_path.stem.casefold():
        raise SystemExit("Semantic review and reviewed extraction filenames must include the extraction query_id.")
    context = load_context(Path(args.research_context).resolve()) if args.research_context else None
    reviewed = apply_review(extraction, load_data(str(review_path)), context)
    # Preserve the query id in the reviewed extraction. It is required to
    # distinguish the same frozen term executed in multiple communities while
    # the hashes below continue to bind the review audit deterministically.
    write_json(str(output_path), reviewed)
    ledger_path = Path(args.audit_ledger).resolve()
    ledger = load_data(str(ledger_path)) if ledger_path.exists() else {"schema_version": "semantic-review-ledger-v0.1", "entries": []}
    entries = ledger.get("entries") if isinstance(ledger, dict) else None
    if not isinstance(entries, list):
        raise SystemExit("Semantic review audit ledger requires an entries array.")
    source_hash = hashlib.sha256(extraction_path.read_bytes()).hexdigest()
    review_hash = hashlib.sha256(review_path.read_bytes()).hexdigest()
    key = (query_id, source_hash, review_hash)
    if not any((as_text(item.get("query_id")), as_text(item.get("extraction_sha256")), as_text(item.get("review_sha256"))) == key for item in entries if isinstance(item, dict)):
        entries.append({"query_id": query_id, "extraction": str(extraction_path), "review": str(review_path),
                        "reviewed_extraction": str(output_path), "extraction_sha256": source_hash,
                        "review_sha256": review_hash, "reviewed_count": reviewed["semantic_review_audit"]["reviewed_count"],
                        "unreviewed_count": reviewed["semantic_review_audit"]["unreviewed_count"],
                        **({"research_intent": context["research_intent"], "profile_version": context["profile_version"]} if context else {})})
    write_json(str(ledger_path), ledger)


if __name__ == "__main__":
    main()
