from __future__ import annotations

import argparse
import copy
import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import load_data, text_integrity_issues, write_json


CONTRACT_VERSION = "video-evidence-contract-v0.1"
ANALYZER_NAME = "mcp-video-analyzer"
ANALYZER_VERSION = "0.8.0"
VIDEO_PLATFORMS = {"tiktok", "instagram", "youtube", "x"}
MAX_CANDIDATES = 10
MAX_FRAMES = 8
MAX_TRANSCRIPT_SEGMENTS = 200
MAX_OCR_ROWS = 80


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def text(value: Any) -> str:
    return str(value or "").strip()


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def timestamp_seconds(value: Any) -> float | None:
    direct = number(value)
    if direct is not None:
        return direct
    raw = text(value)
    if not raw or ":" not in raw:
        return None
    try:
        parts = [float(item) for item in raw.split(":")]
    except ValueError:
        return None
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return None


def signal_key(signal: dict[str, Any]) -> str:
    platform = text(signal.get("platform")).casefold()
    identity = text(signal.get("content_id") or signal.get("canonical_url"))
    return hashlib.sha256(f"{platform}:{identity}".encode("utf-8")).hexdigest()


def is_video_signal(signal: dict[str, Any]) -> bool:
    platform = text(signal.get("platform")).casefold()
    facts = signal.get("platform_facts") if isinstance(signal.get("platform_facts"), dict) else {}
    content_format = text(facts.get("content_format") or signal.get("content_format")).casefold()
    url = text(signal.get("canonical_url")).casefold()
    return bool(
        url
        and (
            platform in VIDEO_PLATFORMS
            or content_format in {"video", "short_video", "reel"}
            or "/video/" in url
            or "youtu.be/" in url
            or "youtube.com/watch" in url
        )
    )


def engagement_score(signal: dict[str, Any]) -> float:
    metrics = signal.get("metrics") if isinstance(signal.get("metrics"), dict) else {}
    weighted = 0.0
    for field, weight in (("views", 0.05), ("likes", 1.0), ("comments", 2.0), ("shares", 2.5), ("saves", 2.5)):
        value = number(metrics.get(field))
        if value is not None and value > 0:
            weighted += value * weight
    return math.log1p(weighted)


def candidate_priority(signal: dict[str, Any]) -> tuple[float, str]:
    relevance = {"direct": 400.0, "adjacent": 300.0, "unreviewed": 150.0, "weak": 50.0}.get(
        text(signal.get("semantic_relevance")).casefold(), 0.0
    )
    layers = {text(signal.get("query_layer")), *[text(item) for item in (signal.get("query_layers") or [])]}
    layer_bonus = 70.0 if "subject_bridge" in layers else 0.0
    counter_bonus = 40.0 if signal.get("evidence_role") == "counter" else 0.0
    unopened_bonus = 20.0 if not signal.get("detail_captured") else 0.0
    return (relevance + layer_bonus + counter_bonus + unopened_bonus + engagement_score(signal), signal_key(signal))


def select_candidates(snapshot: dict[str, Any], limit: int = MAX_CANDIDATES) -> dict[str, Any]:
    if limit < 1 or limit > MAX_CANDIDATES:
        raise ValueError(f"Candidate limit must be between 1 and {MAX_CANDIDATES}.")
    rows = [item for item in snapshot.get("signals", []) if isinstance(item, dict) and is_video_signal(item)]
    ranked = sorted(rows, key=candidate_priority, reverse=True)
    chosen: list[dict[str, Any]] = []
    seen_authors: set[str] = set()
    deferred: list[dict[str, Any]] = []

    def add(signal: dict[str, Any]) -> bool:
        author = signal.get("author") if isinstance(signal.get("author"), dict) else {}
        author_key = text(author.get("id") or author.get("name")).casefold()
        if author_key and author_key in seen_authors:
            return False
        chosen.append(signal)
        if author_key:
            seen_authors.add(author_key)
        return True

    # A small media review must not spend its whole budget on one evidence
    # direction merely because counterevidence receives a ranking bonus.
    # Keep the highest-priority item, then include the opposite observed role
    # when both support and counter candidates exist.
    if ranked:
        add(ranked[0])
    if limit >= 2 and chosen:
        first_role = text(chosen[0].get("evidence_role"))
        opposite_role = "support" if first_role == "counter" else "counter"
        opposite = next((item for item in ranked[1:] if text(item.get("evidence_role")) == opposite_role and add(item)), None)
    for signal in ranked:
        if signal in chosen:
            continue
        author = signal.get("author") if isinstance(signal.get("author"), dict) else {}
        author_key = text(author.get("id") or author.get("name")).casefold()
        if author_key and author_key in seen_authors:
            deferred.append(signal)
            continue
        add(signal)
        if len(chosen) >= limit:
            break
    if len(chosen) < limit:
        for signal in deferred:
            chosen.append(signal)
            if len(chosen) >= limit:
                break
    candidates = []
    for rank, signal in enumerate(chosen, 1):
        author = signal.get("author") if isinstance(signal.get("author"), dict) else {}
        candidates.append({
            "rank": rank,
            "signal_key": signal_key(signal),
            "signal_id": text(signal.get("signal_id")),
            "content_id": text(signal.get("content_id")),
            "platform": text(signal.get("platform")).casefold(),
            "url": text(signal.get("canonical_url")),
            "author": text(author.get("id") or author.get("name")),
            "query_layers": list(dict.fromkeys([text(signal.get("query_layer")), *[text(item) for item in (signal.get("query_layers") or [])]])),
            "semantic_relevance": text(signal.get("semantic_relevance")) or "unreviewed",
            "evidence_role": text(signal.get("evidence_role")) or "neutral",
            "selection_score": round(candidate_priority(signal)[0], 4),
        })
    return {
        "schema_version": "video-evidence-plan-v0.1",
        "contract_version": CONTRACT_VERSION,
        "created_at": now_iso(),
        "source_snapshot_schema": text(snapshot.get("schema_version")),
        "source_platform": text(snapshot.get("platform")),
        "candidate_limit": limit,
        "eligible_count": len(rows),
        "selected_count": len(candidates),
        "selection_policy": "relevance_then_subject_bridge_role_balance_engagement_with_author_diversity",
        "candidates": candidates,
    }


