from __future__ import annotations

import argparse
from pathlib import Path

from _common import load_data
from profile_decisions import require_valid_findings
from research_context import load_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Profile-specific findings against one frozen research context.")
    parser.add_argument("--research-context", required=True)
    parser.add_argument("--findings", required=True)
    parser.add_argument("--signals")
    args = parser.parse_args()
    context = load_context(Path(args.research_context).resolve())
    topic_keys = None
    if args.signals:
        snapshot = load_data(args.signals)
        topic_keys = {
            as_key for item in snapshot.get("topics", [])
            if (as_key := str(item.get("topic_key") or "").strip())
            and (item.get("cluster_audit") or {}).get("status") in {"passed", "not_required"}
        }
    require_valid_findings(load_data(args.findings), context, topic_keys=topic_keys)
    print(f"Validated {context['profile_version']} decision findings.")


if __name__ == "__main__":
    main()
