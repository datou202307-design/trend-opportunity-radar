from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from _common import now_iso, write_json


SCHEMA_VERSION = "collection-adapter-status-v0.2"
Runner = Callable[..., subprocess.CompletedProcess[str]]


def common_dokobot_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("DOKOBOT_CLI_PATH", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    located = shutil.which("dokobot")
    if located:
        candidates.append(Path(located))
    home = Path.home()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            candidates.extend([Path(appdata) / "npm" / "dokobot.cmd", Path(appdata) / "npm" / "dokobot.exe"])
    else:
        candidates.extend([
            home / ".npm-global" / "bin" / "dokobot",
            home / ".local" / "bin" / "dokobot",
            Path("/usr/local/bin/dokobot"),
            Path("/opt/homebrew/bin/dokobot"),
        ])
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def common_opencli_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get("OPENCLI_CLI_PATH", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    located = shutil.which("opencli")
    if located:
        candidates.append(Path(located))
    home = Path.home()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            candidates.extend([Path(appdata) / "npm" / "opencli.cmd", Path(appdata) / "npm" / "opencli.exe"])
    else:
        candidates.extend([
            home / ".npm-global" / "bin" / "opencli",
            home / ".local" / "bin" / "opencli",
            Path("/usr/local/bin/opencli"),
            Path("/opt/homebrew/bin/opencli"),
        ])
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def resolve_dokobot(explicit: str = "") -> tuple[str, str, list[str]]:
    candidates = [Path(explicit).expanduser()] if explicit else common_dokobot_candidates()
    errors: list[str] = []
    for candidate in candidates:
        try:
            candidate.stat()
            return str(candidate), "explicit" if explicit else "path_or_common_location", errors
        except PermissionError:
            errors.append(f"permission_denied:{candidate}")
        except OSError as error:
            if getattr(error, "winerror", None) == 5:
                errors.append(f"permission_denied:{candidate}")
    return "", "unresolved", errors


def resolve_opencli(explicit: str = "") -> tuple[str, str, list[str]]:
    candidates = [Path(explicit).expanduser()] if explicit else common_opencli_candidates()
    errors: list[str] = []
    for candidate in candidates:
        try:
            candidate.stat()
            return str(candidate), "explicit" if explicit else "path_or_common_location", errors
        except PermissionError:
            errors.append(f"permission_denied:{candidate}")
        except OSError as error:
            if getattr(error, "winerror", None) == 5:
                errors.append(f"permission_denied:{candidate}")
    return "", "unresolved", errors


def executable_command(cli_path: str, args: list[str], package: str, entry: tuple[str, ...]) -> list[str]:
    path = Path(cli_path)
    if os.name == "nt" and path.suffix.casefold() in {".cmd", ".bat", ".ps1"}:
        node_entry = path.parent / "node_modules" / package
        for part in entry:
            node_entry /= part
        node = path.parent / "node.exe"
        node_path = str(node) if node.exists() else shutil.which("node")
        if node_path and node_entry.exists():
            return [node_path, str(node_entry), *args]
    return [cli_path, *args]


def run_probe(command: list[str], timeout: int, runner: Runner = subprocess.run) -> dict[str, Any]:
    try:
        completed = runner(command, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "").strip(),
            "stderr": (completed.stderr or "").strip(),
            "error": "",
        }
    except FileNotFoundError:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": "", "error": "not_found"}
    except PermissionError:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": "", "error": "permission_denied"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": "", "error": "timeout"}
    except OSError as error:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": "", "error": f"os_error:{error.__class__.__name__}"}


def has_connected_browser(output: str) -> bool:
    lowered = output.lower()
    if not output or any(marker in lowered for marker in ("no devices", "no device", "not connected")):
        return False
    return bool(re.search(r"\b(chrome|edge|chromium)\b", lowered) and re.search(r"\bpid\s+\d+\b", lowered))


def remediation(status: str, adapter: str = "dokobot") -> list[str]:
    label = "OpenCLI" if adapter == "opencli" else "DokoBot"
    command = "opencli" if adapter == "opencli" else "dokobot"
    messages = {
        "cli_not_found": [
            f"Run `{command} --version` as a standalone command before concluding the CLI is absent.",
            f"If it is genuinely absent, install {label} only with the user's authorization.",
        ],
        "cli_not_visible": [
            f"The sandbox could not inspect a common npm location; run `{command} --version` as a standalone approved command.",
            f"If direct execution succeeds, authorize commands beginning with `{command}` for this task.",
        ],
        "cli_permission_denied": [
            f"Authorize a standalone read-only `{command} --version` probe or provide an allowed CLI path.",
        ],
        "cli_timeout": ["Retry one standalone version probe with a bounded timeout; do not loop."],
        "cli_error": [f"Inspect the recorded CLI error and update {label} if the installed entry point is broken."],
        "browser_not_connected": [
            "Open Chrome with the DokoBot extension and enable the local bridge, then run `dokobot doko list`.",
        ],
        "ready": [],
    }
    return messages.get(status, [])