def analyzer_arguments(url: str, output_dir: Path) -> list[str]:
    return [
        "analyze", url,
        "--detail", "standard", "--max-frames", str(MAX_FRAMES),
        "--fields", "metadata,transcript,frames,ocrResults,timeline",
        "--out", str(output_dir),
    ]


def analyzer_command(url: str, output_dir: Path) -> list[str]:
    return ["npx", "-y", f"{ANALYZER_NAME}@{ANALYZER_VERSION}", *analyzer_arguments(url, output_dir)]


def transcript_rows(value: Any) -> list[dict[str, Any]]:
    source = value.get("segments") if isinstance(value, dict) else value
    if not isinstance(source, list):
        return []
    rows = []
    for item in source[:MAX_TRANSCRIPT_SEGMENTS]:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict) or not text(item.get("text") or item.get("content")):
            continue
        rows.append({
            "start_seconds": timestamp_seconds(item.get("start") if item.get("start") is not None else item.get("startSeconds") or item.get("start_seconds") or item.get("time")),
            "end_seconds": timestamp_seconds(item.get("end") if item.get("end") is not None else item.get("endSeconds") or item.get("end_seconds") or item.get("endTime")),
            "text": text(item.get("text") or item.get("content"))[:2000],
        })
    return rows


def ocr_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value[:MAX_OCR_ROWS]:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict) or not text(item.get("text")):
            continue
        row = {
            "timestamp_seconds": timestamp_seconds(item.get("time") if item.get("time") is not None else item.get("timestamp") or item.get("timestampSeconds") or item.get("timestamp_seconds")),
            "text": text(item.get("text"))[:1000],
            "confidence": number(item.get("confidence")),
        }
        if not text_integrity_issues(row["text"]):
            rows.append(row)
    return rows


def keyframe_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value[:MAX_FRAMES]:
        if not isinstance(item, dict):
            continue
        rows.append({
            "timestamp_seconds": timestamp_seconds(item.get("time") if item.get("time") is not None else item.get("timestamp") or item.get("timestampSeconds")),
            "artifact_retained": False,
        })
    return rows


def normalize_result(raw: dict[str, Any], candidate: dict[str, Any], raw_artifact: str) -> dict[str, Any]:
    transcript_value = raw.get("transcript")
    transcript = transcript_rows(transcript_value)
    raw_ocr = raw.get("ocrResults") or raw.get("ocr_results")
    ocr = ocr_rows(raw_ocr)
    frames = keyframe_rows(raw.get("frames"))
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    warnings = [text(item) for item in raw.get("warnings", []) if text(item)] if isinstance(raw.get("warnings"), list) else []
    raw_ocr_count = len(raw_ocr) if isinstance(raw_ocr, list) else 0
    if raw_ocr_count > len(ocr):
        warnings.append(f"Filtered {raw_ocr_count - len(ocr)} OCR row(s) with suspected encoding corruption; raw analyzer output remains preserved.")
    provenance = text(transcript_value.get("source")) if isinstance(transcript_value, dict) else ""
    provenance = provenance.casefold().replace(" ", "_")
    if provenance not in {"native_subtitle", "asr"}:
        provenance = "asr" if transcript and any("whisper" in item.casefold() for item in warnings) else "unknown"
    # Keyframes alone prove that a media stream was opened, not that its meaning
    # was understood. Only bounded transcript or OCR text can enrich evidence.
    usable = bool(transcript or ocr)
    status = "partial" if usable and warnings else "complete" if usable else "unavailable"
    content_format = "video" if frames else "audio_or_slideshow" if any("does not contain any stream" in item.casefold() for item in warnings) else "unknown"
    return {
        "signal_key": candidate["signal_key"],
        "success": usable,
        "content_evidence": {
            "contract_version": CONTRACT_VERSION,
            "status": status,
            "analyzer": {"name": ANALYZER_NAME, "version": ANALYZER_VERSION},
            "analyzed_at": now_iso(),
            "source_url": candidate["url"],
            "transcript": {
                "provenance": provenance,
                "language": text(transcript_value.get("language")) if isinstance(transcript_value, dict) else "",
                "segments": transcript,
            },
            "visual_text": {"provenance": "ocr", "rows": ocr},
            "keyframes": frames,
            "metadata": {
                "title": text(metadata.get("title"))[:500],
                "duration_seconds": number(metadata.get("duration") or metadata.get("durationSeconds")),
                "uploader": text(metadata.get("uploader") or metadata.get("channel"))[:300],
                "upload_date": text(metadata.get("uploadDate") or metadata.get("upload_date"))[:100],
                "content_format_detected": content_format,
            },
            "raw_artifact": raw_artifact,
            "limitations": warnings,
        },
    }


