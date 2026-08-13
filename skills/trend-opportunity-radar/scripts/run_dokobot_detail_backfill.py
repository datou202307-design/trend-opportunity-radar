from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from orchestrate_dokobot_collection import action, load_state, record_detail_backfill
from run_collection_capture import command_hash
from run_dokobot_capture import classify_failure, resolve_execution_command


X_URL = re.compile(r"https://(?:www\.)?x\.com/([A-Za-z0-9_]+)/status/(\d+)", re.IGNORECASE)
HANDLE = re.compile(r"^@([A-Za-z0-9_]+)\s*(?:\[\d+\])?\s*$", re.MULTILINE)


def command_with_output(command: list[str], output: Path, timeout: int) -> list[str]:
    updated = list(command)
    if "--output" in updated:
        updated[updated.index("--output") + 1] = str(output.resolve())
    else:
        updated.extend(["--output", str(output.resolve())])
    if "--timeout" not in updated:
        updated.extend(["--timeout", str(timeout)])
    return updated


def parse_x_detail(text: str, target_url: str, raw_path: Path, metadata_path: Path, stdout_path: Path, stderr_path: Path) -> dict[str, Any] | None:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return None
    url_match = X_URL.search(normalized) or X_URL.search(target_url)
    if not url_match:
        return None
    sections = re.split(r"(?m)^---\s*$", normalized)
    body = sections[1].strip() if len(sections) > 1 else ""
    body = re.sub(r"(?m)^Show more\s*$", "", body).strip()
    if not body:
        return None
    handle_match = HANDLE.search(normalized)
    handle = handle_match.group(1) if handle_match else url_match.group(1)
    prefix = normalized[: handle_match.start()] if handle_match else ""
    author_lines = [line.strip() for line in prefix.splitlines() if line.strip() and not line.startswith(("#", ">"))]
    author_name = re.sub(r"\s*\[\d+\]\s*$", "", author_lines[-1]) if author_lines else handle
    metrics: dict[str, int] = {}
    for label, key in (("Views", "views"), ("Likes", "likes"), ("Replies", "replies"), ("Reposts", "reposts")):
        match = re.search(rf"([\d,.]+[KMB]?)\s+{label}\b", normalized, re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", "").upper()
            multiplier = 1
            if raw.endswith("K"):
                multiplier, raw = 1_000, raw[:-1]
            elif raw.endswith("M"):
                multiplier, raw = 1_000_000, raw[:-1]
            elif raw.endswith("B"):
                multiplier, raw = 1_000_000_000, raw[:-1]
            try:
                metrics[key] = int(float(raw) * multiplier)
            except ValueError:
                pass
    published = ""
    for line in normalized.splitlines():
        if re.search(r"\b(?:AM|PM)\b", line, re.IGNORECASE) and re.search(r"\b20\d{2}\b", line):
            published = re.sub(r"\s*\[\d+\]\s*", " ", line).split("·", 1)[0].strip()
            break
    canonical = f"https://x.com/{url_match.group(1)}/status/{url_match.group(2)}"
    return {
        "content_id": url_match.group(2),
        "canonical_url": canonical,
        "title": body.splitlines()[0][:180],
        "summary": body,
        "published_at": published,
        "metrics": metrics,
        "author": {"name": author_name, "handle": f"@{handle}"},
        "evidence_refs": [canonical, str(raw_path.resolve()), str(metadata_path.resolve())],
        "raw_artifacts": [str(raw_path.resolve()), str(stdout_path.resolve()), str(stderr_path.resolve()), str(metadata_path.resolve())],
        "captured_at": now_iso(),
        "metrics_captured_at": now_iso(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute eligible DokoBot X detail backfills with immutable execution evidence.")
    parser.add_argument("--state", required=True)
    parser.add_argument("--results-output", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=75)
    parser.add_argument("--max-details", type=int, default=0)
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()
    if args.timeout_seconds < 10 or args.timeout_seconds > 300:
        raise SystemExit("--timeout-seconds must be between 10 and 300.")
    state_path = Path(args.state).resolve()
    state = load_state(state_path)
    if state.get("adapter") != "dokobot" or state.get("platform") != "x":
        raise SystemExit("This runner is limited to the validated DokoBot X detail workflow.")
    next_action = action(state)
    if next_action.get("action") != "backfill_details":
        raise SystemExit("The collection orchestrator does not currently request detail backfill.")
    targets = list(next_action.get("targets") or [])
    if args.max_details:
        targets = targets[:args.max_details]
    results: list[dict[str, Any]] = []
    hard_stop = ""
    for target in targets:
        accepted = None
        last_result: dict[str, Any] = {}
        for attempt in (1, 2):
            base = Path(target["raw_output"])
            raw_path = base.with_name(f"{base.stem}-attempt-{attempt}{base.suffix}").resolve()
            stdout_path = raw_path.with_suffix(raw_path.suffix + ".stdout.txt")
            stderr_path = raw_path.with_suffix(raw_path.suffix + ".stderr.txt")
            metadata_path = raw_path.with_suffix(raw_path.suffix + ".capture.json")
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            requested = command_with_output([str(item) for item in target["capture_command"]], raw_path, args.timeout_seconds)
            executable = resolve_execution_command(requested)
            started_at = now_iso()
            try:
                completed = subprocess.run(executable, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=args.timeout_seconds + 10)
                stdout, stderr, code, timed_out = completed.stdout, completed.stderr, completed.returncode, False
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                code, timed_out = None, True
            finished_at = now_iso()
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            metadata = {
                "schema_version": "collection-detail-execution-v0.2", "adapter": "dokobot",
                "signal_key": target["signal_key"], "requested_command": requested,
                "requested_command_sha256": command_hash(requested), "exit_code": code,
                "timed_out": timed_out, "started_at": started_at, "finished_at": finished_at,
                "raw_artifact": str(raw_path), "stdout_artifact": str(stdout_path),
                "stderr_artifact": str(stderr_path), "metadata_artifact": str(metadata_path),
            }
            write_json(str(metadata_path), metadata)
            stop_reason = ""
            if timed_out:
                stop_reason = "repeated_timeout" if attempt == 2 else ""
            elif code != 0:
                stop_reason, hard_stop = classify_failure(f"{stdout}\n{stderr}")
            elif not raw_path.is_file():
                stop_reason = "cli_error"
            else:
                accepted = parse_x_detail(raw_path.read_text(encoding="utf-8", errors="replace"), target["url"], raw_path, metadata_path, stdout_path, stderr_path)
                if accepted is None:
                    stop_reason = "cli_error"
            last_result = {
                "signal_key": target["signal_key"], "success": accepted is not None,
                "raw_artifact": str(raw_path), "stop_reason": "" if accepted else stop_reason,
                "execution": {key: metadata[key] for key in (
                    "requested_command_sha256", "exit_code", "started_at", "finished_at",
                    "stdout_artifact", "stderr_artifact", "metadata_artifact"
                )},
                **({"signal": accepted} if accepted else {}),
            }
            if accepted or hard_stop or (not timed_out):
                break
        results.append(last_result)
        if hard_stop:
            break
    payload = {"schema_version": "dokobot-detail-backfill-v0.2", "adapter": "dokobot", "status": "blocked" if hard_stop else "complete", "results": results}
    write_json(args.results_output, payload)
    if not args.no_record:
        record_detail_backfill(state, payload)
        write_json(str(state_path), state)
    print(json.dumps({"attempted": len(results), "successful": sum(1 for item in results if item["success"]), "hard_stop": hard_stop, "recorded": not args.no_record, "results": str(Path(args.results_output).resolve())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
