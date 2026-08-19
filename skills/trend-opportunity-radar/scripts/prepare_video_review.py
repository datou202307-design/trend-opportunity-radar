from __future__ import annotations

import argparse
import hashlib
import json
from typing import Any

from _common import as_text, load_data, now_iso, write_json
from video_evidence import signal_key


SCHEMA_VERSION = "video-content-review-queue-v0.1"


def build_queue(snapshot: dict[str, Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for signal in snapshot.get("signals", []):
        if not isinstance(signal, dict):
            continue
        evidence = signal.get("content_evidence") if isinstance(signal.get("content_evidence"), dict) else {}
        if evidence.get("status") not in {"complete", "partial"}:
            continue
        transcript = evidence.get("transcript") if isinstance(evidence.get("transcript"), dict) else {}
        visual = evidence.get("visual_text") if isinstance(evidence.get("visual_text"), dict) else {}
        transcript_rows = transcript.get("segments") if isinstance(transcript.get("segments"), list) else []
        visual_rows = visual.get("rows") if isinstance(visual.get("rows"), list) else []
        if not transcript_rows and not visual_rows:
            continue
        entries.append({
            "signal_key": signal_key(signal),
            "signal_id": as_text(signal.get("signal_id")),
            "topic_key": as_text(signal.get("topic_key")),
            "source_url": as_text(signal.get("canonical_url")),
            "existing_semantic_relevance": as_text(signal.get("semantic_relevance")),
            "existing_evidence_role": as_text(signal.get("evidence_role")),
            "content_format_detected": as_text((evidence.get("metadata") or {}).get("content_format_detected")) or "unknown",
            "transcript": {
                "provenance": as_text(transcript.get("provenance")) or "unknown",
                "segments": transcript_rows,
            },
            "visual_text": {
                "provenance": as_text(visual.get("provenance")) or "ocr",
                "rows": visual_rows,
            },
            "limitations": [as_text(item) for item in evidence.get("limitations", []) if as_text(item)],
        })
    canonical = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "platform": as_text(snapshot.get("platform")),
        "item_count": len(entries),
        "queue_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "items": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare media-derived text for bounded semantic review.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    snapshot = load_data(args.input)
    if not isinstance(snapshot, dict):
        raise SystemExit("Video review input must be a signal snapshot object.")
    write_json(args.output, build_queue(snapshot))


if __name__ == "__main__":
    main()
