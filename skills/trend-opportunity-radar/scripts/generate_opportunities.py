from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from _common import SAMPLING_CONTRACTS, load_data, now_iso, require_text_integrity, write_json
from validate_report_artifacts import validate_report_contents
from validate_subject import validate_subject


def subject_name(subject: dict) -> str:
    return str(subject.get("name") or subject.get("title") or subject.get("summary") or "Untitled research topic").strip()


def communication_profile(subject: dict) -> dict:
    supplied = subject.get("communication") if isinstance(subject.get("communication"), dict) else {}
    language = str(supplied.get("language") or "auto")
    if language == "auto":
        request_text = str(supplied.get("request_text") or "")
        fallback_text = request_text or f"{subject_name(subject)} {subject.get('summary', '')}"
        language = "zh-CN" if any("\u4e00" <= char <= "\u9fff" for char in fallback_text) else "en"
    default_goal = {
        "product": "validate_product_demand",
        "opportunity": "validate_business_opportunity",
        "idea": "validate_business_opportunity",
        "problem": "validate_product_demand",
    }.get(subject.get("subject_type"), "general_research")
    return {
        "language": language,
        "goal": str(supplied.get("goal") or default_goal),
        "audience": str(supplied.get("audience") or "general"),
    }


def reader_title(item: dict, profile: dict) -> tuple[str, list[str]]:
    """Produce a plain-language display title while preserving the supplied audit title."""
    original = str(item.get("title") or "Untitled opportunity").strip()
    if profile.get("audience") == "expert":
        return original, []
    if profile.get("language") == "zh-CN":
        replacements = {
            "跨时区多语言首轮处理队列": "先处理夜间和多语言售后，复杂问题再转人工",
            "售后 Agent 的政策与订单事实守门层": "售后 AI 助手回复前，先核对订单和政策",
            "多语言售后副驾": "跨境电商多语言售后助手",
            "先准备动作": "自动准备处理方案",
            "资金操作人工批准": "退款等资金操作交给人工确认",
            "政策与订单事实守门层": "政策与订单信息检查机制",
            "副驾": "助手",
            "中台": "统一工作台",
            "引擎": "工具",
            "闭环": "完整流程",
            "赋能": "帮助",
            "桥接": "连接",
            "守门层": "检查机制",
            "Agent": "AI 助手",
        }
    else:
        replacements = {
            "copilot": "assistant",
            "orchestration engine": "workflow tool",
            "enablement layer": "support process",
            "flywheel": "feedback process",
        }
    rewritten = original
    matched: list[str] = []
    for jargon, plain in replacements.items():
        if jargon in rewritten:
            rewritten = rewritten.replace(jargon, plain)
            matched.append(jargon)
    return rewritten, matched


def build_decision_support(subject: dict, collection: dict, topics: list[dict], opportunities: list[dict], lang: str) -> dict:
    profile = communication_profile(subject)
    count = len(opportunities)
    first_action = str((opportunities[0] if opportunities else {}).get("expected_action") or "").strip()
    goal = profile["goal"]
    contract_met = collection.get("contract_status") == "met"
    review_ready = sum(1 for item in opportunities if item.get("evidence_status") in {"review_ready", "confirmed"})
    decision_limited = not contract_met or review_ready == 0
    if lang == "zh-CN":
        purpose = {
            "validate_business_opportunity": "选择值得优先做小规模验证的商机方向",
            "validate_product_demand": "确定优先验证的用户任务和 MVP 范围",
            "discover_content_opportunities": "选择更有证据支持的内容话题与切入角度",
            "understand_trend": "识别当前平台信号和后续追踪对象",
            "general_research": "确定下一步研究与验证的优先级",
        }.get(goal, "确定下一步研究与验证的优先级")
        if count and decision_limited:
            headline = f"本次快照形成了 {count} 个可用于设计验证实验的候选方向；当前证据不用于机会排序或判断需求强度。"
            purpose = "围绕候选方向设计用户访谈、原型测试或小范围人工服务实验"
        elif count:
            headline = f"本次研究形成了 {count} 个证据较完整的验证方向，可用于设计和选择下一步验证实验；当前快照不用于给机会排序。"
            purpose = "根据证据设计并选择下一步验证实验"
        else:
            headline = "本次研究尚未形成可测试的机会方向，但已经定位到下一轮采集应验证的具体问题。"
        boundary = "暂时不要据此判断趋势升降、市场规模或真实付费意愿；这些结论需要重复快照或真实用户验证。" if contract_met else "当前可先设计验证实验，但不要判断趋势升降、市场规模或真实付费意愿；先完成采样，再用重复快照或真实用户验证。"
        resolution = first_action or "先补充当前缺口最大的证据层，再围绕首要机会执行一次小规模用户验证。"
        return {"headline": headline, "useful_now": purpose, "boundary": boundary, "resolution": resolution}
    purpose = {
        "validate_business_opportunity": "choose which opportunity deserves a small validation test first",
        "validate_product_demand": "prioritize the user task and define a testable MVP scope",
        "discover_content_opportunities": "choose evidence-backed topics and content angles",
        "understand_trend": "identify current platform signals and what to monitor next",
        "general_research": "prioritize the next research and validation step",
    }.get(goal, "prioritize the next research and validation step")
    if count and decision_limited:
        headline = f"This snapshot produced {count} candidate direction(s) for designing validation experiments; the evidence is not yet suitable for ranking opportunities or judging demand strength."
        purpose = "design user interviews, prototype tests, or a small manual-service experiment around the candidate direction"
    elif count:
        headline = f"This study produced {count} evidence-supported validation direction(s). Use them to design and choose the next validation experiment, not to rank the opportunities."
        purpose = "design and choose the next validation experiment"
    else:
        headline = "This study did not yet produce a testable opportunity, but it identified the specific question the next collection round should answer."
    boundary = "Do not use this snapshot alone to infer trend direction, market size, or willingness to pay; those require repeated snapshots or real-user validation." if contract_met else "Use this evidence to design a test, but not to infer trend direction, market size, or willingness to pay; complete sampling first, then use repeated snapshots or real-user validation."
    resolution = first_action or "Fill the most consequential evidence gap, then run one small user test around the primary opportunity."
    return {"headline": headline, "useful_now": purpose, "boundary": boundary, "resolution": resolution}


def statement(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("statement") or value.get("summary") or value)
    return str(value)


