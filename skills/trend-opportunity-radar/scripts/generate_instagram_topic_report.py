from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from _common import as_text, now_iso, write_json


SCHEMA_VERSION = "instagram-topic-research-report-v0.1"


def validate(snapshot: dict[str, Any], analysis: dict[str, Any]) -> None:
    if snapshot.get("platform") != "instagram" or snapshot.get("research_scope") != "topic_research":
        raise SystemExit("Instagram topic report requires a topic_research snapshot.")
    ids = {as_text(item.get("signal_id")) for item in snapshot.get("signals", []) if isinstance(item, dict)}
    for field in ("direct_answer", "can_support", "cannot_support", "resolution"):
        if not as_text(analysis.get(field)):
            raise SystemExit(f"Instagram topic analysis requires {field}.")
    findings = analysis.get("findings")
    if not isinstance(findings, list) or not findings:
        raise SystemExit("Instagram topic analysis requires at least one evidence-backed finding.")
    for finding in findings:
        refs = finding.get("evidence_signal_ids") if isinstance(finding, dict) else None
        if not isinstance(refs, list) or not refs or any(as_text(item) not in ids for item in refs):
            raise SystemExit("Every Instagram topic finding must reference snapshot signal IDs.")


def metric(value: Any) -> str:
    return "—" if value is None else f"{int(value):,}"


