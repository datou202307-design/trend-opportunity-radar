from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from _common import now_iso, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an auditable loopback-browser QA receipt for a generated HTML report.")
    parser.add_argument("--html-report", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--subject-visible", action="store_true")
    parser.add_argument("--first-screen-readable", action="store_true")
    parser.add_argument("--evidence-sections-readable", action="store_true")
    parser.add_argument("--console-error-count", type=int, required=True)
    args = parser.parse_args()
    if not args.url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise SystemExit("Visual QA URL must be served over loopback HTTP.")
    html_path = Path(args.html_report).resolve()
    if not html_path.is_file():
        raise SystemExit("HTML report does not exist.")
    checks = {
        "subject_visible": args.subject_visible,
        "first_screen_readable": args.first_screen_readable,
        "evidence_sections_readable": args.evidence_sections_readable,
        "console_error_count": args.console_error_count,
    }
    write_json(args.output, {
        "schema_version": "trend-html-visual-qa-v0.1",
        "status": "passed" if all(checks[name] for name in checks if name != "console_error_count") and args.console_error_count == 0 else "failed",
        "inspected_at": now_iso(),
        "url": args.url,
        "title": args.title,
        "html_sha256": hashlib.sha256(html_path.read_bytes()).hexdigest(),
        "checks": checks,
    })


if __name__ == "__main__":
    main()
