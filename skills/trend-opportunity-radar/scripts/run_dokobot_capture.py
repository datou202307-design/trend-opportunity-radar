from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from _common import now_iso, write_json
from orchestrate_dokobot_collection import action, load_state


SCHEMA_VERSION = "dokobot-capture-execution-v0.1"
SESSION_PATTERN = re.compile(r"Session:\s*([A-Za-z0-9_-]+)", re.IGNORECASE)


def requested_command_hash(command: list[str]) -> str:
    return hashlib.sha256(json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def windows_appdata_root() -> Path | None:
    if os.name != "nt":
        return None
    appdata = os.environ.get("APPDATA", "").strip()
    return Path(appdata) if appdata else None


def resolve_execution_command(requested_command: list[str]) -> list[str]:
    executable = shutil.which(requested_command[0])
    if not executable:
        appdata_root = windows_appdata_root()
        if appdata_root:
            shim = appdata_root / "npm" / f"{requested_command[0]}.cmd"
            if shim.is_file():
                executable = str(shim)
    if not executable:
        raise SystemExit("DokoBot executable is not available to the capture wrapper.")
    resolved = Path(executable)
    if resolved.suffix.casefold() in {".cmd", ".bat", ".ps1"}:
        node_entry = resolved.parent / "node_modules" / "@dokobot" / "cli" / "dist" / "cli" / "bin" / "dokobot.js"
        node_executable = resolved.parent / "node.exe"
        node = str(node_executable) if node_executable.exists() else shutil.which("node")
        if not node or not node_entry.exists():
            raise SystemExit("DokoBot Windows shim was found, but its direct Node entry point is unavailable.")
        return [str(node), str(node_entry), *requested_command[1:]]
    return [str(resolved), *requested_command[1:]]


def classify_failure(text: str) -> tuple[str, str]:
    lowered = text.casefold()
    if "session not found or expired" in lowered or "session expired" in lowered:
        return "session_expired", ""
    platform_stops = {
        "captcha": ("captcha",),
        "rate_limit": ("rate limit", "too many requests", "429"),
        "login_expired": ("login expired", "sign in", "not logged in"),
        "permission_prompt": ("permission", "access denied", "403"),
        "abnormal_redirect": ("abnormal redirect", "redirect loop"),
    }
    for stop, markers in platform_stops.items():
        if any(marker in lowered for marker in markers):
            return "", stop
    return "cli_error", ""


def execution_artifact_paths(metadata_path: Path, raw_artifact: Path) -> tuple[Path, Path, Path]:
    """Return immutable per-capture metadata and console artifact paths."""
    stem = raw_artifact.name
    capture_metadata = raw_artifact.parent / f"{stem}.capture.json"
    stdout_path = raw_artifact.parent / f"{stem}.stdout.txt"
    stderr_path = raw_artifact.parent / f"{stem}.stderr.txt"
    if capture_metadata == metadata_path:
        capture_metadata = raw_artifact.parent / f"{stem}.execution.json"
    return capture_metadata, stdout_path, stderr_path


def build_metadata(
    query_id: str,
    requested_command: list[str],
    raw_artifact: str,
    stdout: str,
    stderr: str,
    exit_code: int | None,
    started_at: str,
    finished_at: str,
    timed_out: bool = False,
) -> dict[str, Any]:
    session_match = SESSION_PATTERN.search(f"{stdout}\n{stderr}")
    session_id = session_match.group(1) if session_match else ""
    if timed_out:
        read_status, stop_reason, hard_stop = "timeout", "", ""
    elif exit_code == 0:
        read_status, stop_reason, hard_stop = "success", "", ""
    else:
        stop_reason, hard_stop = classify_failure(f"{stdout}\n{stderr}")
        read_status = "error"
    return {
        "schema_version": SCHEMA_VERSION,
        "query_id": query_id,
        "read_status": read_status,
        "session_id": session_id,
        "can_continue": bool(session_id),
        "continuation_status": "available" if session_id else "unknown",
        "terminal_evidence": "",
        "raw_artifact": raw_artifact,
        "raw_artifact_exists": Path(raw_artifact).exists(),
        "stop_reason": stop_reason,
        "hard_stop": hard_stop,
        "requested_command": requested_command,
        "requested_command_sha256": requested_command_hash(requested_command),
        "exit_code": exit_code,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute the next orchestrated DokoBot read and preserve deterministic metadata.")
    parser.add_argument("--state", required=True)
    parser.add_argument("--metadata-output", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=75)
    args = parser.parse_args()
    if args.timeout_seconds < 10 or args.timeout_seconds > 300:
        raise SystemExit("--timeout-seconds must be between 10 and 300.")
    state = load_state(Path(args.state).resolve())
    next_action = action(state)
    if next_action.get("action") not in {"start_query", "continue_query"}:
        raise SystemExit("The orchestrator does not currently require a DokoBot query capture.")
    requested_command = [str(item) for item in next_action["dokobot_command"]]
    command = resolve_execution_command(requested_command)
    if "--timeout" not in command:
        command.extend(["--timeout", str(args.timeout_seconds)])
    raw_artifact_path = Path(next_action["raw_output"]).resolve()
    raw_artifact = str(raw_artifact_path)
    metadata_path = Path(args.metadata_output).resolve()
    capture_metadata_path, stdout_path, stderr_path = execution_artifact_paths(metadata_path, raw_artifact_path)
    capture_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=args.timeout_seconds + 10)
        stdout, stderr, exit_code, timed_out = completed.stdout, completed.stderr, completed.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        exit_code, timed_out = None, True
    finished_at = now_iso()
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    metadata = build_metadata(
        next_action["query"]["id"], requested_command, raw_artifact, stdout, stderr,
        exit_code, started_at, finished_at, timed_out,
    )
    metadata["stdout_artifact"] = str(stdout_path)
    metadata["stderr_artifact"] = str(stderr_path)
    metadata["metadata_artifact"] = str(capture_metadata_path)
    write_json(str(capture_metadata_path), metadata)
    write_json(str(metadata_path), metadata)
    print(json.dumps({
        "metadata": str(metadata_path),
        "query_id": metadata["query_id"],
        "read_status": metadata["read_status"],
        "session_id": metadata["session_id"],
        "continuation_status": metadata["continuation_status"],
        "raw_artifact": raw_artifact,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