def merge_results(snapshot: dict[str, Any], results: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(snapshot)
    by_key = {
        text(item.get("signal_key")): item
        for item in results.get("results", [])
        if isinstance(item, dict) and item.get("success") and isinstance(item.get("content_evidence"), dict)
    }
    enriched = 0
    for signal in merged.get("signals", []):
        if not isinstance(signal, dict):
            continue
        result = by_key.get(signal_key(signal))
        if not result:
            continue
        content_evidence = copy.deepcopy(result["content_evidence"])
        visual_text = content_evidence.get("visual_text") if isinstance(content_evidence.get("visual_text"), dict) else {}
        imported_ocr = visual_text.get("rows") if isinstance(visual_text.get("rows"), list) else []
        sanitized_ocr = ocr_rows(imported_ocr)
        if len(sanitized_ocr) < len(imported_ocr):
            content_evidence.setdefault("limitations", []).append(
                f"Filtered {len(imported_ocr) - len(sanitized_ocr)} OCR row(s) with suspected encoding corruption during merge; raw analyzer output remains preserved."
            )
        if visual_text:
            visual_text["rows"] = sanitized_ocr
            content_evidence["visual_text"] = visual_text
        content_evidence["promotion_audit"] = {
            "previous_source_type": text(signal.get("source_type")) or "unknown",
            "previous_detail_captured": bool(signal.get("detail_captured")),
            "pending_semantic_review": True,
        }
        signal["content_evidence"] = content_evidence
        signal["detail_captured"] = True
        if signal.get("source_type") == "search_card":
            signal["source_type"] = "direct_post"
        raw_artifact = text(content_evidence.get("raw_artifact"))
        signal["evidence_refs"] = list(dict.fromkeys([*(signal.get("evidence_refs") or []), *([raw_artifact] if raw_artifact else [])]))
        stale = "The adapter did not provide publication time or an independent detail read; the item remains search-card evidence."
        signal["limitations"] = [item for item in signal.get("limitations", []) if text(item) != stale]
        if content_evidence.get("status") == "partial":
            signal["limitations"].append("Video content was only partially available; use the normalized transcript and visual text within their recorded limits.")
        enriched += 1
    audit = merged.setdefault("video_evidence", {})
    audit.update({
        "contract_version": CONTRACT_VERSION,
        "plan_artifact": text(results.get("plan_artifact")),
        "result_artifact": text(results.get("result_artifact")),
        "attempted_count": int(results.get("attempted_count") or len(results.get("results", []))),
        "enriched_count": enriched,
        "sample_count_unchanged": True,
        "semantic_rereview_required": enriched > 0,
    })
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan, normalize, or merge bounded video content evidence.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--snapshot", required=True)
    plan.add_argument("--output", required=True)
    plan.add_argument("--limit", type=int, default=MAX_CANDIDATES)
    normalize = sub.add_parser("normalize")
    normalize.add_argument("--input", required=True)
    normalize.add_argument("--candidate", required=True)
    normalize.add_argument("--output", required=True)
    merge = sub.add_parser("merge")
    merge.add_argument("--snapshot", required=True)
    merge.add_argument("--results", required=True)
    merge.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        write_json(args.output, select_candidates(load_data(args.snapshot), args.limit))
    elif args.command == "normalize":
        candidate = load_data(args.candidate)
        write_json(args.output, normalize_result(load_data(args.input), candidate, str(Path(args.input).resolve())))
    else:
        write_json(args.output, merge_results(load_data(args.snapshot), load_data(args.results)))


if __name__ == "__main__":
    main()
