from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json


SCHEMA_VERSION = "trend-monitor-v0.1"
SNAPSHOT_SCHEMA_VERSION = "trend-monitor-snapshot-v0.1"
COMPARISON_SCHEMA_VERSION = "trend-monitor-comparison-v0.1"
FAST_PLATFORMS = {"x", "tiktok"}


def _object(path: Path) -> dict[str, Any]:
    payload = load_data(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parse_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _plus_days(value: str, days: int) -> str:
    return (_parse_time(value) + timedelta(days=days)).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _eligible_topics(scored: dict[str, Any]) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    for item in scored.get("topics", []):
        if not isinstance(item, dict):
            continue
        audit = item.get("cluster_audit") if isinstance(item.get("cluster_audit"), dict) else {}
        if audit.get("status") not in {"passed", "not_required"}:
            continue
        key = str(item.get("topic_key") or "").strip()
        if not key:
            continue
        topics.append({
            "topic_key": key,
            "title": str(item.get("title") or key),
            "observed_heat": int(item.get("observed_heat") or 0),
            "evidence_confidence": int(item.get("evidence_confidence") or 0),
            "sample_count": int(item.get("sample_count") or 0),
            "counter_signal_count": int(item.get("counter_signal_count") or 0),
            "score_version": str(item.get("score_version") or ""),
            "engagement_weight_version": str(item.get("engagement_weight_version") or ""),
        })
    return sorted(topics, key=lambda item: item["topic_key"])


def _snapshot(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _object(run_dir / "run-manifest.json")
    if manifest.get("state") != "complete":
        raise ValueError("A monitor snapshot requires a completed research run.")
    context = _object(run_dir / "research-context.json")
    subject = _object(run_dir / "subject.json")
    query_plan = _object(run_dir / "query-plan.json")
    scored = _object(run_dir / "scored-signals.json")
    report = _object(run_dir / "profile-report.json")
    report_path = run_dir / "profile-report.json"
    scored_path = run_dir / "scored-signals.json"
    topics = _eligible_topics(scored)
    if not topics:
        raise ValueError("A monitor snapshot requires at least one audited topic.")
    observed_at = str(scored.get("generated_at") or report.get("generated_at") or now_iso())
    report_sha256 = _sha256(report_path)
    scored_signals_sha256 = _sha256(scored_path)
    snapshot_id = _canonical_hash({
        "report_sha256": report_sha256,
        "scored_signals_sha256": scored_signals_sha256,
    })
    collection = scored.get("collection") if isinstance(scored.get("collection"), dict) else {}
    counts = collection.get("counts") if isinstance(collection.get("counts"), dict) else {}
    compatibility = {
        "subject_sha256": _canonical_hash(subject),
        "platform": str(context.get("platform") or manifest.get("platform") or ""),
        "research_intent": str(context.get("research_intent") or ""),
        "profile_version": str(context.get("profile_version") or ""),
        "analysis_unit": str(context.get("analysis_unit") or ""),
        "language": str(context.get("language") or ""),
        "market": str(context.get("market") or ""),
        "mode": str(manifest.get("mode") or ""),
        "query_plan_sha256": _canonical_hash(query_plan),
        "score_versions": sorted({item["score_version"] for item in topics}),
        "engagement_weight_versions": sorted({item["engagement_weight_version"] for item in topics}),
    }
    findings_payload = _object(run_dir / "profile-findings.json")
    findings = [
        {"id": str(item.get("id") or ""), "title": str(item.get("title") or "")}
        for item in findings_payload.get("findings", []) if isinstance(item, dict)
    ]
    snapshot = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "snapshot_id": snapshot_id,
        "observed_at": observed_at,
        "run_dir": str(run_dir),
        "report_sha256": report_sha256,
        "scored_signals_sha256": scored_signals_sha256,
        "counts": {
            "observed_result_count": int(counts.get("observed_result_count") or 0),
            "unique_sample_count": int(counts.get("unique_sample_count") or scored.get("unique_sample_count") or 0),
            "detail_open_count": int(counts.get("detail_open_count") or 0),
            "counter_signal_count": int(counts.get("counter_signal_count") or 0),
        },
        "topics": topics,
        "findings": findings,
    }
    return compatibility, snapshot


def _append_log(monitor_dir: Path, event: dict[str, Any]) -> None:
    log_path = monitor_dir / "monitor-runs.jsonl"
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def create_monitor(run_dir: Path, monitor_dir: Path, *, cadence_days: int | None = None, max_snapshots: int = 4) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    monitor_dir = monitor_dir.resolve()
    if max_snapshots < 2:
        raise ValueError("max_snapshots must be at least 2.")
    compatibility, baseline = _snapshot(run_dir)
    cadence = cadence_days or (3 if compatibility["platform"] in FAST_PLATFORMS else 7)
    if cadence < 1:
        raise ValueError("cadence_days must be at least 1.")
    monitor_dir.mkdir(parents=True, exist_ok=True)
    state_path = monitor_dir / "monitor.json"
    monitor_id = hashlib.sha256(
        f"{compatibility['subject_sha256']}|{compatibility['platform']}|{compatibility['profile_version']}".encode("utf-8")
    ).hexdigest()[:16]
    if state_path.is_file():
        existing = _object(state_path)
        if existing.get("monitor_id") != monitor_id or existing.get("snapshots", [{}])[0].get("snapshot_id") != baseline["snapshot_id"]:
            raise ValueError("The monitor directory already belongs to a different baseline.")
        return existing
    created_at = now_iso()
    monitor = {
        "schema_version": SCHEMA_VERSION,
        "monitor_id": monitor_id,
        "status": "active",
        "compatibility": compatibility,
        "cadence": {
            "days": cadence,
            "target_snapshot_count": max_snapshots,
            "check_rule": "run_when_due",
            "acts_when": "a_new_completed_compatible_snapshot_exists",
        },
        "safety": {
            "read_only": True,
            "external_schedule_created": False,
            "requires_explicit_scheduler_confirmation": True,
            "stop_on_access_or_rate_limit": True,
        },
        "snapshots": [baseline],
        "created_at": created_at,
        "updated_at": created_at,
        "next_run_after": _plus_days(baseline["observed_at"], cadence),
        "last_action": "baseline_created",
    }
    write_json(state_path, monitor)
    write_json(monitor_dir / "frozen-subject.json", _object(run_dir / "subject.json"))
    write_json(monitor_dir / "frozen-research-context.json", _object(run_dir / "research-context.json"))
    write_json(monitor_dir / "frozen-query-plan.json", _object(run_dir / "query-plan.json"))
    _append_log(monitor_dir, {
        "at": created_at, "event": "create", "checked": 1, "acted": 1,
        "snapshot_id": baseline["snapshot_id"], "note": "baseline snapshot frozen; no external schedule created",
    })
    return monitor


def append_snapshot(monitor_dir: Path, run_dir: Path) -> dict[str, Any]:
    monitor_dir = monitor_dir.resolve()
    run_dir = run_dir.resolve()
    state_path = monitor_dir / "monitor.json"
    monitor = _object(state_path)
    compatibility, snapshot = _snapshot(run_dir)
    if compatibility != monitor.get("compatibility"):
        different = sorted(
            key for key in set(compatibility) | set(monitor.get("compatibility", {}))
            if compatibility.get(key) != monitor.get("compatibility", {}).get(key)
        )
        raise ValueError("Snapshot is incompatible with the frozen monitor: " + ", ".join(different))
    snapshots = monitor.get("snapshots") if isinstance(monitor.get("snapshots"), list) else []
    if any(item.get("snapshot_id") == snapshot["snapshot_id"] for item in snapshots if isinstance(item, dict)):
        _append_log(monitor_dir, {
            "at": now_iso(), "event": "append", "checked": 1, "acted": 0,
            "snapshot_id": snapshot["snapshot_id"], "note": "duplicate snapshot skipped",
        })
        return monitor
    target = int(monitor.get("cadence", {}).get("target_snapshot_count") or 4)
    if len(snapshots) >= target:
        raise ValueError("The monitor reached its target snapshot count; create a new monitoring cycle to continue.")
    if snapshots and _parse_time(snapshot["observed_at"]) <= _parse_time(str(snapshots[-1].get("observed_at"))):
        raise ValueError("A monitor snapshot must be newer than the latest appended snapshot.")
    snapshots.append(snapshot)
    monitor["snapshots"] = snapshots
    cadence = int(monitor.get("cadence", {}).get("days") or 7)
    monitor["next_run_after"] = _plus_days(snapshot["observed_at"], cadence)
    monitor["status"] = "complete" if len(snapshots) >= target else "active"
    monitor["last_action"] = "snapshot_appended"
    monitor["updated_at"] = now_iso()
    write_json(state_path, monitor)
    _append_log(monitor_dir, {
        "at": monitor["updated_at"], "event": "append", "checked": 1, "acted": 1,
        "snapshot_id": snapshot["snapshot_id"], "note": f"snapshot {len(snapshots)} of {target} appended",
    })
    return monitor


def _movement(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    before = {item["topic_key"]: item for item in previous.get("topics", [])}
    after = {item["topic_key"]: item for item in current.get("topics", [])}
    result: dict[str, list[dict[str, Any]]] = {key: [] for key in ("new", "strengthened", "persistent", "weakened", "disappeared")}
    for key in sorted(set(before) | set(after)):
        if key not in before:
            result["new"].append(after[key])
            continue
        if key not in after:
            result["disappeared"].append(before[key])
            continue
        old, new = before[key], after[key]
        delta = int(new.get("observed_heat") or 0) - int(old.get("observed_heat") or 0)
        item = {
            "topic_key": key,
            "title": new.get("title") or old.get("title"),
            "previous_observed_heat": int(old.get("observed_heat") or 0),
            "current_observed_heat": int(new.get("observed_heat") or 0),
            "observed_heat_delta": delta,
            "previous_evidence_confidence": int(old.get("evidence_confidence") or 0),
            "current_evidence_confidence": int(new.get("evidence_confidence") or 0),
        }
        if delta >= 5:
            result["strengthened"].append(item)
        elif delta <= -5:
            result["weakened"].append(item)
        else:
            result["persistent"].append(item)
    return result


def _comparison_markdown(result: dict[str, Any], language: str) -> str:
    zh = language.lower().startswith("zh")
    title = "持续监测对比" if zh else "Monitoring comparison"
    lines = [f"# {title}", "", result["summary"], ""]
    labels = {
        "new": "本轮新出现" if zh else "New in this snapshot",
        "strengthened": "本轮更明显" if zh else "More visible in this snapshot",
        "persistent": "持续存在" if zh else "Persistent",
        "weakened": "本轮减弱" if zh else "Less visible in this snapshot",
        "disappeared": "本轮未再出现" if zh else "Not observed again",
    }
    for key, label in labels.items():
        lines.extend((f"## {label}", ""))
        items = result["movement"][key]
        if not items:
            lines.append("- 无" if zh else "- None")
        else:
            for item in items:
                lines.append(f"- {item.get('title') or item.get('topic_key')}")
        lines.append("")
    boundary = (
        "这些变化只描述两个兼容平台快照之间的可见信号差异，不证明需求增长、因果关系或未来表现。"
        if zh else
        "These changes describe visible differences between two compatible platform snapshots; they do not prove demand growth, causality, or future performance."
    )
    lines.extend(("## " + ("解释边界" if zh else "Interpretation boundary"), "", boundary, ""))
    return "\n".join(lines)


def _comparison_html(result: dict[str, Any], language: str) -> str:
    zh = language.lower().startswith("zh")
    labels = {
        "new": "新出现" if zh else "New",
        "strengthened": "更明显" if zh else "More visible",
        "persistent": "持续存在" if zh else "Persistent",
        "weakened": "减弱" if zh else "Less visible",
        "disappeared": "未再出现" if zh else "Not observed again",
    }
    cards = []
    for key, label in labels.items():
        items = result["movement"][key]
        body = "".join(f"<li>{html.escape(str(item.get('title') or item.get('topic_key')))}</li>" for item in items)
        if not body:
            body = f"<li class='empty'>{'无' if zh else 'None'}</li>"
        cards.append(f"<section><span>{html.escape(label)}</span><strong>{len(items)}</strong><ul>{body}</ul></section>")
    boundary = (
        "只比较兼容快照中的可见信号，不证明需求增长、因果关系或未来表现。"
        if zh else
        "This compares visible signals in compatible snapshots; it does not prove demand growth, causality, or future performance."
    )
    embedded = html.escape(json.dumps(result, ensure_ascii=False))
    return f"""<!doctype html><html lang=\"{html.escape(language)}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{'持续监测对比' if zh else 'Monitoring comparison'}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6fb;color:#142033;font:16px/1.55 system-ui,sans-serif}}main{{max-width:1080px;margin:auto;padding:40px 22px}}header{{padding:34px;border-radius:24px;background:linear-gradient(135deg,#1d2a64,#5a48a8);color:white}}h1{{margin:6px 0 12px;font-size:clamp(30px,5vw,54px)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px;margin:22px 0}}section{{background:white;border:1px solid #e4e8f1;border-radius:18px;padding:20px;min-width:0}}section span{{color:#667085}}section strong{{display:block;font-size:32px;margin:4px 0}}ul{{padding-left:20px;margin-bottom:0}}li{{overflow-wrap:anywhere}}.empty{{color:#98a2b3}}aside{{background:#fff8e8;border:1px solid #f2d89c;border-radius:16px;padding:18px}}details{{margin-top:18px;color:#667085}}pre{{max-width:100%;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}}@media(max-width:520px){{main{{padding:16px 12px}}header{{padding:24px 20px;border-radius:18px}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main><header><small>{'受约束的时间对比' if zh else 'Constrained temporal comparison'}</small><h1>{'持续监测对比' if zh else 'Monitoring comparison'}</h1><p>{html.escape(result['summary'])}</p></header><div class=\"grid\">{''.join(cards)}</div><aside>{html.escape(boundary)}</aside><details><summary>{'查看机器审计' if zh else 'View machine audit'}</summary><pre>{embedded}</pre></details></main></body></html>"""


def compare_monitor(monitor_dir: Path, *, json_output: Path | None = None, markdown_output: Path | None = None, html_output: Path | None = None) -> dict[str, Any]:
    monitor_dir = monitor_dir.resolve()
    monitor = _object(monitor_dir / "monitor.json")
    snapshots = monitor.get("snapshots") if isinstance(monitor.get("snapshots"), list) else []
    if len(snapshots) < 2:
        raise ValueError("At least two compatible snapshots are required before temporal comparison.")
    previous, current = snapshots[-2], snapshots[-1]
    movement = _movement(previous, current)
    language = str(monitor.get("compatibility", {}).get("language") or "en")
    counts = {key: len(value) for key, value in movement.items()}
    if language.lower().startswith("zh"):
        summary = f"已比较第 {len(snapshots) - 1} 次与第 {len(snapshots)} 次兼容快照：新出现 {counts['new']} 项、持续 {counts['persistent']} 项、本轮更明显 {counts['strengthened']} 项、减弱 {counts['weakened']} 项、未再出现 {counts['disappeared']} 项。"
    else:
        summary = f"Compared compatible snapshots {len(snapshots) - 1} and {len(snapshots)}: {counts['new']} new, {counts['persistent']} persistent, {counts['strengthened']} more visible, {counts['weakened']} less visible, and {counts['disappeared']} not observed again."
    result = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "monitor_id": monitor.get("monitor_id"),
        "generated_at": now_iso(),
        "snapshot_count": len(snapshots),
        "compared_snapshot_ids": [previous.get("snapshot_id"), current.get("snapshot_id")],
        "summary": summary,
        "movement": movement,
        "boundary": "visible_compatible_snapshot_difference_only",
        "compatibility": monitor.get("compatibility"),
    }
    json_path = (json_output or monitor_dir / "monitor-compare.json").resolve()
    markdown_path = (markdown_output or monitor_dir / "monitor-compare.md").resolve()
    html_path = (html_output or monitor_dir / "monitor-compare.html").resolve()
    result["outputs"] = {
        "json": str(json_path),
        "markdown": str(markdown_path),
        "html": str(html_path),
    }
    write_json(json_path, result)
    markdown_path.write_text(_comparison_markdown(result, language), encoding="utf-8", newline="\n")
    html_path.write_text(_comparison_html(result, language), encoding="utf-8", newline="\n")
    _append_log(monitor_dir, {
        "at": result["generated_at"], "event": "compare", "checked": 2,
        "acted": sum(counts.values()), "note": summary,
    })
    return result
