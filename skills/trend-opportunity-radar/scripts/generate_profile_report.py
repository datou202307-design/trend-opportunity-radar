from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

from _common import as_text, load_data, now_iso, require_text_integrity, write_json
from profile_decisions import require_valid_findings
from research_context import load_context
from validate_report_artifacts import validate_report_contents


PROFILE_UI = {
    "business_opportunity": {
        "zh-CN": {"name": "商业机会研究", "question": "这个方向值得做吗？最应该先验证什么？", "findings": "值得验证的机会", "action": "下一步验证", "why": "用户问题与可行切口", "follow_title": "7 天后再看一次，确认机会是否持续"},
        "en": {"name": "Business opportunity research", "question": "Is this direction worth pursuing, and what should be tested first?", "findings": "Opportunities to validate", "action": "Next validation", "why": "User problem and viable wedge", "follow_title": "Check again in 7 days to see whether the opportunity persists"},
    },
    "brand_sentiment": {
        "zh-CN": {"name": "品牌议题监测", "question": "现在最需要关注什么？应该回应、修复，还是继续观察？", "findings": "当前需要关注的议题", "action": "回应与观察建议", "why": "发生了什么、先怎么处理", "follow_title": "24 小时后复查，确认问题是否继续出现"},
        "en": {"name": "Brand issue monitoring", "question": "What needs attention now: respond, fix, or keep watching?", "findings": "Issues needing attention", "action": "Response and monitoring", "why": "What happened and what to do first", "follow_title": "Check again in 24 hours to see whether the issue continues"},
    },
    "competitor_users": {
        "zh-CN": {"name": "竞品用户研究", "question": "用户为什么继续使用、抱怨或转向别的产品？我们能从哪里切入？", "findings": "用户留下或切换的原因", "action": "产品切入验证", "why": "用户为什么留下或切换", "follow_title": "7 天后再看一次，确认切换原因是否持续"},
        "en": {"name": "Competitor user research", "question": "Why do users stay, complain, or switch, and where could we enter?", "findings": "Why users stay or switch", "action": "Product wedge validation", "why": "Why users stay or switch", "follow_title": "Check again in 7 days to see whether switching reasons persist"},
    },
    "content_opportunity": {
        "zh-CN": {"name": "内容机会研究", "question": "受众现在最想解决什么问题？哪些内容值得先做？", "findings": "值得回应的受众问题", "action": "内容测试建议", "why": "受众问题与内容切口", "follow_title": "7 天后再看一次，确认受众问题是否持续"},
        "en": {"name": "Content opportunity research", "question": "What does the audience most want to solve now, and which content should come first?", "findings": "Audience questions to address", "action": "Content tests", "why": "Audience problem and content angle", "follow_title": "Check again in 7 days to see whether the audience need persists"},
    },
    "product_demand": {
        "zh-CN": {"name": "产品需求验证", "question": "这个需求值得做吗？首版应该解决什么问题？", "findings": "需要验证的真实任务", "action": "MVP 验证建议", "why": "用户为什么需要、为什么会放弃", "follow_title": "7 天后再看一次，确认需求是否持续"},
        "en": {"name": "Product demand validation", "question": "Is this demand worth building for, and what should the first version solve?", "findings": "Real tasks to validate", "action": "MVP demand tests", "why": "Why users need it and why they might leave", "follow_title": "Check again in 7 days to see whether demand persists"},
    },
}

ACTION_FIELD_LABELS = {
    "zh-CN": {
        "success_metric": "怎样判断有效", "validation_metric": "怎样判断需求成立",
        "audience_response_metric": "怎样判断内容有效", "response_level": "建议怎么处理",
        "target_segment": "优先验证的人群", "stop_condition": "什么时候停止",
        "human_boundary": "必须由谁确认",
    },
    "en": {
        "success_metric": "How success is measured", "validation_metric": "How demand is validated",
        "audience_response_metric": "How audience response is measured", "response_level": "Recommended response",
        "target_segment": "Segment to test first", "stop_condition": "When to stop",
        "human_boundary": "What requires human confirmation",
    },
}

