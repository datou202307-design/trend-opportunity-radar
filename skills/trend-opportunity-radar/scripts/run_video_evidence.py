from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from video_evidence import ANALYZER_NAME, ANALYZER_VERSION, CONTRACT_VERSION, analyzer_arguments, analyzer_command, normalize_result


BLOCKED_ENV = {
    "YTDLP_COOKIES", "YTDLP_COOKIES_FROM_BROWSER",
    "OPENAI_API_KEY", "TWELVELABS_API_KEY", "WHISPER_HF_MODEL",
    "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN",
}


def safe_child_environment(
    runtime_bin: Path | None = None,
    whisper_bin: Path | None = None,
    whisper_model: str = "tiny",
    whisper_language: str = "",
    model_cache_dir: Path | None = None,
) -> dict[str, str]:
    environment = dict(os.environ)
    for name in BLOCKED_ENV:
        environment.pop(name, None)
    if runtime_bin:
        environment["PATH"] = f"{runtime_bin}{os.pathsep}{environment.get('PATH', '')}"
    if whisper_bin:
        environment["WHISPER_BIN"] = str(whisper_bin)
        environment["WHISPER_MODEL"] = whisper_model
        environment["WHISPER_DEVICE"] = "cpu"
        environment["WHISPER_COMPUTE"] = "int8"
        if whisper_language:
            environment["WHISPER_LANGUAGE"] = whisper_language
        if model_cache_dir:
            environment["HF_HOME"] = str(model_cache_dir)
            environment["HF_HUB_DISABLE_TELEMETRY"] = "1"
    return environment


def classify_failure(value: str) -> str:
    lowered = value.casefold()
    if any(token in lowered for token in ("captcha", "rate limit", "too many requests")):
        return "safety_stop"
    if any(token in lowered for token in ("login", "sign in", "cookie", "private video", "forbidden", "permission")):
        return "authorization_required"
    if "timed out" in lowered or "timeout" in lowered:
        return "timeout"
    if "npm warn cleanup" in lowered and "eperm" in lowered:
        return "runtime_install_error"
    return "analyzer_error"


def immutable_path(directory: Path, stem: str, suffix: str) -> Path:
    target = directory / f"{stem}{suffix}"
    index = 2
    while target.exists():
        target = directory / f"{stem}-run-{index}{suffix}"
        index += 1
    return target


