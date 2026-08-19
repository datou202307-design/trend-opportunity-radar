from __future__ import annotations

import argparse
import copy
from typing import Any

from _common import as_text, load_data, now_iso, write_json
from prepare_video_review import SCHEMA_VERSION as QUEUE_SCHEMA_VERSION
from video_evidence import signal_key


SCHEMA_VERSION = "video-content-review-v0.1"
CHANNELS = {"native_subtitle", "asr", "ocr"}
RELEVANCE = {"direct", "adjacent", "weak"}
ROLES = {"support", "counter", "neutral"}
FORMATS = {"video", "slideshow", "audio", "unknown"}


def normalized(value: Any) -> str:
    return " ".join(as_text(value).split()).casefold()


def channel_texts(item: dict[str, Any], channel: str) -> list[str]:
    if channel == "ocr":
        return [as_text(row.get("text")) for row in (item.get("visual_text") or {}).get("rows", []) if isinstance(row, dict)]
    transcript = item.get("transcript") or {}
    if transcript.get("provenance") != channel:
        return []
    return [as_text(row.get("text")) for row in transcript.get("segments", []) if isinstance(row, dict)]


def require_review(queue: dict[str, Any], review: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if queue.get("schema_version") != QUEUE_SCHEMA_VERSION:
        raise SystemExit(f"Video review queue must use {QUEUE_SCHEMA_VERSION}.")
    if review.get("schema_version") != SCHEMA_VERSION:
        raise SystemExit(f"Video review must use {SCHEMA_VERSION}.")
    if review.get("queue_sha256") != queue.get("queue_sha256"):
        raise SystemExit("Video review queue_sha256 does not match the unchanged queue.")
    queued = {as_text(item.get("signal_key")): item for item in queue.get("items", []) if isinstance(item, dict)}
    rows = review.get("reviews")
    if not isinstance(rows, list):
        raise SystemExit("Video review reviews must be an array.")
    indexed: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"reviews[{index}] must be an object.")
            continue
        key = as_text(row.get("signal_key"))
        item = queued.get(key)
        if not key or key in indexed:
            errors.append(f"reviews[{index}].signal_key must be non-empty and unique.")
            continue
        if item is None:
            errors.append(f"reviews[{index}].signal_key is not in the queue.")
            continue
        if row.get("content_format") not in FORMATS:
            errors.append(f"reviews[{index}].content_format is invalid.")
        if not as_text(row.get("summary")):
            errors.append(f"reviews[{index}].summary is required.")
        channels = row.get("usable_channels")
        if not isinstance(channels, list) or not channels or any(channel not in CHANNELS for channel in channels):
            errors.append(f"reviews[{index}].usable_channels must contain supported channels.")
        excerpts = row.get("excerpts")
        if not isinstance(excerpts, list) or not excerpts or len(excerpts) > 4:
            errors.append(f"reviews[{index}].excerpts must contain 1 to 4 items.")
            excerpts = []
        for excerpt_index, excerpt in enumerate(excerpts):
            prefix = f"reviews[{index}].excerpts[{excerpt_index}]"
            if not isinstance(excerpt, dict):
                errors.append(f"{prefix} must be an object.")
                continue
            channel = excerpt.get("channel")
            excerpt_text = as_text(excerpt.get("text"))
            if channel not in CHANNELS:
                errors.append(f"{prefix}.channel is invalid.")
            if excerpt.get("semantic_relevance") not in RELEVANCE:
                errors.append(f"{prefix}.semantic_relevance is invalid.")
            if excerpt.get("evidence_role") not in ROLES:
                errors.append(f"{prefix}.evidence_role is invalid.")
            if not as_text(excerpt.get("reason")):
                errors.append(f"{prefix}.reason is required.")
            source_texts = channel_texts(item, str(channel))
            normalized_excerpt = normalized(excerpt_text)
            verbatim_match = any(
                normalized_excerpt == normalized(source) or (
                    len(normalized_excerpt) >= 12 and normalized_excerpt in normalized(source)
                )
                for source in source_texts
            )
            if not excerpt_text or not verbatim_match:
                errors.append(f"{prefix}.text must be a verbatim row or bounded contiguous excerpt from one queued {channel} row.")
        indexed[key] = row
    missing = set(queued) - set(indexed)
    if missing:
        errors.append(f"Missing reviews for {len(missing)} queued video items.")
    if errors:
        raise SystemExit("Video review validation failed:\n- " + "\n- ".join(errors))
    return indexed


def apply(snapshot: dict[str, Any], queue: dict[str, Any], review: dict[str, Any]) -> dict[str, Any]:
    indexed = require_review(queue, review)
    merged = copy.deepcopy(snapshot)
    reviewed = relevant = 0
    source_refs: list[str] = []
    for signal in merged.get("signals", []):
        if not isinstance(signal, dict):
            continue
        row = indexed.get(signal_key(signal))
        evidence = signal.get("content_evidence") if isinstance(signal.get("content_evidence"), dict) else None
        if row is None or evidence is None:
            continue
        excerpts = [dict(item) for item in row["excerpts"]]
        relevant_excerpts = [item for item in excerpts if item.get("semantic_relevance") in {"direct", "adjacent"}]
        evidence["semantic_review"] = {
            "status": "reviewed",
            "review_version": SCHEMA_VERSION,
            "reviewed_at": now_iso(),
            "content_format": row["content_format"],
            "usable_channels": list(dict.fromkeys(row["usable_channels"])),
            "summary": as_text(row["summary"]),
            "excerpts": excerpts,
            "relevant_excerpt_count": len(relevant_excerpts),
            "limitations": [as_text(item) for item in row.get("limitations", []) if as_text(item)],
        }
        promotion = evidence.get("promotion_audit") if isinstance(evidence.get("promotion_audit"), dict) else {}
        promotion["pending_semantic_review"] = False
        promotion["review_supported_promotion"] = bool(relevant_excerpts)
        evidence["promotion_audit"] = promotion
        if not relevant_excerpts and promotion:
            signal["detail_captured"] = bool(promotion.get("previous_detail_captured"))
            signal["source_type"] = as_text(promotion.get("previous_source_type")) or "search_card"
            stale = "The adapter did not provide publication time or an independent detail read; the item remains search-card evidence."
            if stale not in signal.setdefault("limitations", []):
                signal["limitations"].append(stale)
        reviewed += 1
        if relevant_excerpts:
            relevant += 1
        if as_text(signal.get("canonical_url")):
            source_refs.append(as_text(signal["canonical_url"]))
    audit = merged.setdefault("video_evidence", {})
    audit.update({
        "semantic_review_status": "complete",
        "semantic_review_version": SCHEMA_VERSION,
        "reviewed_count": reviewed,
        "relevant_reviewed_count": relevant,
        "source_refs": list(dict.fromkeys(source_refs)),
        "semantic_rereview_required": False,
        "reviewed_at": now_iso(),
    })
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and merge reviewed video evidence into a signal snapshot.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--queue", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot, queue, review = load_data(args.input), load_data(args.queue), load_data(args.review)
    if not all(isinstance(item, dict) for item in (snapshot, queue, review)):
        raise SystemExit("Video review inputs must be JSON objects.")
    write_json(args.output, apply(snapshot, queue, review))


if __name__ == "__main__":
    main()