def fallback_opportunity(topic: dict, subject: dict) -> dict:
    name = subject_name(subject)
    audience = (subject.get("audiences") or ["people discussing this platform topic"])[0]
    return {
        "title": f"Validate the connection between {topic.get('title')} and {name}",
        "topic_key": topic.get("topic_key"),
        "audience": audience,
        "task_gap": "The signal exists, but the unresolved task has not been verified.",
        "subject_entry": f"Test whether {name} can address one adjacent task without extending unverified claims.",
        "expected_action": "Collect direct evidence and run a small user test before implementation.",
        "support_refs": topic.get("evidence_refs", [])[:2],
        "counter_refs": [],
        "counter_review": "",
        "counter_search_status": "not_searched",
        "semantic_review": "not_reviewed",
        "risk_boundaries": ["Treat this as a candidate, not a confirmed market conclusion."],
        "missing_evidence": ["Semantic opportunity review and counterevidence collection are incomplete."],
    }


def opportunity_gates(item: dict, topic: dict | None, collection_status: str) -> tuple[dict, list[str]]:
    topic = topic or {}
    counter_status = item.get("counter_search_status", "")
    counter_ok = bool(item.get("counter_refs")) and counter_status == "found"
    counter_ok = counter_ok or counter_status == "searched_none_found"
    gates = {
        "sampling_contract_completed": collection_status == "met",
        "audience_relevance": bool(item.get("audience")),
        "task_continuity": bool(item.get("task_gap") and item.get("subject_entry")),
        "subject_boundary": bool(item.get("risk_boundaries")),
        "supporting_evidence": bool(item.get("support_refs")),
        "minimum_independent_signals": int(topic.get("sample_count") or 0) >= 3,
        "minimum_independent_authors": int(topic.get("unique_author_count") or 0) >= 2,
        "direct_source_present": int(topic.get("direct_source_count") or 0) >= 1,
        "subject_bridge_direct_evidence": int(topic.get("subject_bridge_direct_count") or 0) >= 1,
        "semantic_relevance_reviewed": float(topic.get("relevance_review_coverage") or 0) >= 0.8,
        "cluster_audit_passed": (topic.get("cluster_audit") or {}).get("status") in {"passed", "not_required"},
        "confidence_threshold": float(topic.get("evidence_confidence") or 0) >= 55,
        "counterevidence_review": counter_ok,
        "semantic_link_review": item.get("semantic_review") in {"agent_reviewed", "human_reviewed"},
        "concrete_action": bool(item.get("expected_action")),
    }
    reasons = [name for name, passed in gates.items() if not passed]
    return gates, reasons


def topic_is_eligible(topic: dict, mode: str = "standard") -> bool:
    internal = {"unreviewed", "excluded-keyword-collision", "reviewed-unclustered"}
    audit = (topic.get("cluster_audit") or {}).get("status")
    return topic.get("topic_key") not in internal and (audit == "passed" or (mode == "quick" and audit == "not_required"))


def display_value(value: object, lang: str, kind: str) -> str:
    text = str(value or "")
    if lang != "zh-CN":
        return text
    mappings = {
        "mode": {"quick": "快速", "standard": "标准", "deep": "深度", "untracked": "未追踪"},
        "contract": {"met": "证据较完整", "blocked": "初步证据", "partial": "初步证据", "in_progress": "采集中", "untracked": "证据未追踪"},
        "topic_status": {"snapshot": "单次快照", "comparable": "可比较快照"},
        "opportunity_status": {"candidate": "初步方向", "review_ready": "值得验证", "confirmed": "已确认", "rejected": "已排除"},
        "layer": {"platform_baseline": "平台基线", "category": "品类任务", "subject_bridge": "主题桥接"},
        "dimension": {"velocity": "时间变化", "search_demand": "搜索需求", "freshness": "新鲜度", "engagement": "互动", "diffusion": "扩散"},
        "gate": {
            "sampling_contract_completed": "当前结论保持为候选，避免过度确定",
            "confidence_threshold": "证据置信度尚未达到审核线",
            "minimum_independent_signals": "独立信号不足",
            "minimum_independent_authors": "独立作者不足",
            "direct_source_present": "缺少详情直证",
            "subject_bridge_direct_evidence": "缺少主题桥接直证",
            "semantic_relevance_reviewed": "语义相关性尚未完成复核",
            "cluster_audit_passed": "话题聚类审计未通过",
            "counterevidence_review": "反证尚未完成审查",
            "semantic_link_review": "主题与机会的语义连接尚未复核",
            "audience_relevance": "适用对象不明确",
            "task_continuity": "任务链不完整",
            "subject_boundary": "能力边界不明确",
            "supporting_evidence": "缺少支持证据",
            "concrete_action": "缺少下一步验证动作",
        },
        "contract_gate": {
            "queries": "查询数量",
            "observed_results": "观察结果数量",
            "unique_signals": "去重信号数量",
            "detail_opens": "详情页数量",
            "counter_signals": "反证数量",
            "layer_queries": "各层查询数量",
            "layer_observed_results": "各层观察结果数量",
            "layer_unique_signals": "各层去重信号数量",
            "layer_detail_opens": "各层详情页数量",
            "subject_bridge_direct_evidence": "主题桥接直证",
            "relevance_review_coverage": "语义复核覆盖率",
        },
    }
    return mappings.get(kind, {}).get(text, text)


def display_list(values: list[object], lang: str, kind: str) -> str:
    return "、".join(display_value(value, lang, kind) for value in values)