def build(snapshot: dict[str, Any], analysis: dict[str, Any], language: str) -> dict[str, Any]:
    validate(snapshot, analysis)
    signals = [item for item in snapshot.get("signals", []) if isinstance(item, dict)]
    detailed = [item for item in signals if item.get("detail_captured") is True]
    relevant = [item for item in signals if item.get("semantic_relevance") in {"direct", "adjacent"}]
    counter = [item for item in signals if item.get("evidence_role") == "counter"]
    comments = sum(int((item.get("platform_facts") or {}).get("representative_comment_count") or 0) for item in signals)
    query = snapshot.get("query") if isinstance(snapshot.get("query"), dict) else {}
    collection = snapshot.get("collection") if isinstance(snapshot.get("collection"), dict) else {}
    repeatability = collection.get("repeatability") if isinstance(collection.get("repeatability"), dict) else {}
    query_runs = collection.get("query_runs") if isinstance(collection.get("query_runs"), list) else []
    if not query_runs:
        query_runs = [{
            "query_term": query.get("term", ""),
            "query_layer": query.get("layer", ""),
            "observed_result_count": int((collection.get("counts") or {}).get("observed_result_count") or snapshot.get("raw_sample_count") or len(signals)),
            "detail_open_count": int((collection.get("counts") or {}).get("detail_open_count") or len(detailed)),
            "repeatability": repeatability,
        }]
    reviewed = [item for item in signals if item.get("semantic_relevance") in {"direct", "adjacent", "weak"}]
    layer_audit = {}
    for layer in ("platform_baseline", "category", "subject_bridge"):
        layer_signals = [item for item in signals if layer in (item.get("query_layers") or [item.get("query_layer")])]
        layer_relevant = [item for item in layer_signals if item.get("semantic_relevance") in {"direct", "adjacent"}]
        layer_direct = [item for item in layer_signals if item.get("semantic_relevance") == "direct"]
        layer_audit[layer] = {
            "query_count": sum(1 for run in query_runs if run.get("query_layer") == layer),
            "observed_count": sum(int(run.get("observed_result_count") or 0) for run in query_runs if run.get("query_layer") == layer),
            "unique_count": len(layer_signals),
            "relevant_count": len(layer_relevant),
            "direct_count": len(layer_direct),
            "detail_count": sum(1 for item in layer_signals if item.get("detail_captured") is True),
        }
    reviewed_ratio = len(reviewed) / max(1, len(signals))
    query_repeat_counts = [int((run.get("repeatability") or {}).get("pass_count") or 0) for run in query_runs]
    query_overlaps = [(run.get("repeatability") or {}).get("overlap_jaccard") for run in query_runs]
    query_overlaps = [float(value) for value in query_overlaps if value is not None]
    repeat_complete = all(int((run.get("repeatability") or {}).get("pass_count") or 0) >= 2 for run in query_runs)
    subject_bridge_direct_detail = sum(1 for item in signals if "subject_bridge" in (item.get("query_layers") or [item.get("query_layer")]) and item.get("semantic_relevance") == "direct" and item.get("detail_captured") is True)
    standard_checks = {
        "query_count": len(query_runs) >= 3,
        "observed_volume": int((collection.get("counts") or {}).get("observed_result_count") or snapshot.get("raw_sample_count") or len(signals)) >= 60,
        "unique_volume": len(signals) >= 30,
        "detail_volume": len(detailed) >= 12,
        "relevant_volume": len(relevant) >= 18,
        "counterevidence": len(counter) >= 3,
        "review_coverage": reviewed_ratio >= 0.8,
        "repeatability": repeat_complete,
        "direct_subject_bridge": subject_bridge_direct_detail >= 2,
        "per_layer_quality": all(value["query_count"] >= 1 and value["observed_count"] >= 8 and value["unique_count"] >= 4 and value["relevant_count"] >= 4 and value["direct_count"] >= 2 and value["detail_count"] >= 2 for value in layer_audit.values()),
    }
    complete = all(standard_checks.values())
    labels = {
        "zh": {
            "title": "Instagram 主题研究", "basis": "本次研究基础", "queries": "已完成搜索主题", "observed": "发现的帖子链接",
            "unique": "去重帖子", "details": "已核对详情", "relevant": "确认相关", "counter": "反向证据", "comments": "可见评论正文",
            "answer": "直接结论", "supports": "现在可以帮助判断", "cannot": "暂时不能据此判断", "resolution": "下一步怎么补强",
            "findings": "值得验证的方向", "evidence": "已核对的帖子", "more": "其余发现链接", "boundary": "证据说明",
            "action": "建议动作", "why": "为什么值得关注", "status": "研究状态", "bounded": "本轮可用于设计验证", "complete": "采样要求已满足",
            "likes": "点赞", "comment_total": "评论", "date": "发布时间", "monitor": "建议后续复采",
            "feedback": "评论里出现的实际要求", "reviewed_comments": "已审查评论", "relevant_comments": "相关评论",
        },
        "en": {
            "title": "Instagram topic research", "basis": "Research basis", "queries": "Completed search themes", "observed": "Observed post links",
            "unique": "Unique posts", "details": "Opened details", "relevant": "Confirmed relevant", "counter": "Counter signals", "comments": "Visible comment bodies",
            "answer": "Direct answer", "supports": "What this can support now", "cannot": "What this cannot support yet", "resolution": "How to strengthen it",
            "findings": "Directions worth validating", "evidence": "Opened evidence", "more": "Other observed links", "boundary": "Evidence notes",
            "action": "Recommended action", "why": "Why it matters", "status": "Research status", "bounded": "Useful for designing a validation test", "complete": "Sampling contract met",
            "likes": "Likes", "comment_total": "Comments", "date": "Published", "monitor": "Suggested follow-up",
            "feedback": "What people asked for or objected to", "reviewed_comments": "Reviewed comments", "relevant_comments": "Relevant comments",
        },
    }[language]
    by_id = {item["signal_id"]: item for item in signals}
    findings = []
    for item in analysis["findings"]:
        refs = [as_text(value) for value in item["evidence_signal_ids"]]
        findings.append({
            "title": as_text(item.get("title")),
            "claim": as_text(item.get("claim")),
            "why_it_matters": as_text(item.get("why_it_matters")),
            "recommended_action": as_text(item.get("recommended_action")),
            "status": as_text(item.get("status")) or "candidate",
            "evidence_signal_ids": refs,
            "evidence_urls": [by_id[value]["canonical_url"] for value in refs],
        })
    limitations = [as_text(item) for item in analysis.get("limitations", []) if as_text(item)]
    if not limitations:
        limitations = [
            "Hashtag results are ranked and may be personalized; this snapshot is not an exhaustive or chronological Instagram corpus.",
            "The displayed hashtag post count describes visible content supply, not search demand or future performance.",
        ]
    subject = as_text(snapshot.get("subject"))
    comment_evidence = snapshot.get("comment_evidence") if isinstance(snapshot.get("comment_evidence"), dict) and snapshot.get("comment_evidence", {}).get("status") == "reviewed" else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "language": language,
        "labels": labels,
        "platform": "instagram",
        "research_scope": "topic_research",
        "subject": subject,
        "query": query,
        "queries": snapshot.get("queries") if isinstance(snapshot.get("queries"), list) else [{"term": query.get("term", ""), "layer": query.get("layer", "")}],
        "research_basis": {
            "query_count": len(query_runs),
            "observed_post_count": int(snapshot.get("raw_sample_count") or len(signals)),
            "unique_post_count": int(snapshot.get("unique_sample_count") or len(signals)),
            "detail_post_count": len(detailed),
            "relevant_post_count": len(relevant),
            "counter_signal_count": len(counter),
            "visible_comment_count": comments,
            "reviewed_comment_count": int(comment_evidence.get("reviewed_count") or 0),
            "relevant_comment_count": int(comment_evidence.get("relevant_count") or 0),
            "displayed_hashtag_volume_label": as_text(((signals[0].get("platform_facts") or {}) if signals else {}).get("displayed_hashtag_volume_label")),
            "repeat_pass_count": min(query_repeat_counts) if query_repeat_counts else int(repeatability.get("pass_count") or 0),
            "repeat_overlap_jaccard": round(sum(query_overlaps) / len(query_overlaps), 4) if query_overlaps else repeatability.get("overlap_jaccard"),
            "reviewed_ratio": round(reviewed_ratio, 4),
            "sampling_status": "complete" if complete else "bounded",
            "sampling_checks": standard_checks,
            "layer_audit": layer_audit,
        },
        "decision_support": {
            "can_support": as_text(analysis["can_support"]),
            "cannot_support": as_text(analysis["cannot_support"]),
            "resolution": as_text(analysis["resolution"]),
        },
        "direct_answer": as_text(analysis["direct_answer"]),
        "findings": findings,
        "comment_evidence": {
            "status": as_text(comment_evidence.get("status")) or "not_reviewed",
            "reviewed_count": int(comment_evidence.get("reviewed_count") or 0),
            "relevant_count": int(comment_evidence.get("relevant_count") or 0),
            "counter_count": int(comment_evidence.get("counter_count") or 0),
            "category_counts": comment_evidence.get("category_counts") if isinstance(comment_evidence.get("category_counts"), dict) else {},
            "insights": [as_text(item) for item in comment_evidence.get("insights", []) if as_text(item)][:5],
        },
        "evidence_items": [{
            "signal_id": item["signal_id"], "canonical_url": item["canonical_url"], "caption": item.get("summary", ""),
            "published_at": item.get("published_at", ""), "detail_captured": item.get("detail_captured") is True,
            "semantic_relevance": item.get("semantic_relevance", "unreviewed"), "evidence_role": item.get("evidence_role", "neutral"),
            "content_format": (item.get("platform_facts") or {}).get("content_format", ""),
            "likes": (item.get("metrics") or {}).get("likes"), "comments": (item.get("metrics") or {}).get("comments"),
        } for item in signals],
        "limitations": limitations[:4],
        "monitoring_recommendation": {
            "suggested_cadence": "weekly",
            "suggested_runs": 4,
            "reason": as_text(analysis.get("monitoring_reason")) or "Repeat the same frozen hashtags to measure result overlap and observe change without overwriting this snapshot.",
            "requires_confirmation": True,
            "automation_prompt": (
                f"使用 trend-opportunity-radar，按已冻结的三个 Instagram Hashtag 复采“{subject}”，追加新快照并与历史兼容快照比较。"
                if language == "zh" else
                f"Use trend-opportunity-radar to repeat the frozen Instagram hashtag study for {subject}, append a new snapshot, and compare it with prior compatible runs."
            ),
        },
    }