SECTION_LABELS = {
    "decision_answer": {"zh-CN": "直接回答", "en": "Decision answer"},
    "opportunity_hypotheses": {"zh-CN": "机会假设", "en": "Opportunity hypothesis"},
    "audience_and_task": {"zh-CN": "用户与任务", "en": "Audience and task"},
    "validation_actions": {"zh-CN": "验证方法", "en": "Validation action"},
    "evidence_boundary": {"zh-CN": "证据边界", "en": "Evidence boundary"},
    "issue_priority": {"zh-CN": "议题优先级", "en": "Issue priority"},
    "affected_audience": {"zh-CN": "受影响人群", "en": "Affected audience"},
    "response_recommendation": {"zh-CN": "回应建议", "en": "Response recommendation"},
    "observation_status": {"zh-CN": "观察状态", "en": "Observation status"},
    "retained_strengths": {"zh-CN": "用户留下的原因", "en": "Why users stay"},
    "user_complaints": {"zh-CN": "主要抱怨", "en": "User complaints"},
    "switching_triggers": {"zh-CN": "切换触发点", "en": "Switching triggers"},
    "product_wedge": {"zh-CN": "可验证的切入点", "en": "Product wedge"},
    "audience_questions": {"zh-CN": "受众问题", "en": "Audience questions"},
    "content_angles": {"zh-CN": "内容角度", "en": "Content angles"},
    "audience_handoff": {"zh-CN": "看完后的承接", "en": "Audience handoff"},
    "content_test": {"zh-CN": "内容测试", "en": "Content test"},
    "user_tasks": {"zh-CN": "真实任务", "en": "User tasks"},
    "workarounds_and_failures": {"zh-CN": "替代办法与失败", "en": "Workarounds and failures"},
    "mvp_scope": {"zh-CN": "MVP 范围", "en": "MVP scope"},
    "validation_metrics": {"zh-CN": "验证指标", "en": "Validation metrics"},
    "stop_conditions": {"zh-CN": "停止条件", "en": "Stop conditions"},
}

STATUS_LABELS = {
    "zh-CN": {
        "candidate": "待验证",
        "review_ready": "值得执行小测试",
        "confirmed": "已人工确认",
        "rejected": "暂不继续",
    },
    "en": {
        "candidate": "Needs validation",
        "review_ready": "Ready for a small test",
        "confirmed": "Human confirmed",
        "rejected": "Do not continue",
    },
}


def visible_status(status: Any, language: str) -> str:
    locale = "zh-CN" if language == "zh-CN" else "en"
    return STATUS_LABELS[locale].get(str(status), "待复核" if locale == "zh-CN" else "Needs review")


def score_level(value: Any, language: str) -> str:
    """Return a plain-language grade without changing the audited score."""
    score = float(value)
    labels = (
        (80, "很强" if language == "zh-CN" else "Very strong"),
        (60, "较强" if language == "zh-CN" else "Strong"),
        (40, "中等" if language == "zh-CN" else "Moderate"),
        (20, "较弱" if language == "zh-CN" else "Weak"),
        (0, "很弱" if language == "zh-CN" else "Very weak"),
    )
    return next(label for threshold, label in labels if score >= threshold)


def finding_score_summary(topic: dict[str, Any] | None) -> dict[str, Any] | None:
    """Expose only existing audited scores; never synthesize a finding score."""
    if not topic or topic.get("observed_heat") is None or topic.get("evidence_confidence") is None:
        return None
    return {
        "observed_heat": topic["observed_heat"],
        "evidence_confidence": topic["evidence_confidence"],
    }


def _normalized_visible_text(value: Any) -> str:
    return "".join(character.casefold() for character in str(value) if character.isalnum())


def materially_duplicates(first: Any, second: Any) -> bool:
    """Reject a top answer that merely repeats the first result card."""
    left, right = _normalized_visible_text(first), _normalized_visible_text(second)
    if not left or not right:
        return False
    shorter, longer = sorted((left, right), key=len)
    return shorter == longer or (len(shorter) >= 48 and shorter in longer and len(shorter) / len(longer) >= 0.85)


def subject_name(report: dict[str, Any]) -> str:
    subject = report.get("subject") or {}
    return str(subject.get("name") or subject.get("title") or subject.get("summary") or "Research topic")