def summarize_limitations(limitations: list[object], lang: str) -> list[str]:
    """Turn per-signal audit notes into at most four decision-facing summaries."""
    categories = {"context": 0, "source": 0, "relevance": 0, "validation": 0}
    patterns = {
        "context": (
            "search card", "search-card", "not opened", "unopened", "truncat",
            "linked article not opened", "linked offer page not opened",
        ),
        "source": (
            "vendor", "promotional", "builder", "seller claim", "self-reported",
            "job ", "job listing", "employer", "paid-work", "conflict",
            "made-with-ai", "creator claim",
        ),
        "relevance": (
            "not specific", "not explicitly", "weakly related", "weak semantic",
            "broad ", "context signal", "rather than", "pre-fulfilment",
            "not full after-sales", "not ecommerce", "not shopify", "generic business",
            "enterprise-focused", "specific to", "nigeria-specific", "idea list",
            "growth workflow", "upstream", "cro context",
        ),
        "validation": (
            "unverified", "unsourced", "not sourced", "not independently",
            "no measurable", "no documented", "no company-level", "not observed",
            "no customer outcome", "outcome evidence", "authenticity", "low reach",
            "no external customer", "no workflow or outcome", "not buyer-demand",
            "not buyer outcome", "not measured", "no production outcome",
        ),
    }
    for value in dict.fromkeys(str(item).strip() for item in limitations if str(item).strip()):
        text = value.casefold()
        if text.startswith("sampling_contract_unmet:"):
            continue
        category = next(
            (name for name in ("context", "source", "relevance", "validation") if any(token in text for token in patterns[name])),
            "validation",
        )
        categories[category] += 1

    if lang == "zh-CN":
        templates = {
            "context": "搜索卡或未打开全文的证据尚未完成语境与结果核验（{count} 条）。",
            "source": "供应商、创作者、招聘等利益相关方自述仍缺少独立验证（{count} 条）。",
            "relevance": "相邻话题不能直接代表目标用户的真实需求（{count} 条）。",
            "validation": "真实采用、效果或商业结果仍缺少可复核数据（{count} 条）。",
        }
    else:
        templates = {
            "context": "Search-card or unopened-page evidence still lacks full context and outcome verification ({count} items).",
            "source": "Vendor, creator, job, or other interested-party claims still need independent verification ({count} items).",
            "relevance": "Adjacent signals do not directly establish demand from the target audience ({count} items).",
            "validation": "Adoption, outcome, or commercial claims still lack verifiable data ({count} items).",
        }
    return [templates[name].format(count=count) for name, count in categories.items() if count]


def build_monitoring_recommendation(subject: dict, platform: object, lang: str) -> dict:
    platform_name = str(platform or "the same platform")
    fast_platforms = {"x", "twitter", "tiktok", "reddit"}
    every_days = 3 if platform_name.casefold() in fast_platforms else 7
    cadence_key = "every_3_days" if every_days == 3 else "weekly"
    occurrences = 4
    name = subject_name(subject)
    if lang == "zh-CN":
        reason = "追加可比较快照后，才能判断话题是升温、降温、持续还是消退。"
        cadence_label = f"每 {every_days} 天一次，连续 {occurrences} 次" if every_days != 7 else f"每周一次，连续 {occurrences} 周"
        prompt = (
            f"使用 trend-opportunity-radar，沿用研究主题“{name}”及本次 {platform_name} 的语言、地区、查询分层和采样合同进行只读复采；"
            "将新快照追加到历史记录，并与已有快照比较新增、升温、降温、消退的话题及机会变化。"
            "不得覆盖历史快照；采样未达标时返回待补采。"
        )
    else:
        reason = "Comparable snapshots are required to tell whether topics are rising, falling, persisting, or fading."
        cadence_label = f"Every {every_days} days for {occurrences} runs" if every_days != 7 else f"Weekly for {occurrences} weeks"
        prompt = (
            f"Use trend-opportunity-radar to repeat authorized read-only collection for “{name}” on {platform_name}, reusing the language, region, query layers, and sampling contract from this run. "
            "Append each snapshot without overwriting history, then compare new, rising, falling, and fading topics and opportunity changes. "
            "Return an incomplete-collection status when the sampling contract is not met."
        )
    return {
        "recommended": True,
        "reason": reason,
        "cadence": {"type": "interval_days", "value": every_days, "occurrences": occurrences, "key": cadence_key, "label": cadence_label},
        "comparison_ready_after_snapshots": 2,
        "reuse": ["subject", "platform", "language", "region", "query_layers", "sampling_contract", "output_history"],
        "requires_user_confirmation": ["cadence", "authorized_collection_access"],
        "automation_prompt": prompt,
    }


def link_list(refs: list[str]) -> str:
    return "; ".join(refs) if refs else "none listed"


