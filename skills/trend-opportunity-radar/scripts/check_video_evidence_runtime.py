from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from _common import now_iso, write_json
from video_evidence import ANALYZER_NAME, ANALYZER_VERSION, CONTRACT_VERSION


def executable_version(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (completed.stdout or completed.stderr).strip().splitlines()[0] if completed.returncode == 0 else ""


def inspect_runtime(analyzer_entry: Path | None, runtime_bin: Path | None, whisper_bin: Path | None) -> dict[str, Any]:
    node = shutil.which("node") or ""
    npx = shutil.which("npx") or shutil.which("npx.cmd") or ""
    analyzer_local = bool(analyzer_entry and analyzer_entry.is_file() and node)
    yt_dlp_path = ""
    if runtime_bin:
        for name in ("yt-dlp.exe", "yt-dlp"):
            candidate = runtime_bin / name
            if candidate.is_file():
                yt_dlp_path = str(candidate)
                break
    yt_dlp_path = yt_dlp_path or (shutil.which("yt-dlp") or "")
    whisper_path = str(whisper_bin) if whisper_bin and whisper_bin.is_file() else ""
    analyzer_available = analyzer_local or bool(npx)
    media_ready = analyzer_available and bool(yt_dlp_path)
    status = "multimodal_ready" if media_ready and whisper_path else "visual_ready" if media_ready else "runtime_incomplete"
    remediation = []
    if not analyzer_available:
        remediation.append("Install Node.js 18+ and provide a pinned local mcp-video-analyzer entry.")
    elif not analyzer_local:
        remediation.append("npx is visible, but a pinned local analyzer entry is recommended on Windows before a live run.")
    if not yt_dlp_path:
        remediation.append("Provide a working yt-dlp executable in an isolated runtime directory.")
    if media_ready and not whisper_path:
        remediation.append("Visual OCR can run; provide a local Whisper-compatible CLI only when speech transcription is required.")
    return {
        "schema_version": "video-evidence-runtime-status-v0.1",
        "contract_version": CONTRACT_VERSION,
        "checked_at": now_iso(),
        "status": status,
        "ready": media_ready,
        "capabilities": {
            "metadata": media_ready,
            "keyframes": media_ready,
            "ocr": media_ready,
            "local_asr": bool(media_ready and whisper_path),
            "douyin": False,
        },
        "runtime": {
            "analyzer": {"name": ANALYZER_NAME, "version": ANALYZER_VERSION, "local_entry": str(analyzer_entry or ""), "local_ready": analyzer_local},
            "node": node,
            "npx": npx,
            "yt_dlp": yt_dlp_path,
            "yt_dlp_version": executable_version([yt_dlp_path, "--version"]) if yt_dlp_path else "",
            "whisper": whisper_path,
        },
        "security": {
            "cookies_required": False,
            "cloud_api_keys_forwarded": False,
            "max_concurrency": 1,
        },
        "remediation": remediation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect the optional local video-evidence runtime without installing or collecting data.")
    parser.add_argument("--analyzer-entry", default="")
    parser.add_argument("--runtime-bin", default="")
    parser.add_argument("--whisper-bin", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    result = inspect_runtime(
        Path(args.analyzer_entry).resolve() if args.analyzer_entry else None,
        Path(args.runtime_bin).resolve() if args.runtime_bin else None,
        Path(args.whisper_bin).resolve() if args.whisper_bin else None,
    )
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_ready and not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