def markdown(report: dict[str, Any]) -> str:
    l, b, d = report["labels"], report["research_basis"], report["decision_support"]
    lines = [f"# {l['title']} · {report['subject']}", "", f"## {l['answer']}", "", report["direct_answer"], "", f"## {l['basis']}", "",
        f"- {l['queries']}: {b['query_count']}", f"- {l['observed']}: {b['observed_post_count']}", f"- {l['unique']}: {b['unique_post_count']}",
        f"- {l['details']}: {b['detail_post_count']}", f"- {l['relevant']}: {b['relevant_post_count']}", f"- {l['counter']}: {b['counter_signal_count']}",
        f"- {l['comments']}: {b['visible_comment_count']}", f"- {l['status']}: {l['complete'] if b['sampling_status']=='complete' else l['bounded']}", "",
        f"## {l['supports']}", "", d["can_support"], "", f"## {l['cannot']}", "", d["cannot_support"], "", f"## {l['resolution']}", "", d["resolution"], "",
        f"## {l['findings']}", ""]
    for finding in report["findings"]:
        lines += [f"### {finding['title']}", "", finding["claim"], "", f"- {l['why']}: {finding['why_it_matters']}", f"- {l['action']}: {finding['recommended_action']}", "- Evidence: " + ", ".join(f"[{url}]({url})" for url in finding["evidence_urls"]), ""]
    if report["comment_evidence"]["status"] == "reviewed":
        lines += [f"## {l['feedback']}", "", f"- {l['reviewed_comments']}: {report['comment_evidence']['reviewed_count']}", f"- {l['relevant_comments']}: {report['comment_evidence']['relevant_count']}", ""]
        lines += [f"- {item}" for item in report["comment_evidence"]["insights"]] + [""]
    lines += [f"## {l['evidence']}", ""]
    for item in [value for value in report["evidence_items"] if value["detail_captured"]]:
        lines.append(f"- [{(item['caption'] or item['signal_id'])[:110]}]({item['canonical_url']}) · {l['date']} {item['published_at'] or '—'} · {l['likes']} {metric(item['likes'])} · {l['comment_total']} {metric(item['comments'])}")
    lines += ["", f"## {l['boundary']}", "", *[f"- {item}" for item in report["limitations"]], "", f"## {l['monitor']}", "", report["monitoring_recommendation"]["reason"], ""]
    return "\n".join(lines)


