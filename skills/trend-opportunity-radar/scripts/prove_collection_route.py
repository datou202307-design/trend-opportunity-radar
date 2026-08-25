from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from _common import as_text, load_data, now_iso, write_json


SCHEMA_VERSION = "collection-route-execution-proof-v0.1"
ROLE_NAMES = {"search", "detail", "comments", "media"}
SCHEMA_ADAPTERS = {
    "facebook-posts-read-receipt-v0.1": "facebook_posts_browser_capture",
    "instagram-hashtag-read-receipt-v0.1": "instagram_hashtag_browser_capture",
    "instagram-account-read-receipt-v0.1": "browser_readonly_capture",
    "tiktok-visible-comment-receipt-v0.1": "dokobot",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _platform(payload: dict[str, Any]) -> str:
    return as_text(payload.get("platform")).casefold()


def _adapter(payload: dict[str, Any]) -> str:
    direct = as_text(payload.get("adapter")).casefold()
    if direct:
        return direct
    audit = payload.get("platform_adapter") if isinstance(payload.get("platform_adapter"), dict) else {}
    nested = as_text(audit.get("adapter")).casefold()
    if nested:
        return nested
    return SCHEMA_ADAPTERS.get(as_text(payload.get("schema_version")), "")


def _signals(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("signals")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _detail_count(payload: dict[str, Any]) -> int:
    rows = _signals(payload)
    if rows:
        return sum(1 for row in rows if row.get("detail_captured") is True or as_text(row.get("source_type")) in {"direct_post", "direct_video"})
    counts = payload.get("collection", {}).get("counts", {}) if isinstance(payload.get("collection"), dict) else {}
    return int(counts.get("detail_open_count") or payload.get("detail_open_count") or payload.get("detail_post_count") or 0)


def _comment_count(payload: dict[str, Any]) -> int:
    total = 0
    for row in _signals(payload):
        platform_facts = row.get("platform_facts") if isinstance(row.get("platform_facts"), dict) else {}
        comments = (
            row.get("representative_comments")
            or row.get("comments")
            or platform_facts.get("representative_comments")
        )
        if isinstance(comments, list):
            total += sum(1 for item in comments if isinstance(item, (dict, str)) and as_text(item.get("text") if isinstance(item, dict) else item))
    if total:
        return total
    comment_evidence = payload.get("comment_evidence") if isinstance(payload.get("comment_evidence"), dict) else {}
    return int(
        payload.get("visible_comment_count")
        or payload.get("reviewed_comment_count")
        or comment_evidence.get("reviewed_comment_count")
        or comment_evidence.get("reviewed_count")
        or 0
    )


def _media_count(payload: dict[str, Any]) -> int:
    total = 0
    for row in _signals(payload):
        media = row.get("media_evidence") or row.get("video_evidence")
        if isinstance(media, (dict, list)) and media:
            total += 1
    return total


def _search_observed(payload: dict[str, Any]) -> bool:
    if _signals(payload):
        return True
    collection = payload.get("collection") if isinstance(payload.get("collection"), dict) else {}
    counts = collection.get("counts") if isinstance(collection.get("counts"), dict) else {}
    observed = counts.get("observed_result_count", payload.get("observed_result_count"))
    terminal = as_text(collection.get("terminal_reason") or payload.get("stop_reason"))
    return bool((isinstance(observed, (int, float)) and observed > 0) or terminal in {"verified_zero_results", "success_empty_result"})


def _parse_receipts(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        role, separator, raw_path = value.partition("=")
        if not separator or role not in ROLE_NAMES or not raw_path:
            raise ValueError("Each --receipt must use role=PATH for search, detail, comments, or media.")
        if role in result:
            raise ValueError(f"Duplicate receipt role: {role}")
        result[role] = Path(raw_path).resolve()
    return result


def build_proof(
    manifest_path: Path,
    signals_path: Path,
    receipt_paths: dict[str, Path] | None = None,
) -> dict[str, Any]:
    manifest = load_data(manifest_path)
    snapshot = load_data(signals_path)
    if not isinstance(manifest, dict) or not isinstance(snapshot, dict):
        raise ValueError("Manifest and signals must be JSON objects.")
    run_dir = manifest_path.resolve().parent
    if signals_path.resolve().parent != run_dir:
        raise ValueError("The final signals artifact must be stored in the frozen run directory.")
    route = manifest.get("collection_route") if isinstance(manifest.get("collection_route"), dict) else {}
    if route.get("status") != "frozen_ready" or not as_text(route.get("route_id")):
        raise ValueError("The run does not contain a frozen ready collection route.")
    platform = as_text(route.get("platform")).casefold()
    if _platform(snapshot) != platform:
        raise ValueError("Signals platform does not match the frozen collection route.")
    roles = route.get("roles") if isinstance(route.get("roles"), dict) else {}
    search = roles.get("search") if isinstance(roles.get("search"), dict) else {}
    if _adapter(snapshot) != as_text(search.get("adapter")).casefold():
        raise ValueError("Signals adapter does not match the frozen search route.")
    if not _search_observed(snapshot):
        raise ValueError("Signals do not contain observed search evidence or a verified empty terminal state.")

    provided = dict(receipt_paths or {})
    required = {"search"}
    if isinstance(roles.get("detail"), dict) and roles["detail"].get("receipt_required") is True:
        required.add("detail")
    if _comment_count(snapshot) > 0:
        required.add("comments")
    if _media_count(snapshot) > 0:
        required.add("media")

    evidence_counts = {
        "search": len(_signals(snapshot)),
        "detail": _detail_count(snapshot),
        "comments": _comment_count(snapshot),
        "media": _media_count(snapshot),
    }
    role_proofs: dict[str, Any] = {}
    for role in sorted(required):
        spec = roles.get(role) if isinstance(roles.get(role), dict) else {}
        expected_adapter = as_text(spec.get("adapter")).casefold()
        if not expected_adapter:
            raise ValueError(f"The frozen route does not provide the required {role} adapter.")
        artifact_path = provided.get(role)
        if artifact_path is None and expected_adapter == _adapter(snapshot):
            artifact_path = signals_path
        if artifact_path is None or not artifact_path.is_file():
            raise ValueError(f"A real {role} receipt artifact is required for adapter {expected_adapter}.")
        if artifact_path.resolve().parent != run_dir:
            raise ValueError(f"The {role} receipt artifact must be stored in the frozen run directory.")
        artifact = load_data(artifact_path)
        if not isinstance(artifact, dict):
            raise ValueError(f"The {role} receipt artifact must be a JSON object.")
        artifact_adapter = _adapter(artifact)
        if artifact_adapter and artifact_adapter != expected_adapter:
            raise ValueError(f"The {role} receipt adapter does not match the frozen route.")
        if not artifact_adapter and artifact_path != signals_path:
            raise ValueError(f"The {role} receipt does not identify its adapter.")
        if role == "detail" and evidence_counts[role] < 1:
            raise ValueError("The standard live route requires at least one verified detail before reporting.")
        if role in {"comments", "media"} and evidence_counts[role] < 1:
            raise ValueError(f"The {role} role was declared as used but has no preserved evidence.")
        role_proofs[role] = {
            "adapter": expected_adapter,
            "runner": spec.get("runner"),
            "artifact": artifact_path.name,
            "artifact_sha256": file_sha256(artifact_path),
            "evidence_count": evidence_counts[role],
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "route_id": route["route_id"],
        "request_sha256": manifest.get("request_sha256"),
        "platform": platform,
        "signals_artifact": signals_path.name,
        "signals_sha256": file_sha256(signals_path),
        "roles": role_proofs,
        "verified_at": now_iso(),
    }


def validate_proof(manifest_path: Path, signals_path: Path, proof_path: Path) -> dict[str, Any]:
    manifest = load_data(manifest_path)
    proof = load_data(proof_path)
    if not isinstance(manifest, dict) or not isinstance(proof, dict):
        raise ValueError("Manifest and route proof must be JSON objects.")
    route = manifest.get("collection_route") if isinstance(manifest.get("collection_route"), dict) else {}
    checks = {
        "schema": proof.get("schema_version") == SCHEMA_VERSION,
        "status": proof.get("status") == "passed",
        "route": proof.get("route_id") == route.get("route_id"),
        "request": proof.get("request_sha256") == manifest.get("request_sha256"),
        "signals": proof.get("signals_sha256") == file_sha256(signals_path),
    }
    if not all(checks.values()):
        raise ValueError("Collection route execution proof is missing, stale, or does not match this run.")
    roles = route.get("roles") if isinstance(route.get("roles"), dict) else {}
    proved = proof.get("roles") if isinstance(proof.get("roles"), dict) else {}
    required = {"search"}
    if isinstance(roles.get("detail"), dict) and roles["detail"].get("receipt_required") is True:
        required.add("detail")
    missing = sorted(role for role in required if role not in proved)
    if missing:
        raise ValueError("Collection route proof is missing required roles: " + ", ".join(missing))
    for role, item in proved.items():
        if role not in ROLE_NAMES or not isinstance(item, dict):
            raise ValueError("Collection route proof contains an invalid role receipt.")
        artifact_name = as_text(item.get("artifact"))
        if not artifact_name or Path(artifact_name).name != artifact_name:
            raise ValueError("Collection route proof contains an unsafe receipt reference.")
        artifact_path = proof_path.resolve().parent / artifact_name
        if not artifact_path.is_file() or item.get("artifact_sha256") != file_sha256(artifact_path):
            raise ValueError(f"The {role} route receipt is missing or has changed since proof generation.")
    return proof


def enforce_report_gate(research_context_path: Path, signals_path: Path) -> dict[str, Any] | None:
    run_dir = research_context_path.resolve().parent
    manifest_path = run_dir / "run-manifest.json"
    if not manifest_path.is_file():
        return None
    manifest = load_data(manifest_path)
    route = manifest.get("collection_route") if isinstance(manifest, dict) and isinstance(manifest.get("collection_route"), dict) else {}
    if route.get("status") != "frozen_ready":
        return None
    proof_path = run_dir / "route-execution-proof.json"
    if not proof_path.is_file():
        raise ValueError("A verified collection route execution proof is required before generating a standard live report.")
    return validate_proof(manifest_path, signals_path.resolve(), proof_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prove that live evidence followed the frozen collection route before report generation.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--signals", required=True)
    parser.add_argument("--receipt", action="append", default=[], help="Optional split-adapter artifact as role=PATH.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-passed", action="store_true")
    args = parser.parse_args()
    try:
        proof = build_proof(Path(args.manifest).resolve(), Path(args.signals).resolve(), _parse_receipts(args.receipt))
    except (OSError, ValueError) as exc:
        if args.require_passed:
            raise SystemExit(str(exc)) from exc
        proof = {"schema_version": SCHEMA_VERSION, "status": "blocked", "reason": str(exc), "verified_at": now_iso()}
    write_json(args.output, proof)
    print(json.dumps(proof, ensure_ascii=False, indent=2))
    if args.require_passed and proof.get("status") != "passed":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
