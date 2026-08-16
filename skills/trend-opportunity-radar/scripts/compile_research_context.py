from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import load_data, write_json
from research_context import compile_context, validate_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile a simple user request into a frozen research context.")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--intent", default="")
    parser.add_argument("--platform", default="")
    parser.add_argument("--subject")
    parser.add_argument("--language", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    subject = load_data(args.subject) if args.subject else None
    result = compile_context(args.prompt, intent=args.intent, platform=args.platform, subject=subject, language=args.language)
    validate_context(result, require_ready=args.require_ready)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_ready and result["status"] != "ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