def run_plan(
    plan: dict[str, Any], output_dir: Path, timeout_seconds: int, dry_run: bool = False,
    analyzer_entry: Path | None = None, runtime_bin: Path | None = None,
    whisper_bin: Path | None = None, whisper_model: str = "tiny", whisper_language: str = "",
    model_cache_dir: Path | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    npx = shutil.which("npx") or shutil.which("npx.cmd")
    node = shutil.which("node")
    if analyzer_entry and not analyzer_entry.is_file():
        raise SystemExit(f"The analyzer entry file does not exist: {analyzer_entry}")
    if analyzer_entry and not node:
        raise SystemExit("Node.js is required to execute the configured analyzer entry.")
    if whisper_bin and not whisper_bin.is_file():
        raise SystemExit(f"The configured local Whisper executable does not exist: {whisper_bin}")
    if not npx and not analyzer_entry and not dry_run:
        raise SystemExit("Node.js npx is required for the optional video evidence runtime.")
    results: list[dict[str, Any]] = []
    hard_stop = ""
    for candidate in plan.get("candidates", []):
        if not isinstance(candidate, dict) or not candidate.get("url"):
            continue
        stem = f"video-{candidate.get('rank', len(results) + 1):02d}-{str(candidate['signal_key'])[:12]}"
        raw_path = immutable_path(output_dir, stem, ".analyzer.json")
        stderr_path = raw_path.with_suffix(".stderr.txt")
        receipt_path = raw_path.with_suffix(".capture.json")
        with tempfile.TemporaryDirectory(prefix="trend-video-frames-") as frame_directory:
            if analyzer_entry:
                command = [node or "node", str(analyzer_entry), *analyzer_arguments(str(candidate["url"]), Path(frame_directory))]
            else:
                command = analyzer_command(str(candidate["url"]), Path(frame_directory))
                command[0] = npx or "npx"
            command_hash = hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest()
            started_at = now_iso()
            if dry_run:
                results.append({
                    "signal_key": candidate["signal_key"],
                    "success": False,
                    "status": "dry_run",
                    "requested_command_sha256": command_hash,
                    "command_preview": [*command[:4], "<URL>", *command[5:]],
                })
                continue
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                    env=safe_child_environment(runtime_bin, whisper_bin, whisper_model, whisper_language, model_cache_dir),
                )
                stdout, stderr, exit_code, timed_out = completed.stdout, completed.stderr, completed.returncode, False
            except subprocess.TimeoutExpired as error:
                stdout = error.stdout.decode("utf-8", errors="replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
                stderr = error.stderr.decode("utf-8", errors="replace") if isinstance(error.stderr, bytes) else (error.stderr or "")
                exit_code, timed_out = None, True
            finished_at = now_iso()
            raw_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")
            failure = ""
            normalized: dict[str, Any] | None = None
            if timed_out:
                failure = "timeout"
            elif exit_code != 0:
                failure = classify_failure(f"{stdout}\n{stderr}")
            else:
                try:
                    decoded = json.loads(stdout)
                    normalized = normalize_result(decoded, candidate, str(raw_path.resolve()))
                    if not normalized["success"]:
                        failure = "no_media_evidence"
                except json.JSONDecodeError:
                    failure = "malformed_analyzer_output"
            write_json(str(receipt_path), {
                "schema_version": "video-evidence-execution-v0.1",
                "contract_version": CONTRACT_VERSION,
                "analyzer": {"name": ANALYZER_NAME, "version": ANALYZER_VERSION},
                "signal_key": candidate["signal_key"],
                "source_url_sha256": hashlib.sha256(str(candidate["url"]).encode("utf-8")).hexdigest(),
                "requested_command_sha256": command_hash,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "status": "complete" if normalized and normalized["success"] else failure,
                "started_at": started_at,
                "finished_at": finished_at,
                "raw_artifact": str(raw_path.resolve()),
                "stderr_artifact": str(stderr_path.resolve()),
                "temporary_frames_deleted": True,
                "cookie_environment_forwarded": False,
                "cloud_api_environment_forwarded": False,
                "local_whisper_configured": bool(whisper_bin),
                "runtime_bin_configured": bool(runtime_bin),
            })
            result = normalized or {"signal_key": candidate["signal_key"], "success": False}
            result.update({
                "status": "complete" if normalized and normalized["success"] else failure,
                "receipt_artifact": str(receipt_path.resolve()),
            })
            results.append(result)
            if failure == "safety_stop":
                hard_stop = failure
                break
    successful_count = sum(1 for item in results if item.get("success"))
    overall_status = (
        "blocked" if hard_stop else "dry_run" if dry_run else
        "complete" if results and successful_count == len(results) else
        "partial" if successful_count else "failed"
    )
    return {
        "schema_version": "video-evidence-results-v0.1",
        "contract_version": CONTRACT_VERSION,
        "created_at": now_iso(),
        "status": overall_status,
        "hard_stop": hard_stop,
        "max_concurrency": 1,
        "attempted_count": len(results),
        "successful_count": successful_count,
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Sequentially execute a bounded video evidence plan.")
    parser.add_argument("--plan", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--results-output", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--analyzer-entry", default="", help="Optional local dist/index.js for a pinned analyzer installation.")
    parser.add_argument("--runtime-bin", default="", help="Optional isolated directory containing yt-dlp or other analyzer executables.")
    parser.add_argument("--whisper-bin", default="", help="Optional local Whisper-compatible CLI executable. Cloud speech APIs remain disabled.")
    parser.add_argument("--whisper-model", default="tiny")
    parser.add_argument("--whisper-language", default="")
    parser.add_argument("--model-cache-dir", default="", help="Optional isolated Hugging Face model cache used by local Whisper.")
    args = parser.parse_args()
    if args.timeout_seconds < 30 or args.timeout_seconds > 600:
        raise SystemExit("--timeout-seconds must be between 30 and 600.")
    plan_path = Path(args.plan).resolve()
    analyzer_entry = Path(args.analyzer_entry).resolve() if args.analyzer_entry else None
    runtime_bin = Path(args.runtime_bin).resolve() if args.runtime_bin else None
    whisper_bin = Path(args.whisper_bin).resolve() if args.whisper_bin else None
    model_cache_dir = Path(args.model_cache_dir).resolve() if args.model_cache_dir else None
    result = run_plan(
        load_data(str(plan_path)), Path(args.output_dir).resolve(), args.timeout_seconds,
        args.dry_run, analyzer_entry, runtime_bin, whisper_bin, args.whisper_model,
        args.whisper_language, model_cache_dir,
    )
    result["plan_artifact"] = str(plan_path)
    result["result_artifact"] = str(Path(args.results_output).resolve())
    write_json(args.results_output, result)
    print(json.dumps({
        "status": result["status"],
        "attempted": result["attempted_count"],
        "successful": result["successful_count"],
        "output": str(Path(args.results_output).resolve()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