def render_markdown(result: dict) -> str:
    subject = result["subject"]
    collection = result.get("collection", {})
    counts = collection.get("counts", {})
    zh = communication_profile(subject)["language"] == "zh-CN"
    status_labels = {
        "met": "采样达标", "partial": "采样未完成", "blocked": "采集受阻", "untracked": "未记录采样过程",
        "review_ready": "值得进入下一步验证", "candidate": "初步方向", "confirmed": "已人工确认",
        "quick": "快速扫描", "standard": "标准研究", "deep": "深度研究",
        "product": "产品", "opportunity": "商机", "idea": "想法", "problem": "问题", "project": "项目",
        "snapshot": "单次快照", "comparable": "可比较快照",
    }
    field_labels = {"velocity": "时间变化", "search_demand": "搜索需求", "freshness": "时效性", "diffusion": "传播范围", "engagement": "互动表现", "content_volume": "内容数量"}

    def human(value: object) -> str:
        text = str(value or "")
        return status_labels.get(text, text) if zh else text.replace("_", " ")

    def fields(values: list[object]) -> str:
        rendered = [field_labels.get(str(value), human(value)) if zh else human(value) for value in values]
        return "、".join(rendered) if zh else ", ".join(rendered)

    ready_count = sum(1 for item in result["opportunities"] if item["evidence_status"] == "review_ready")
    if zh:
        lines = [
            f"# {subject_name(subject)}：{result.get('platform') or '未指定平台'}趋势机会",
            "", f"生成时间：{result['generated_at']}", "", "## 一分钟结论", "",
            f"- 采样状态：{human(collection.get('contract_status', 'untracked'))}",
            f"- 研究模式：{human(collection.get('mode', 'unspecified'))}",
            f"- 观察结果 / 保留样本 / 去重样本：{counts.get('observed_result_count')} / {counts.get('retained_sample_count')} / {counts.get('unique_sample_count')}",
            f"- 可进入评审的机会：{ready_count} / {len(result['opportunities'])}",
            f"- 已排除话题 / 机会：{len(result.get('excluded_topics', []))} / {len(result.get('excluded_opportunities', []))}",
            "- 单次采集反映当前平台信号，不代表趋势正在上升或下降。", "", "## 研究主题与前提", "",
            f"- 主题类型：{human(subject.get('subject_type', 'unspecified'))}", f"- 主题说明：{subject.get('summary', '')}",
        ]
        lines.extend([f"- 已知事实：{statement(item)}" for item in subject.get("facts", [])] or ["- 已知事实：未提供"])
        lines.extend([f"- 待验证假设：{statement(item)}" for item in subject.get("hypotheses", [])] or ["- 待验证假设：未提供"])
        lines.extend(["", "## 平台话题信号", ""])
        for topic in result["topics"]:
            topic_title = ((topic.get("cluster_audit") or {}).get("title") or topic.get("title"))
            lines.extend([
                f"### {topic_title}", "", f"- 状态：{human(topic.get('status'))}",
                f"- 当前可见热度：{topic.get('observed_heat')}/100", f"- 证据支持度：{topic.get('evidence_confidence')}/100",
                f"- 数据覆盖率：{topic.get('data_coverage')}%",
                f"- 样本 / 独立作者 / 直接来源 / 反向证据：{topic.get('sample_count')} / {topic.get('unique_author_count')} / {topic.get('direct_source_count')} / {topic.get('counter_signal_count')}", "",
            ])
        lines.extend(["## 研究主题的机会方向", ""])
        for item in result["opportunities"]:
            lines.extend([
                f"### {item.get('reader_title') or item.get('title', '未命名机会')}", "", f"- 证据状态：{human(item['evidence_status'])}",
                f"- 适用人群：{item.get('audience', '')}", f"- 尚未解决的任务：{item.get('task_gap', '')}",
                f"- 可切入方式：{item.get('subject_entry', '')}", f"- 下一步验证：{item.get('expected_action', '')}",
                f"- 支持证据：{link_list(item.get('support_refs', []))}",
                f"- 反向证据：{link_list(item.get('counter_refs', [])) if item.get('counter_refs') else item.get('counter_review', '尚未评审')}",
                f"- 未通过的证据门槛：{fields(item.get('failed_gates', [])) or '无'}",
                f"- 使用边界：{'；'.join(item.get('risk_boundaries', []))}",
                f"- 后续验证重点：{'；'.join(item.get('missing_evidence', [])) or '无'}", "",
            ])
        lines.extend(["## 后续验证重点", ""])
    else:
        lines = [
            f"# Trend opportunities: {subject_name(subject)} on {result.get('platform') or 'unspecified platform'}", "",
            f"Generated: {result['generated_at']}", "", "## One-minute conclusion", "",
            f"- Snapshot status: {human(collection.get('contract_status', 'untracked'))}", f"- Collection mode: {human(collection.get('mode', 'unspecified'))}",
            f"- Observed / retained / unique: {counts.get('observed_result_count')} / {counts.get('retained_sample_count')} / {counts.get('unique_sample_count')}",
            f"- Review-ready opportunities: {ready_count} of {len(result['opportunities'])}",
            f"- Excluded topics / opportunities: {len(result.get('excluded_topics', []))} / {len(result.get('excluded_opportunities', []))}",
            "- A single collection is a signal snapshot, not evidence of a rising or falling trend.", "", "## Research topic and assumptions", "",
            f"- Subject type: {human(subject.get('subject_type', 'unspecified'))}", f"- Summary: {subject.get('summary', '')}",
        ]
        lines.extend([f"- Fact: {statement(item)}" for item in subject.get("facts", [])] or ["- Facts: none supplied"])
        lines.extend([f"- Hypothesis: {statement(item)}" for item in subject.get("hypotheses", [])] or ["- Hypotheses: none supplied"])
        lines.extend(["", "## Platform topics", ""])
        for topic in result["topics"]:
            topic_title = ((topic.get("cluster_audit") or {}).get("title") or topic.get("title"))
            lines.extend([
                f"### {topic_title}", "", f"- Status: {human(topic.get('status'))}", f"- Observed heat: {topic.get('observed_heat')}/100",
                f"- Evidence support: {topic.get('evidence_confidence')}/100", f"- Data coverage: {topic.get('data_coverage')}%",
                f"- Samples / independent authors / direct sources / counters: {topic.get('sample_count')} / {topic.get('unique_author_count')} / {topic.get('direct_source_count')} / {topic.get('counter_signal_count')}", "",
            ])
        lines.extend(["## Research-topic opportunities", ""])
        for item in result["opportunities"]:
            lines.extend([
                f"### {item.get('reader_title') or item.get('title', 'Untitled opportunity')}", "", f"- Evidence status: {human(item['evidence_status'])}",
                f"- Audience: {item.get('audience', '')}", f"- Task gap: {item.get('task_gap', '')}", f"- Topic entry: {item.get('subject_entry', '')}",
                f"- Next validation: {item.get('expected_action', '')}", f"- Supporting evidence: {link_list(item.get('support_refs', []))}",
                f"- Counterevidence: {link_list(item.get('counter_refs', [])) if item.get('counter_refs') else item.get('counter_review', 'not reviewed')}",
                f"- Failed gates: {fields(item.get('failed_gates', [])) or 'none'}", f"- Risk boundaries: {'; '.join(item.get('risk_boundaries', []))}",
                f"- Next evidence to validate: {'; '.join(item.get('missing_evidence', [])) or 'none listed'}", "",
            ])
        lines.extend(["## Next evidence to validate", ""])
    gaps = list(dict.fromkeys(
        [gap for item in result["opportunities"] for gap in item.get("missing_evidence", [])]
    ))
    lines.extend([f"- {gap}" for gap in gaps] or (["- 当前没有需要单独展示的缺口；确认前仍需遵守报告中的使用边界。"] if zh else ["- No separate gap is declared; follow the report's decision boundaries before confirmation."]))
    if result.get("limitation_summary"):
        lines.extend(["", "## 决策使用边界" if zh else "## Decision boundaries", ""] + [f"- {item}" for item in result["limitation_summary"]])
    monitoring = result.get("monitoring_recommendation") or {}
    if monitoring.get("recommended"):
        lines.extend([
            "", "## 建议的后续定时追踪" if zh else "## Suggested follow-up monitoring", "",
            f"- {'为什么值得追踪' if zh else 'Why'}：{monitoring.get('reason', '')}" if zh else f"- Why: {monitoring.get('reason', '')}",
            f"- {'建议频率' if zh else 'Suggested cadence'}：{(monitoring.get('cadence') or {}).get('label', '')}" if zh else f"- Suggested cadence: {(monitoring.get('cadence') or {}).get('label', '')}",
            f"- {'可复用任务口令' if zh else 'Reusable task'}：{monitoring.get('automation_prompt', '')}" if zh else f"- Reusable task: {monitoring.get('automation_prompt', '')}",
        ])
    return "\n".join(lines) + "\n"


def pill(value: object, label: str) -> str:
    return f'<div class="metric"><strong>{html.escape(str(value))}</strong><span>{html.escape(label)}</span></div>'


