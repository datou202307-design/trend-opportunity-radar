from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from _common import as_text, load_data, now_iso, write_json
from check_collection_adapter import executable_command, resolve_opencli
from run_facebook_topic_capture import CAPTURE_SCHEMA, canonical_content


Runner = Callable[..., subprocess.CompletedProcess[str]]
Sleeper = Callable[[float], None]
Checkpoint = Callable[[dict[str, Any]], None]
METRIC_CONTRACT = "facebook-engagement-fields-v0.2"
PACING_POLICY = "controlled-read-pacing-v0.1"
PACING_INTERVAL_SECONDS = 10.0
PACING_COOLDOWN_SECONDS = 30.0
HARD_STOP_REASONS = {"captcha", "rate_limit", "login_expired", "permission_prompt", "abnormal_redirect", "private_content"}

CARD_JS = r"""JSON.stringify((function(){
function clean(s){return (s||'').replace(/\s+/g,' ').trim();}
function targetLink(a){return /facebook\.com\/(?:reel\/|[^/?#]+\/posts\/|share\/p\/|photo\/|permalink\.php)/i.test(a.href||'');}
return Array.from(document.querySelectorAll('[role="article"]')).map(function(article){
  var anchors=Array.from(article.querySelectorAll('a[href]'));
  var link=anchors.find(targetLink);
  if(!link){return null;}
  var heading=article.querySelector('h2,h3,h4,strong');
  var buttons=Array.from(article.querySelectorAll('[role="button"],button')).map(function(b){return {label:clean(b.getAttribute('aria-label')),text:clean(b.innerText)};}).filter(function(b){return b.label||b.text;});
  var observed=clean(link.innerText);
  return {canonical_url:link.href,author_name:clean(heading&&heading.innerText),preview_text:clean(article.innerText).slice(0,3000),observed_time_label:observed,button_labels:buttons};
}).filter(Boolean);
})())"""

DETAIL_JS = r"""JSON.stringify((function(){
function clean(s){return (s||'').replace(/\s+/g,' ').trim();}
var metas=Array.from(document.querySelectorAll('meta'));
function meta(k,v){var x=metas.find(function(m){return m.getAttribute(k)===v;});return x?x.content:'';}
var article=document.querySelector('[role="article"]')||document.querySelector('[role="main"]')||document.body;
var heading=article&&article.querySelector('h2,h3,h4,strong');
var time=article&&article.querySelector('abbr,time,a[href*="/posts/"],a[href*="/reel/"]');
var buttons=article?Array.from(article.querySelectorAll('[role="button"],button')).map(function(b){return {label:clean(b.getAttribute('aria-label')),text:clean(b.innerText)};}).filter(function(b){return b.label||b.text;}):[];
var comments=Array.from(document.querySelectorAll('[role="article"]')).map(function(node){
  var label=clean(node.getAttribute('aria-label'));
  if(!/(comment by|comment from|的评论|评论者|回复者)/i.test(label)){return null;}
  var author=node.querySelector('h3,h4,strong,a[role="link"]');
  var text=clean(node.innerText);
  if(!text){return null;}
  var visibleAuthor=clean(author&&author.innerText)||clean(text.split(' · ')[0]);
  var labelledAuthor=label.replace(/^(comment by|comment from|评论者|回复者)\s*/i,'').replace(/^[:：]\s*/, '').replace(/(?:\d+\s*(?:分钟|小时|天|周|月|年)(?:前)?).*$/,'').trim();
  return {author_name:visibleAuthor||labelledAuthor,text:text,top_level_visible:true};
}).filter(Boolean).slice(0,5);
return {canonical_url:location.href,page_title:document.title,og_title:meta('property','og:title'),description:meta('property','og:description')||meta('name','description'),visible_text:clean(article&&article.innerText).slice(0,6000),page_text:clean(document.body&&document.body.innerText).slice(0,6000),author_name:clean(heading&&heading.innerText),observed_time_label:clean(time&&(time.getAttribute('datetime')||time.innerText)),button_labels:buttons,representative_comments:comments,password_input_count:document.querySelectorAll('input[type="password"]').length};
})())"""

