from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Expected a JSON object: {path}")
    return data


def write_text(path: str, text: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def parse_reports(values: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    reports: dict[str, dict[str, Any]] = {}
    paths: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit("Each --report must use platform=PATH syntax.")
        platform, path = value.split("=", 1)
        platform = platform.strip().lower()
        if not platform or platform in reports:
            raise SystemExit("Report platform labels must be non-empty and unique.")
        report = load_json(path)
        if report.get("platform") != platform:
            raise SystemExit(f"Platform label {platform!r} does not match report platform {report.get('platform')!r}.")
        if (report.get("collection_summary") or {}).get("sampling_status") != "complete":
            raise SystemExit(f"Report {platform!r} is not a completed sampling snapshot.")
        reports[platform] = report
        paths[platform] = str(Path(path).resolve())
    if len(reports) < 2:
        raise SystemExit("Cross-platform comparison requires at least two completed reports.")
    return reports, paths


def compatibility_key(report: dict[str, Any]) -> tuple[str, str, str, str, str]:
    context = report.get("research_context") or {}
    subject = report.get("subject") or {}
    return (
        str(subject.get("name") or ""),
        str(context.get("research_intent") or ""),
        str(context.get("profile_version") or ""),
        str(context.get("analysis_unit") or ""),
        str(report.get("language") or subject.get("communication", {}).get("language") or ""),
    )


def resolve_finding(report: dict[str, Any], finding_id: str) -> dict[str, Any]:
    finding = next((item for item in report.get("findings", []) if item.get("id") == finding_id), None)
    if not finding:
        raise SystemExit(f"Unknown finding id {finding_id!r} for platform {report.get('platform')!r}.")
    score = finding.get("score_summary") or {}
    return {
        "finding_id": finding_id,
        "title": finding.get("title"),
        "decision_summary": finding.get("decision_summary"),
        "observed_heat": score.get("observed_heat"),
        "evidence_confidence": score.get("evidence_confidence"),
        "evidence_boundary": finding.get("evidence_boundary"),
        "support_refs": finding.get("support_refs", []),
        "counter_refs": finding.get("counter_refs", []),
    }


def build_output(reports: dict[str, dict[str, Any]], paths: dict[str, str], synthesis: dict[str, Any]) -> dict[str, Any]:
    keys = {compatibility_key(report) for report in reports.values()}
    if len(keys) != 1 or not all(next(iter(keys))):
        raise SystemExit("Reports are incompatible: subject, intent, Profile, analysis unit, and language must match.")
    subject_name, intent, profile_version, analysis_unit, language = next(iter(keys))
    if synthesis.get("subject") != subject_name:
        raise SystemExit("Synthesis subject must exactly match the compatible report subject.")

    platform_summaries = []
    report_hrefs = synthesis.get("source_report_hrefs") or {}
    for platform, report in reports.items():
        platform_summaries.append({
            "platform": platform,
            "source_report": paths[platform],
            "source_report_href": report_hrefs.get(platform),
            "collection_summary": report.get("collection_summary") or {},
            "decision_answer": report.get("decision_answer"),
        })

    shared = []
    for item in synthesis.get("shared_findings", []):
        evidence = {}
        refs = item.get("platform_findings") or {}
        if set(refs) != set(reports):
            raise SystemExit("Every shared finding must reference one finding from every platform.")
        for platform, finding_id in refs.items():
            evidence[platform] = resolve_finding(reports[platform], finding_id)
        shared.append({
            "title": item.get("title"),
            "summary": item.get("summary"),
            "decision_implication": item.get("decision_implication"),
            "platform_evidence": evidence,
        })

    differences = []
    for item in synthesis.get("platform_differences", []):
        platform = item.get("platform")
        if platform not in reports:
            raise SystemExit(f"Unknown platform in difference: {platform!r}")
        finding_id = item.get("finding_id")
        differences.append({
            "platform": platform,
            "title": item.get("title"),
            "summary": item.get("summary"),
            "decision_implication": item.get("decision_implication"),
            "platform_evidence": resolve_finding(reports[platform], finding_id) if finding_id else None,
        })

    if not synthesis.get("decision_answer") or not shared or not synthesis.get("mvp_sequence"):
        raise SystemExit("Synthesis requires a decision answer, shared findings, and an MVP sequence.")

    return {
        "schema_version": "platform-profile-comparison-v0.1",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "subject": subject_name,
        "research_intent": intent,
        "profile_version": profile_version,
        "analysis_unit": analysis_unit,
        "language": language,
        "platforms": list(reports),
        "score_boundary": "Platform scores are independent. They are not added, averaged, normalized, or used to rank platforms.",
        "decision_answer": synthesis.get("decision_answer"),
        "platform_summaries": platform_summaries,
        "shared_findings": shared,
        "platform_differences": differences,
        "mvp_sequence": synthesis.get("mvp_sequence"),
        "evidence_boundary": synthesis.get("evidence_boundary"),
        "follow_up": synthesis.get("follow_up"),
    }


def render_markdown(data: dict[str, Any]) -> str:
    names = {"xiaohongshu": "小红书", "x": "X"}
    lines = [
        f"# 跨平台需求对照：{data['subject']}", "",
        "## 直接回答", "", str(data["decision_answer"]), "",
        "> 各平台分数仅用于理解该平台内部信号，不相加、不平均，也不用于平台排名。", "",
        "## 研究基础", "",
    ]
    for item in data["platform_summaries"]:
        c = item["collection_summary"]
        lines.append(
            f"- **{names.get(item['platform'], item['platform'])}**：{c.get('query_count', 0)} 个搜索主题，"
            f"{c.get('observed_result_count', 0)} 条可见结果，{c.get('unique_signal_count', 0)} 条去重信号，"
            f"{c.get('relevant_signal_count', 0)} 条相关信号，{c.get('detail_open_count', 0)} 条详情，"
            f"{c.get('reviewed_comment_count', 0)} 条评论审查。"
        )
        if item.get("source_report_href"):
            lines.append(f"  - [打开{names.get(item['platform'], item['platform'])}单平台报告]({item['source_report_href']})")
    lines += ["", "## 两个平台共同支持的判断", ""]
    for item in data["shared_findings"]:
        lines += [f"### {item['title']}", "", str(item["summary"]), "", f"**对产品的含义：** {item['decision_implication']}", ""]
        for platform, evidence in item["platform_evidence"].items():
            lines.append(
                f"- {names.get(platform, platform)}：讨论强度 {evidence['observed_heat']}/100；"
                f"判断可靠度 {evidence['evidence_confidence']}/100；{evidence['title']}"
            )
        lines.append("")
    lines += ["## 平台差异", ""]
    for item in data["platform_differences"]:
        lines += [f"### {names.get(item['platform'], item['platform'])} · {item['title']}", "", str(item["summary"]), "", f"**验证含义：** {item['decision_implication']}", ""]
    lines += ["## 建议的 MVP 验证顺序", ""]
    for index, step in enumerate(data["mvp_sequence"], 1):
        lines += [f"### {index}. {step['title']}", "", str(step["action"]), "", f"- 成功指标：{step['validation_metric']}", f"- 停止条件：{step['stop_condition']}", ""]
    lines += ["## 证据边界", "", str(data.get("evidence_boundary") or ""), ""]
    return "\n".join(lines)


def render_html(data: dict[str, Any]) -> str:
    names = {"xiaohongshu": "小红书", "x": "X"}
    basis = "".join(
        f"<article class='basis-card'><span class='platform'>{esc(names.get(item['platform'], item['platform']))}</span>"
        f"<strong>{item['collection_summary'].get('relevant_signal_count', 0)} 条相关信号</strong>"
        f"<p>{item['collection_summary'].get('query_count', 0)} 个搜索主题 · {item['collection_summary'].get('observed_result_count', 0)} 条可见结果 · "
        f"{item['collection_summary'].get('detail_open_count', 0)} 条详情 · {item['collection_summary'].get('reviewed_comment_count', 0)} 条评论审查</p>"
        + (f"<a href='{esc(item['source_report_href'])}'>打开单平台证据报告 →</a>" if item.get("source_report_href") else "")
        + "</article>"
        for item in data["platform_summaries"]
    )
    shared = "".join(
        "<article class='finding'><div class='eyebrow'>共同判断</div>"
        f"<h2>{esc(item['title'])}</h2><p class='summary'>{esc(item['summary'])}</p>"
        "<div class='score-grid'>" + "".join(
            f"<div class='score-card'><span>{esc(names.get(platform, platform))}</span>"
            f"<strong>讨论强度 {evidence['observed_heat']}/100</strong>"
            f"<strong>判断可靠度 {evidence['evidence_confidence']}/100</strong>"
            f"<small>{esc(evidence['title'])}</small></div>"
            for platform, evidence in item["platform_evidence"].items()
        ) + "</div>"
        f"<div class='implication'><b>对产品的含义</b><p>{esc(item['decision_implication'])}</p></div></article>"
        for item in data["shared_findings"]
    )
    differences = "".join(
        f"<article class='difference'><span>{esc(names.get(item['platform'], item['platform']))}</span>"
        f"<h3>{esc(item['title'])}</h3><p>{esc(item['summary'])}</p>"
        f"<div><b>验证含义</b> {esc(item['decision_implication'])}</div></article>"
        for item in data["platform_differences"]
    )
    steps = "".join(
        f"<article class='step'><span>{index:02d}</span><div><h3>{esc(item['title'])}</h3><p>{esc(item['action'])}</p>"
        f"<details><summary>查看成功指标和停止条件</summary><p><b>成功指标：</b>{esc(item['validation_metric'])}</p>"
        f"<p><b>停止条件：</b>{esc(item['stop_condition'])}</p></details></div></article>"
        for index, item in enumerate(data["mvp_sequence"], 1)
    )
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>跨平台需求对照 · {esc(data['subject'])}</title><style>
:root{{--ink:#122033;--muted:#627083;--line:#dfe6ef;--paper:#fff;--bg:#f3f6fa;--blue:#3459d9;--teal:#0b998b;--purple:#6b55c7}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,"Noto Sans SC","Microsoft YaHei",sans-serif;line-height:1.65}}main{{width:min(1120px,calc(100% - 32px));margin:28px auto 70px}}.hero{{padding:38px 42px;border-radius:30px;color:#fff;background:linear-gradient(125deg,#152658,#5044a2 58%,#087c78)}}.hero .eyebrow,.eyebrow{{font-size:13px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;opacity:.76}}h1{{font-size:clamp(30px,4vw,48px);line-height:1.18;margin:12px 0}}.answer{{margin:20px 0;padding:26px 30px;border-radius:22px;background:#fff;box-shadow:0 12px 30px rgba(25,43,78,.08)}}.answer h2{{font-size:clamp(22px,3vw,31px);line-height:1.35;margin:8px 0}}.boundary{{color:var(--muted);font-size:14px}}section{{margin-top:28px}}section>h2{{font-size:24px;margin:0 0 14px}}.basis-grid,.difference-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}}.basis-card,.difference,.finding{{background:#fff;border:1px solid var(--line);border-radius:22px;padding:24px}}.basis-card .platform,.difference>span{{display:inline-block;color:var(--blue);font-size:13px;font-weight:800;margin-bottom:10px}}.basis-card strong{{display:block;font-size:24px}}.basis-card p{{margin:8px 0 0;color:var(--muted)}}.finding{{margin-bottom:16px}}.finding h2{{font-size:25px;line-height:1.35;margin:8px 0}}.summary{{font-size:17px}}.score-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:18px 0}}.score-card{{padding:16px;border-radius:16px;background:#f6f8fc}}.score-card span,.score-card strong,.score-card small{{display:block}}.score-card span{{color:var(--purple);font-weight:800}}.score-card strong{{margin-top:3px}}.score-card small{{margin-top:8px;color:var(--muted)}}.implication{{border-left:4px solid var(--teal);padding:5px 0 5px 16px}}.implication p{{margin:3px 0}}.difference h3,.step h3{{margin:5px 0;font-size:20px}}.difference div{{margin-top:12px;padding-top:12px;border-top:1px solid var(--line)}}.step{{display:grid;grid-template-columns:54px 1fr;gap:14px;background:#fff;border:1px solid var(--line);border-radius:20px;padding:20px;margin-bottom:12px}}.step>span{{display:grid;place-items:center;width:46px;height:46px;border-radius:14px;background:#e9f5f2;color:var(--teal);font-weight:900}}.step p{{margin:6px 0}}details{{margin-top:10px}}summary{{cursor:pointer;font-weight:700;color:var(--blue)}}footer{{margin-top:30px;padding:20px 24px;border-radius:18px;background:#e9eef7;color:var(--muted)}}@media(max-width:760px){{main{{width:min(100% - 20px,1120px);margin-top:10px}}.hero{{padding:28px 22px;border-radius:22px}}.basis-grid,.difference-grid,.score-grid{{grid-template-columns:1fr}}.answer,.finding,.basis-card,.difference{{padding:20px}}}}
</style></head><body><main><header class='hero'><div class='eyebrow'>X × 小红书 · 产品需求验证</div><h1>{esc(data['subject'])}</h1><p>两个独立平台快照，一份产品决策对照。</p></header>
<section class='answer'><div class='eyebrow'>直接回答</div><h2>{esc(data['decision_answer'])}</h2><p class='boundary'>各平台的讨论强度和判断可靠度独立展示，不相加、不平均，也不用于平台排名。</p></section>
<section><h2>两份研究的基础</h2><div class='basis-grid'>{basis}</div></section>
<section><h2>两个平台共同支持的判断</h2>{shared}</section>
<section><h2>平台差异决定怎样验证</h2><div class='difference-grid'>{differences}</div></section>
<section><h2>建议的 MVP 验证顺序</h2>{steps}</section>
<footer><b>证据边界</b><br>{esc(data.get('evidence_boundary'))}</footer>
<script type='application/json' id='comparison-data'>{payload}</script></main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a report-level comparison from compatible platform Profile reports.")
    parser.add_argument("--report", action="append", required=True, help="platform=PATH; repeat for each platform")
    parser.add_argument("--synthesis", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--html-output", required=True)
    args = parser.parse_args()

    reports, paths = parse_reports(args.report)
    synthesis = load_json(args.synthesis)
    output = build_output(reports, paths, synthesis)
    write_text(args.json_output, json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    write_text(args.markdown_output, render_markdown(output))
    write_text(args.html_output, render_html(output))


if __name__ == "__main__":
    main()
