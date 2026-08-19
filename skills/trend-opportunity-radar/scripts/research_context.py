from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from _common import as_text
from decision_profiles import get_profile
from platform_adapter_contract import normalize_platform


SCHEMA_VERSION = "research-context-v0.1"
LANGUAGE_ZH = re.compile(r"[\u3400-\u9fff]")

INTENT_PATTERNS = [
    ("competitor_users", [r"竞品用户", r"切换原因", r"切换触发", r"switching triggers?", r"competitor users?", r"\bversus\b.*\busers?\b", r"用户分别喜欢和抱怨"]),
    ("brand_sentiment", [r"品牌舆情", r"监测.*舆情", r"\bsentiment\b", r"需要.*回应", r"负面问题", r"怎么评价.*扩大"]),
    ("content_opportunity", [r"内容机会", r"content opportunities?", r"值得持续做内容", r"哪些问题值得.*内容"]),
    ("product_demand", [r"产品需求", r"validate demand", r"验证.*需求", r"采用阻力", r"adoption barriers?", r"workarounds?.*adoption"]),
    ("business_opportunity", [r"商业机会", r"business opportunities?", r"值得验证的生意", r"趋势机会", r"trend opportunities?"])
]
PLATFORM_PATTERNS = [
    ("xiaohongshu", [r"小红书", r"\bxiaohongshu\b", r"\bxhs\b"]),
    ("reddit", [r"\breddit\b", r"红迪"]),
    ("youtube", [r"\byoutube\b", r"油管"]),
    ("tiktok", [r"\btik[ -]?tok\b", r"国际抖音"]),
    ("douyin", [r"抖音", r"\bdouyin\b"]),
    ("instagram", [r"\binstagram\b", r"(?:^|[，。；、,.!?\s])ins(?:平台|$|[，。；、,.!?\s])"]),
    ("x", [r"(?:^|[，。；、,.!?\s])x(?:上|平台|英语市场|$|[，。；、,.!?\s])", r"\bon\s+x\b", r"\btwitter\b"]),
]
MARKET_PATTERNS = [
    ("英语市场", [r"英语市场", r"英文市场", r"english[- ]speaking market", r"english market"]),
    ("中国市场", [r"中国市场", r"china market", r"mainland china"]),
    ("全球市场", [r"全球市场", r"global market", r"worldwide"]),
]


def infer_language(prompt: str) -> str:
    return "zh-CN" if LANGUAGE_ZH.search(prompt) else "en"


def infer_intent(prompt: str) -> str | None:
    lowered = prompt.casefold()
    for intent, patterns in INTENT_PATTERNS:
        if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns):
            return intent
    return None


def infer_platform(prompt: str) -> str | None:
    lowered = prompt.casefold()
    matches = [platform for platform, patterns in PLATFORM_PATTERNS if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)]
    return matches[0] if len(set(matches)) == 1 else None


def infer_market(prompt: str) -> str | None:
    lowered = prompt.casefold()
    matches = [market for market, patterns in MARKET_PATTERNS if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)]
    return matches[0] if len(set(matches)) == 1 else None


def subject_name(prompt: str) -> str:
    value = re.sub(r"^(使用\s+trend-opportunity-radar[，,]?\s*|use\s+trend-opportunity-radar\s+to\s+)", "", prompt.strip(), flags=re.IGNORECASE)
    return value[:240]


def clarification_question(language: str, missing: list[str]) -> str:
    if language == "zh-CN":
        if set(missing) == {"research_intent", "platform"}:
            return "你希望在哪个平台研究，并用结果支持哪一种决策？"
        if "platform" in missing:
            return "你希望研究哪个平台？"
        return "你希望这次研究用于发现商业机会、监测品牌舆情、研究竞品用户、寻找内容机会，还是验证产品需求？"
    if set(missing) == {"research_intent", "platform"}:
        return "Which platform and business decision should this research support?"
    if "platform" in missing:
        return "Which platform should this research analyze?"
    return "Should this research find business opportunities, monitor brand sentiment, study competitor users, find content opportunities, or validate product demand?"


def compile_context(prompt: str, *, intent: str = "", platform: str = "", subject: dict[str, Any] | None = None, language: str = "") -> dict[str, Any]:
    prompt = as_text(prompt)
    if not prompt:
        raise ValueError("A non-empty source prompt is required.")
    resolved_language = language or infer_language(prompt)
    resolved_intent = intent or infer_intent(prompt)
    resolved_platform = normalize_platform(platform) if platform else infer_platform(prompt)
    missing = [name for name, value in (("research_intent", resolved_intent), ("platform", resolved_platform)) if not value]
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if missing:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "clarification_required",
            "missing": missing,
            "clarification_question": clarification_question(resolved_language, missing),
            "source_prompt_sha256": digest,
            "language": resolved_language,
        }
    profile = get_profile(resolved_intent)
    questions = profile["decision_question"]
    subject_payload = subject if isinstance(subject, dict) else {"name": subject_name(prompt), "subject_type": "idea", "summary": subject_name(prompt)}
    assumptions = []
    if not language:
        assumptions.append(f"Output language inferred as {resolved_language} from the request.")
    if not intent and resolved_intent == "business_opportunity" and re.search(r"趋势机会|trend opportunities?", prompt, re.IGNORECASE):
        assumptions.append("Legacy trend-opportunity phrasing defaults to business opportunity research.")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "research_intent": resolved_intent,
        "profile_version": profile["version"],
        "profile_implementation_status": profile["implementation_status"],
        "subject": subject_payload,
        "platform": resolved_platform,
        "market": infer_market(prompt),
        "language": resolved_language,
        "audience": None,
        "decision_question": questions.get(resolved_language) or questions["en"],
        "analysis_unit": profile["analysis_unit"],
        "evidence_roles": profile["evidence_roles"],
        "counterevidence_targets": profile["counterevidence_targets"],
        "query_profile": profile["query_profile"],
        "query_intents": profile["query_intents"],
        "decision_thresholds": profile["decision_thresholds"],
        "action_contract": profile["action_contract"],
        "report_profile": profile["report_profile"],
        "report_sections": profile["report_sections"],
        **({"temporal_contract": profile["temporal_contract"]} if profile.get("temporal_contract") else {}),
        "assumptions": assumptions,
        "source_prompt_sha256": digest,
    }


def validate_context(context: Any, require_ready: bool = True) -> None:
    if not isinstance(context, dict) or context.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Research context must use {SCHEMA_VERSION}.")
    if require_ready and context.get("status") != "ready":
        raise ValueError("Research context is not ready; resolve its clarification first.")
    if context.get("status") == "ready":
        required = {"research_intent", "profile_version", "subject", "platform", "language", "decision_question", "analysis_unit", "evidence_roles", "counterevidence_targets", "query_profile", "query_intents", "decision_thresholds", "action_contract", "report_profile", "report_sections", "assumptions", "source_prompt_sha256"}
        missing = sorted(field for field in required if field not in context or context[field] in (None, ""))
        if missing:
            raise ValueError("Research context is incomplete: " + ", ".join(missing))
        profile = get_profile(context["research_intent"])
        if context["profile_version"] != profile["version"]:
            raise ValueError("Research context profile version does not match the registry.")


def load_context(path: Path, require_ready: bool = True) -> dict[str, Any]:
    context = json.loads(path.read_text(encoding="utf-8"))
    validate_context(context, require_ready=require_ready)
    return context
