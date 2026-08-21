from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

from _common import load_data, require_text_integrity
from append_collection_result import signal_key


RAW_PATTERNS = (
    re.compile(r'<pre id=["\']raw["\']>(.*?)</pre>', re.DOTALL),
    re.compile(r'<script type=["\']application/json["\'] id=["\']comparison-data["\']>(.*?)</script>', re.DOTALL),
    re.compile(r'<script id=["\']report-data["\'] type=["\']application/json["\']>(.*?)</script>', re.DOTALL),
)
FORBIDDEN_RUN_REPAIRS = {
    "extract_x_capture.py", "sanitize_signals.py", "dedupe_audit_execution.py",
    "repair_signals.py", "patch_orchestrator.py",
}


def normalized_refs(values: Any) -> set[str]:
    return {str(value).strip().rstrip("/").casefold() for value in (values or []) if str(value).strip()}


def resolve_artifact(value: str, base: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def validate_collection_artifacts(result: dict[str, Any], base: Path) -> None:
    present_repairs = sorted(item.name for item in base.iterdir() if item.is_file() and item.name.casefold() in FORBIDDEN_RUN_REPAIRS)
    if present_repairs:
        raise SystemExit("Report run depends on prohibited one-off data repair scripts: " + ", ".join(present_repairs))
    runs = ((result.get("collection") or {}).get("query_runs") or [])
    stdout_refs: list[str] = []
    stderr_refs: list[str] = []
    metadata_refs: list[str] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        for value in run.get("raw_artifacts", []) or []:
            if not value or not resolve_artifact(str(value), base).is_file():
                raise SystemExit(f"Report references a missing raw capture artifact: {value}")
        for execution in run.get("capture_executions", []) or []:
            if not isinstance(execution, dict):
                raise SystemExit("Report capture execution audit must contain objects.")
            for field, bucket in (("stdout_artifact", stdout_refs), ("stderr_artifact", stderr_refs), ("metadata_artifact", metadata_refs)):
                value = str(execution.get(field) or "")
                if not value or not resolve_artifact(value, base).is_file():
                    raise SystemExit(f"Report references a missing execution {field}: {value}")
                bucket.append(str(resolve_artifact(value, base)))
    detail_backfills = ((result.get("collection") or {}).get("detail_backfills") or [])
    for audit in detail_backfills:
        if not isinstance(audit, dict):
            raise SystemExit("Report detail backfill audit must contain objects.")
        raw = str(audit.get("raw_artifact") or "")
        if not raw or not resolve_artifact(raw, base).is_file():
            raise SystemExit(f"Report references a missing detail raw artifact: {raw}")
        execution = audit.get("execution")
        if audit.get("success") and not isinstance(execution, dict):
            raise SystemExit("Every successful controlled detail capture requires deterministic execution evidence.")
        if not isinstance(execution, dict):
            continue
        for field, bucket in (("stdout_artifact", stdout_refs), ("stderr_artifact", stderr_refs), ("metadata_artifact", metadata_refs)):
            value = str(execution.get(field) or "")
            if not value or not resolve_artifact(value, base).is_file():
                raise SystemExit(f"Report references a missing detail execution {field}: {value}")
            bucket.append(str(resolve_artifact(value, base)))
    execution_count = len(stdout_refs)
    if execution_count and (
        len(set(stdout_refs)) != execution_count
        or len(set(stderr_refs)) != execution_count
        or len(set(metadata_refs)) != execution_count
    ):
        raise SystemExit("Every capture execution must reference unique stdout, stderr, and metadata artifacts.")


def validate_collection_state_consistency(result: dict[str, Any], base: Path) -> None:
    collection = result.get("collection") or {}
    report_status = str(collection.get("contract_status") or "")
    report_stop = str(collection.get("stop_reason") or "")
    if report_status == "met" and report_stop != "sampling_contract_met":
        raise SystemExit("A report cannot claim sampling met while retaining a blocked collection stop reason.")

    raw_path = base / "raw-signals.json"
    if raw_path.is_file():
        raw = load_data(str(raw_path))
        raw_collection = (raw.get("collection") or {}) if isinstance(raw, dict) else {}
        raw_stop = str(raw_collection.get("stop_reason") or "")
        raw_signals = raw.get("signals") or [] if isinstance(raw, dict) else []
        raw_counts = raw_collection.get("counts") or {}
        platform = str(raw.get("platform") or result.get("platform") or "")
        raw_detail_count = len({
            signal_key(item, platform)
            for item in raw_signals
            if isinstance(item, dict) and item.get("detail_captured")
        })
        stored_raw_details = int(raw_counts.get("detail_open_count") or 0)
        if stored_raw_details != raw_detail_count:
            raise SystemExit("Raw acquisition ledger is internally inconsistent on successful detail capture count.")
        actual_counters = len({
            signal_key(item, platform)
            for item in raw_signals
            if isinstance(item, dict) and item.get("evidence_role") == "counter"
        })
        stored_counters = int(raw_counts.get("counter_signal_count") or 0)
        if stored_counters != actual_counters:
            raise SystemExit("Raw acquisition ledger is internally inconsistent on counter-signal count.")

        # Acquisition evidence is immutable. Semantic review and controlled detail
        # backfills are append-only enrichments, so compare the report with the
        # latest scored ledger when it exists instead of forcing raw-signals.json
        # to be rewritten after collection.
        derived_path = base / "scored-signals.json"
        derived = load_data(str(derived_path)) if derived_path.is_file() else raw
        derived_collection = (derived.get("collection") or {}) if isinstance(derived, dict) else {}
        derived_signals = derived.get("signals") or [] if isinstance(derived, dict) else []
        derived_platform = str(derived.get("platform") or platform) if isinstance(derived, dict) else platform
        derived_detail_keys = {
            signal_key(item, derived_platform)
            for item in derived_signals
            if isinstance(item, dict) and item.get("detail_captured")
        }
        derived_counters = {
            signal_key(item, derived_platform)
            for item in derived_signals
            if isinstance(item, dict) and item.get("evidence_role") == "counter"
        }
        report_details = int((collection.get("counts") or {}).get("detail_open_count") or 0)
        report_counters = int((collection.get("counts") or {}).get("counter_signal_count") or 0)
        if report_details != len(derived_detail_keys):
            raise SystemExit("Reviewed ledger and report disagree on successful detail capture count.")
        if report_counters != len(derived_counters):
            raise SystemExit("Reviewed ledger and report disagree on counter-signal count.")

        raw_detail_keys = {
            signal_key(item, platform)
            for item in raw_signals
            if isinstance(item, dict) and item.get("detail_captured")
        }
        appended_detail_keys = derived_detail_keys - raw_detail_keys
        if appended_detail_keys:
            successful_audits = [
                audit for audit in (collection.get("detail_backfills") or [])
                if isinstance(audit, dict) and audit.get("success")
            ]
            if not successful_audits:
                raise SystemExit("Reviewed ledger contains appended details without a successful backfill audit.")
            audited_keys = {
                str(audit.get("signal_key"))
                for audit in successful_audits
                if str(audit.get("signal_key") or "")
            }
            if audited_keys and not appended_detail_keys.issubset(audited_keys):
                raise SystemExit("Reviewed ledger contains detail keys missing from successful backfill audits.")
            audited_ids = {
                str(content_id)
                for audit in successful_audits
                for content_id in (audit.get("content_ids") or [])
                if str(content_id)
            }
            appended_ids = {
                str(item.get("content_id"))
                for item in derived_signals
                if isinstance(item, dict)
                and item.get("detail_captured")
                and signal_key(item, derived_platform) in appended_detail_keys
                and item.get("content_id")
            }
            if audited_ids and not appended_ids.issubset(audited_ids):
                raise SystemExit("Reviewed ledger contains detail IDs missing from successful backfill audits.")
            audited_count = sum(int(audit.get("detail_open_count") or 0) for audit in successful_audits)
            if not audited_keys and not audited_ids and audited_count < len(appended_detail_keys):
                raise SystemExit("Successful backfill audits do not cover every appended detail.")

        invalid_details = [
            item for item in derived_signals
            if isinstance(item, dict) and item.get("detail_captured") and (
                not item.get("evidence_role")
                or not item.get("semantic_review")
                or (item.get("semantic_relevance") in {"direct", "adjacent"} and not item.get("topic_key"))
            )
        ]
        if invalid_details:
            raise SystemExit("Detail backfill lost semantic review, evidence role, or topic assignment.")
        effective_stop = str(derived_collection.get("stop_reason") or raw_stop)
        if report_status == "met" and effective_stop != "sampling_contract_met":
            raise SystemExit("Reviewed ledger remains blocked while the report claims sampling met.")

    state_path = base / "collection-state.json"
    if state_path.is_file():
        state = load_data(str(state_path))
        require_text_integrity(state, "Collection state")
        state_status = str(state.get("status") or "") if isinstance(state, dict) else ""
        state_stop = str(state.get("stop_reason") or "") if isinstance(state, dict) else ""
        if report_status == "met" and (state_status != "complete" or state_stop != "sampling_contract_met"):
            raise SystemExit("Collection state is not complete while the report claims sampling met.")


def validate_visual_qa(receipt_path: str, html_path: Path) -> None:
    receipt = load_data(receipt_path)
    require_text_integrity(receipt, "HTML visual QA receipt")
    url = str(receipt.get("url") or "") if isinstance(receipt, dict) else ""
    if not url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("HTML visual QA must use a loopback HTTP URL, not file:// or an external host.")
    expected = hashlib.sha256(html_path.read_bytes()).hexdigest()
    if receipt.get("html_sha256") != expected:
        raise SystemExit("HTML visual QA receipt does not match the delivered HTML artifact.")
    checks = receipt.get("checks") or {}
    required = ("subject_visible", "first_screen_readable", "evidence_sections_readable")
    if receipt.get("status") != "passed" or any(checks.get(name) is not True for name in required):
        raise SystemExit("HTML visual QA receipt does not prove the required reader-path checks passed.")
    if int(checks.get("console_error_count") or 0) != 0:
        raise SystemExit("HTML visual QA found browser console errors.")


def validate_report_contents(result: dict[str, Any], markdown: str, page: str | None = None) -> None:
    require_text_integrity(result, "Report JSON")
    require_text_integrity(markdown, "Report Markdown")
    subject = result.get("subject") or {}
    name = str(subject.get("name") if isinstance(subject, dict) else subject).strip()
    if name and name not in markdown:
        raise SystemExit("Report Markdown does not contain the exact UTF-8 subject name.")
    for item in [*(result.get("opportunities", []) or []), *(result.get("findings", []) or [])]:
        if not isinstance(item, dict):
            continue
        overlap = normalized_refs(item.get("support_refs")) & normalized_refs(item.get("counter_refs"))
        if overlap:
            raise SystemExit("A decision item cannot use the same evidence as both support and counterevidence.")
    if page is None:
        return
    require_text_integrity(page, "Report HTML")
    if not re.search(r'<meta\s+charset=["\']utf-8["\']\s*/?>', page, re.IGNORECASE):
        raise SystemExit("Report HTML must declare UTF-8.")
    if name and name not in page:
        raise SystemExit("Report HTML does not contain the exact UTF-8 subject name.")
    match = next((candidate.search(page) for candidate in RAW_PATTERNS if candidate.search(page)), None)
    if not match:
        raise SystemExit("Report HTML is missing the machine-readable raw payload.")
    try:
        embedded = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Report HTML contains invalid embedded JSON: {exc}") from exc
    if embedded != result:
        raise SystemExit("Report HTML embedded JSON differs from the standalone report JSON.")
    if "getElementById('raw')" in page or 'getElementById("raw")' in page:
        raise SystemExit("Report HTML must not mutate the machine-readable payload after generation.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate UTF-8 and cross-format report integrity.")
    parser.add_argument("--json-report", required=True)
    parser.add_argument("--markdown-report", required=True)
    parser.add_argument("--html-report")
    parser.add_argument("--visual-qa-receipt")
    args = parser.parse_args()
    result = load_data(args.json_report)
    markdown = Path(args.markdown_report).read_text(encoding="utf-8")
    page = Path(args.html_report).read_text(encoding="utf-8") if args.html_report else None
    validate_collection_artifacts(result, Path(args.json_report).resolve().parent)
    validate_collection_state_consistency(result, Path(args.json_report).resolve().parent)
    validate_report_contents(result, markdown, page)
    if args.html_report:
        if not args.visual_qa_receipt:
            raise SystemExit("HTML delivery requires --visual-qa-receipt from a loopback-browser inspection.")
        validate_visual_qa(args.visual_qa_receipt, Path(args.html_report).resolve())
    print("Report artifacts are UTF-8 and mutually consistent.")


if __name__ == "__main__":
    main()