STATUS_JS = r"""JSON.stringify({url:location.href,title:document.title,body_text:(document.body&&document.body.innerText||'').slice(0,6000),article_count:document.querySelectorAll('[role="article"]').length,listitem_count:document.querySelectorAll('[role="listitem"]').length,feed_count:document.querySelectorAll('[role="feed"]').length,password_input_count:document.querySelectorAll('input[type="password"]').length})"""

COMMENT_TRIGGER_JS = r"""JSON.stringify((function(){
function clean(s){return (s||'').replace(/\s+/g,' ').trim();}
var candidates=Array.from(document.querySelectorAll('[role="button"],button,a[role="link"]'));
var target=candidates.find(function(node){
  var label=clean((node.getAttribute('aria-label')||'')+' '+(node.innerText||''));
  return /\d/.test(label)&&/(comments?|评论|留言|回覆)/i.test(label)&&!/(write|reply|respond|发表评论|写评论|回复)/i.test(label);
});
if(!target){return {clicked:false,label:''};}
var label=clean((target.getAttribute('aria-label')||'')+' '+(target.innerText||''));
target.click();
return {clicked:true,label:label.slice(0,200)};
})())"""


def sanitize_visible_text(value: Any) -> str:
    text = as_text(value)
    if "�" not in text:
        return text
    return " ".join(part for part in text.split() if "�" not in part).strip()


def is_unavailable_surface(value: Any) -> bool:
    text = sanitize_visible_text(value).casefold()
    return bool(re.search(r"页面无法显示|页面已被移除|link may be broken|page may have been removed|content isn't available|content is not available", text))


def detect_safety_stop(raw: object, expected_url: str = "", *, query_surface: bool = False) -> str:
    data = raw if isinstance(raw, dict) else {}
    actual_url = sanitize_visible_text(data.get("url") or data.get("canonical_url"))
    title = sanitize_visible_text(data.get("title") or data.get("page_title"))
    body = sanitize_visible_text(data.get("body_text") or data.get("page_text") or data.get("visible_text"))
    combined = f"{title}\n{body}".casefold()
    path = urlparse(actual_url).path.casefold()
    if re.search(r"captcha|验证码|security check|安全检查|confirm you(?:'|’)re human|确认你是真人", combined):
        return "captcha"
    if re.search(r"too many requests|rate limit|try again later|操作过于频繁|请求过多|请稍后再试", combined):
        return "rate_limit"
    if path.startswith("/login") or int(data.get("password_input_count") or 0) > 0 or re.search(r"log into facebook|登录 facebook 帐号|登录 facebook", combined):
        return "login_expired"
    if path.startswith("/checkpoint") or re.search(r"approval required|permission required|需要你的许可|需要获得许可|请确认你的身份", combined):
        return "permission_prompt"
    if re.search(r"this content is private|private group|仅限成员|私密小组|你无权查看", combined):
        return "private_content"
    if expected_url and actual_url:
        expected = urlparse(expected_url)
        actual = urlparse(actual_url)
        if query_surface:
            expected_query = parse_qs(expected.query).get("q", [""])[0].casefold()
            actual_query = parse_qs(actual.query).get("q", [""])[0].casefold()
            if actual.scheme in {"http", "https"} and not (actual.netloc.casefold().endswith("facebook.com") and actual.path.rstrip("/") == "/search/posts" and actual_query == expected_query):
                return "abnormal_redirect"
        elif expected.netloc.casefold().endswith("facebook.com") and not actual.netloc.casefold().endswith("facebook.com"):
            return "abnormal_redirect"
    return ""


def inspect_surface(raw: object, query_url: str, query_term: str, card_count: int) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    actual_url = sanitize_visible_text(data.get("url"))
    parsed = urlparse(actual_url)
    expected = urlparse(query_url)
    actual_query = parse_qs(parsed.query).get("q", [""])[0]
    expected_query = parse_qs(expected.query).get("q", [query_term])[0]
    url_matches = parsed.netloc.casefold().endswith("facebook.com") and parsed.path.rstrip("/") == "/search/posts" and actual_query.casefold() == expected_query.casefold()
    body = sanitize_visible_text(data.get("body_text"))
    title = sanitize_visible_text(data.get("title"))
    query_identity = url_matches and query_term.casefold() in f"{title}\n{body}".casefold()
    lowered = body.casefold()
    explicit_empty = bool(re.search(r"没有(?:找到|任何).{0,20}(?:结果|帖子)|找不到.{0,20}(?:结果|帖子)|未找到.{0,20}(?:结果|帖子)|no results(?: found)?|couldn['’]t find any results|didn['’]t find any results", lowered))
    safety_stop = detect_safety_stop(data, query_url, query_surface=True)
    if safety_stop:
        state = "safety_stop"
    elif query_identity and card_count > 0:
        state = "results_visible"
    elif query_identity and explicit_empty:
        state = "explicit_empty"
    else:
        state = "surface_unreadable"
    return {"state": state, "url_matches_request": url_matches, "query_identity": query_identity, "canonical_card_count": int(card_count), "explicit_empty": explicit_empty, "safety_stop": safety_stop}


