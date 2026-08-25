from __future__ import annotations

import hashlib
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from _common import load_data


SCHEMA_VERSION = "trend-workspace-v0.1"
PLATFORM_NAMES = {
    "x": "X",
    "xiaohongshu": "小红书",
    "youtube": "YouTube",
    "reddit": "Reddit",
    "instagram": "Instagram",
    "facebook": "Facebook",
    "tiktok": "TikTok",
}
INTENT_NAMES = {
    "business_opportunity": ("发现商业机会", "Business opportunity"),
    "brand_sentiment": ("监测品牌舆情", "Brand sentiment"),
    "competitor_users": ("研究竞品用户", "Competitor users"),
    "content_opportunity": ("寻找内容机会", "Content opportunity"),
    "product_demand": ("验证产品需求", "Product demand"),
}


def _object(path: Path) -> dict[str, Any]:
    payload = load_data(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return payload


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _href(target: Path, output_dir: Path) -> str:
    return quote(os.path.relpath(target.resolve(), output_dir.resolve()).replace("\\", "/"), safe="/.:#")


def _parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _latest_time(*values: object) -> str:
    parsed = [(item, _parse_time(item)) for item in values]
    valid = [(str(raw), moment) for raw, moment in parsed if moment]
    return max(valid, key=lambda item: item[1])[0] if valid else ""


def _write_if_changed(path: Path, value: str) -> bool:
    payload = value.encode("utf-8")
    if path.is_file() and path.read_bytes() == payload:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
    return True


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _run_record(path: Path, root: Path, output_dir: Path) -> dict[str, Any]:
    manifest = _object(path / "run-manifest.json")
    context_path = path / "research-context.json"
    subject_path = path / "subject.json"
    report_path = path / "profile-report.json"
    context = _object(context_path) if context_path.is_file() else {}
    subject = _object(subject_path) if subject_path.is_file() else {}
    report = _object(report_path) if report_path.is_file() else {}
    language = str(context.get("language") or report.get("language") or "en")
    zh = language.lower().startswith("zh")
    platform_key = str(context.get("platform") or manifest.get("platform") or report.get("platform") or "")
    intent = str(context.get("research_intent") or manifest.get("research_intent") or "")
    relative_dir = _relative(path, root)
    run_id = hashlib.sha256(f"{relative_dir}|{manifest.get('request_sha256', '')}".encode("utf-8")).hexdigest()[:14]
    state = str(manifest.get("state") or "unknown")
    report_html = path / "profile-report.html"
    return {
        "run_id": run_id,
        "relative_dir": relative_dir,
        "subject": str(subject.get("name") or subject.get("summary") or relative_dir),
        "platform": PLATFORM_NAMES.get(platform_key, platform_key or "—"),
        "platform_key": platform_key,
        "intent": intent,
        "intent_label": INTENT_NAMES.get(intent, (intent or "研究", intent or "Research"))[0 if zh else 1],
        "language": language,
        "state": state,
        "is_complete": state == "complete",
        "next_action": str(manifest.get("next_action") or ""),
        "decision_answer": str(report.get("decision_answer") or report.get("summary") or ""),
        "follow_up_recommended": bool((report.get("follow_up_recommendation") or {}).get("recommended")),
        "report_href": _href(report_html, output_dir) if report_html.is_file() else "",
        "updated_at": _latest_time(manifest.get("completed_at"), manifest.get("updated_at"), report.get("generated_at")),
    }


def _monitor_record(path: Path, root: Path, output_dir: Path, now: datetime) -> dict[str, Any]:
    monitor = _object(path / "monitor.json")
    snapshots = [item for item in monitor.get("snapshots", []) if isinstance(item, dict)]
    next_run = _parse_time(monitor.get("next_run_after"))
    status = str(monitor.get("status") or "unknown")
    due = bool(status == "active" and next_run and now >= next_run)
    safety = monitor.get("safety") if isinstance(monitor.get("safety"), dict) else {}
    relative_dir = _relative(path, root)
    latest = snapshots[-1] if snapshots else {}
    topics = latest.get("topics") if isinstance(latest.get("topics"), list) else []
    return {
        "monitor_id": str(monitor.get("monitor_id") or hashlib.sha256(relative_dir.encode()).hexdigest()[:14]),
        "relative_dir": relative_dir,
        "platform": PLATFORM_NAMES.get(str((monitor.get("compatibility") or {}).get("platform") or ""), str((monitor.get("compatibility") or {}).get("platform") or "—")),
        "status": status,
        "due": due,
        "next_run_after": str(monitor.get("next_run_after") or ""),
        "snapshot_count": len(snapshots),
        "target_snapshot_count": int((monitor.get("cadence") or {}).get("target_snapshot_count") or 4),
        "external_schedule_created": bool(safety.get("external_schedule_created")),
        "latest_topics": [str(item.get("title") or item.get("topic_key") or "") for item in topics[:3] if isinstance(item, dict)],
        "comparison_href": _href(path / "monitor-compare.html", output_dir) if (path / "monitor-compare.html").is_file() else "",
    }


def _action(kind: str, title: str, body: str, prompt: str, source: dict[str, Any]) -> dict[str, Any]:
    return {"kind": kind, "title": title, "body": body, "prompt": prompt, "source": source}


def build_workspace(root: Path, output_dir: Path, *, language: str = "en", now: datetime | None = None) -> dict[str, Any]:
    root = root.resolve()
    output_dir = output_dir.resolve()
    if not root.is_dir():
        raise ValueError("Workspace root must be an existing directory.")
    if not _inside(output_dir, root):
        raise ValueError("Workspace output must stay inside the indexed root so local report links remain usable.")
    existing_path = output_dir / "workspace.json"
    root_id = hashlib.sha256(str(root).casefold().encode("utf-8")).hexdigest()[:16]
    if existing_path.is_file():
        existing = _object(existing_path)
        if existing.get("schema_version") != SCHEMA_VERSION or existing.get("root_id") != root_id:
            raise ValueError("The output directory already belongs to a different workspace.")
    moment = now or datetime.now(timezone.utc)
    run_dirs = sorted({item.parent for item in root.rglob("run-manifest.json") if not _inside(item, output_dir)})
    monitor_dirs = sorted({item.parent for item in root.rglob("monitor.json") if not _inside(item, output_dir)})
    runs = [_run_record(path, root, output_dir) for path in run_dirs]
    monitors = [_monitor_record(path, root, output_dir, moment) for path in monitor_dirs]
    monitored_runs = {
        Path(str(snapshot.get("run_dir") or "")).resolve()
        for path in monitor_dirs
        for snapshot in (_object(path / "monitor.json").get("snapshots") or [])
        if isinstance(snapshot, dict) and snapshot.get("run_dir")
    }
    actions: list[dict[str, Any]] = []
    zh = language.lower().startswith("zh")
    for monitor in monitors:
        if monitor["due"]:
            title = f"采集 {monitor['platform']} 的下一期数据" if zh else f"Collect the next {monitor['platform']} snapshot"
            if monitor["external_schedule_created"]:
                body = (f"已到复采时间；当前 {monitor['snapshot_count']}/{monitor['target_snapshot_count']} 期。外部调度记录为已创建，本次仍需核对真实执行结果。" if zh else f"Collection is due; {monitor['snapshot_count']}/{monitor['target_snapshot_count']} snapshots exist. An external schedule is recorded, but this run must still verify its result.")
            else:
                body = (f"已到建议复采时间；当前 {monitor['snapshot_count']}/{monitor['target_snapshot_count']} 期。尚未因此宣称已创建定时任务。" if zh else f"The recommended collection time is due; {monitor['snapshot_count']}/{monitor['target_snapshot_count']} snapshots exist. This does not claim a scheduled task exists.")
            prompt = (f"使用 trend-opportunity-radar，继续监测目录 {monitor['relative_dir']} 的下一次兼容复采。" if zh else f"Use trend-opportunity-radar to continue the next compatible snapshot for monitor directory {monitor['relative_dir']}.")
            actions.append(_action("monitor_due", title, body, prompt, monitor))
    for run in runs:
        run_path = root / run["relative_dir"]
        if not run["is_complete"]:
            title = f"继续：{run['subject']}" if zh else f"Continue: {run['subject']}"
            body = run["next_action"] or ("读取运行清单中的唯一下一步。" if zh else "Follow the single next action in the run manifest.")
            prompt = (f"使用 trend-opportunity-radar，继续运行目录 {run['relative_dir']}，严格执行 run-manifest.json 中唯一的 next_action。" if zh else f"Use trend-opportunity-radar to continue run directory {run['relative_dir']} and follow the single next_action in run-manifest.json.")
            actions.append(_action("continue_run", title, body, prompt, run))
        elif run["follow_up_recommended"] and run_path.resolve() not in monitored_runs:
            title = f"决定是否持续观察：{run['subject']}" if zh else f"Decide whether to monitor: {run['subject']}"
            body = ("这份报告建议用兼容快照观察时间变化；当前只是建议，尚未创建监测或定时任务。" if zh else "This report recommends compatible snapshots for temporal change; no monitor or scheduled task has been created.")
            prompt = (f"使用 trend-opportunity-radar，为完成的运行目录 {run['relative_dir']} 创建本地监测周期；不要创建外部定时任务，除非我另行确认。" if zh else f"Use trend-opportunity-radar to create a local monitoring cycle for completed run {run['relative_dir']}; do not create an external scheduled task unless I confirm separately.")
            actions.append(_action("consider_monitoring", title, body, prompt, run))
    priority = {"monitor_due": 0, "continue_run": 1, "consider_monitoring": 2}
    actions.sort(key=lambda item: (priority[item["kind"]], str(item["title"]).casefold()))
    indexed_at = max([item.get("updated_at", "") for item in runs] + [item.get("next_run_after", "") for item in monitors] + [""])
    payload = {
        "schema_version": SCHEMA_VERSION,
        "root_id": root_id,
        "language": language,
        "indexed_at": indexed_at,
        "counts": {
            "runs": len(runs),
            "completed_runs": sum(1 for item in runs if item["is_complete"]),
            "open_runs": sum(1 for item in runs if not item["is_complete"]),
            "monitors": len(monitors),
            "due_monitors": sum(1 for item in monitors if item["due"]),
            "actions": len(actions),
        },
        "actions": actions,
        "runs": runs,
        "monitors": monitors,
        "privacy": {
            "local_only": True,
            "uploaded": False,
            "contains_raw_platform_content": False,
            "absolute_paths_exposed": False,
        },
    }
    cards_dir = output_dir / "summary-cards"
    for run in runs:
        if run["is_complete"] and run["decision_answer"]:
            _write_if_changed(cards_dir / f"{run['run_id']}.html", _summary_card(run, language))
            run["summary_card_href"] = f"summary-cards/{run['run_id']}.html"
    payload["source_fingerprint"] = hashlib.sha256(_json_text({k: v for k, v in payload.items() if k != "source_fingerprint"}).encode("utf-8")).hexdigest()
    _write_if_changed(existing_path, _json_text(payload))
    _write_if_changed(output_dir / "index.html", _workspace_html(payload))
    return payload


def _summary_card(run: dict[str, Any], language: str) -> str:
    zh = language.lower().startswith("zh")
    boundary = "这是单次平台信号研究的本地摘要，不代表需求增长、市场规模或未来表现。分享前请检查主题与结论是否适合公开。" if zh else "This is a local summary of one platform-signal study. It does not prove demand growth, market size, or future performance. Review the topic and decision before sharing."
    return f'''<!doctype html><html lang="{html.escape(language)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(run['subject'])}</title><style>*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:#071723;color:#f4f8fb;font:16px/1.65 system-ui,sans-serif}}main{{width:min(760px,100%);padding:clamp(28px,6vw,58px);border:1px solid #275064;border-radius:28px;background:linear-gradient(145deg,#102d3a,#0a1f2c);box-shadow:0 28px 80px #0005}}small{{color:#5eead4;font-weight:800;letter-spacing:.08em}}h1{{margin:16px 0 20px;font-size:clamp(34px,7vw,60px);line-height:1.08}}.answer{{font-size:clamp(18px,3vw,25px);color:#dbecef}}.meta{{display:flex;gap:10px;flex-wrap:wrap;margin-top:28px}}.meta span{{padding:6px 11px;border:1px solid #315163;border-radius:999px;color:#a9c6cf;font-size:13px}}aside{{margin-top:30px;padding-top:20px;border-top:1px solid #284454;color:#94aeb8;font-size:13px}}</style></head><body><main><small>{html.escape(run['intent_label'])}</small><h1>{html.escape(run['subject'])}</h1><p class="answer">{html.escape(run['decision_answer'])}</p><div class="meta"><span>{html.escape(run['platform'])}</span><span>{'单次信号快照' if zh else 'Single signal snapshot'}</span></div><aside>{html.escape(boundary)}</aside></main></body></html>'''


def _workspace_html(payload: dict[str, Any]) -> str:
    zh = str(payload.get("language") or "").lower().startswith("zh")
    headline = '<span>你的研究，</span><span>下一步做什么</span>' if zh else "What should happen next in your research?"
    actions = payload["actions"]
    action_cards = "".join(
        f'''<article class="action {html.escape(item['kind'])}"><span>{html.escape({'monitor_due': '到期复采', 'continue_run': '继续研究', 'consider_monitoring': '后续观察'}.get(item['kind'], item['kind']) if zh else {'monitor_due': 'Due snapshot', 'continue_run': 'Continue research', 'consider_monitoring': 'Follow-up'}.get(item['kind'], item['kind']))}</span><h3>{html.escape(item['title'])}</h3><p>{html.escape(item['body'])}</p><details><summary>{'查看继续用语' if zh else 'View the prompt to continue'}</summary><pre>{html.escape(item['prompt'])}</pre></details></article>'''
        for item in actions
    ) or f"<div class='empty'>{'目前没有待处理动作。' if zh else 'No actions need attention.'}</div>"
    run_cards = "".join(
        f'''<article class="run"><div><span class="platform">{html.escape(item['platform'])}</span><span class="status">{html.escape('已完成' if item['is_complete'] and zh else '进行中' if zh else 'Complete' if item['is_complete'] else 'In progress')}</span></div><h3>{html.escape(item['subject'])}</h3><p>{html.escape(item['intent_label'])}</p><nav>{f'<a href="{item["report_href"]}">{"打开报告" if zh else "Open report"}</a>' if item['report_href'] else ''}{f'<a href="{item.get("summary_card_href", "")}">{"摘要卡" if zh else "Summary card"}</a>' if item.get('summary_card_href') else ''}</nav></article>'''
        for item in payload["runs"]
    ) or f"<div class='empty'>{'尚未发现研究运行。' if zh else 'No research runs found.'}</div>"
    monitor_cards = "".join(
        f'''<article class="run"><div><span class="platform">{html.escape(item['platform'])}</span><span class="status">{html.escape('周期完成' if item['status'] == 'complete' and zh else '可以复采' if item['due'] and zh else '等待下一期' if zh else 'Cycle complete' if item['status'] == 'complete' else 'Due now' if item['due'] else 'Waiting')}</span></div><h3>{item['snapshot_count']}/{item['target_snapshot_count']} {'期数据' if zh else 'snapshots'}</h3><p>{html.escape(('已创建外部调度' if item['external_schedule_created'] else '未创建外部调度') if zh else ('External schedule created' if item['external_schedule_created'] else 'No external schedule created'))}</p>{f'<nav><a href="{item["comparison_href"]}">{"打开最近对比" if zh else "Open latest comparison"}</a></nav>' if item['comparison_href'] else ''}</article>'''
        for item in payload["monitors"]
    ) or f"<div class='empty'>{'尚未创建本地监测周期。' if zh else 'No local monitoring cycles exist.'}</div>"
    counts = payload["counts"]
    return f'''<!doctype html><html lang="{html.escape(payload['language'])}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{'趋势研究工作区' if zh else 'Trend research workspace'}</title><style>
:root{{--bg:#f4f7f8;--ink:#102a35;--muted:#607984;--line:#d9e4e7;--mint:#15b8a6;--navy:#0a2633}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui,sans-serif}}main{{width:min(1160px,calc(100% - 36px));margin:auto;padding:52px 0 90px}}header{{padding:clamp(28px,5vw,58px);border-radius:30px;background:linear-gradient(135deg,#092634,#104658);color:white}}header small{{color:#72f0df;font-weight:800;letter-spacing:.1em}}h1{{max-width:760px;margin:12px 0;font-size:clamp(38px,6vw,66px);line-height:1.08}}header p{{max-width:720px;color:#c2d8df}}.counts{{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}}.counts span{{padding:7px 12px;border:1px solid #ffffff2e;border-radius:999px}}section{{margin-top:48px}}.section-head{{display:flex;align-items:end;justify-content:space-between;gap:20px;margin-bottom:18px}}h2{{margin:0;font-size:30px}}.section-head p{{margin:0;color:var(--muted)}}.actions,.runs{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}article,.empty{{padding:24px;border:1px solid var(--line);border-radius:22px;background:white;box-shadow:0 12px 36px #1232}}.action>span{{color:var(--mint);font-size:12px;font-weight:800;letter-spacing:.08em}}h3{{margin:10px 0 8px;font-size:22px;line-height:1.2}}article p{{color:var(--muted)}}details{{margin-top:18px}}summary{{cursor:pointer;font-weight:750}}pre{{padding:14px;white-space:pre-wrap;overflow-wrap:anywhere;border-radius:12px;background:#edf4f5;color:#24414c;font:13px/1.6 ui-monospace,monospace}}.run>div{{display:flex;justify-content:space-between;gap:12px}}.platform{{color:var(--mint);font-weight:800}}.status{{color:var(--muted);font-size:13px}}nav{{display:flex;gap:14px;margin-top:20px}}a{{color:#087d72;font-weight:800}}footer{{margin-top:52px;padding:22px;border-top:1px solid var(--line);color:var(--muted);font-size:13px}}@media(max-width:820px){{.actions,.runs{{grid-template-columns:1fr 1fr}}}}@media(max-width:560px){{main{{width:min(100% - 24px,1160px);padding-top:18px}}header{{border-radius:20px}}header h1 span{{display:block}}.actions,.runs{{grid-template-columns:1fr}}.section-head{{display:block}}.section-head p{{margin-top:6px}}}}
</style></head><body><main><header><small>{'本地 · 不上传研究内容' if zh else 'Local · research content is not uploaded'}</small><h1>{headline}</h1><p>{'汇总已完成报告、尚未结束的研究和到期复采建议。这里显示的是本地状态，不会把建议冒充为已经创建的定时任务。' if zh else 'See completed reports, unfinished studies, and due collection recommendations. Local recommendations are never presented as scheduled tasks.'}</p><div class="counts"><span>{counts['runs']} {'项研究' if zh else 'runs'}</span><span>{counts['completed_runs']} {'项完成' if zh else 'complete'}</span><span>{counts['due_monitors']} {'项到期复采' if zh else 'due monitors'}</span></div></header><section><div class="section-head"><h2>{'现在值得处理' if zh else 'Worth acting on now'}</h2><p>{len(actions)} {'项明确动作' if zh else 'clear actions'}</p></div><div class="actions">{action_cards}</div></section><section><div class="section-head"><h2>{'研究与报告' if zh else 'Research and reports'}</h2><p>{'从原报告继续，不复制平台原文。' if zh else 'Continue from the source report without copying platform content.'}</p></div><div class="runs">{run_cards}</div></section><section><div class="section-head"><h2>{'持续观察' if zh else 'Monitoring cycles'}</h2><p>{'建议时间与真实外部调度分开显示。' if zh else 'Recommended timing and real external scheduling are shown separately.'}</p></div><div class="runs">{monitor_cards}</div></section><footer>{'工作区只保存在当前设备。摘要卡可能包含研究主题和结论，分享前请人工检查。' if zh else 'This workspace stays on this device. Summary cards may contain a research topic and decision; review them before sharing.'}</footer></main></body></html>'''
