from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from _common import load_data, now_iso, write_json
from research_context import compile_context, validate_context
from select_collection_adapter import select_adapter
from validate_subject import validate_subject


SCHEMA_VERSION = "trend-radar-run-v0.1"
DOCTOR_SCHEMA_VERSION = "trend-radar-doctor-v0.1"
MODES = {"quick", "standard", "deep"}


def _language_text(language: str, zh: str, en: str) -> str:
    return zh if language == "zh-CN" else en


def _status_summaries(statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return capability facts without leaking local paths or raw diagnostics."""
    summaries: list[dict[str, Any]] = []
    for status in statuses:
        if not isinstance(status, dict):
            continue
        raw_capabilities = status.get("capabilities") if isinstance(status.get("capabilities"), dict) else {}
        capabilities = {
            str(key): value
            for key, value in raw_capabilities.items()
            if isinstance(value, bool)
        }
        summaries.append({
            "adapter": str(status.get("adapter") or "unknown"),
            "ready": status.get("ready") is True and status.get("status") == "ready",
            "status": str(status.get("status") or "unknown"),
            "capabilities": capabilities,
            "checked_at": status.get("checked_at"),
        })
    return summaries


def _prerequisites(platform: str, state: str, language: str) -> dict[str, Any]:
    """Show setup guidance only when the current live route actually needs user action."""
    platform_name = {
        "x": "X", "xiaohongshu": "小红书", "youtube": "YouTube",
        "tiktok": "TikTok", "instagram": "Instagram", "facebook": "Facebook",
        "reddit": "Reddit",
    }.get(platform, platform)
    if state not in {"preflight_required", "live_unavailable_import_ready"}:
        return {"required": False, "items": [], "message": ""}
    if platform == "reddit":
        items = ["connect_read_only_service", "authorize_platform_read"]
        zh = f"开始实时采集前，请连接可读取 {platform_name} 的服务并完成只读授权。系统会再次验证；请勿发送密码、Cookie 或 Token。"
        en = f"Before live collection, connect a service that can read {platform_name} and grant read-only access. The system will verify it again; never send passwords, cookies, or tokens."
    else:
        items = ["start_supported_browser", "sign_in_to_platform", "connect_read_adapter"]
        zh = f"开始实时采集前，请启动 Chrome 或适配器明确支持的浏览器，在 {platform_name} 完成登录，并确保只读采集连接已启用。系统会自动复检；请勿发送密码、Cookie 或 Token。"
        en = f"Before live collection, start Chrome or the browser supported by the adapter, sign in to {platform_name}, and enable the read-only collection connection. The system will verify it automatically; never send passwords, cookies, or tokens."
    return {"required": True, "items": items, "message": _language_text(language, zh, en)}


def build_doctor_report(
    platform: str,
    statuses: list[dict[str, Any]],
    *,
    research_scope: str = "topic_research",
    allow_pilot: bool = False,
    language: str = "en",
) -> dict[str, Any]:
    selection = select_adapter(platform, statuses, research_scope, allow_pilot)
    release_status = str(selection.get("release_status") or "unsupported")
    live_ready = bool(selection.get("ready"))
    import_ready = True

    if live_ready:
        state = "ready_live"
        action = _language_text(
            language,
            "读取环境已就绪，可以生成三层查询并开始有界采集。",
            "The read-only environment is ready; generate the three query layers and begin bounded collection.",
        )
    elif release_status == "pilot" and not allow_pilot:
        state = "pilot_opt_in_required"
        action = _language_text(
            language,
            "该平台当前属于 Beta/试点。获得用户明确同意后，用 --allow-pilot 重新诊断；也可以导入合规数据。",
            "This platform is currently Beta/pilot. After explicit user opt-in, rerun with --allow-pilot; a compliant data import is also available.",
        )
    elif release_status in {"validated", "pilot"} and not statuses:
        state = "preflight_required"
        action = _language_text(
            language,
            "先执行该平台实际读取能力的只读预检，再把状态文件交给 doctor；不要仅凭 CLI 路径或浏览器外观判断。",
            "Run the platform's actual read-only capability preflight, then pass its status file to doctor; do not infer readiness from a CLI path or browser appearance.",
        )
    elif release_status in {"validated", "pilot"}:
        state = "live_unavailable_import_ready"
        action = _language_text(
            language,
            "本次实时读取尚未通过预检。修复状态文件中对应的登录或连接问题，或改用合规结构化数据导入。",
            "Live reading did not pass this run's preflight. Resolve the reported login or connection issue, or use a compliant structured import.",
        )
    else:
        state = "import_only"
        action = _language_text(
            language,
            "当前范围没有已发布的实时适配器；使用合规结构化数据导入继续同一研究流程。",
            "No released live adapter exists for this scope; continue with a compliant structured import.",
        )

    prerequisites = _prerequisites(str(selection.get("platform") or platform), state, language)
    return {
        "schema_version": DOCTOR_SCHEMA_VERSION,
        "platform": selection.get("platform"),
        "research_scope": research_scope,
        "release_status": release_status,
        "state": state,
        "live": {
            "ready": live_ready,
            "search_adapter": selection.get("selected_adapter") or None,
            "detail_adapter": selection.get("detail_adapter") or None,
            "detail_ready": bool(selection.get("detail_ready")),
        },
        "structured_import": {
            "ready": import_ready,
            "source_mode": "customer_export",
        },
        "checked_adapters": _status_summaries(statuses),
        "prerequisites": prerequisites,
        "next_action": action,
        "checked_at": now_iso(),
    }


def _subject_from_context(context: dict[str, Any]) -> dict[str, Any]:
    source = context.get("subject") if isinstance(context.get("subject"), dict) else {}
    subject_type = str(source.get("subject_type") or "idea")
    if subject_type not in {"product", "opportunity", "idea", "problem", "project"}:
        subject_type = "idea"
    return {
        "name": str(source.get("name") or "").strip(),
        "subject_type": subject_type,
        "summary": str(source.get("summary") or source.get("name") or "").strip(),
        "facts": source.get("facts") if isinstance(source.get("facts"), list) else [],
        "hypotheses": source.get("hypotheses") if isinstance(source.get("hypotheses"), list) else [],
        "audiences": source.get("audiences") if isinstance(source.get("audiences"), list) else [],
        "scenarios": source.get("scenarios") if isinstance(source.get("scenarios"), list) else [],
        "constraints": source.get("constraints") if isinstance(source.get("constraints"), list) else [],
        "source_refs": source.get("source_refs") if isinstance(source.get("source_refs"), list) else [],
        "communication": {
            "language": context.get("language") or "auto",
            "goal": {
                "business_opportunity": "validate_business_opportunity",
                "product_demand": "validate_product_demand",
                "content_opportunity": "discover_content_opportunities",
            }.get(str(context.get("research_intent")), "general_research"),
            "audience": "general",
        },
    }


def _load_statuses(paths: list[str]) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for value in paths:
        loaded = load_data(Path(value))
        if not isinstance(loaded, dict):
            raise ValueError(f"Adapter status must be a JSON object: {value}")
        statuses.append(loaded)
    return statuses


def _request_digest(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def start_run(args: argparse.Namespace) -> dict[str, Any]:
    if args.mode not in MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(MODES))}")
    output_dir = Path(args.output_dir).resolve()
    manifest_path = output_dir / "run-manifest.json"
    digest = _request_digest(args.prompt)
    existing: dict[str, Any] | None = None
    if manifest_path.exists():
        loaded = load_data(manifest_path)
        if not isinstance(loaded, dict) or loaded.get("request_sha256") != digest:
            raise ValueError("The output directory already belongs to a different research request.")
        existing = loaded
        if existing.get("mode") != args.mode:
            raise ValueError("The sampling mode is frozen for this research run.")

    output_dir.mkdir(parents=True, exist_ok=True)
    supplied_subject = load_data(Path(args.subject)) if args.subject else None
    context = compile_context(
        args.prompt,
        intent=args.intent,
        platform=args.platform,
        subject=supplied_subject if isinstance(supplied_subject, dict) else None,
        language=args.language,
    )
    existing_context_path = output_dir / "research-context.json"
    if existing and existing.get("state") != "clarification_required" and existing_context_path.exists():
        frozen_context = load_data(existing_context_path)
        if isinstance(frozen_context, dict) and frozen_context.get("status") == "ready":
            for field in ("research_intent", "platform", "language", "profile_version", "source_prompt_sha256"):
                if context.get(field) != frozen_context.get(field):
                    raise ValueError(f"The frozen research context cannot change field: {field}")
    write_json(output_dir / "research-context.json", context)

    if context.get("status") != "ready":
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "request_sha256": digest,
            "state": "clarification_required",
            "mode": args.mode,
            "research_context": "research-context.json",
            "subject": None,
            "doctor": None,
            "next_action": context.get("clarification_question"),
            "created_at": existing.get("created_at") if existing else now_iso(),
            "updated_at": now_iso(),
        }
        write_json(manifest_path, manifest)
        return manifest

    validate_context(context, require_ready=True)
    subject = supplied_subject if isinstance(supplied_subject, dict) else _subject_from_context(context)
    subject_errors = validate_subject(subject)
    if subject_errors:
        raise ValueError("Subject validation failed: " + "; ".join(subject_errors))
    existing_subject_path = output_dir / "subject.json"
    if existing and existing.get("state") != "clarification_required" and existing_subject_path.exists():
        frozen_subject = load_data(existing_subject_path)
        if frozen_subject != subject:
            raise ValueError("The subject is frozen for this research run.")
    write_json(output_dir / "subject.json", subject)

    statuses = _load_statuses(args.status)
    doctor = build_doctor_report(
        str(context["platform"]),
        statuses,
        research_scope=args.research_scope,
        allow_pilot=args.allow_pilot,
        language=str(context.get("language") or "en"),
    )
    write_json(output_dir / "environment-doctor.json", doctor)

    if doctor["state"] == "ready_live":
        state = "query_plan_required"
        next_action = _language_text(
            str(context.get("language")),
            "依据冻结的 Decision Profile 生成平台基线、品类和主题桥接三层查询计划。",
            "Generate the platform-baseline, category, and subject-bridge query plan from the frozen Decision Profile.",
        )
    elif doctor["state"] in {"import_only", "live_unavailable_import_ready"}:
        state = "import_required"
        next_action = doctor["next_action"]
    else:
        state = doctor["state"]
        next_action = doctor["next_action"]

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "request_sha256": digest,
        "state": state,
        "mode": args.mode,
        "research_context": "research-context.json",
        "subject": "subject.json",
        "doctor": "environment-doctor.json",
        "platform": context["platform"],
        "research_intent": context["research_intent"],
        "profile_version": context["profile_version"],
        "prerequisites": doctor["prerequisites"],
        "next_action": next_action,
        "created_at": existing.get("created_at") if existing else now_iso(),
        "updated_at": now_iso(),
    }
    write_json(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Start and diagnose a Trend Opportunity Radar research run.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Report the live and import capability for one platform scope.")
    doctor.add_argument("--platform", required=True)
    doctor.add_argument("--research-scope", default="topic_research", choices=["topic_research", "account_research"])
    doctor.add_argument("--status", action="append", default=[], help="Saved adapter preflight JSON; repeat as needed.")
    doctor.add_argument("--allow-pilot", action="store_true")
    doctor.add_argument("--language", default="en", choices=["en", "zh-CN"])
    doctor.add_argument("--output")
    doctor.add_argument("--require-live", action="store_true")

    start = subparsers.add_parser("start", help="Freeze a request and return the single next workflow action.")
    start.add_argument("--prompt", required=True)
    start.add_argument("--output-dir", required=True)
    start.add_argument("--intent", default="")
    start.add_argument("--platform", default="")
    start.add_argument("--language", default="")
    start.add_argument("--subject")
    start.add_argument("--research-scope", default="topic_research", choices=["topic_research", "account_research"])
    start.add_argument("--status", action="append", default=[])
    start.add_argument("--allow-pilot", action="store_true")
    start.add_argument("--mode", default="standard", choices=sorted(MODES))

    args = parser.parse_args()
    if args.command == "doctor":
        statuses = _load_statuses(args.status)
        result = build_doctor_report(
            args.platform,
            statuses,
            research_scope=args.research_scope,
            allow_pilot=args.allow_pilot,
            language=args.language,
        )
        if args.output:
            write_json(args.output, result)
        # ASCII-escaped console JSON remains lossless on legacy Windows shells;
        # persisted artifacts stay readable UTF-8 through write_json.
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if args.require_live and not result["live"]["ready"]:
            raise SystemExit(2)
        return

    result = start_run(args)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
