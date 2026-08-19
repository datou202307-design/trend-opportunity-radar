from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from _common import as_text, now_iso, write_json


SCHEMA_VERSION = "instagram-account-research-report-v0.1"


def validate(snapshot: dict[str, Any], analysis: dict[str, Any]) -> None:
    if snapshot.get("platform") != "instagram" or snapshot.get("research_scope") != "account_research":
        raise SystemExit("Instagram account report requires an account_research snapshot.")
    ids = {as_text(item.get("signal_id")) for item in snapshot.get("signals", []) if isinstance(item, dict)}
    if not as_text(analysis.get("direct_answer")):
        raise SystemExit("Account analysis requires a direct_answer.")
    findings = analysis.get("findings")
    if not isinstance(findings, list) or not findings:
        raise SystemExit("Account analysis requires at least one evidence-backed finding.")
    for finding in findings:
        refs = finding.get("evidence_signal_ids") if isinstance(finding, dict) else None
        if not isinstance(refs, list) or not refs or any(as_text(item) not in ids for item in refs):
            raise SystemExit("Every account finding must reference one or more snapshot signal IDs.")


def metric(value: Any) -> str:
    return "—" if value is None else f"{int(value):,}"


def build(snapshot: dict[str, Any], analysis: dict[str, Any], language: str) -> dict[str, Any]:
    validate(snapshot, analysis)
    signals = [item for item in snapshot.get("signals", []) if isinstance(item, dict)]
    detailed = [item for item in signals if item.get("detail_captured") is True]
    comments = sum(int((item.get("platform_facts") or {}).get("representative_comment_count") or 0) for item in signals)
    labels = {
        "zh": {"title": "Instagram 账号研究", "basis": "研究基础", "observed": "近期内容链接", "details": "已打开详情", "comments": "可见评论正文", "answer": "直接结论", "findings": "值得采取行动的发现", "evidence": "逐条证据", "boundary": "结论边界", "action": "建议动作", "why": "为什么重要", "likes": "点赞", "comment_total": "评论", "date": "发布时间"},
        "en": {"title": "Instagram account research", "basis": "Research basis", "observed": "Recent content links", "details": "Opened details", "comments": "Visible comment bodies", "answer": "Direct answer", "findings": "Actionable findings", "evidence": "Evidence items", "boundary": "Evidence boundary", "action": "Recommended action", "why": "Why it matters", "likes": "Likes", "comment_total": "Comments", "date": "Published"},
    }[language]
    findings = []
    by_id = {item["signal_id"]: item for item in signals}
    for item in analysis["findings"]:
        findings.append({
            "title": as_text(item.get("title")),
            "claim": as_text(item.get("claim")),
            "why_it_matters": as_text(item.get("why_it_matters")),
            "recommended_action": as_text(item.get("recommended_action")),
            "evidence_signal_ids": [as_text(value) for value in item["evidence_signal_ids"]],
            "evidence_urls": [by_id[as_text(value)]["canonical_url"] for value in item["evidence_signal_ids"]],
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "language": language,
        "labels": labels,
        "platform": "instagram",
        "research_scope": "account_research",
        "account": snapshot.get("account", {}),
        "research_basis": {"observed_post_count": len(signals), "detail_post_count": len(detailed), "visible_comment_count": comments},
        "direct_answer": as_text(analysis["direct_answer"]),
        "findings": findings,
        "evidence_items": [{
            "signal_id": item["signal_id"], "canonical_url": item["canonical_url"], "caption": item.get("summary", ""),
            "published_at": item.get("published_at", ""), "detail_captured": item.get("detail_captured") is True,
            "content_format": (item.get("platform_facts") or {}).get("content_format", ""),
            "likes": (item.get("metrics") or {}).get("likes"), "comments": (item.get("metrics") or {}).get("comments"),
        } for item in signals],
        "limitations": [as_text(item) for item in analysis.get("limitations", []) if as_text(item)] or [
            "This bounded account snapshot describes recent visible content and response, not platform-wide demand or trend growth."
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    l = report["labels"]
    b = report["research_basis"]
    lines = [f"# {l['title']} · @{report['account'].get('username', '')}", "", f"## {l['basis']}", "", f"- {l['observed']}: {b['observed_post_count']}", f"- {l['details']}: {b['detail_post_count']}", f"- {l['comments']}: {b['visible_comment_count']}", "", f"## {l['answer']}", "", report["direct_answer"], "", f"## {l['findings']}", ""]
    for finding in report["findings"]:
        lines += [f"### {finding['title']}", "", finding["claim"], "", f"- {l['why']}: {finding['why_it_matters']}", f"- {l['action']}: {finding['recommended_action']}", "- Evidence: " + ", ".join(f"[{value}]({value})" for value in finding["evidence_urls"]), ""]
    lines += [f"## {l['evidence']}", ""]
    for item in report["evidence_items"]:
        label = item["caption"] or item["signal_id"]
        lines.append(f"- [{label[:100]}]({item['canonical_url']}) · {l['date']} {item['published_at'] or '—'} · {l['likes']} {metric(item['likes'])} · {l['comment_total']} {metric(item['comments'])}")
    lines += ["", f"## {l['boundary']}", "", *[f"- {item}" for item in report["limitations"]], ""]
    return "\n".join(lines)


def html_page(report: dict[str, Any]) -> str:
    l = report["labels"]
    b = report["research_basis"]
    esc = lambda value: html.escape(as_text(value))
    finding_cards = "".join(f"<article class='card'><h3>{esc(item['title'])}</h3><p>{esc(item['claim'])}</p><p><b>{esc(l['why'])}:</b> {esc(item['why_it_matters'])}</p><p><b>{esc(l['action'])}:</b> {esc(item['recommended_action'])}</p><div class='refs'>{''.join(f'<a href=\"{esc(url)}\">Evidence ↗</a>' for url in item['evidence_urls'])}</div></article>" for item in report["findings"])
    evidence = "".join(f"<article class='evidence'><span>{esc(item['content_format'] or 'post')}</span><h3>{esc((item['caption'] or item['signal_id'])[:160])}</h3><p>{esc(l['date'])} {esc(item['published_at'] or '—')} · {esc(l['likes'])} {metric(item['likes'])} · {esc(l['comment_total'])} {metric(item['comments'])}</p><a href='{esc(item['canonical_url'])}'>Instagram ↗</a></article>" for item in report["evidence_items"])
    limits = "".join(f"<li>{esc(item)}</li>" for item in report["limitations"])
    return f"""<!doctype html><html lang='{report['language']}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(l['title'])}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#071421;color:#eef8f8;font:16px/1.65 system-ui,sans-serif}}main{{width:min(1120px,calc(100% - 32px));margin:40px auto 80px}}header{{padding:34px;border:1px solid #24485a;border-radius:28px;background:linear-gradient(135deg,#0b2032,#0d3e3d)}}h1{{font-size:clamp(34px,7vw,66px);line-height:1.05;margin:8px 0}}h2{{margin-top:48px}}.muted{{color:#9bc1c8}}.stats,.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.stat,.card,.evidence{{padding:20px;border:1px solid #24485a;border-radius:20px;background:#0c1d2a}}.stat strong{{display:block;font-size:32px;color:#62e6d6}}.answer{{font-size:clamp(20px,3vw,29px);padding:24px;border-left:4px solid #62e6d6;background:#0c1d2a;border-radius:0 18px 18px 0}}.grid{{grid-template-columns:repeat(2,1fr)}}a{{color:#70dff2}}.refs{{display:flex;gap:10px;flex-wrap:wrap}}ul{{padding-left:22px}}@media(max-width:720px){{main{{width:min(100% - 22px,1120px);margin-top:18px}}header{{padding:24px}}.stats,.grid{{grid-template-columns:1fr}}}}</style></head><body><main><header><p class='muted'>ACCOUNT RESEARCH · INSTAGRAM</p><h1>@{esc(report['account'].get('username',''))}</h1><p>{esc(report['account'].get('display_name',''))}</p></header><h2>{esc(l['basis'])}</h2><section class='stats'><div class='stat'><strong>{b['observed_post_count']}</strong>{esc(l['observed'])}</div><div class='stat'><strong>{b['detail_post_count']}</strong>{esc(l['details'])}</div><div class='stat'><strong>{b['visible_comment_count']}</strong>{esc(l['comments'])}</div></section><h2>{esc(l['answer'])}</h2><p class='answer'>{esc(report['direct_answer'])}</p><h2>{esc(l['findings'])}</h2><section class='grid'>{finding_cards}</section><h2>{esc(l['evidence'])}</h2><section class='grid'>{evidence}</section><h2>{esc(l['boundary'])}</h2><ul>{limits}</ul></main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a bounded Instagram account-research report.")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--language", choices=["zh", "en"], default="zh")
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--html-output", required=True)
    args = parser.parse_args()
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    report = build(snapshot, analysis, args.language)
    write_json(args.json_output, report)
    Path(args.markdown_output).write_text(markdown(report), encoding="utf-8")
    Path(args.html_output).write_text(html_page(report), encoding="utf-8")


if __name__ == "__main__":
    main()
