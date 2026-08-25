from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.parse import urlparse

from _common import as_text, load_data, now_iso, write_json


SCHEMA_VERSION = "facebook-posts-browser-preflight-v0.1"


def is_posts_search_url(value: Any) -> bool:
    try:
        parsed = urlparse(as_text(value))
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.netloc.casefold() in {"facebook.com", "www.facebook.com"} and parsed.path.rstrip("/") == "/search/posts"


def build_status(probe: dict[str, Any]) -> dict[str, Any]:
    links = probe.get("canonical_public_post_links") if isinstance(probe.get("canonical_public_post_links"), list) else []
    detail = probe.get("detail_probe") if isinstance(probe.get("detail_probe"), dict) else {}
    visible_links = {as_text(item) for item in links if as_text(item)}
    checks = {
        "logged_in_session": probe.get("logged_in_session") is True,
        "posts_search_url": is_posts_search_url(probe.get("query_url")),
        "frozen_query_identity": bool(as_text(probe.get("query")) and probe.get("query_identity_visible") is True),
        "posts_only_surface": probe.get("posts_only_surface") is True,
        "canonical_public_post_links": len(visible_links) >= 1,
        "detail_identity": bool(as_text(detail.get("canonical_url")) and as_text(detail.get("content_id"))),
        "detail_publication_or_body": bool(as_text(detail.get("published_at")) or as_text(detail.get("body"))),
        "no_personal_surfaces": probe.get("no_personal_surfaces") is True,
        "no_write_actions": probe.get("no_write_actions") is True,
        "no_credential_export": probe.get("no_credential_export") is True,
    }
    ready = all(checks.values())
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter": "facebook_posts_browser_capture",
        "checked_at": now_iso(),
        "ready": ready,
        "status": "ready" if ready else "probe_incomplete",
        "capabilities": {"facebook": ready},
        "research_scopes": {"facebook": ["topic_research"] if ready else []},
        "checks": checks,
        "missing_checks": [key for key, value in checks.items() if not value],
        "session_packaged": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a redacted Facebook Posts topic-read capability probe.")
    parser.add_argument("--probe", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    probe = load_data(args.probe)
    if not isinstance(probe, dict):
        raise SystemExit("Facebook Posts browser probe must be a JSON object.")
    result = build_status(probe)
    write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if args.require_ready and not result["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
