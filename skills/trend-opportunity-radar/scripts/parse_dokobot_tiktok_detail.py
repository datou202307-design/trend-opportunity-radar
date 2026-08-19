from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from _common import as_text, now_iso


TIKTOK_URL = re.compile(
    r"https://(?:www\.)?tiktok\.com/@([A-Za-z0-9._-]+)/(video|photo)/(\d+)(?:[^\s]*)?",
    re.IGNORECASE,
)
REFERENCE = re.compile(r"(?m)^\[(\d+)\]\s+(https://(?:www\.)?tiktok\.com/@[^\s]+)\s*$", re.IGNORECASE)
COUNT = re.compile(r"^([\d,.]+)\s*([KMB])?$", re.IGNORECASE)


def parse_count(value: str) -> int | None:
    match = COUNT.match(as_text(value).replace(" ", ""))
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get((match.group(2) or "").upper(), 1)
    return int(number * multiplier)


def clean_line(value: str) -> str:
    line = as_text(value).lstrip(">").strip()
    return re.sub(r"\*\*", "", line).strip()


def target_identity(text: str, target_url: str) -> dict[str, str] | None:
    requested = TIKTOK_URL.search(target_url)
    if not requested:
        return None
    requested_handle, requested_format, requested_id = requested.groups()
    observed = next((match for match in TIKTOK_URL.finditer(text) if match.group(3) == requested_id), None)
    if not observed:
        return None
    observed_handle, observed_format, _ = observed.groups()
    if observed_handle.casefold() != requested_handle.casefold():
        return None
    return {
        "content_id": requested_id,
        "handle": requested_handle,
        "requested_format": requested_format.casefold(),
        "content_format": observed_format.casefold(),
        "canonical_url": f"https://www.tiktok.com/@{requested_handle}/{observed_format.casefold()}/{requested_id}",
    }


def author_reference(text: str, handle: str) -> str:
    for ref, url in REFERENCE.findall(text):
        match = re.search(r"tiktok\.com/@([^/?#]+)", url, re.IGNORECASE)
        if match and match.group(1).casefold() == handle.casefold():
            return ref
    return ""


def target_block(text: str, identity: dict[str, str]) -> tuple[str, str, str, str] | None:
    ref = author_reference(text, identity["handle"])
    if not ref:
        return None
    pattern = re.compile(
        rf"(?ms)^([^\n]+?)\s+\[{re.escape(ref)}\]\s*\n\s*·\s*([^\n]+)\n\s*\n(.+?)(?=^---\s*$)",
    )
    candidates = []
    for match in pattern.finditer(text.replace("\r\n", "\n")):
        author = clean_line(match.group(1))
        published = clean_line(match.group(2))
        body_lines = [clean_line(line) for line in match.group(3).splitlines()]
        body = " ".join(line for line in body_lines if line and not line.startswith("[")).strip()
        body = re.sub(r"\s+", " ", body).replace(" more ", " ").strip()
        if body:
            candidates.append((author, published, body, match.group(0)))
    if not candidates:
        return None
    return max(candidates, key=lambda item: len(item[2]))


def metric_block(text: str, block_text: str) -> str:
    start = text.find(block_text)
    if start < 0:
        return ""
    before = text[:start]
    sections = re.split(r"(?m)^---\s*$", before)
    return next((section for section in reversed(sections) if section.strip()), "")


def parse_metrics(block: str) -> dict[str, int | None]:
    plain = "\n".join(clean_line(line) for line in block.splitlines() if clean_line(line))
    result: dict[str, int | None] = {"views": None, "likes": None, "comments": None, "shares": None, "saves": None}
    explicit = {
        "likes": re.search(r"([\d,.]+\s*[KMB]?)\s+likes?\b", plain, re.IGNORECASE),
        "shares": re.search(r"([\d,.]+\s*[KMB]?)\s+shares?\b", plain, re.IGNORECASE),
    }
    for key, match in explicit.items():
        if match:
            result[key] = parse_count(match.group(1))
    lines = [line for line in plain.splitlines() if line]
    favorite_boundary = next((i for i, line in enumerate(lines) if "favorite" in line.casefold()), len(lines))
    leading_counts = [parse_count(line) for line in lines[:favorite_boundary]]
    leading_counts = [value for value in leading_counts if value is not None]
    if result["likes"] is None and leading_counts:
        result["likes"] = leading_counts[0]
    if result["comments"] is None and len(leading_counts) > 1:
        result["comments"] = leading_counts[1]
    labels = {line.casefold(): index for index, line in enumerate(lines)}
    for label, key in (("comments", "comments"), ("favorites", "saves"), ("share", "shares"), ("like", "likes")):
        index = labels.get(label)
        if index is None or result[key] is not None:
            continue
        neighbors = lines[index + 1:index + 3] if label != "like" else lines[max(0, index - 1):index]
        value = next((parse_count(item) for item in neighbors if parse_count(item) is not None), None)
        if value is not None:
            result[key] = value
    if result["comments"] is None and result["likes"] is not None:
        like_line = next((i for i, line in enumerate(lines) if "likes" in line.casefold()), None)
        favorite_line = next((i for i, line in enumerate(lines) if "favorite" in line.casefold()), None)
        if like_line is not None and favorite_line is not None:
            value = next((parse_count(item) for item in lines[like_line + 1:favorite_line] if parse_count(item) is not None), None)
            result["comments"] = value
    return result


