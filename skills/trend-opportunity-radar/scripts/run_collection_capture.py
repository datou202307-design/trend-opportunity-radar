from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from check_collection_adapter import executable_command, resolve_opencli
from collection_pacing import RATE_LIMIT_COOLDOWN_SECONDS, throttle_before_read
from orchestrate_dokobot_collection import action, load_state
from platform_adapter_contract import parse_search_capture
from run_dokobot_capture import build_metadata as build_dokobot_metadata
from run_dokobot_capture import execution_artifact_paths, resolve_execution_command


SCHEMA_VERSION = "collection-capture-execution-v0.2"


def prior_query_read_count(state: dict[str, Any]) -> int:
    """Count every search read already attempted in the run, including finalized queries."""
    total = 0
    for query in state.get("queries", []):
        if not isinstance(query, dict):
            continue
        executions = query.get("capture_executions")
        if isinstance(executions, list) and executions:
            total += len(executions)
            continue
        result_path = str(query.get("query_result") or "").strip()
        if result_path and Path(result_path).is_file():
            result = load_data(Path(result_path))
            saved = result.get("capture_executions") if isinstance(result, dict) else None
            if isinstance(saved, list):
                total += len(saved)
    active = state.get("active_query")
    if isinstance(active, dict) and isinstance(active.get("capture_executions"), list):
        total += len(active["capture_executions"])
    return total


def immutable_raw_path(requested: Path) -> Path:
    """Return a fresh evidence path without overwriting an earlier attempt."""
    if not requested.exists():
        return requested
    attempt = 2
    while True:
        candidate = requested.with_name(f"{requested.stem}-attempt-{attempt}{requested.suffix}")
        if not candidate.exists():
            return candidate
        attempt += 1


def command_hash(command: list[str]) -> str:
    return hashlib.sha256(json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def classify_opencli_failure(text: str) -> tuple[str, str]:
    lowered = text.casefold()
    stops = {
        "captcha": ("captcha", "验证码", "安全验证"),
        "rate_limit": ("rate limit", "too many requests", "429", "频控"),
        "login_expired": ("login_required", "not logged in", "登录失效"),
        "permission_prompt": ("permission", "access denied", "403"),
        "abnormal_redirect": ("abnormal redirect", "redirect loop", "页面错配"),
    }
    for stop, markers in stops.items():
        if any(marker in lowered for marker in markers):
            return "", stop
    if "browser_connect" in lowered or "not connected" in lowered:
        return "cli_error", ""
    return "cli_error", ""


def resolve_opencli_command(requested: list[str]) -> list[str]:
    located = shutil.which(requested[0])
    if not located:
        located, _, _ = resolve_opencli()
    if not located:
        raise SystemExit("OpenCLI executable is not available to the collection wrapper.")
    return executable_command(located, requested[1:], "@jackwener/opencli", ("dist", "src", "main.js"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the next adapter-neutral controlled-capture action and preserve immutable evidence.")
    parser.add_argument("--state", required=True)
    parser.add_argument("--metadata-output", required=True)
    parser.add_argument("--extraction-output", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=75)
    args = parser.parse_args()
    if args.timeout_seconds < 10 or args.timeout_seconds > 300:
        raise SystemExit("--timeout-seconds must be between 10 and 300.")
    state = load_state(Path(args.state).resolve())
    next_action = action(state)
    if next_action.get("action") not in {"start_query", "continue_query"}:
        raise SystemExit("The orchestrator does not currently require a query capture.")
    adapter = str(state.get("adapter") or "dokobot")
    requested = [str(item) for item in (next_action.get("capture_command") or next_action.get("dokobot_command") or [])]
    if not requested:
        raise SystemExit("The orchestrator did not provide a capture command.")
    command = resolve_opencli_command(requested) if adapter == "opencli" else resolve_execution_command(requested)
    if adapter == "dokobot" and "--timeout" not in command:
        command.extend(["--timeout", str(args.timeout_seconds)])
    raw_path = immutable_raw_path(Path(next_action["raw_output"]).resolve())
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path = Path(args.metadata_output).resolve()
    capture_metadata_path, stdout_path, stderr_path = execution_artifact_paths(metadata_path, raw_path)
    pacing = throttle_before_read(str(state.get("platform") or ""), "search", prior_query_read_count(state))
    started_at = now_iso()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=args.timeout_seconds)
        stdout, stderr, exit_code, timed_out = completed.stdout, completed.stderr, completed.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
        exit_code, timed_out = None, True
    finished_at = now_iso()
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    if adapter == "opencli":
        raw_path.write_text(stdout, encoding="utf-8")
        if timed_out:
            read_status, stop_reason, hard_stop = "timeout", "", ""
        elif exit_code == 0:
            read_status, stop_reason, hard_stop = "success", "", ""
        else:
            stop_reason, hard_stop = classify_opencli_failure(f"{stdout}\n{stderr}")
            read_status = "error"
        metadata: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "adapter": adapter,
            "query_id": next_action["query"]["id"],
            "read_status": read_status,
            "session_id": "",
            "can_continue": False,
            "continuation_status": "unknown",
            "terminal_evidence": "",
            "raw_artifact": str(raw_path),
            "raw_artifact_exists": raw_path.is_file(),
            "stop_reason": stop_reason,
            "hard_stop": hard_stop,
            "requested_command": requested,
            "requested_command_sha256": command_hash(requested),
            "exit_code": exit_code,
            "started_at": started_at,
            "finished_at": finished_at,
        }
        if hard_stop == "rate_limit":
            metadata["retry_after_seconds"] = RATE_LIMIT_COOLDOWN_SECONDS
    else:
        metadata = build_dokobot_metadata(next_action["query"]["id"], requested, str(raw_path), stdout, stderr, exit_code, started_at, finished_at, timed_out)
        metadata["schema_version"] = SCHEMA_VERSION
        metadata["adapter"] = adapter
    metadata["pacing"] = pacing
    extraction_path = Path(args.extraction_output).resolve()
    extraction = parse_search_capture(adapter, state.get("platform", ""), raw_path, next_action["query"]) if metadata["read_status"] == "success" else None
    if extraction is not None:
        extraction["query_id"] = metadata["query_id"]
        if not extraction["observed_result_keys"]:
            metadata.update({"can_continue": False, "continuation_status": "exhausted", "terminal_evidence": "zero_results", "stop_reason": "zero_results"})
        write_json(str(extraction_path), extraction)
    elif not extraction_path.exists():
        write_json(str(extraction_path), {"observed_result_keys": [], "signals": [], "detail_open_keys": []})
    metadata["stdout_artifact"] = str(stdout_path)
    metadata["stderr_artifact"] = str(stderr_path)
    metadata["metadata_artifact"] = str(capture_metadata_path)
    write_json(str(capture_metadata_path), metadata)
    write_json(str(metadata_path), metadata)
    print(json.dumps({
        "adapter": adapter,
        "metadata": str(metadata_path),
        "extraction": str(extraction_path),
        "query_id": metadata["query_id"],
        "read_status": metadata["read_status"],
        "raw_artifact": str(raw_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