def score_level(value: object, score_type: str, lang: str) -> str:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0
    if score_type == "heat":
        levels = ((70, "高信号" if lang == "zh-CN" else "strong signal"),
                  (40, "中等信号" if lang == "zh-CN" else "moderate signal"),
                  (0, "弱信号" if lang == "zh-CN" else "weak signal"))
    else:
        levels = ((75, "证据充分" if lang == "zh-CN" else "well supported"),
                  (55, "可供参考" if lang == "zh-CN" else "usable support"),
                  (0, "证据待补强" if lang == "zh-CN" else "needs stronger evidence"))
    return next(label for threshold, label in levels if score >= threshold)


def confidence_audit(topic: dict, lang: str) -> str:
    reason = topic.get("confidence_cap_reason", "none")
    if reason == "none":
        return ""
    reason_labels = {
        "sampling_contract_incomplete": "分层采样尚未完整" if lang == "zh-CN" else "layered sampling is incomplete",
        "sampling_untracked": "采样过程未被完整记录" if lang == "zh-CN" else "sampling was not fully tracked",
        "cluster_audit_incomplete": "话题聚类审查尚未完成" if lang == "zh-CN" else "topic clustering review is incomplete",
    }
    reason_text = reason_labels.get(str(reason), "证据条件尚未全部满足" if lang == "zh-CN" else "the evidence conditions are not fully met")
    raw = topic.get("raw_evidence_confidence", topic.get("evidence_confidence", 0))
    shown = topic.get("evidence_confidence", topic.get("confidence_cap", 0))
    if lang == "zh-CN":
        return f"评分审计：证据质量计算值为 {raw}；由于{reason_text}，以 {shown} 进入证据支撑等级。"
    return f"Scoring audit: the evidence-quality calculation is {raw}; because {reason_text}, {shown} is used for the evidence-support grade."


def refs_html(refs: list[str], evidence_label: str = "Evidence", none_label: str = "None listed") -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        text = str(ref).strip()
        match = __import__("re").search(r"/status/(\d+)", text)
        key = f"status:{match.group(1)}" if match else text.rstrip("/").casefold()
        if text and key not in seen:
            seen.add(key)
            unique.append(text)
    if not unique:
        return f'<span class="muted">{html.escape(none_label)}</span>'
    return "".join(f'<a href="{html.escape(ref, quote=True)}" target="_blank" rel="noreferrer">{html.escape(evidence_label)} {index + 1}</a>' for index, ref in enumerate(unique))


def html_labels(subject: dict) -> tuple[str, dict[str, str]]:
    profile = communication_profile(subject)
    if profile["language"] == "en":
        return "en", {
            "snapshot": "Single-platform signal snapshot", "collection_mode": "collection mode", "contract_status": "contract status",
            "topics": "topics", "opportunities": "opportunities", "ledger": "Collection ledger", "collected": "What was actually collected",
            "queries": "queries", "observed": "observed", "retained": "retained", "unique": "unique", "details": "details", "counters": "counters",
            "platform_evidence": "Platform evidence", "top_topics": "Top topics", "view_topics": "View all topics", "primary": "Show primary view",
            "topic_subject": "Topic × research subject", "opportunity_cards": "Opportunity cards", "view_opportunities": "View all opportunities",
            "boundaries": "Decision boundaries", "limitations": "What limits this conclusion", "limitation_intro": "Only decision-relevant summaries are shown here. Per-signal audit notes remain in the machine-readable result.", "monitoring_eyebrow": "Follow-up monitoring", "monitoring_title": "Turn this snapshot into a trend", "monitoring_cadence": "Suggested cadence", "monitoring_details": "Reusable scheduled-task instructions", "machine": "Machine-readable result", "heat": "observed heat", "confidence": "evidence support",
            "signals": "signals", "authors": "independent authors", "direct": "direct sources", "search_cards": "search cards", "counter_count": "counters",
            "who": "Who", "task_gap": "Task gap", "entry": "Entry", "next": "Next validation", "evidence_gates": "Evidence, objections and gates",
            "support": "Support", "counter": "Counter", "failed": "Failed gates", "none": "none", "none_listed": "None listed", "evidence": "Evidence",
            "decision_eyebrow": "Decision first", "decision_title": "What this study can help you decide", "useful_now": "Useful now", "not_for": "Do not conclude yet", "resolution": "Recommended next step",
            "score_details": "How to read the scores", "score_guide": "Observed heat grades the visible platform signal. Evidence support grades how well the current material supports that signal level. Neither is a prediction.",
        }
    return "zh-CN", {
        "snapshot": "单平台信号快照", "collection_mode": "采集模式", "contract_status": "合同状态",
        "topics": "话题", "opportunities": "机会", "ledger": "采集台账", "collected": "实际采集情况",
        "queries": "查询", "observed": "观察结果", "retained": "筛选保留", "unique": "去重信号", "details": "详情页", "counters": "反证",
        "platform_evidence": "平台证据", "top_topics": "重点话题", "view_topics": "查看全部话题", "primary": "返回首屏",
        "topic_subject": "话题 × 研究主题", "opportunity_cards": "机会卡片", "view_opportunities": "查看全部机会",
        "boundaries": "决策边界", "limitations": "影响结论的主要限制", "limitation_intro": "这里只展示影响判断的汇总；逐条证据审计保留在机器可读结果中。", "monitoring_eyebrow": "后续监测", "monitoring_title": "把这次快照变成趋势", "monitoring_cadence": "建议频率", "monitoring_details": "可复用的定时任务说明", "machine": "机器可读结果", "heat": "观察热度", "confidence": "证据支撑",
        "signals": "信号", "authors": "独立作者", "direct": "详情直证", "search_cards": "搜索卡片", "counter_count": "反证",
        "who": "适用对象", "task_gap": "任务缺口", "entry": "切入方式", "next": "下一步验证", "evidence_gates": "证据、反对意见与门槛",
        "support": "支持证据", "counter": "反证审查", "failed": "仍需满足", "none": "无", "none_listed": "未列出", "evidence": "证据",
        "decision_eyebrow": "先说结论", "decision_title": "这次研究现在能帮你做什么决定", "useful_now": "现在可以用于", "not_for": "暂时不要据此判断", "resolution": "建议的解决路径",
        "score_details": "评分怎么看", "score_guide": "观察热度用于给平台上的可见信号分级；证据支撑用于说明现有材料能否支撑这一分级。两者都不是趋势预测。",
    }