def parse_visible_comments(text: str, limit: int = 5) -> list[dict[str, Any]]:
    normalized = text.replace("\r\n", "\n")
    section = re.search(r"(?ms)^Comments\s*$\n(.+?)(?=^You may like\s*$)", normalized)
    if not section:
        return []
    comments: list[dict[str, Any]] = []
    for block in re.split(r"(?m)^---\s*$", section.group(1)):
        lines = [clean_line(line) for line in block.splitlines() if clean_line(line)]
        if len(lines) < 2:
            continue
        author = lines[0]
        body = lines[1]
        if author.casefold() in {"comments", "you may like"} or not body:
            continue
        likes = None
        published = ""
        for line in lines[2:]:
            if likes is None and re.search(r"\blikes?\b", line, re.IGNORECASE):
                match = re.search(r"([\d,.]+\s*[KMB]?)", line, re.IGNORECASE)
                likes = parse_count(match.group(1)) if match else None
            elif not published and re.search(r"(?:ago|\d{1,2}-\d{1,2}|\d{4})", line, re.IGNORECASE):
                published = line
        comments.append({"author_name": author, "text": body, "likes": likes, "reply_count": None, "published_at": published})
        if len(comments) >= limit:
            break
    return comments


def parse_tiktok_detail(
    text: str,
    target_url: str,
    raw_path: Path,
    metadata_path: Path,
    stdout_path: Path,
    stderr_path: Path,
    expected_title: str = "",
) -> dict[str, Any] | None:
    normalized = text.replace("\r\n", "\n").strip()
    identity = target_identity(normalized, target_url)
    if not normalized or not identity:
        return None
    target = target_block(normalized, identity)
    if not target:
        return None
    author_name, published, body, matched_block = target
    comments = parse_visible_comments(normalized, limit=5)
    metrics = parse_metrics(metric_block(normalized, matched_block))
    limitations = []
    if identity["content_format"] != identity["requested_format"]:
        limitations.append(f"The browser resolved the requested {identity['requested_format']} route as {identity['content_format']} for the same content ID.")
    if not comments:
        limitations.append("No representative comment text was visible in the bounded detail read; the displayed comment total is preserved when available.")
    if expected_title:
        expected_terms = {term.casefold() for term in re.findall(r"[A-Za-z0-9]{4,}", expected_title)}
        body_terms = {term.casefold() for term in re.findall(r"[A-Za-z0-9]{4,}", body)}
        if expected_terms and not expected_terms.intersection(body_terms):
            limitations.append("The opened detail shared the stable content identity but did not repeat the search-card wording.")
    now = now_iso()
    return {
        "content_id": identity["content_id"],
        "canonical_url": identity["canonical_url"],
        "title": body[:180],
        "summary": body,
        "published_at": published,
        "metrics": metrics,
        "author": {"id": identity["handle"], "name": author_name, "handle": f"@{identity['handle']}"},
        "platform_facts": {
            "content_format": identity["content_format"],
            "representative_comments": comments,
            "representative_comment_count": len(comments),
            "comment_sample_limit": 5,
            "comment_capture_status": "captured" if comments else "unavailable",
        },
        "limitations": limitations,
        "evidence_refs": [identity["canonical_url"], str(raw_path.resolve()), str(metadata_path.resolve())],
        "raw_artifacts": [str(raw_path.resolve()), str(stdout_path.resolve()), str(stderr_path.resolve()), str(metadata_path.resolve())],
        "captured_at": now,
        "metrics_captured_at": now,
    }
