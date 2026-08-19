from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _common import as_text, load_data, write_json


def normalized_url(value: Any) -> str:
    return as_text(value).replace("https://reddit.com/", "https://www.reddit.com/").rstrip("/")


def apply_backfill(snapshot: Any, backfill: Any, artifact: str = "") -> dict[str, Any]:
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("signals"), list):
        raise SystemExit("Reddit detail backfill requires a snapshot with signals.")
    entries = backfill.get("entries") if isinstance(backfill, dict) else None
    execution = backfill.get("execution") if isinstance(backfill, dict) and isinstance(backfill.get("execution"), dict) else None
    if not isinstance(entries, list) or not entries:
        raise SystemExit("Reddit detail backfill requires a non-empty entries array.")
    by_id = {as_text(item.get("content_id")): item for item in snapshot["signals"] if isinstance(item, dict)}
    applied: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("Every Reddit detail entry must be an object.")
        content_id = as_text(entry.get("content_id"))
        url = normalized_url(entry.get("canonical_url"))
        body = as_text(entry.get("body_text"))
        body_text_kind = as_text(entry.get("body_text_kind"))
        captured_at = as_text(entry.get("captured_at"))
        if not content_id or content_id in seen or content_id not in by_id:
            raise SystemExit("Every Reddit detail entry must reference one unique known content_id.")
        signal = by_id[content_id]
        if signal.get("platform") != "reddit" or normalized_url(signal.get("canonical_url")) != url:
            raise SystemExit("Reddit detail URL must match the searched signal canonical URL.")
        if not body or body_text_kind not in {"verbatim_excerpt", "agent_summary"} or not captured_at or as_text(entry.get("source_mode")) != "public_web":
            raise SystemExit("Every Reddit detail requires body_text, body_text_kind, captured_at, and source_mode=public_web.")
        signal["detail_captured"] = True
        signal["source_type"] = "direct_post"
        signal["summary"] = body
        signal["detail_text_kind"] = body_text_kind
        signal["detail_access"] = {"url": signal["canonical_url"], "source": "public_reddit_permalink"}
        signal["detail_source_mode"] = "public_web"
        refs = [as_text(item) for item in signal.get("evidence_refs", []) if as_text(item)]
        signal["evidence_refs"] = list(dict.fromkeys([*refs, signal["canonical_url"], artifact]))
        signal["limitations"] = [
            as_text(item) for item in signal.get("limitations", [])
            if as_text(item) and "post body was not returned" not in as_text(item)
        ]
        seen.add(content_id)
        applied.append(content_id)
    snapshot.setdefault("collection", {}).setdefault("detail_backfills", []).append({
        "adapter": "public_reddit_permalink",
        "source_mode": "public_web",
        "success": execution is not None,
        "detail_open_count": len(applied),
        "content_ids": applied,
        "raw_artifact": artifact,
        **({"execution": execution} if execution is not None else {}),
    })
    snapshot["collection"]["counts"]["detail_open_count"] = sum(
        1 for item in snapshot["signals"] if item.get("detail_captured")
    )
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply bounded public Reddit permalink details to MCP search cards.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--backfill", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    backfill_path = Path(args.backfill).resolve()
    result = apply_backfill(load_data(args.input), load_data(backfill_path), str(backfill_path))
    write_json(args.output, result)


if __name__ == "__main__":
    main()
