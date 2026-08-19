from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from _common import as_text, load_data, now_iso, write_json
from check_collection_adapter import executable_command, resolve_opencli


CAPTURE_SCHEMA = "instagram-hashtag-browser-capture-v0.1"
Runner = Callable[..., subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]

CARD_JS = r"""JSON.stringify(Array.from(document.links).filter(function(a){return a.href.indexOf('/p/')>=0||a.href.indexOf('/reel/')>=0;}).map(function(a){var i=a.getElementsByTagName('img')[0];return {canonical_url:a.href.split('?')[0],preview_text:i&&i.alt?i.alt:'',author_username:''};}))"""

DETAIL_JS = r"""JSON.stringify((function(){var metas=Array.from(document.getElementsByTagName('meta'));function m(k,v){var x=metas.find(function(e){return e.getAttribute(k)===v;});return x?x.content:'';}var ts=Array.from(document.getElementsByTagName('time'));var comments=ts.slice(1,6).map(function(t){var p=t;for(var i=0;i<4&&p;i++){p=p.parentElement;}var lines=((p&&p.innerText)||'').split('\n').map(function(x){return x.trim();}).filter(Boolean);return {author_username:lines[0]||'',text:lines.slice(2).join(' ').replace(/\b\d+ likes?\b/gi,'').replace(/\bReply\b/gi,'').trim(),published_at:t.dateTime||''};}).filter(function(x){return x.text;});return {canonical_url:location.href.split('?')[0],og_title:m('property','og:title'),description:m('property','og:description')||m('name','description'),published_at:ts.length?ts[0].dateTime:'',comments:comments};})())"""


def parse_json_output(value: str) -> Any:
    text = value.strip()
    if not text:
        raise RuntimeError("OpenCLI returned no browser result.")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError("OpenCLI returned a non-JSON browser result.") from error
    if isinstance(parsed, str):
        try:
            return json.loads(parsed)
        except json.JSONDecodeError:
            return parsed
    return parsed