def html_page(report: dict[str, Any]) -> str:
    l, b, d = report["labels"], report["research_basis"], report["decision_support"]
    esc = lambda value: html.escape(as_text(value))
    stats = [(l["queries"], b["query_count"]), (l["observed"], b["observed_post_count"]), (l["unique"], b["unique_post_count"]), (l["details"], b["detail_post_count"]), (l["relevant"], b["relevant_post_count"]), (l["counter"], b["counter_signal_count"]), (l["reviewed_comments"], b["reviewed_comment_count"])]
    stat_html = "".join(f"<div class='stat'><strong>{value}</strong><span>{esc(label)}</span></div>" for label, value in stats)
    finding_cards = "".join(f"<article class='card'><span class='pill'>{esc(l['bounded'] if item['status']=='candidate' else item['status'])}</span><h3>{esc(item['title'])}</h3><p>{esc(item['claim'])}</p><p><b>{esc(l['why'])}:</b> {esc(item['why_it_matters'])}</p><p><b>{esc(l['action'])}:</b> {esc(item['recommended_action'])}</p><div class='refs'>{''.join(f'<a href=\"{esc(url)}\">Instagram ↗</a>' for url in item['evidence_urls'])}</div></article>" for item in report["findings"])
    detailed = [item for item in report["evidence_items"] if item["detail_captured"]]
    format_labels = {"p": "图文内容", "reel": "短视频"} if report["language"] == "zh" else {"p": "Post", "reel": "Reel"}
    evidence = "".join(f"<article class='evidence'><span class='pill'>{esc(format_labels.get(item['content_format'], item['content_format'] or 'Post'))}</span><h3>{esc((item['caption'] or item['signal_id'])[:180])}</h3><p>{esc(l['date'])} {esc(item['published_at'] or '—')} · {esc(l['likes'])} {metric(item['likes'])} · {esc(l['comment_total'])} {metric(item['comments'])}</p><a href='{esc(item['canonical_url'])}'>Instagram ↗</a></article>" for item in detailed)
    extra = "".join(f"<a href='{esc(item['canonical_url'])}'>{esc(item['signal_id'])}</a>" for item in report["evidence_items"] if not item["detail_captured"])
    limits = "".join(f"<li>{esc(item)}</li>" for item in report["limitations"])
    feedback = "".join(f"<article class='decision'><p>{esc(item)}</p></article>" for item in report["comment_evidence"]["insights"])
    feedback_section = f"<h2>{esc(l['feedback'])}</h2><section class='grid'>{feedback}</section>" if report["comment_evidence"]["status"] == "reviewed" else ""
    payload = html.escape(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    status = l["complete"] if b["sampling_status"] == "complete" else l["bounded"]
    return f"""<!doctype html><html lang='{report['language']}'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(l['title'])} · {esc(report['subject'])}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#071421;color:#eef8f8;font:16px/1.65 system-ui,sans-serif}}main{{width:min(1120px,calc(100% - 32px));margin:36px auto 80px}}header{{padding:34px;border:1px solid #24485a;border-radius:28px;background:linear-gradient(135deg,#0b2032,#0d3e3d)}}h1{{font-size:clamp(34px,7vw,64px);line-height:1.06;margin:8px 0}}h2{{margin-top:44px}}.muted{{color:#9bc1c8}}.answer{{font-size:clamp(20px,3vw,28px);max-width:900px}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-top:20px}}.stat,.card,.evidence,.decision{{padding:18px;border:1px solid #24485a;border-radius:18px;background:#0c1d2a}}.stat strong{{display:block;font-size:30px;color:#62e6d6}}.stat span{{color:#b9d1d5;font-size:13px}}.decision-grid,.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}.decision-grid{{margin-top:32px}}.grid{{grid-template-columns:repeat(2,1fr)}}.pill{{display:inline-block;padding:4px 10px;border-radius:999px;background:#123d47;color:#7ff3e6;font-size:12px}}a{{color:#70dff2}}.refs,.extra{{display:flex;gap:10px;flex-wrap:wrap}}details{{margin-top:20px;padding:16px;border:1px solid #24485a;border-radius:16px}}ul{{padding-left:22px}}@media(max-width:820px){{.stats{{grid-template-columns:repeat(2,1fr)}}.decision-grid,.grid{{grid-template-columns:1fr}}main{{width:min(100% - 22px,1120px);margin-top:18px}}header{{padding:24px}}}}</style></head><body><main><header><p class='muted'>INSTAGRAM · {esc(report['query'].get('term',''))}</p><h1>{esc(report['subject'])}</h1><p class='answer'>{esc(report['direct_answer'])}</p><span class='pill'>{esc(status)}</span></header><h2>{esc(l['basis'])}</h2><section class='stats'>{stat_html}</section><section class='decision-grid'><article class='decision'><h3>{esc(l['supports'])}</h3><p>{esc(d['can_support'])}</p></article><article class='decision'><h3>{esc(l['cannot'])}</h3><p>{esc(d['cannot_support'])}</p></article><article class='decision'><h3>{esc(l['resolution'])}</h3><p>{esc(d['resolution'])}</p></article></section><h2>{esc(l['findings'])}</h2><section class='grid'>{finding_cards}</section>{feedback_section}<h2>{esc(l['evidence'])}</h2><section class='grid'>{evidence}</section><details><summary>{esc(l['more'])} ({len(report['evidence_items'])-len(detailed)})</summary><div class='extra'>{extra}</div></details><h2>{esc(l['boundary'])}</h2><ul>{limits}</ul><h2>{esc(l['monitor'])}</h2><article class='decision'><p>{esc(report['monitoring_recommendation']['reason'])}</p><p class='muted'>{esc(report['monitoring_recommendation']['automation_prompt'])}</p></article><script id='report-data' type='application/json'>{payload}</script></main></body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a bounded Instagram hashtag topic-research report.")
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
    html_text = html_page(report)
    Path(args.html_output).write_text(html_text, encoding="utf-8")
    receipt = {"schema_version": "instagram-topic-report-receipt-v0.1", "generated_at": now_iso(), "html_sha256": hashlib.sha256(html_text.encode("utf-8")).hexdigest()}
    write_json(str(Path(args.html_output).with_name("report-generation-receipt.json")), receipt)


if __name__ == "__main__":
    main()