def pace_before_request(completed_requests: int, sleeper: Sleeper) -> dict[str, float | int | bool]:
    if completed_requests <= 0:
        return {"request_index": 1, "wait_seconds": 0.0, "cooldown": False}
    cooldown = completed_requests % 5 == 0
    wait_seconds = PACING_COOLDOWN_SECONDS if cooldown else PACING_INTERVAL_SECONDS
    sleeper(wait_seconds)
    return {"request_index": completed_requests + 1, "wait_seconds": wait_seconds, "cooldown": cooldown}


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


def run_cli(cli_path: str, args: list[str], timeout: int, runner: Runner, *, expect_json: bool = True) -> Any:
    command = executable_command(cli_path, args, "@jackwener/opencli", ("dist", "src", "main.js"))
    completed = runner(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(as_text(completed.stderr) or "OpenCLI Facebook browser command failed.")
    if not expect_json:
        return as_text(completed.stdout)
    return parse_json_output(completed.stdout)


def parse_count(value: Any) -> int | None:
    text = as_text(value).replace("，", ",").casefold()
    match = re.search(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*([kmb万亿]?)", text)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    suffix = match.group(2)
    factor = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000, "万": 10_000, "亿": 100_000_000}.get(suffix, 1)
    return int(number * factor)


def parse_metrics(buttons: Any) -> dict[str, int | None]:
    result: dict[str, int | None] = {"reactions": None, "comments": None, "shares": None, "views": None}
    if not isinstance(buttons, list):
        return result
    for item in buttons:
        if not isinstance(item, dict):
            continue
        label = " ".join(filter(None, [as_text(item.get("label")), as_text(item.get("text"))]))
        count = parse_count(label)
        if count is None:
            continue
        lowered = label.casefold()
        if re.search(r"评论|comment", lowered):
            if result["comments"] is None:
                result["comments"] = count
        elif re.search(r"分享|share|发送给", lowered):
            if result["shares"] is None:
                result["shares"] = count
        elif re.search(r"播放|观看|views?|plays?", lowered):
            if result["views"] is None:
                result["views"] = count
        elif re.search(r"回应|reactions?", lowered):
            if result["reactions"] is None:
                result["reactions"] = count
    return result


def normalize_card(raw: dict[str, Any]) -> dict[str, Any] | None:
    identity = canonical_content(raw.get("canonical_url"))
    if not identity:
        return None
    kind, _, url = identity
    preview = sanitize_visible_text(raw.get("preview_text"))
    if not preview:
        return None
    return {
        "canonical_url": url,
        "author_name": sanitize_visible_text(raw.get("author_name")),
        "preview_text": preview,
        "observed_time_label": sanitize_visible_text(raw.get("observed_time_label")),
        "content_format": kind,
        **parse_metrics(raw.get("button_labels")),
    }


def normalize_detail(raw: dict[str, Any], requested_url: str, fallback_card: dict[str, Any] | None = None) -> dict[str, Any] | None:
    requested = canonical_content(requested_url)
    observed = canonical_content(raw.get("canonical_url"))
    if not requested or not observed or requested[1] != observed[1]:
        return None
    description = sanitize_visible_text(raw.get("description"))
    visible = sanitize_visible_text(raw.get("visible_text"))
    title = sanitize_visible_text(raw.get("og_title"))
    body = description or visible or title
    fallback = fallback_card if isinstance(fallback_card, dict) else {}
    time_label = sanitize_visible_text(raw.get("observed_time_label")) or sanitize_visible_text(fallback.get("observed_time_label"))
    if not body or not time_label or is_unavailable_surface(body):
        return None
    representative_comments: list[dict[str, Any]] = []
    seen_comments: set[tuple[str, str]] = set()
    for value in raw.get("representative_comments", []) if isinstance(raw.get("representative_comments"), list) else []:
        if not isinstance(value, dict) or value.get("top_level_visible") is not True:
            continue
        author = sanitize_visible_text(value.get("author_name"))
        text = sanitize_visible_text(value.get("text"))
        key = (author.casefold(), text)
        if not text or key in seen_comments:
            continue
        seen_comments.add(key)
        representative_comments.append({"author_name": author, "text": text, "top_level_visible": True})
        if len(representative_comments) >= 5:
            break
    detail = {
        "canonical_url": requested[2],
        "author_name": sanitize_visible_text(raw.get("author_name")) or sanitize_visible_text(fallback.get("author_name")),
        "body_text": body,
        "published_at": time_label if re.match(r"^\d{4}-\d{2}-\d{2}", time_label) else "",
        "observed_time_label": time_label,
        "content_format": requested[0],
        **parse_metrics(raw.get("button_labels")),
        "representative_comments": representative_comments,
    }
    for field in ("reactions", "comments", "shares", "views"):
        if detail[field] is None:
            detail[field] = fallback.get(field)
    return detail


def select_detail_urls(pass_urls: list[str], max_detail_posts: int, content_ids: list[str] | None = None, attempt_limit: int | None = None) -> list[str]:
    frozen = [(url, canonical_content(url)) for url in pass_urls]
    if content_ids:
        requested = list(dict.fromkeys(as_text(value) for value in content_ids if as_text(value)))
        selected = [url for url, identity in frozen if identity and identity[1] in requested]
        missing = [value for value in requested if not any(identity and identity[1] == value for _, identity in frozen)]
        if missing:
            raise RuntimeError("Requested Facebook detail identities are not present in the frozen first pass.")
        if len(selected) > int(max_detail_posts):
            raise RuntimeError("Requested Facebook detail identities exceed the frozen detail budget.")
    else:
        selected = [url for url, identity in frozen if identity][: int(max_detail_posts)]
    if attempt_limit is not None:
        selected = selected[: max(0, int(attempt_limit))]
    return selected


def collect_pass(cli_path: str, session: str, query_url: str, query_term: str, max_posts: int, scrolls: int, pause_seconds: float, timeout: int, runner: Runner, sleeper: Sleeper, window: str = "background") -> tuple[list[str], dict[str, dict[str, Any]], dict[str, Any]]:
    run_cli(cli_path, ["browser", session, "open", query_url, "--window", window], timeout, runner, expect_json=False)
    sleeper(pause_seconds)
    ordered: list[str] = []
    cards: dict[str, dict[str, Any]] = {}
    for index in range(scrolls + 1):
        raw_rows = run_cli(cli_path, ["browser", session, "eval", CARD_JS], timeout, runner)
        if not isinstance(raw_rows, list):
            raise RuntimeError("Facebook Posts page did not return a card list.")
        if not raw_rows and index == 0:
            sleeper(pause_seconds)
            raw_rows = run_cli(cli_path, ["browser", session, "eval", CARD_JS], timeout, runner)
            if not isinstance(raw_rows, list):
                raise RuntimeError("Facebook Posts page did not return a card list after its bounded load wait.")
        for raw in raw_rows:
            card = normalize_card(raw) if isinstance(raw, dict) else None
            if not card:
                continue
            url = card["canonical_url"]
            if url not in cards:
                ordered.append(url)
                cards[url] = card
            elif len(card["preview_text"]) > len(cards[url]["preview_text"]):
                cards[url] = card
            if len(ordered) >= max_posts:
                break
        if len(ordered) >= max_posts or index == scrolls:
            break
        run_cli(cli_path, ["browser", session, "scroll", "down", "--amount", "900"], timeout, runner, expect_json=False)
        sleeper(pause_seconds)
    surface = run_cli(cli_path, ["browser", session, "eval", STATUS_JS], timeout, runner)
    return ordered[:max_posts], cards, inspect_surface(surface, query_url, query_term, len(ordered))


def capture_payload(request: dict[str, Any], passes: list[list[str]], card_index: dict[str, dict[str, Any]], posts: list[dict[str, Any]], scrolls: int, pause_seconds: float, repeat_pause_seconds: float, detail_pause_seconds: float, terminal: bool, pacing_count: int = 0, pacing_events: list[dict[str, Any]] | None = None, page_probes: list[dict[str, Any]] | None = None, forced_stop_reason: str = "") -> dict[str, Any]:
    first_pass = next((values for values in passes if values), [])
    probes = list(page_probes or [])
    if forced_stop_reason:
        stop_reason = forced_stop_reason
    elif posts:
        stop_reason = ""
    elif first_pass:
        stop_reason = "details_unavailable"
    elif terminal and probes and all(probe.get("state") == "explicit_empty" for probe in probes):
        stop_reason = "verified_zero_results"
    elif terminal and passes:
        stop_reason = "surface_unreadable"
    else:
        stop_reason = "details_unavailable"
    identity_verified = all(probe.get("query_identity") is True for probe in probes) if probes else True
    return {
        "schema_version": CAPTURE_SCHEMA,
        "captured_at": now_iso(),
        "request_sha256": request["request_sha256"],
        "query_term": request["query_term"],
        "query_url": request["query_url"],
        "stop_reason": stop_reason,
        "result_passes": passes,
        "result_cards": [card_index[url] for url in first_pass if url in card_index],
        "posts": posts,
        "page_probes": probes,
        "checks": {"posts_surface": identity_verified, "frozen_query_visible": identity_verified, "public_content_only": True, "no_home_feed": True, "no_mixed_search": True, "no_write_actions": True, "no_credential_export": True},
        "capture_audit": {"controller": "opencli_browser", "metric_contract_version": METRIC_CONTRACT, "terminal": terminal, "terminal_state": stop_reason or "results_observed", "pass_count": len(passes), "scroll_count_per_pass": scrolls, "pause_seconds": pause_seconds, "repeat_pause_seconds": repeat_pause_seconds, "detail_pause_seconds": detail_pause_seconds, "observed_first_pass": len(first_pass), "observed_second_pass": len(passes[1]) if len(passes) > 1 else 0, "preview_card_count": len(card_index), "detail_count": len(posts), "pacing": {"policy_version": PACING_POLICY, "request_count": pacing_count, "interval_seconds": PACING_INTERVAL_SECONDS, "cooldown_seconds": PACING_COOLDOWN_SECONDS, "events": list(pacing_events or [])}},
    }


def execute(request: dict[str, Any], cli_path: str, session: str, scrolls: int, pause_seconds: float, repeat_pause_seconds: float, detail_pause_seconds: float, timeout: int, runner: Runner = subprocess.run, sleeper: Sleeper = time.sleep, checkpoint: Checkpoint | None = None, window: str = "background", initial_capture: dict[str, Any] | None = None, target_passes: int = 2, include_details: bool = True, detail_only: bool = False, pacing_seed_count: int = 0, pacing_seed_events: list[dict[str, Any]] | None = None, detail_attempt_limit: int | None = None, detail_content_ids: list[str] | None = None) -> dict[str, Any]:
    max_posts = int(request["max_posts"])
    initial = initial_capture if isinstance(initial_capture, dict) else {}
    if initial and initial.get("request_sha256") != request.get("request_sha256"):
        raise RuntimeError("Facebook resume capture does not match the frozen request.")
    passes = [list(values) for values in initial.get("result_passes", []) if isinstance(values, list)]
    page_probes = [dict(value) for value in initial.get("page_probes", []) if isinstance(value, dict)]
    if len(passes) > target_passes:
        raise RuntimeError("Facebook resume capture already has more passes than requested.")
    card_index = {as_text(card.get("canonical_url")): dict(card) for card in initial.get("result_cards", []) if isinstance(card, dict) and as_text(card.get("canonical_url"))}
    for card in card_index.values():
        for field in ("author_name", "preview_text", "observed_time_label"):
            card[field] = sanitize_visible_text(card.get(field))
    initial_audit = initial.get("capture_audit") if isinstance(initial.get("capture_audit"), dict) else {}
    if initial and initial_audit.get("metric_contract_version") != METRIC_CONTRACT:
        for card in card_index.values():
            card["reactions"] = None
    posts = [dict(post) for post in initial.get("posts", []) if isinstance(post, dict) and sanitize_visible_text(post.get("body_text")) and sanitize_visible_text(post.get("observed_time_label")) and not is_unavailable_surface(post.get("body_text"))]
    initial_pacing = initial_audit.get("pacing") if isinstance(initial_audit.get("pacing"), dict) else {}
    local_pacing_count = int(initial_pacing.get("request_count", len(passes) + len(posts)))
    if int(pacing_seed_count) > local_pacing_count:
        pacing_count = int(pacing_seed_count)
        pacing_events = [dict(event) for event in (pacing_seed_events or []) if isinstance(event, dict)]
    else:
        pacing_count = local_pacing_count
        pacing_events = [dict(event) for event in initial_pacing.get("events", []) if isinstance(event, dict)]
    start_pass = len(passes)
    for pass_index in range(start_pass, target_passes if not detail_only else start_pass):
        pace_event = pace_before_request(pacing_count, sleeper)
        pace_event.update({"kind": "search_pass", "pass": pass_index + 1})
        pacing_events.append(pace_event)
        pass_session = f"{session}-pass-{pass_index + 1}"
        links, cards, surface = collect_pass(cli_path, pass_session, request["query_url"], request["query_term"], max_posts, scrolls, pause_seconds, timeout, runner, sleeper, window)
        pacing_count += 1
        passes.append(links)
        page_probes.append(surface)
        card_index.update(cards)
        if checkpoint:
            checkpoint(capture_payload(request, passes, card_index, posts, scrolls, pause_seconds, repeat_pause_seconds, detail_pause_seconds, False, pacing_count, pacing_events, page_probes))
        print(json.dumps({"stage": "search_pass", "pass": pass_index + 1, "observed": len(links)}, ensure_ascii=False), flush=True)
        if as_text(surface.get("safety_stop")) in HARD_STOP_REASONS:
            return capture_payload(request, passes, card_index, posts, scrolls, pause_seconds, repeat_pause_seconds, detail_pause_seconds, True, pacing_count, pacing_events, page_probes, as_text(surface.get("safety_stop")))
        if pass_index == 0 and target_passes > 1:
            sleeper(repeat_pause_seconds)
    if not passes:
        return capture_payload(request, passes, card_index, posts, scrolls, pause_seconds, repeat_pause_seconds, detail_pause_seconds, True, pacing_count, pacing_events, page_probes)
    if not include_details:
        return capture_payload(request, passes, card_index, posts, scrolls, pause_seconds, repeat_pause_seconds, detail_pause_seconds, True, pacing_count, pacing_events, page_probes)
    detail_session = f"{session}-detail"
    detail_source = next((values for values in passes if values), [])
    detail_urls = select_detail_urls(detail_source, int(request["max_detail_posts"]), detail_content_ids, detail_attempt_limit)
    for url in detail_urls:
        if any(as_text(post.get("canonical_url")) == url for post in posts):
            continue
        pace_event = pace_before_request(pacing_count, sleeper)
        pace_event.update({"kind": "detail", "url": url})
        pacing_events.append(pace_event)
        pacing_count += 1
        try:
            run_cli(cli_path, ["browser", detail_session, "open", url, "--window", window], timeout, runner, expect_json=False)
            sleeper(detail_pause_seconds)
            raw = run_cli(cli_path, ["browser", detail_session, "eval", DETAIL_JS], timeout, runner)
            fallback_comments = parse_count(card_index.get(url, {}).get("comments")) if isinstance(card_index.get(url), dict) else None
            raw_comments = parse_metrics(raw.get("button_labels"))["comments"] if isinstance(raw, dict) else None
            visible_comments = raw.get("representative_comments") if isinstance(raw, dict) and isinstance(raw.get("representative_comments"), list) else []
            safety_stop = detect_safety_stop(raw, url) if isinstance(raw, dict) else ""
            if safety_stop in HARD_STOP_REASONS:
                pace_event.update({"status": "safety_stop", "reason": safety_stop})
                return capture_payload(request, passes, card_index, posts, scrolls, pause_seconds, repeat_pause_seconds, detail_pause_seconds, True, pacing_count, pacing_events, page_probes, safety_stop)
            detail = normalize_detail(raw, url, card_index.get(url)) if isinstance(raw, dict) else None
            comment_expansion_allowed = "expand_exact_detail_comments_once" in set(request.get("allowed_actions", []))
            if detail and comment_expansion_allowed and not visible_comments and int(raw_comments or fallback_comments or 0) > 0:
                comment_event = pace_before_request(pacing_count, sleeper)
                comment_event.update({"kind": "comment_expand_and_read", "url": url})
                pacing_events.append(comment_event)
                pacing_count += 1
                trigger = run_cli(cli_path, ["browser", detail_session, "eval", COMMENT_TRIGGER_JS], timeout, runner)
                if isinstance(trigger, dict) and trigger.get("clicked") is True:
                    sleeper(detail_pause_seconds)
                    reread = run_cli(cli_path, ["browser", detail_session, "eval", DETAIL_JS], timeout, runner)
                    if isinstance(reread, dict):
                        raw = reread
                    reread_comments = raw.get("representative_comments") if isinstance(raw, dict) and isinstance(raw.get("representative_comments"), list) else []
                    if not reread_comments:
                        retry_event = pace_before_request(pacing_count, sleeper)
                        retry_event.update({"kind": "comment_read_retry", "url": url})
                        pacing_events.append(retry_event)
                        pacing_count += 1
                        retry = run_cli(cli_path, ["browser", detail_session, "eval", DETAIL_JS], timeout, runner)
                        if isinstance(retry, dict):
                            raw = retry
                    safety_stop = detect_safety_stop(raw, url) if isinstance(raw, dict) else ""
                    if safety_stop in HARD_STOP_REASONS:
                        pace_event.update({"status": "safety_stop", "reason": safety_stop})
                        return capture_payload(request, passes, card_index, posts, scrolls, pause_seconds, repeat_pause_seconds, detail_pause_seconds, True, pacing_count, pacing_events, page_probes, safety_stop)
                    detail = normalize_detail(raw, url, card_index.get(url)) if isinstance(raw, dict) else None
            if detail:
                posts.append(detail)
                pace_event.update({"status": "captured", "captured_comment_count": len(detail.get("representative_comments", []))})
                if checkpoint:
                    checkpoint(capture_payload(request, passes, card_index, posts, scrolls, pause_seconds, repeat_pause_seconds, detail_pause_seconds, False, pacing_count, pacing_events, page_probes))
            else:
                reason = "content_unavailable" if isinstance(raw, dict) and is_unavailable_surface(raw.get("page_text") or raw.get("visible_text")) else "detail_identity_or_fields_unverified"
                pace_event.update({"status": "rejected", "reason": reason})
        except subprocess.TimeoutExpired:
            pace_event.update({"status": "unavailable", "reason": "timeout"})
            break
        except RuntimeError:
            pace_event.update({"status": "unavailable", "reason": "controller_read_failed"})
            break
        sleeper(detail_pause_seconds)
    return capture_payload(request, passes, card_index, posts, scrolls, pause_seconds, repeat_pause_seconds, detail_pause_seconds, True, pacing_count, pacing_events, page_probes)


def probe_surface(request: dict[str, Any], cli_path: str, session: str, pause_seconds: float, timeout: int, runner: Runner = subprocess.run, sleeper: Sleeper = time.sleep, window: str = "background") -> dict[str, Any]:
    run_cli(cli_path, ["browser", session, "open", request["query_url"], "--window", window], timeout, runner, expect_json=False)
    sleeper(pause_seconds)
    value = run_cli(cli_path, ["browser", session, "eval", STATUS_JS], timeout, runner)
    if not isinstance(value, dict):
        raise RuntimeError("Facebook surface probe did not return an object.")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture a frozen Facebook Posts request through a logged-in, read-only OpenCLI browser session.")
    parser.add_argument("--request", required=True); parser.add_argument("--output", required=True)
    parser.add_argument("--session", default="trend-radar-facebook"); parser.add_argument("--cli-path", default="")
    parser.add_argument("--scrolls", type=int, default=4); parser.add_argument("--pause-seconds", type=float, default=10.0)
    parser.add_argument("--repeat-pause-seconds", type=float, default=20.0); parser.add_argument("--detail-pause-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=int, default=45)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--inspect-current-cards", action="store_true")
    parser.add_argument("--inspect-current-surface", action="store_true")
    parser.add_argument("--inspect-current-detail", action="store_true")
    parser.add_argument("--window", choices=["background", "foreground"], default="background")
    parser.add_argument("--resume-capture", default="")
    parser.add_argument("--target-passes", type=int, choices=[1, 2], default=2)
    parser.add_argument("--skip-details", action="store_true")
    parser.add_argument("--detail-only", action="store_true")
    parser.add_argument("--detail-attempt-limit", type=int, default=0)
    parser.add_argument("--detail-content-id", action="append", default=[])
    parser.add_argument("--pacing-state", default="")
    args = parser.parse_args()
    request = load_data(str(Path(args.request).resolve()))
    cli_path, _, errors = resolve_opencli(args.cli_path)
    if not cli_path:
        raise SystemExit("OpenCLI is unavailable; pass an existing executable path. " + "; ".join(errors))
    if args.inspect_current_cards:
        rows = run_cli(cli_path, ["browser", args.session, "eval", CARD_JS], args.timeout_seconds, subprocess.run)
        write_json(args.output, rows)
        print(json.dumps({"card_count": len(rows) if isinstance(rows, list) else 0}, ensure_ascii=False), flush=True)
        return
    if args.inspect_current_surface:
        surface = run_cli(cli_path, ["browser", args.session, "eval", STATUS_JS], args.timeout_seconds, subprocess.run)
        write_json(args.output, surface)
        print(json.dumps({"url": surface.get("url", "") if isinstance(surface, dict) else "", "article_count": surface.get("article_count", 0) if isinstance(surface, dict) else 0}, ensure_ascii=False), flush=True)
        return
    if args.inspect_current_detail:
        detail = run_cli(cli_path, ["browser", args.session, "eval", DETAIL_JS], args.timeout_seconds, subprocess.run)
        write_json(args.output, detail)
        print(json.dumps({"url": detail.get("canonical_url", "") if isinstance(detail, dict) else "", "visible_comment_count": len(detail.get("representative_comments", [])) if isinstance(detail, dict) and isinstance(detail.get("representative_comments"), list) else 0}, ensure_ascii=False), flush=True)
        return
    if args.probe_only:
        probe = probe_surface(request, cli_path, args.session, max(10.0, args.pause_seconds), args.timeout_seconds, window=args.window)
        write_json(args.output, probe)
        print(json.dumps(probe, ensure_ascii=False, indent=2), flush=True)
        return
    output_path = Path(args.output)
    pacing_path = Path(args.pacing_state).resolve() if args.pacing_state else None
    shared_pacing = load_data(str(pacing_path)) if pacing_path and pacing_path.exists() else {}
    if shared_pacing and shared_pacing.get("policy_version") != PACING_POLICY:
        raise SystemExit("Facebook pacing state uses an incompatible policy version.")

    def save_pacing(value: dict[str, Any]) -> None:
        if not pacing_path:
            return
        pacing = value.get("capture_audit", {}).get("pacing", {})
        write_json(pacing_path, {"schema_version": "facebook-controlled-read-state-v0.1", "updated_at": now_iso(), "session": args.session, "policy_version": PACING_POLICY, "request_count": int(pacing.get("request_count", 0)), "events": list(pacing.get("events", []))})

    def save_checkpoint(value: dict[str, Any]) -> None:
        write_json(output_path, value)
        save_pacing(value)
    initial_capture = load_data(str(Path(args.resume_capture).resolve())) if args.resume_capture else None
    capture = execute(request, cli_path, args.session, max(0, args.scrolls), max(10.0, args.pause_seconds), max(20.0, args.repeat_pause_seconds), max(10.0, args.detail_pause_seconds), args.timeout_seconds, checkpoint=save_checkpoint, window=args.window, initial_capture=initial_capture, target_passes=args.target_passes, include_details=not args.skip_details, detail_only=args.detail_only, pacing_seed_count=int(shared_pacing.get("request_count", 0)), pacing_seed_events=shared_pacing.get("events", []), detail_attempt_limit=args.detail_attempt_limit or None, detail_content_ids=args.detail_content_id)
    write_json(args.output, capture)
    save_pacing(capture)
    print(json.dumps(capture["capture_audit"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    main()