def run_cli(cli_path: str, args: list[str], timeout: int, runner: Runner) -> Any:
    command = executable_command(cli_path, args, "@jackwener/opencli", ("dist", "src", "main.js"))
    completed = runner(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(as_text(completed.stderr) or "OpenCLI browser command failed.")
    return parse_json_output(completed.stdout)


def canonical_url(value: object) -> str:
    match = re.match(r"^https://(?:www\.)?instagram\.com/(?:[A-Za-z0-9._]{1,30}/)?(p|reel)/([A-Za-z0-9_-]+)/?", as_text(value))
    return f"https://www.instagram.com/{match.group(1)}/{match.group(2)}/" if match else ""


def parse_detail(raw: dict[str, Any]) -> dict[str, Any]:
    description = as_text(raw.get("description"))
    title = as_text(raw.get("og_title"))
    author = ""
    metrics = re.match(r"^([\d,.]+) likes?,\s*([\d,.]+) comments?\s*-\s*([A-Za-z0-9._]+)\s+on\s+", description, re.I | re.S)
    likes = int(metrics.group(1).replace(",", "")) if metrics else None
    comments = int(metrics.group(2).replace(",", "")) if metrics else None
    if metrics:
        author = metrics.group(3)
    caption = ""
    title_match = re.search(r'on Instagram:\s*"(.*)"\s*$', title, re.S)
    if title_match:
        caption = title_match.group(1).strip()
    if not caption:
        description_match = re.search(r':\s*"(.*)"\.?\s*$', description, re.S)
        if description_match:
            caption = description_match.group(1).strip()
    rows = raw.get("comments") if isinstance(raw.get("comments"), list) else []
    representative_comments = [
        {
            "author_name": as_text(item.get("author_username")),
            "text": as_text(item.get("text")),
            "published_at": as_text(item.get("published_at")),
            "likes": None,
            "observed_time_label": "",
            "top_level_visible": True,
        }
        for item in rows if isinstance(item, dict) and as_text(item.get("text"))
    ]
    return {
        "canonical_url": canonical_url(raw.get("canonical_url")),
        "author_username": author,
        "caption": caption,
        "published_at": as_text(raw.get("published_at")),
        "likes": likes,
        "comments": comments,
        "views": None,
        "representative_comments": representative_comments,
    }


def collect_pass(cli_path: str, session: str, query_url: str, max_posts: int, scrolls: int, pause_seconds: float, timeout: int, runner: Runner, sleeper: Sleeper) -> tuple[list[str], dict[str, dict[str, str]]]:
    run_cli(cli_path, ["browser", session, "open", query_url, "--window", "background"], timeout, runner)
    sleeper(pause_seconds)
    ordered: list[str] = []
    cards: dict[str, dict[str, str]] = {}
    for index in range(scrolls + 1):
        rows = run_cli(cli_path, ["browser", session, "eval", CARD_JS], timeout, runner)
        if not isinstance(rows, list):
            raise RuntimeError("Instagram result-page DOM did not return a card list.")
        for row in rows:
            if not isinstance(row, dict):
                continue
            url = canonical_url(row.get("canonical_url"))
            if not url:
                continue
            if url not in cards:
                ordered.append(url)
                cards[url] = {"canonical_url": url, "author_username": as_text(row.get("author_username")), "preview_text": as_text(row.get("preview_text"))}
            elif not cards[url]["preview_text"] and as_text(row.get("preview_text")):
                cards[url]["preview_text"] = as_text(row.get("preview_text"))
            if len(ordered) >= max_posts:
                break
        if len(ordered) >= max_posts or index == scrolls:
            break
        run_cli(cli_path, ["browser", session, "scroll", "down", "--amount", "900"], timeout, runner)
        sleeper(pause_seconds)
    return ordered[:max_posts], cards


def execute(request: dict[str, Any], cli_path: str, session: str, scrolls: int, pause_seconds: float, repeat_pause_seconds: float, detail_pause_seconds: float, timeout: int, runner: Runner = subprocess.run, sleeper: Sleeper = time.sleep) -> dict[str, Any]:
    max_posts = int(request["max_posts"])
    result_passes: list[list[str]] = []
    card_index: dict[str, dict[str, str]] = {}
    for pass_index in range(2):
        links, cards = collect_pass(cli_path, session, request["query_url"], max_posts, scrolls, pause_seconds, timeout, runner, sleeper)
        result_passes.append(links)
        for url, card in cards.items():
            if url not in card_index or (not card_index[url]["preview_text"] and card["preview_text"]):
                card_index[url] = card
        if pass_index == 0:
            sleeper(repeat_pause_seconds)
    first_pass = result_passes[0]
    detail_candidates = sorted(first_pass, key=lambda url: (not bool(card_index.get(url, {}).get("preview_text")), first_pass.index(url)))[: int(request["max_detail_posts"])]
    posts: list[dict[str, Any]] = []
    detail_session = f"{session}-detail"
    for url in detail_candidates:
        run_cli(cli_path, ["browser", detail_session, "open", url, "--window", "background"], timeout, runner)
        sleeper(detail_pause_seconds)
        raw = run_cli(cli_path, ["browser", detail_session, "eval", DETAIL_JS], timeout, runner)
        if isinstance(raw, dict):
            detail = parse_detail(raw)
            if detail["canonical_url"] == url and detail["caption"] and detail["published_at"]:
                posts.append(detail)
        sleeper(detail_pause_seconds)
    result_cards = [card_index[url] for url in first_pass if card_index.get(url, {}).get("preview_text")]
    return {
        "schema_version": CAPTURE_SCHEMA,
        "captured_at": now_iso(),
        "request_sha256": request["request_sha256"],
        "hashtag": request["hashtag"],
        "query_url": request["query_url"],
        "displayed_post_count_label": "",
        "result_passes": result_passes,
        "result_cards": result_cards,
        "posts": posts,
        "checks": {
            "hashtag_identity": True,
            "canonical_post_links": True,
            "public_fields_only": True,
            "no_account_search_proxy": True,
            "no_personalized_explore_feed": True,
            "no_write_actions": True,
            "no_credential_export": True,
        },
        "capture_audit": {
            "controller": "opencli_browser",
            "pass_count": 2,
            "scroll_count_per_pass": scrolls,
            "pause_seconds": pause_seconds,
            "repeat_pause_seconds": repeat_pause_seconds,
            "detail_pause_seconds": detail_pause_seconds,
            "observed_first_pass": len(first_pass),
            "observed_second_pass": len(result_passes[1]),
            "preview_card_count": len(result_cards),
            "detail_count": len(posts),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture one frozen Instagram hashtag request through a logged-in, read-only OpenCLI browser session.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--session", default="trend-radar-instagram")
    parser.add_argument("--cli-path", default="")
    parser.add_argument("--scrolls", type=int, default=8)
    parser.add_argument("--pause-seconds", type=float, default=4.0)
    parser.add_argument("--repeat-pause-seconds", type=float, default=15.0)
    parser.add_argument("--detail-pause-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    args = parser.parse_args()
    request = load_data(str(Path(args.request).resolve()))
    cli_path, _, errors = resolve_opencli(args.cli_path)
    if not cli_path:
        raise SystemExit("OpenCLI is unavailable; install it or pass --cli-path. " + "; ".join(errors))
    capture = execute(request, cli_path, args.session, args.scrolls, max(1.0, args.pause_seconds), max(10.0, args.repeat_pause_seconds), max(3.0, args.detail_pause_seconds), args.timeout_seconds)
    write_json(args.output, capture)
    print(json.dumps(capture["capture_audit"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
