from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from append_collection_result import signal_key
from check_collection_adapter import executable_command
from orchestrate_dokobot_collection import action, load_state, record_detail_backfill
from parse_opencli_xhs_search import parse_count
from run_collection_capture import classify_opencli_failure, command_hash


def fields_map(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, list):
        return {}
    return {
        str(item.get("field")): item.get("value")
        for item in value
        if isinstance(item, dict) and item.get("field")
    }


def execute(requested: list[str], timeout: int) -> tuple[int | None, str, str, bool]:
    located = shutil.which(requested[0])
    if not located:
        raise SystemExit("OpenCLI executable is not available for detail backfill.")
    command = executable_command(located, requested[1:], "@jackwener/opencli", ("dist", "src", "main.js"))
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return completed.returncode, completed.stdout, completed.stderr, False
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
        return None, stdout, stderr, True


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute eligible OpenCLI Xiaohongshu detail backfills and atomically update the canonical ledger.")
    parser.add_argument("--state", required=True)
    parser.add_argument("--results-output", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--max-details", type=int, default=0, help="0 processes every currently eligible target.")
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()
    if args.timeout_seconds < 10 or args.timeout_seconds > 180:
        raise SystemExit("--timeout-seconds must be between 10 and 180.")
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    if state.get("adapter") != "opencli" or state.get("platform") != "xiaohongshu":
        raise SystemExit("This detail runner is limited to the validated OpenCLI Xiaohongshu adapter.")
    next_action = action(state)
    if next_action.get("action") != "backfill_details":
        raise SystemExit("The collection orchestrator does not currently request detail backfill.")
    targets = list(next_action.get("targets") or [])
    if args.max_details:
        targets = targets[:args.max_details]
    snapshot = load_data(state["snapshot"])
    by_key = {signal_key(item): item for item in snapshot.get("signals", []) if isinstance(item, dict)}
    results: list[dict[str, Any]] = []
    hard_stop = ""
    for target in targets:
        attempts = 2
        accepted: dict[str, Any] | None = None
        last_raw = ""
        last_metadata = ""
        last_stop = ""
        for attempt in range(1, attempts + 1):
            requested = [str(item) for item in target["capture_command"]]
            started_at = now_iso()
            code, stdout, stderr, timed_out = execute(requested, args.timeout_seconds)
            finished_at = now_iso()
            base = Path(target["raw_output"])
            raw_path = base.with_name(f"{base.stem}-attempt-{attempt}{base.suffix}")
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(stdout, encoding="utf-8")
            stderr_path = raw_path.with_suffix(raw_path.suffix + ".stderr.txt")
            stdout_path = raw_path.with_suffix(raw_path.suffix + ".stdout.txt")
            metadata_path = raw_path.with_suffix(raw_path.suffix + ".capture.json")
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            write_json(str(metadata_path), {
                "schema_version": "collection-detail-execution-v0.1",
                "adapter": "opencli",
                "signal_key": target["signal_key"],
                "requested_command": requested,
                "requested_command_sha256": command_hash(requested),
                "exit_code": code,
                "timed_out": timed_out,
                "started_at": started_at,
                "finished_at": finished_at,
                "raw_artifact": str(raw_path.resolve()),
                "stdout_artifact": str(stdout_path.resolve()),
                "stderr_artifact": str(stderr_path.resolve()),
                "metadata_artifact": str(metadata_path.resolve()),
            })
            last_raw = str(raw_path.resolve())
            last_metadata = str(metadata_path.resolve())
            if timed_out:
                last_stop = "repeated_timeout" if attempt == attempts else ""
                if attempt < attempts:
                    continue
                break
            if code != 0:
                stop_reason, hard_stop = classify_opencli_failure(f"{stdout}\n{stderr}")
                last_stop = hard_stop or stop_reason
                break
            try:
                fields = fields_map(json.loads(stdout))
            except json.JSONDecodeError:
                last_stop = "cli_error"
                break
            likes = parse_count(fields.get("likes"))
            saves = parse_count(fields.get("collects") or fields.get("saves"))
            comments = parse_count(fields.get("comments"))
            original = by_key.get(str(target["signal_key"]), {})
            original_likes = ((original.get("metrics") or {}).get("likes") or 0) if isinstance(original, dict) else 0
            all_zero = original_likes > 0 and likes == 0 and saves == 0 and comments == 0
            complete = bool(str(fields.get("title") or "").strip() and str(fields.get("author") or "").strip() and str(fields.get("content") or "").strip() and likes is not None and not all_zero)
            if complete:
                accepted = {
                    "title": str(fields.get("title") or "").strip(),
                    "summary": str(fields.get("content") or "").strip(),
                    "published_at": str(fields.get("published_at") or fields.get("date") or "").strip(),
                    "metrics": {"likes": likes, "saves": saves, "comments": comments},
                    "author": {"name": str(fields.get("author") or "").strip()},
                    "evidence_refs": [str(raw_path.resolve()), str(metadata_path.resolve()), target["url"]],
                    "raw_artifacts": [str(raw_path.resolve()), str(stdout_path.resolve()), str(metadata_path.resolve()), str(stderr_path.resolve())],
                    "captured_at": now_iso(),
                    "metrics_captured_at": now_iso(),
                }
                break
            last_stop = "cli_error"
            if not all_zero:
                break
        results.append({
            "signal_key": target["signal_key"],
            "success": accepted is not None,
            "raw_artifact": last_raw,
            "metadata_artifact": last_metadata,
            "stop_reason": "" if accepted else last_stop,
            "execution": {
                "requested_command_sha256": command_hash(requested), "exit_code": code,
                "started_at": started_at, "finished_at": finished_at,
                "stdout_artifact": str(stdout_path.resolve()), "stderr_artifact": str(stderr_path.resolve()),
                "metadata_artifact": str(metadata_path.resolve()),
            },
            **({"signal": accepted} if accepted else {}),
        })
        if hard_stop:
            break
    payload = {"schema_version": "opencli-detail-backfill-v0.2", "adapter": "opencli", "status": "blocked" if hard_stop else "complete", "results": results}
    write_json(args.results_output, payload)
    if not args.no_record:
        record_detail_backfill(state, payload)
        write_json(str(state_path), state)
    print(json.dumps({"attempted": len(results), "successful": sum(1 for item in results if item["success"]), "hard_stop": hard_stop, "recorded": not args.no_record, "results": str(Path(args.results_output).resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
