from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


TEXT_SUFFIXES = {".md", ".py", ".json", ".yaml", ".yml", ".txt", ".toml", ".ini", ".html", ".css", ".xml"}
FORBIDDEN_FRAGMENTS = (
    "Circle" + "Up",
    "文旅全链路营销中心",
    "codex-clipboard-",
    "AppData/Local/Temp",
    "AppData\\Local\\Temp",
)
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"][^'\"]{8,}"),
    re.compile(r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/-]{12,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
)


def tracked_files(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [root / item for item in completed.stdout.splitlines() if item]


def audit(root: Path) -> list[str]:
    findings: list[str] = []
    for path in tracked_files(root):
        relative = path.relative_to(root).as_posix()
        if not path.is_file():
            continue
        if path.stat().st_size > 1_000_000:
            findings.append(f"large_file:{relative}:{path.stat().st_size}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"not_utf8:{relative}")
            continue
        if relative != "tools/audit_open_source_release.py":
            for fragment in FORBIDDEN_FRAGMENTS:
                if fragment.casefold() in text.casefold():
                    findings.append(f"private_or_branded_fragment:{relative}:{fragment}")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(f"possible_secret:{relative}:{pattern.pattern}")
        if relative != "LICENSE" and re.search(r"(?i)C:\\Users\\(?!example(?:\\|$))[^\\\s]+", text):
            findings.append(f"personal_windows_path:{relative}")
    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the public repository for common release leaks.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    findings = audit(Path(args.root).resolve())
    if findings:
        print("Open-source release audit failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Open-source release audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