def collection_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Create a compact, user-facing sampling basis from canonical evidence counts."""
    collection = snapshot.get("collection") or {}
    counts = collection.get("counts") or {}
    signals = snapshot.get("signals") or []

    def count(name: str, fallback: Any = None) -> int | None:
        value = counts.get(name, fallback)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    relevant = None
    counter = count("counter_signal_count")
    unique = count("unique_sample_count", snapshot.get("unique_sample_count"))
    if signals:
        unique = len(signals)
        relevant = sum(
            1 for signal in signals
            if signal.get("semantic_relevance") in {"direct", "adjacent"}
        )
        counter = sum(1 for signal in signals if signal.get("evidence_role") == "counter")

    query_count = count("query_count")
    if query_count is None and collection.get("query_runs"):
        query_count = len(collection["query_runs"])

    complete = (
        collection.get("contract_status") == "met"
        and collection.get("stop_reason") in {None, "", "sampling_contract_met"}
    )
    comment_evidence = snapshot.get("comment_evidence") or {}
    result = {
        "query_count": query_count,
        "observed_result_count": count("observed_result_count", snapshot.get("raw_sample_count")),
        "unique_signal_count": unique,
        "relevant_signal_count": relevant,
        "detail_open_count": count("detail_open_count"),
        "counter_signal_count": counter,
        "sampling_status": "complete" if complete else "bounded",
    }
    if comment_evidence.get("status") == "reviewed":
        result["reviewed_comment_count"] = int(comment_evidence.get("reviewed_count") or 0)
        result["relevant_comment_count"] = int(comment_evidence.get("relevant_count") or 0)
    return result


def platform_label(platform: Any, language: str) -> str:
    value = str(platform or "platform")
    labels = {
        "x": "X",
        "xiaohongshu": "小红书" if language == "zh-CN" else "Xiaohongshu",
        "youtube": "YouTube",
    }
    return labels.get(value.casefold(), value)


def collection_summary_text(report: dict[str, Any]) -> str:
    summary = report.get("collection_summary") or {}
    zh = report.get("language") == "zh-CN"
    platform = platform_label(report.get("platform"), report.get("language", "en"))
    queries = summary.get("query_count")
    observed = summary.get("observed_result_count")
    unique = summary.get("unique_signal_count")
    relevant = summary.get("relevant_signal_count")
    details = summary.get("detail_open_count")
    counters = summary.get("counter_signal_count")
    reviewed_comments = summary.get("reviewed_comment_count")
    relevant_comments = summary.get("relevant_comment_count")

    if zh:
        parts = []
        if queries is not None and observed is not None:
            parts.append(f"本轮通过 {queries} 个搜索主题，在{platform}观察到 {observed} 条可见结果")
        elif observed is not None:
            parts.append(f"本轮在{platform}观察到 {observed} 条可见结果")
        if unique is not None:
            text = f"去重后 {unique} 条"
            if relevant is not None:
                text += f"，其中 {relevant} 条与研究主题相关"
            parts.append(text)
        if details is not None:
            parts.append(f"打开并核验 {details} 条详情")
        if counters is not None:
            parts.append(f"检查 {counters} 条不同意见或相反情况")
        if reviewed_comments:
            comment_text = f"审查 {reviewed_comments} 条代表性评论"
            if relevant_comments is not None:
                comment_text += f"，其中 {relevant_comments} 条提供了相关用户反馈"
            parts.append(comment_text)
        basis = "；".join(parts) + "。" if parts else "本轮采集数量保留在研究记录中。"
        status = "标准采样已完成。" if summary.get("sampling_status") == "complete" else "本轮为有限快照，以上数据仍可支持报告中的小范围判断。"
        return basis + status

    parts = []
    if queries is not None and observed is not None:
        parts.append(f"This run used {queries} search themes and observed {observed} visible results on {platform}")
    elif observed is not None:
        parts.append(f"This run observed {observed} visible results on {platform}")
    if unique is not None:
        text = f"{unique} remained after deduplication"
        if relevant is not None:
            text += f", including {relevant} relevant to the research topic"
        parts.append(text)
    if details is not None:
        parts.append(f"{details} detail pages were opened and verified")
    if counters is not None:
        parts.append(f"{counters} counter-signals or differing views were reviewed")
    if reviewed_comments:
        comment_text = f"{reviewed_comments} representative comments were reviewed"
        if relevant_comments is not None:
            comment_text += f", including {relevant_comments} with relevant user feedback"
        parts.append(comment_text)
    basis = "; ".join(parts) + ". " if parts else "Collection counts remain available in the research record. "
    status = "The standard sampling requirement was met." if summary.get("sampling_status") == "complete" else "This is a bounded snapshot; the evidence still supports the report's limited decisions."
    return basis + status


def visible_report_sections(intent: str, section_keys: list[str]) -> list[str]:
    """Keep the audit schema intact while avoiding repeated visible prose."""
    hidden = {"decision_answer", "evidence_boundary"}
    if intent == "brand_sentiment":
        hidden.add("affected_audience")
    return [key for key in section_keys if key not in hidden]


def finding_comment_evidence(snapshot: dict[str, Any], topic_key: str) -> dict[str, Any] | None:
    """Aggregate reviewed comments for one topic without changing trend volume."""
    analyses: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for signal in snapshot.get("signals", []):
        if str(signal.get("topic_key") or "") != topic_key:
            continue
        analysis = ((signal.get("platform_facts") or {}).get("comment_analysis") or {})
        if analysis.get("status") == "reviewed" and int(analysis.get("relevant_count") or 0) > 0:
            analyses.append((signal, analysis))
    if not analyses:
        return None
    categories: dict[str, int] = {}
    insights: list[str] = []
    refs: list[str] = []
    reviewed = relevant = support = counter = 0
    for signal, analysis in analyses:
        reviewed += int(analysis.get("reviewed_count") or 0)
        relevant += int(analysis.get("relevant_count") or 0)
        support += int(analysis.get("support_count") or 0)
        counter += int(analysis.get("counter_count") or 0)
        for category, count in (analysis.get("category_counts") or {}).items():
            categories[str(category)] = categories.get(str(category), 0) + int(count)
        insights.extend(str(item) for item in analysis.get("insights", []) if str(item).strip())
        if signal.get("canonical_url"):
            refs.append(str(signal["canonical_url"]))
    return {
        "reviewed_count": reviewed,
        "relevant_count": relevant,
        "support_count": support,
        "counter_count": counter,
        "category_counts": dict(sorted(categories.items())),
        "insights": list(dict.fromkeys(insights))[:4],
        "source_refs": list(dict.fromkeys(refs)),
        "boundary": "Representative comments provide qualitative context and do not increase trend sample volume.",
    }


def follow_up_contract(context: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    intent = context["research_intent"]
    zh = context["language"] == "zh-CN"
    cadence = {
        "brand_sentiment": {"initial": "24 小时" if zh else "24 hours", "comparison": "7 天" if zh else "7 days", "runs": 3},
        "content_opportunity": {"initial": "7 天" if zh else "7 days", "comparison": "每周" if zh else "weekly", "runs": 3},
    }.get(intent, {"initial": "7 天" if zh else "7 days", "comparison": "两周" if zh else "two weeks", "runs": 2})
    topic = context["subject"].get("name") or context["subject"].get("summary")
    platform = context["platform"]
    prompt = (
        f"使用 trend-opportunity-radar，按本次“{topic}”的 {context['profile_version']}、{platform} 平台、市场、语言、查询意图和采样合同执行第 {{run_number}} 次只读复采；追加快照，不覆盖历史。达到至少两个兼容快照后，只比较新增、持续、减弱和消失的信号，并重新生成同一决策模式报告。"
        if zh else
        f"Use trend-opportunity-radar to run read-only follow-up collection {{run_number}} for “{topic}” on {platform}, reusing {context['profile_version']}, market, language, query intents, and sampling contract. Append without overwriting history. After at least two compatible snapshots, compare new, persistent, weakening, and fading signals and regenerate the same decision report."
    )
    return {
        "recommended": True,
        "created": False,
        "requires_explicit_confirmation": True,
        "cadence": cadence,
        "observe": ["finding status", "profile evidence roles", "counterevidence", "recommended action outcome"],
        "trigger": "after_first_delivery",
        "automation_prompt": prompt,
        "feedback_contract": {
            "schema_version": "decision-action-feedback-v0.1",
            "fields": ["finding_id", "action_id", "adopted", "outcome", "observed_at", "human_notes"],
            "rule": "Feedback is audit evidence and never rewrites scoring weights automatically.",
        },
    }


def build_report(context: dict[str, Any], snapshot: dict[str, Any], findings_payload: dict[str, Any]) -> dict[str, Any]:
    topics_by_key = {
        str(item.get("topic_key")): item for item in snapshot.get("topics", []) if item.get("topic_key")
    }
    eligible = {
        str(item.get("topic_key")) for item in snapshot.get("topics", [])
        if (item.get("cluster_audit") or {}).get("status") in {"passed", "not_required"}
    }
    require_valid_findings(findings_payload, context, topic_keys=eligible)
    findings = []
    for source_finding in findings_payload["findings"]:
        finding = dict(source_finding)
        topic_key = str(finding.get("topic_key"))
        summary = finding_score_summary(topics_by_key.get(topic_key))
        if summary:
            finding["score_summary"] = summary
        comment_evidence = finding_comment_evidence(snapshot, topic_key)
        if comment_evidence:
            finding["comment_evidence"] = comment_evidence
        findings.append(finding)
    finding_topic_keys = {str(item.get("topic_key") or "") for item in findings}
    excluded_topics = []
    for item in snapshot.get("topics", []):
        cluster_audit = item.get("cluster_audit") or {}
        if cluster_audit.get("status") != "failed":
            continue
        checks = cluster_audit.get("checks") or {}
        excluded_topics.append({
            "topic_key": str(item.get("topic_key") or ""),
            "title": str(item.get("title") or item.get("topic_key") or ""),
            "exclusion_reason": "cluster_audit_failed",
            "failed_gates": sorted(str(key) for key, passed in checks.items() if not passed),
        })
    unused_eligible_topics = sorted(eligible - finding_topic_keys)
    temporal = context.get("temporal_contract") or {}
    ready_count = sum(1 for item in findings if item["conclusion_status"] in {"review_ready", "confirmed"})
    decision_answer = (
        as_text((findings[0].get("report_sections") or {}).get("decision_answer"))
        or as_text(findings[0].get("decision_summary"))
    ) if findings else (
        "当前证据尚未形成可执行结论。" if context["language"] == "zh-CN" else "The current evidence does not yet support an actionable conclusion."
    )
    if findings and materially_duplicates(decision_answer, findings[0].get("decision_summary")):
        raise SystemExit("The report-level decision answer duplicates the first finding summary; make the answer shorter and decision-oriented.")
    return {
        "schema_version": "profile-research-report-v0.3",
        "generated_at": now_iso(),
        "research_context": {
            "research_intent": context["research_intent"], "profile_version": context["profile_version"],
            "decision_question": context["decision_question"], "analysis_unit": context["analysis_unit"],
            "report_sections": context["report_sections"], "source_prompt_sha256": context["source_prompt_sha256"],
        },
        "subject": context["subject"], "platform": context["platform"], "language": context["language"],
        "collection": snapshot.get("collection", {}),
        "collection_summary": collection_summary(snapshot),
        "decision_answer": decision_answer,
        "decision_readiness": {"ready_findings": ready_count, "total_findings": len(findings), "status": "actionable_test" if ready_count else "exploratory"},
        "findings": findings,
        "excluded_topics": excluded_topics,
        "temporal_status": {
            "claim": "current_snapshot", "label": temporal.get("single_snapshot_label", "signal_snapshot"),
            "compatible_snapshot_count": max([int(item.get("compatible_snapshot_count") or 1) for item in findings], default=1),
        },
        "follow_up_recommendation": follow_up_contract(context, findings),
        "audit": {
            "eligible_topic_count": len(eligible), "finding_count": len(findings),
            "unused_eligible_topics": unused_eligible_topics,
            "profile_evidence_roles": context["evidence_roles"], "counterevidence_targets": context["counterevidence_targets"],
            "decision_thresholds": context["decision_thresholds"],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lang = report["language"]
    zh = lang == "zh-CN"
    ui = PROFILE_UI[report["research_context"]["research_intent"]][lang if lang in {"zh-CN", "en"} else "en"]
    lines = [f"# {ui['name']}：{subject_name(report)}" if zh else f"# {ui['name']}: {subject_name(report)}", "", f"> {ui['question']}", "",
             f"## {'直接回答' if zh else 'Decision answer'}", "", report["decision_answer"], "",
             f"## {'本次研究基础' if zh else 'Research basis'}", "", collection_summary_text(report), "", f"## {ui['findings']}", ""]
    for finding_index, finding in enumerate(report["findings"]):
        lines.extend([f"### {finding['title']}", "", finding["decision_summary"], "",
                      f"- {'适用人群' if zh else 'Audience'}: {finding['audience']}",
                      f"- {'证据边界' if zh else 'Evidence boundary'}: {finding['evidence_boundary']}", ""])
        scores = finding.get("score_summary")
        if scores:
            lines.extend([
                f"- **{'平台讨论强度' if zh else 'Platform discussion strength'}**: {scores['observed_heat']}/100 · {score_level(scores['observed_heat'], lang)}",
                f"- **{'这项判断的可靠度' if zh else 'Reliability of this finding'}**: {scores['evidence_confidence']}/100 · {score_level(scores['evidence_confidence'], lang)}",
                "",
            ])
            if finding_index == 0:
                lines.extend(["讨论强度看这个问题在平台上有多明显；可靠度看这项判断有多少证据支撑。" if zh else "Discussion strength shows how visible the issue is on the platform; reliability shows how much evidence supports this finding.", ""])
        comment_evidence = finding.get("comment_evidence")
        if comment_evidence:
            lines.extend([f"#### {'评论中的用户反馈' if zh else 'What users said in comments'}", ""])
            lines.extend([f"- {item}" for item in comment_evidence["insights"]])
            note = (
                f"已审查 {comment_evidence['reviewed_count']} 条代表性评论，其中 {comment_evidence['relevant_count']} 条与本主题相关。评论用于理解用户反馈，不增加趋势样本数。"
                if zh else
                f"Reviewed {comment_evidence['reviewed_count']} representative comments; {comment_evidence['relevant_count']} were relevant to this topic. Comments add qualitative context, not trend sample volume."
            )
            lines.extend([f"- {note}", ""])
        for key in visible_report_sections(
            report["research_context"]["research_intent"],
            report["research_context"]["report_sections"],
        ):
            lines.append(f"- **{SECTION_LABELS[key][lang if lang in {'zh-CN', 'en'} else 'en']}**: {finding['report_sections'][key]}")
        lines.extend(["", f"#### {ui['action']}", ""])
        for action in finding["recommended_actions"]:
            lines.append(f"- **{action['action']}**（测试范围：{action['intensity']}）" if zh else f"- **{action['action']}** (Scope: {action['intensity']})")
            lines.append(f"  - {'适用前提' if zh else 'Use when'}：{action['condition']}" if zh else f"  - Use when: {action['condition']}")
            for key, value in action.items():
                if key in {"action", "intensity", "condition"}:
                    continue
                label = ACTION_FIELD_LABELS[lang].get(key, key.replace("_", " "))
                lines.append(f"  - {label}：{value}" if zh else f"  - {label}: {value}")
        lines.extend(["", f"**{'支持依据' if zh else 'Support'}**"])
        lines.extend([f"- [{('支持依据' if zh else 'Support')} {index}]({ref})" for index, ref in enumerate(finding["support_refs"], 1)] or [f"- {'未列出直接链接' if zh else 'No direct links listed'}"])
        lines.extend(["", f"**{'相反情况' if zh else 'Counterexamples'}**"])
        lines.extend([f"- [{('相反情况' if zh else 'Counterexample')} {index}]({ref})" for index, ref in enumerate(finding["counter_refs"], 1)] or [f"- {'未列出直接链接' if zh else 'No direct links listed'}"])
        lines.append("")
    follow = report["follow_up_recommendation"]
    lines.extend([f"## {ui['follow_title']}", "",
                  (f"建议在 {follow['cadence']['initial']} 后再研究一次，共观察 {follow['cadence']['runs']} 次。只有你确认后才会创建定时任务。" if zh else f"Run the research again after {follow['cadence']['initial']} and observe {follow['cadence']['runs']} times in total. A scheduled task is created only after your confirmation."), ""])
    return "\n".join(lines)


def _refs(refs: list[str], zh: bool, kind: str) -> str:
    if not refs:
        return f"<span class=\"muted\">{'本结论未列直接链接' if zh else 'No direct links listed'}</span>"
    label = ({"support": "支持依据", "counter": "相反情况"}[kind] if zh else {"support": "Support", "counter": "Counterexample"}[kind])
    return "".join(f'<a href="{html.escape(ref, quote=True)}" target="_blank" rel="noreferrer">{label} {index}</a>' for index, ref in enumerate(refs, 1))


def render_html(report: dict[str, Any]) -> str:
    lang = report["language"] if report["language"] in {"zh-CN", "en"} else "en"
    zh = lang == "zh-CN"
    ui = PROFILE_UI[report["research_context"]["research_intent"]][lang]
    findings_html = []
    for index, finding in enumerate(report["findings"]):
        section_keys = visible_report_sections(
            report["research_context"]["research_intent"],
            report["research_context"]["report_sections"],
        )
        sections = "".join(
            f'<div class="detail"><span>{html.escape(SECTION_LABELS[key][lang])}</span><p>{html.escape(str(finding["report_sections"][key]))}</p></div>'
            for key in section_keys
        )
        actions = "".join(
            f'''<article class="action"><div><span class="tag">{('测试范围：' if zh else 'Scope: ')}{html.escape(str(action["intensity"]))}</span><h4>{html.escape(str(action["action"]))}</h4></div><p><b>{'适用前提：' if zh else 'Use when: '}</b>{html.escape(str(action["condition"]))}</p><details><summary>{'查看怎样判断有效、何时停止' if zh else 'See how to measure success and when to stop'}</summary><dl>{''.join(f'<dt>{html.escape(ACTION_FIELD_LABELS[lang].get(key, key.replace("_", " ")))}</dt><dd>{html.escape(str(value))}</dd>' for key, value in action.items() if key not in {"action", "intensity", "condition"})}</dl></details></article>'''
            for action in finding["recommended_actions"]
        )
        scores = finding.get("score_summary")
        score_html = ""
        if scores:
            score_html = f'''<div class="score-row" aria-label="{'评分' if zh else 'Scores'}"><span class="score"><b>{'平台讨论强度' if zh else 'Platform discussion strength'} {html.escape(str(scores['observed_heat']))}/100</b><em>{html.escape(score_level(scores['observed_heat'], lang))}</em></span><span class="score"><b>{'这项判断的可靠度' if zh else 'Reliability of this finding'} {html.escape(str(scores['evidence_confidence']))}/100</b><em>{html.escape(score_level(scores['evidence_confidence'], lang))}</em></span></div>{('<p class="score-help">讨论强度看这个问题在平台上有多明显；可靠度看这项判断有多少证据支撑。</p>' if zh else '<p class="score-help">Discussion strength shows how visible the issue is on the platform; reliability shows how much evidence supports this finding.</p>') if index == 0 else ''}'''
        comment_evidence = finding.get("comment_evidence")
        comment_html = ""
        if comment_evidence:
            insights = "".join(f"<li>{html.escape(str(item))}</li>" for item in comment_evidence["insights"])
            note = (
                f"已审查 {comment_evidence['reviewed_count']} 条代表性评论，其中 {comment_evidence['relevant_count']} 条与本主题相关。评论用于理解用户反馈，不增加趋势样本数。"
                if zh else
                f"Reviewed {comment_evidence['reviewed_count']} representative comments; {comment_evidence['relevant_count']} were relevant to this topic. Comments add qualitative context, not trend sample volume."
            )
            comment_html = f'''<section class="comment-voice" style="margin-top:14px;padding:14px 16px;border:1px solid #dfe8e4;border-radius:14px;background:#f4fbf8"><b>{'评论中的用户反馈' if zh else 'What users said in comments'}</b><ul>{insights}</ul><p style="margin:6px 0 0;color:#667085;font-size:12px">{html.escape(note)}</p></section>'''
        findings_html.append(f'''<section class="finding {'secondary' if index else ''}"><div class="finding-head"><div><span class="kicker">{html.escape(ui['why'])}</span><h2>{html.escape(str(finding['title']))}</h2>{score_html}</div><span class="status">{html.escape(visible_status(finding['conclusion_status'], lang))}</span></div><p class="summary">{html.escape(str(finding['decision_summary']))}</p><div class="audience"><b>{'与谁有关' if zh else 'Who this affects'}</b><span>{html.escape(str(finding['audience']))}</span></div>{comment_html}<div class="details-grid">{sections}</div><div class="action-title"><span class="kicker">{html.escape(ui['action'])}</span></div><div class="actions">{actions}</div><details class="evidence"><summary>{'查看依据和目前不能确定的部分' if zh else 'View evidence and what remains uncertain'}</summary><p>{html.escape(str(finding['evidence_boundary']))}</p><div class="refs">{_refs(finding['support_refs'], zh, 'support')}{_refs(finding['counter_refs'], zh, 'counter')}</div></details></section>''')
    follow = report["follow_up_recommendation"]
    payload = html.escape(json.dumps(report, ensure_ascii=False), quote=False)
    return f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(ui['name'])} · {html.escape(subject_name(report))}</title><style>
:root{{--bg:#f3f5f9;--panel:#fff;--ink:#16202c;--muted:#667085;--line:#e4e8ef;--accent:#5364d9;--accent2:#7a55ca;--soft:#eef0ff;--good:#14775a}}*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(180deg,#eef1f7 0,#f7f8fa 320px);color:var(--ink);font:15px/1.58 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}main{{max-width:1120px;margin:auto;padding:28px 22px 64px}}header{{padding:34px;border-radius:26px;color:#fff;background:linear-gradient(135deg,#20274d,#5b4f9c);box-shadow:0 22px 55px #30385d26}}.kicker{{display:block;color:#888fa6;font-size:11px;font-weight:750;letter-spacing:.12em;text-transform:uppercase}}header .kicker{{color:#cad0ff}}h1{{font-size:clamp(30px,5vw,52px);line-height:1.1;margin:8px 0 16px;max-width:900px}}header p{{color:#e5e7f8;max-width:850px;margin:0}}.answer{{margin:18px 0 0;background:#fff;border:1px solid var(--line);border-radius:22px;padding:25px;box-shadow:0 8px 26px #1520380a}}.answer h2{{margin:6px 0 0;font-size:24px;line-height:1.45}}.basis{{margin-top:12px;padding:14px 18px;border:1px solid #dfe2fa;border-radius:16px;background:#f8f8ff}}.basis p{{margin:5px 0 0;color:#4f586b}}.finding{{margin-top:22px;background:var(--panel);border:1px solid var(--line);border-radius:22px;padding:25px;box-shadow:0 7px 24px #1520380a}}.finding-head{{display:flex;justify-content:space-between;align-items:start;gap:20px}}.finding h2{{font-size:23px;line-height:1.3;margin:5px 0 0}}.status,.tag{{border-radius:99px;padding:6px 10px;background:#e9f7f1;color:var(--good);font-size:12px;font-weight:700}}.status{{white-space:nowrap}}.tag{{display:inline-block;white-space:normal}}.score-row{{display:flex;flex-wrap:wrap;gap:8px;margin-top:13px}}.score{{display:inline-flex;align-items:center;gap:7px;padding:6px 10px;border:1px solid #dfe2fa;border-radius:99px;background:#f8f8ff;font-size:12px}}.score b{{color:#343e9c}}.score em{{color:var(--muted);font-style:normal}}.score-help{{margin:8px 0 0;color:var(--muted);font-size:12px}}.summary{{font-size:18px;max-width:850px}}.audience{{display:flex;gap:12px;padding:12px 14px;border-radius:12px;background:#f7f8fb}}.audience span{{color:var(--muted)}}.details-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}}.detail{{border:1px solid var(--line);border-radius:14px;padding:15px}}.detail span{{font-size:12px;color:var(--accent);font-weight:750}}.detail p{{margin:6px 0 0}}.action-title{{margin-top:23px}}.actions{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:9px}}.action{{min-width:0;border:1px solid #dfe2fa;background:#fafaff;border-radius:16px;padding:16px}}.action h4{{font-size:17px;margin:9px 0 0}}.action p{{color:var(--muted)}}details{{border-top:1px solid var(--line);padding-top:11px;margin-top:13px}}summary{{cursor:pointer;font-weight:700}}dl{{display:grid;grid-template-columns:150px minmax(0,1fr);gap:7px 10px}}dt{{color:var(--muted)}}dd{{margin:0;overflow-wrap:anywhere}}.refs{{display:flex;flex-wrap:wrap;gap:8px}}.refs a{{text-decoration:none;color:#454eb2;background:var(--soft);padding:6px 9px;border-radius:9px}}.follow{{margin-top:22px;padding:22px;border:1px solid #dbdef8;background:#f8f8ff;border-radius:20px;display:grid;grid-template-columns:1.1fr .9fr;gap:20px}}.follow h2{{margin:5px 0 8px}}.cadence{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}.cadence b{{font-size:20px}}.prompt{{background:#fff;border:1px solid var(--line);border-radius:14px;padding:13px;color:var(--muted)}}.audit{{margin-top:18px;background:#fff;border:1px solid var(--line);border-radius:16px;padding:15px}}.muted{{color:var(--muted)}}#raw{{white-space:pre-wrap;max-height:440px;overflow:auto;font:12px/1.5 ui-monospace,Consolas,monospace}}@media(max-width:760px){{.finding-head,.audience{{display:block}}.status{{display:inline-block;margin-top:10px}}.details-grid,.actions,.follow{{grid-template-columns:1fr}}header{{padding:26px}}main{{padding:16px}}}}@media print{{body{{background:#fff}}main{{padding:0}}.finding,.answer,header{{box-shadow:none}}}}
/* Keep long research subjects readable as interface titles, not billboard copy. */
h1{{font-size:clamp(28px,3.8vw,42px);line-height:1.15;overflow-wrap:anywhere}}
</style></head><body><main><header><span class="kicker">{html.escape(ui['name'])} · {html.escape(str(report['platform']))}</span><h1>{html.escape(subject_name(report))}</h1><p>{html.escape(ui['question'])}</p></header><section class="answer"><span class="kicker">{'直接回答' if zh else 'Decision answer'}</span><h2>{html.escape(str(report['decision_answer']))}</h2></section><section class="basis" aria-label="{'本次研究基础' if zh else 'Research basis'}"><span class="kicker">{'本次研究基础' if zh else 'Research basis'}</span><p>{html.escape(collection_summary_text(report))}</p></section><div aria-label="{html.escape(ui['findings'])}">{''.join(findings_html)}</div><section class="follow"><div><span class="kicker">{'可选的后续检查' if zh else 'Optional follow-up check'}</span><h2>{html.escape(ui['follow_title'])}</h2><p class="muted">{'这能帮助判断信号是否持续。定时任务尚未创建，只有你明确确认后才会设置。' if zh else 'This helps establish whether the signal persists. No scheduled task has been created; it will be set up only after your explicit confirmation.'}</p><div class="cadence"><span>{'首次' if zh else 'First'}</span><b>{html.escape(str(follow['cadence']['initial']))}</b><span>· {follow['cadence']['runs']} {'次' if zh else 'runs'}</span></div></div><details><summary>{'查看下次继续研究时使用的指令' if zh else 'View instructions for the next research run'}</summary><p class="prompt">{html.escape(str(follow['automation_prompt']))}</p></details></section><details class="audit"><summary>{'查看研究方法和原始记录' if zh else 'View research method and source record'}</summary><p class="muted">{'这些信息用于复核，不影响上面的业务阅读顺序。' if zh else 'This information supports audit and does not interrupt the decision flow above.'}</p><pre id="raw">{payload}</pre></details></main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Profile-specific JSON, Markdown, and visual HTML from one evidence model.")
    parser.add_argument("--research-context", required=True); parser.add_argument("--signals", required=True); parser.add_argument("--findings", required=True)
    parser.add_argument("--json-output", required=True); parser.add_argument("--markdown-output", required=True); parser.add_argument("--html-output")
    args = parser.parse_args()
    context = load_context(Path(args.research_context).resolve()); snapshot = load_data(args.signals); findings = load_data(args.findings)
    require_text_integrity(snapshot, "Signals"); require_text_integrity(findings, "Profile findings")
    report = build_report(context, snapshot, findings); require_text_integrity(report, "Profile report")
    markdown = render_markdown(report); page = render_html(report) if args.html_output else ""
    validate_report_contents(report, markdown, page or None)
    write_json(args.json_output, report)
    markdown_target = Path(args.markdown_output); markdown_target.parent.mkdir(parents=True, exist_ok=True); markdown_target.write_text(markdown, encoding="utf-8")
    if args.html_output:
        html_target = Path(args.html_output); html_target.parent.mkdir(parents=True, exist_ok=True); html_target.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
