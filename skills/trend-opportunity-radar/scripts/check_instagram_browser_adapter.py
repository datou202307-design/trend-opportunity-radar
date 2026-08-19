from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from _common import as_text, load_data, now_iso, write_json


SCHEMA_VERSION = "instagram-browser-preflight-v0.1"


def build_status(probe: dict[str, Any]) -> dict[str, Any]:
    links = probe.get("canonical_post_links") if isinstance(probe.get("canonical_post_links"), list) else []
    detail = probe.get("detail_probe") if isinstance(probe.get("detail_probe"), dict) else {}
    checks = {
        "logged_in_session": probe.get("logged_in_session") is True,
        "public_profile_accessible": probe.get("public_profile_accessible") is True,
        "canonical_post_links": len({as_text(item) for item in links if as_text(item)}) >= 3,
        "detail_identity": bool(as_text(detail.get("canonical_url")) and as_text(detail.get("content_id"))),
        "detail_publication_time": bool(as_text(detail.get("published_at"))),
        "detail_caption": bool(as_text(detail.get("caption"))),
        "no_follow_graph": probe.get("no_follow_graph") is True,
        "no_write_actions": probe.get("no_write_actions") is True,
        "no_credential_export": probe.get("no_credential_export") is True,
    }
    ready = all(checks.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter": "browser_readonly_capture",
        "checked_at": now_iso(),
        "ready": ready,
        "status": "ready" if ready else "probe_incomplete",
        "capabilities": {"instagram": ready},
        "research_scopes": {"instagram": ["account_research"] if ready else []},
        "checks": checks,
        "missing_checks": [key for key, value in checks.items() if not value],
        "session_packaged": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a redacted, read-only Instagram browser capability probe.")
    parser.add_argument("--probe", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    probe = load_data(args.probe)
    if not isinstance(probe, dict):
        raise SystemExit("Instagram browser probe must be a JSON object.")
    result = build_status(probe)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