def diagnose_dokobot(
    cli_path: str,
    resolution: str,
    resolution_errors: list[str] | None = None,
    timeout: int = 15,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    errors = resolution_errors or []
    base = {
        "schema_version": SCHEMA_VERSION,
        "adapter": "dokobot",
        "checked_at": now_iso(),
        "os": platform.system().lower(),
        "ready": False,
        "status": "",
        "cli": {"path": cli_path, "resolution": resolution, "version": ""},
        "browser": {"connected": False},
        "diagnostics": {"resolution_errors": errors},
    }
    if not cli_path:
        status = "cli_not_visible" if any(item.startswith("permission_denied:") for item in errors) else "cli_not_found"
        base["status"] = status
        base["remediation"] = remediation(status)
        return base

    version_probe = run_probe([cli_path, "--version"], timeout, runner)
    base["diagnostics"]["version_probe"] = version_probe
    if not version_probe["ok"]:
        error = version_probe["error"]
        status = "cli_permission_denied" if error == "permission_denied" else "cli_timeout" if error == "timeout" else "cli_not_found" if error == "not_found" else "cli_error"
        base["status"] = status
        base["remediation"] = remediation(status)
        return base
    base["cli"]["version"] = version_probe["stdout"].splitlines()[0] if version_probe["stdout"] else "unknown"

    device_probe = run_probe([cli_path, "doko", "list"], timeout, runner)
    base["diagnostics"]["device_probe"] = device_probe
    if not device_probe["ok"] or not has_connected_browser(device_probe["stdout"]):
        base["status"] = "browser_not_connected"
        base["remediation"] = remediation("browser_not_connected")
        return base
    base["status"] = "ready"
    base["ready"] = True
    base["browser"]["connected"] = True
    base["remediation"] = []
    return base


def diagnose_opencli(
    cli_path: str,
    resolution: str,
    resolution_errors: list[str] | None = None,
    timeout: int = 15,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    errors = resolution_errors or []
    base = {
        "schema_version": SCHEMA_VERSION,
        "adapter": "opencli",
        "checked_at": now_iso(),
        "os": platform.system().lower(),
        "ready": False,
        "status": "",
        "cli": {"path": cli_path, "resolution": resolution, "version": ""},
        "browser": {"connected": False},
        "capabilities": {"xiaohongshu": False, "x": False},
        "diagnostics": {"resolution_errors": errors},
    }
    if not cli_path:
        status = "cli_not_visible" if any(item.startswith("permission_denied:") for item in errors) else "cli_not_found"
        base["status"] = status
        base["remediation"] = remediation(status, "opencli")
        return base
    version_command = executable_command(cli_path, ["--version"], "@jackwener/opencli", ("dist", "src", "main.js"))
    version_probe = run_probe(version_command, timeout, runner)
    base["diagnostics"]["version_probe"] = version_probe
    if not version_probe["ok"]:
        error = version_probe["error"]
        status = "cli_permission_denied" if error == "permission_denied" else "cli_timeout" if error == "timeout" else "cli_not_found" if error == "not_found" else "cli_error"
        base["status"] = status
        base["remediation"] = remediation(status, "opencli")
        return base
    base["cli"]["version"] = version_probe["stdout"].splitlines()[0] if version_probe["stdout"] else "unknown"
    identity_command = executable_command(cli_path, ["xiaohongshu", "whoami", "-f", "json", "--window", "background"], "@jackwener/opencli", ("dist", "src", "main.js"))
    identity_probe = run_probe(identity_command, timeout, runner)
    combined = f"{identity_probe['stdout']}\n{identity_probe['stderr']}\n{identity_probe['error']}".casefold()
    base["diagnostics"]["identity_probe"] = {
        "ok": identity_probe["ok"],
        "returncode": identity_probe["returncode"],
        "error": identity_probe["error"],
        "session_state_redacted": True,
    }
    if not identity_probe["ok"] or any(marker in combined for marker in ("browser_connect", "not connected", "login_required", "not logged in")):
        base["status"] = "browser_not_connected"
        base["remediation"] = ["Enable the OpenCLI Chrome extension, keep the authorized Xiaohongshu session open, and rerun the preflight."]
        return base
    base["status"] = "ready"
    base["ready"] = True
    base["browser"]["connected"] = True
    base["capabilities"]["xiaohongshu"] = True
    base["remediation"] = []
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose whether a collection adapter is callable without installing or mutating it.")
    parser.add_argument("--adapter", choices=["dokobot", "opencli"], default="dokobot")
    parser.add_argument("--cli-path", default="")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--output")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    if args.timeout < 1 or args.timeout > 60:
        raise SystemExit("--timeout must be between 1 and 60 seconds.")
    if args.adapter == "opencli":
        cli_path, resolution, errors = resolve_opencli(args.cli_path)
        result = diagnose_opencli(cli_path, resolution, errors, args.timeout)
    else:
        cli_path, resolution, errors = resolve_dokobot(args.cli_path)
        result = diagnose_dokobot(cli_path, resolution, errors, args.timeout)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_ready and not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