def render_html(result: dict) -> str:
    subject = result["subject"]
    lang, label = html_labels(subject)
    collection = result.get("collection", {})
    counts = collection.get("counts", {})
    topics = result.get("topics", [])
    opportunities = result.get("opportunities", [])
    is_zh = lang == "zh-CN"
    decision = result.get("decision_support") or build_decision_support(subject, collection, topics, opportunities, lang)
    topic_cards = []
    for index, topic in enumerate(topics):
        topic_title = ((topic.get("cluster_audit") or {}).get("title") if is_zh else "") or topic.get("title", "Untitled topic")
        heat_score = topic.get('observed_heat', 0)
        confidence_score = topic.get('evidence_confidence', 0)
        audit_note = confidence_audit(topic, lang)
        topic_cards.append(f'''<article class="topic-card {'extra' if index >= 3 else ''}">
          <div class="eyebrow">{html.escape(display_value(topic.get('status', 'snapshot'), lang, 'topic_status'))}</div>
          <h3>{html.escape(str(topic_title))}</h3>
          <div class="metrics">{pill(f'{heat_score}/100', f'{label["heat"]} · {score_level(heat_score, "heat", lang)}')}{pill(f'{confidence_score}/100', f'{label["confidence"]} · {score_level(confidence_score, "confidence", lang)}')}{pill(topic.get('sample_count', 0), label['signals'])}</div>
          <p class="muted">{topic.get('unique_author_count', 0)} {label['authors']} · {topic.get('direct_source_count', 0)} {label['direct']} · {topic.get('search_card_count', 0)} {label['search_cards']} · {topic.get('counter_signal_count', 0)} {label['counter_count']}</p>
          <details class="score-details"><summary>{label['score_details']}</summary><p class="muted">{label['score_guide']}</p>{f'<p class="muted">{html.escape(audit_note)}</p>' if audit_note else ''}</details>
          <div class="links">{refs_html(topic.get('evidence_refs', [])[:4], label['evidence'], label['none_listed'])}</div>
        </article>''')
    opportunity_cards = []
    for index, item in enumerate(opportunities):
        status = item.get("evidence_status", "candidate")
        failed_gates = display_list(item.get("failed_gates", []), lang, "gate") or label["none"]
        opportunity_cards.append(f'''<article class="opportunity-card {'extra' if index >= 1 else ''}">
          <div class="row"><span class="status {status}">{html.escape(display_value(status, lang, 'opportunity_status'))}</span></div>
          <h3>{html.escape(str(item.get('reader_title') or item.get('title', 'Untitled opportunity')))}</h3>
          <dl><dt>{label['who']}</dt><dd>{html.escape(str(item.get('audience', '')))}</dd><dt>{label['task_gap']}</dt><dd>{html.escape(str(item.get('task_gap', '')))}</dd><dt>{label['entry']}</dt><dd>{html.escape(str(item.get('subject_entry', '')))}</dd><dt>{label['next']}</dt><dd>{html.escape(str(item.get('expected_action', '')))}</dd></dl>
          <details><summary>{label['evidence_gates']}</summary><p><b>{label['support']}</b></p><div class="links">{refs_html(item.get('support_refs', []), label['evidence'], label['none_listed'])}</div><p><b>{label['counter']}</b> {html.escape(str(item.get('counter_review', '')))}</p><div class="links">{refs_html(item.get('counter_refs', []), label['evidence'], label['none_listed'])}</div><p><b>{label['failed']}</b> {html.escape(failed_gates)}</p></details>
        </article>''')
    limitation_summary = result.get("limitation_summary") or summarize_limitations(result.get("limitations", []), lang)
    limitations = "".join(f"<li>{html.escape(str(item))}</li>" for item in limitation_summary) or f"<li>{html.escape(label['none'])}</li>"
    monitoring = result.get("monitoring_recommendation") or {}
    monitoring_section = ""
    if monitoring.get("recommended"):
        cadence = monitoring.get("cadence") or {}
        monitoring_section = f'''<section data-monitoring-recommendation><div class="section-head"><div><div class="eyebrow">{label['monitoring_eyebrow']}</div><h2>{label['monitoring_title']}</h2></div></div><div class="panel monitoring"><div><span class="status review_ready">{label['monitoring_cadence']}</span><strong>{html.escape(str(cadence.get('label', '')))}</strong><p class="muted">{html.escape(str(monitoring.get('reason', '')))}</p></div><details><summary>{label['monitoring_details']}</summary><p class="task-prompt">{html.escape(str(monitoring.get('automation_prompt', '')))}</p></details></div></section>'''
    layer_rows = "".join(
        f"<tr><td>{html.escape(display_value(layer, lang, 'layer'))}</td><td>{stats.get('query_count', 0)}</td><td>{stats.get('observed_result_count', 0)}</td><td>{stats.get('unique_signal_count', 0)}</td><td>{stats.get('detail_open_count', 0)}</td><td>{stats.get('direct_relevance_count', 0)}</td></tr>"
        for layer, stats in (collection.get("layer_stats") or {}).items()
    )
    decision_section = f'''<section data-decision-support><div class="section-head"><div><div class="eyebrow">{label['decision_eyebrow']}</div><h2>{label['decision_title']}</h2></div></div><div class="panel decision-panel"><p class="decision-headline">{html.escape(str(decision.get('headline', '')))}</p><div class="decision-grid"><div><b>{label['useful_now']}</b><span>{html.escape(str(decision.get('useful_now', '')))}</span></div><div><b>{label['not_for']}</b><span>{html.escape(str(decision.get('boundary', '')))}</span></div><div><b>{label['resolution']}</b><span>{html.escape(str(decision.get('resolution', '')))}</span></div></div></div></section>'''
    readiness = f'''<section><div class="panel readiness"><h2>{'如何使用这份结果' if is_zh else 'How to use this result'}</h2><div class="readiness-grid">
      <div><b>{'采样覆盖' if is_zh else 'Sampling coverage'}</b><span>{html.escape(display_value(collection.get('contract_status', 'untracked'), lang, 'contract'))}</span></div>
      <div><b>{'话题证据' if is_zh else 'Topic evidence'}</b><span>{sum(1 for topic in topics if topic.get('evidence_confidence', 0) >= 55)} / {len(topics)} {'达到审核线' if is_zh else 'above threshold'}</span></div>
      <div><b>{'趋势方向' if is_zh else 'Trend direction'}</b><span>{'单次快照无法判断' if is_zh else 'Unavailable from a single snapshot'}</span></div>
      <div><b>{'商业验证' if is_zh else 'Commercial validation'}</b><span>{'尚未开始，除非另有数据' if is_zh else 'Not started unless separately supplied'}</span></div>
    </div></div></section>'''
    layer_table = f'''<section><div class="section-head"><div><div class="eyebrow">{'分层质量' if is_zh else 'Layer quality'}</div><h2>{'各层采集情况' if is_zh else 'Per-layer collection health'}</h2></div></div><div class="panel table-wrap"><table><thead><tr><th>{'层级' if is_zh else 'Layer'}</th><th>{'查询' if is_zh else 'Queries'}</th><th>{'观察结果' if is_zh else 'Observed'}</th><th>{'去重信号' if is_zh else 'Unique'}</th><th>{'详情页' if is_zh else 'Details'}</th><th>{'直接相关' if is_zh else 'Direct relevance'}</th></tr></thead><tbody>{layer_rows}</tbody></table></div></section>''' if layer_rows else ""
    audit_section = f'''<section data-research-audit><details class="panel audit-details"><summary>{'查看采样与评分依据' if is_zh else 'View sampling and scoring audit'}</summary><p class="muted">{'这里保留采集数量、分层覆盖和评分依据，供复核时查看。' if is_zh else 'Collection volume, layer coverage, and scoring evidence are retained here for audit.'}</p><div class="contract"><div><strong>{counts.get('query_count', 0)}</strong>{label['queries']}</div><div><strong>{counts.get('observed_result_count', '—')}</strong>{label['observed']}</div><div><strong>{counts.get('retained_sample_count', 0)}</strong>{label['retained']}</div><div><strong>{counts.get('unique_sample_count', 0)}</strong>{label['unique']}</div><div><strong>{counts.get('detail_open_count', 0)}</strong>{label['details']}</div><div><strong>{counts.get('counter_signal_count', 0)}</strong>{label['counters']}</div></div>{layer_table}</details></section>'''
    payload = html.escape(json.dumps(result, ensure_ascii=False), quote=False)
    return f'''<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(subject_name(subject))} · {label['snapshot']}</title>
<style>
:root{{--bg:#f4f5f7;--panel:#fff;--ink:#17202a;--muted:#667085;--line:#e5e7eb;--accent:#5b5bd6;--soft:#eeeeff;--good:#13795b;--warn:#b54708}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}main{{max-width:1240px;margin:auto;padding:34px 24px 64px}}header{{background:linear-gradient(135deg,#171a2b,#34346f);color:#fff;border-radius:24px;padding:32px;box-shadow:0 18px 50px #24245b24}}.eyebrow{{font-size:11px;text-transform:uppercase;letter-spacing:.12em;color:#8b8fa3}}header .eyebrow{{color:#c9c9ff}}h1{{font-size:clamp(28px,5vw,48px);line-height:1.08;margin:8px 0 12px;max-width:850px}}header p{{max-width:820px;color:#e2e3ef}}.metrics{{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}}.metric{{min-width:98px;padding:12px 14px;background:#ffffff10;border:1px solid #ffffff20;border-radius:14px}}.metric strong{{display:block;font-size:22px}}.metric span{{font-size:11px;color:#cfd1df}}section{{margin-top:28px}}.section-head{{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:12px}}h2{{font-size:20px;margin:0}}button{{border:1px solid var(--line);background:#fff;padding:9px 13px;border-radius:10px;cursor:pointer;color:var(--ink)}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}}.opportunity-grid{{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1.6fr);gap:14px}}article,.panel{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:20px;box-shadow:0 5px 18px #1018280a}}article h3{{font-size:18px;line-height:1.35;margin:7px 0 14px}}article .metric{{background:#f8f8fb;border-color:#ececf3}}article .metric span{{color:var(--muted)}}.bar{{height:7px;background:#eceef2;border-radius:99px;overflow:hidden;margin-top:15px}}.bar i{{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#8f72ff)}}.muted{{color:var(--muted)}}.warning{{background:#fff7ed;color:#9a3412;border-radius:10px;padding:9px 10px}}.links{{display:flex;gap:8px;flex-wrap:wrap}}.links a{{color:#4848bd;background:var(--soft);padding:5px 8px;border-radius:8px;text-decoration:none}}.row{{display:flex;justify-content:space-between;align-items:center;gap:10px}}.status{{font-size:11px;font-weight:700;padding:5px 8px;border-radius:99px;background:#fff1e8;color:var(--warn)}}.status.review_ready{{background:#e8f7f1;color:var(--good)}}dl{{display:grid;grid-template-columns:110px 1fr;gap:9px 12px}}dt{{color:var(--muted)}}dd{{margin:0}}details{{border-top:1px solid var(--line);margin-top:16px;padding-top:12px}}summary{{cursor:pointer;font-weight:600}}.contract{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}.contract div{{background:#f8f8fb;border-radius:12px;padding:12px}}.contract strong{{display:block;font-size:18px}}.extra{{display:none}}body.show-all .extra{{display:block}}#raw{{white-space:pre-wrap;max-height:460px;overflow:auto;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace}}@media(max-width:900px){{.grid,.opportunity-grid{{grid-template-columns:1fr}}.contract{{grid-template-columns:repeat(2,1fr)}}}}@media print{{body{{background:#fff}}button{{display:none}}main{{padding:0}}header{{box-shadow:none}}.extra{{display:block}}}}
</style><style>.decision-headline{{font-size:20px;line-height:1.5;margin:0 0 16px;max-width:920px}}.decision-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}.decision-grid div,.readiness-grid div{{background:#f8f8fb;border-radius:12px;padding:12px}}.decision-grid span,.readiness-grid span{{display:block;color:var(--muted);margin-top:5px}}.readiness-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;text-align:left;border-bottom:1px solid var(--line)}}.monitoring{{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:18px;align-items:start}}.monitoring strong{{display:block;font-size:18px;margin-top:10px}}.monitoring details{{margin-top:0}}.task-prompt{{background:#f8f8fb;border-radius:12px;padding:12px;margin-bottom:0}}@media(max-width:900px){{.decision-grid{{grid-template-columns:1fr}}.readiness-grid{{grid-template-columns:1fr 1fr}}.monitoring{{grid-template-columns:1fr}}}}</style></head><body><main>
<header><div class="eyebrow">{label['snapshot']} · {html.escape(str(result.get('platform', 'unspecified')))}</div><h1>{html.escape(subject_name(subject))}</h1><p>{html.escape(str(subject.get('summary', '')))}</p><div class="metrics">{pill(display_value(collection.get('mode', 'untracked'), lang, 'mode'), label['collection_mode'])}{pill(display_value(collection.get('contract_status', 'untracked'), lang, 'contract'), '证据状态' if is_zh else label['contract_status'])}{pill(len(topics), label['topics'])}{pill(len(opportunities), label['opportunities'])}</div></header>
{decision_section}
<section><div class="section-head"><div><div class="eyebrow">{label['topic_subject']}</div><h2>{label['opportunity_cards']}</h2></div><button data-toggle data-all="{label['view_opportunities']}" data-primary="{label['primary']}">{label['view_opportunities']}</button></div><div class="opportunity-grid">{''.join(opportunity_cards) or f'<div class="panel muted">{label["none"]}</div>'}</div></section>
<section><div class="section-head"><div><div class="eyebrow">{label['platform_evidence']}</div><h2>{label['top_topics']}</h2></div><button data-toggle data-all="{label['view_topics']}" data-primary="{label['primary']}">{label['view_topics']}</button></div><div class="grid">{''.join(topic_cards) or f'<div class="panel muted">{label["none"]}</div>'}</div></section>
{monitoring_section}
<section data-decision-boundaries><div class="section-head"><div><div class="eyebrow">{label['boundaries']}</div><h2>{label['limitations']}</h2></div></div><div class="panel"><p class="muted">{label['limitation_intro']}</p><ul class="summary-list">{limitations}</ul></div></section>
{audit_section}
<section><details class="panel"><summary>{label['machine']}</summary><pre id="raw">{payload}</pre></details></section>
</main><script>document.querySelectorAll('[data-toggle]').forEach(b=>b.addEventListener('click',()=>{{document.body.classList.toggle('show-all');document.querySelectorAll('[data-toggle]').forEach(x=>x.textContent=document.body.classList.contains('show-all')?x.dataset.primary:x.dataset.all)}}));</script></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate opportunity evidence gates and render standalone reports.")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--signals", required=True)
    parser.add_argument("--opportunities")
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--html-output")
    args = parser.parse_args()
    subject = load_data(args.subject)
    require_text_integrity(subject, "Subject")
    subject_errors = validate_subject(subject)
    if subject_errors:
        raise SystemExit("Subject validation failed:\n- " + "\n- ".join(subject_errors))
    snapshot = load_data(args.signals)
    require_text_integrity(snapshot, "Signals")
    if (snapshot.get("collection") or {}).get("contract_status") == "in_progress":
        raise SystemExit("Collection is still in_progress. Finalize the orchestrator as complete or blocked before generating a report.")
    supplied = load_data(args.opportunities) if args.opportunities else []
    require_text_integrity(supplied, "Opportunities")
    if isinstance(supplied, dict):
        supplied = supplied.get("opportunities", [])
    mode = (snapshot.get("collection") or {}).get("mode", "quick")
    maximum = SAMPLING_CONTRACTS.get(mode, SAMPLING_CONTRACTS["quick"])["opportunity_target"][1]
    all_topics = snapshot.get("topics", [])
    topics = [topic for topic in all_topics if topic_is_eligible(topic, mode)]
    excluded_topics = [
        {**topic, "exclusion_reason": "unreviewed_or_cluster_audit_missing_or_failed"}
        for topic in all_topics if not topic_is_eligible(topic, mode)
    ]
    topics_by_key = {topic.get("topic_key"): topic for topic in topics}
    proposed = supplied or [fallback_opportunity(topic, subject) for topic in topics[:maximum]]
    opportunities: list[dict] = []
    excluded_opportunities: list[dict] = []
    used_topic_keys: set[str] = set()
    profile = communication_profile(subject)
    for item in proposed:
        topic_key = item.get("topic_key")
        if topic_key not in topics_by_key:
            excluded_opportunities.append({**item, "exclusion_reason": "topic_not_eligible"})
            continue
        if topic_key in used_topic_keys:
            excluded_opportunities.append({**item, "exclusion_reason": "one_primary_opportunity_per_topic"})
            continue
        used_topic_keys.add(topic_key)
        gates, failed = opportunity_gates(
            item,
            topics_by_key.get(topic_key),
            (snapshot.get("collection") or {}).get("contract_status", "untracked"),
        )
        item["gates"] = gates
        item["failed_gates"] = failed
        display_title, jargon = reader_title(item, profile)
        item["reader_title"] = display_title
        item["title_readability"] = {"status": "rewritten" if jargon else "passed", "replaced_terms": jargon}
        if item.get("evidence_status") == "confirmed" and item.get("human_confirmation"):
            opportunities.append(item)
            continue
        item["evidence_status"] = "review_ready" if not failed else "candidate"
        opportunities.append(item)
    limitations = list(dict.fromkeys(
        [limit for signal in snapshot.get("signals", []) for limit in signal.get("limitations", [])]
        + (snapshot.get("collection", {}).get("limitations", []))
    ))
    report_lang, _ = html_labels(subject)
    monitoring_recommendation = build_monitoring_recommendation(subject, snapshot.get("platform"), report_lang)
    decision_support = build_decision_support(subject, snapshot.get("collection", {}), topics, opportunities, report_lang)
    result = {
        "schema_version": "trend-opportunity-report-v0.3",
        "generated_at": now_iso(),
        "subject": subject,
        "platform": snapshot.get("platform"),
        "collection": snapshot.get("collection", {}),
        "topics": topics,
        "excluded_topics": excluded_topics,
        "opportunities": opportunities,
        "excluded_opportunities": excluded_opportunities,
        "limitations": limitations,
        "limitation_summary": summarize_limitations(limitations, report_lang),
        "monitoring_recommendation": monitoring_recommendation,
        "communication": communication_profile(subject),
        "decision_support": decision_support,
    }
    require_text_integrity(result, "Generated report")
    markdown = render_markdown(result)
    page = render_html(result) if args.html_output else ""
    validate_report_contents(result, markdown, page or None)
    write_json(args.json_output, result)
    markdown_target = Path(args.markdown_output)
    markdown_target.parent.mkdir(parents=True, exist_ok=True)
    markdown_target.write_text(markdown, encoding="utf-8")
    if args.html_output:
        html_target = Path(args.html_output)
        html_target.parent.mkdir(parents=True, exist_ok=True)
        html_target.write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
