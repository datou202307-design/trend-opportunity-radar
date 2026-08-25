from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

from _common import load_data, now_iso, write_json
from monitoring import append_snapshot, compare_monitor, create_monitor
from prove_collection_route import validate_proof
from research_context import compile_context, validate_context
from select_collection_adapter import select_adapter
from validate_report_artifacts import (
    validate_collection_artifacts,
    validate_collection_state_consistency,
    validate_report_contents,
    validate_visual_qa,
)
from validate_subject import validate_subject


SCHEMA_VERSION = "trend-radar-run-v0.1"
DOCTOR_SCHEMA_VERSION = "trend-radar-doctor-v0.1"
MODES = {"quick", "standard", "deep"}


RESUME_STAGES = (
    ("query_plan_required", ("query-plan.json",)),
    ("collection_required", ("collection-state.json",)),
    ("semantic_review_required", ("reviewed-signals-final.json",)),
    ("normalization_required", ("normalized-signals.json",)),
    ("cluster_plan_required", ("cluster-plan.json",)),
    ("clustering_required", ("clustered-signals.json",)),
    ("scoring_required", ("scored-signals.json",)),
    ("decision_synthesis_required", ("profile-findings.json",)),
    ("route_proof_required", ("route-execution-proof.json",)),
    ("report_required", ("profile-report.json", "profile-report.md", "profile-report.html")),
    ("visual_qa_required", ("html-visual-qa.json",)),
)


STAGE_ACTIONS = {
    "query_plan_required": (
        "依据冻结的研究目标生成平台基线、品类和主题桥接三层查询计划。",
        "Generate the platform-baseline, category, and subject-bridge query plan from the frozen research goal.",
    ),
    "collection_required": (
        "严格执行已冻结的只读采集路线，完成有界搜索、详情核验和采样合同；不得静默更换采集器。",
        "Execute the frozen read-only route, including bounded search, detail verification, and the sampling contract; never switch collectors silently.",
    ),
    "semantic_review_required": (
        "审查本轮保留的全部信号，明确相关性、证据方向和排除理由，再生成最终审查快照。",
        "Review every retained signal for relevance, evidence direction, and exclusion reason, then write the final reviewed snapshot.",
    ),
    "normalization_required": (
        "运行规范化脚本，将最终审查快照转换为统一信号结构。",
        "Run the normalization script on the final reviewed snapshot.",
    ),
    "cluster_plan_required": (
        "依据冻结的 Decision Profile 生成候选议题计划，不得用关键词碰撞直接形成结论。",
        "Build the candidate topic plan from the frozen Decision Profile; keyword collisions cannot become conclusions directly.",
    ),
    "clustering_required": (
        "应用议题计划并审计每个聚类的任务一致性、证据角色和直接来源。",
        "Apply the topic plan and audit task coherence, evidence roles, and direct sources for every cluster.",
    ),
    "scoring_required": (
        "按当前平台与采样模式计算讨论强度和证据可靠度，保留评分版本。",
        "Calculate platform discussion strength and evidence confidence for the current platform and sampling mode, preserving the scoring version.",
    ),
    "decision_synthesis_required": (
        "只从通过审计的议题生成一至三项决策发现，并为每项保存反证、行动指标和停止条件。",
        "Create one to three decision findings only from audited topics, preserving counterevidence, action metrics, and stop conditions for each.",
    ),
    "route_proof_required": (
        "证明最终证据确实来自冻结的搜索、详情、评论和媒体路线；缺少收据时不得生成报告。",
        "Prove that final evidence followed the frozen search, detail, comment, and media routes; do not report without the required receipts.",
    ),
    "report_required": (
        "生成一致的 JSON、Markdown 和本地 HTML 决策报告。",
        "Generate consistent JSON, Markdown, and local HTML decision reports.",
    ),
    "visual_qa_required": (
        "通过 loopback HTTP 在桌面端和移动端检查真实 HTML，并记录可审计的视觉验收回执。",
        "Inspect the real HTML over loopback HTTP on desktop and mobile, then record an auditable visual-QA receipt.",
    ),
    "complete": (
        "本轮研究已经完成，可交付报告；如需判断时间变化，可在用户确认后创建后续复采。",
        "This research run is complete and ready for delivery; create follow-up snapshots only after user confirmation if temporal change matters.",
    ),
}


AUTOMATIC_STAGES = {
    "normalization_required",
    "cluster_plan_required",
    "clustering_required",
    "scoring_required",
    "route_proof_required",
    "report_required",
}


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
            "collection_route": selection.get("collection_route"),
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
        "collection_route": doctor["live"].get("collection_route"),
        "next_action": next_action,
        "created_at": existing.get("created_at") if existing else now_iso(),
        "updated_at": now_iso(),
    }
    write_json(manifest_path, manifest)
    return manifest


def _load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    loaded = load_data(path)
    return loaded if isinstance(loaded, dict) else None


def _query_plan_ready(path: Path) -> bool:
    payload = _load_json_object(path)
    return bool(payload and isinstance(payload.get("queries"), list) and payload["queries"])


def _collection_ready(path: Path) -> bool:
    payload = _load_json_object(path)
    return bool(
        payload
        and payload.get("status") == "complete"
        and payload.get("stop_reason") in {"sampling_contract_met", "verified_zero_results"}
    )


def _signals_ready(path: Path, *, require_full_review: bool = False) -> bool:
    payload = _load_json_object(path)
    signals = payload.get("signals") if payload else None
    if not isinstance(signals, list) or not signals:
        return False
    if not require_full_review:
        return True
    return all(
        isinstance(item, dict)
        and isinstance(item.get("semantic_review"), dict)
        and item["semantic_review"].get("status") == "agent_reviewed"
        for item in signals
    )


def _topics_ready(path: Path) -> bool:
    payload = _load_json_object(path)
    return bool(payload and isinstance(payload.get("topics"), list) and payload["topics"])


def _findings_ready(path: Path) -> bool:
    payload = _load_json_object(path)
    return bool(payload and isinstance(payload.get("findings"), list) and payload["findings"])


def _visual_qa_ready(path: Path, html_path: Path) -> bool:
    try:
        validate_visual_qa(str(path), html_path)
        return True
    except (OSError, ValueError, SystemExit):
        return False


def _report_ready(paths: tuple[Path, ...]) -> bool:
    json_path, markdown_path, html_path = paths
    if not all(path.is_file() and path.stat().st_size > 0 for path in paths):
        return False
    try:
        result = load_data(json_path)
        if not isinstance(result, dict):
            return False
        markdown = markdown_path.read_text(encoding="utf-8")
        page = html_path.read_text(encoding="utf-8")
        validate_collection_artifacts(result, json_path.parent)
        validate_collection_state_consistency(result, json_path.parent)
        validate_report_contents(result, markdown, page)
        return True
    except (OSError, UnicodeError, ValueError, SystemExit):
        return False


def _stage_is_ready(state: str, paths: tuple[Path, ...], run_dir: Path, manifest: dict[str, Any]) -> bool:
    if state == "query_plan_required":
        return _query_plan_ready(paths[0])
    if state == "collection_required":
        return _collection_ready(paths[0])
    if state == "semantic_review_required":
        return _signals_ready(paths[0], require_full_review=True)
    if state == "normalization_required":
        return _signals_ready(paths[0])
    if state == "cluster_plan_required":
        payload = _load_json_object(paths[0])
        return bool(payload and isinstance(payload.get("clusters"), list) and payload["clusters"])
    if state == "clustering_required":
        payload = _load_json_object(paths[0])
        return bool(
            payload
            and isinstance(payload.get("signals"), list)
            and payload["signals"]
            and isinstance(payload.get("cluster_audits"), list)
            and payload["cluster_audits"]
        )
    if state == "scoring_required":
        return _topics_ready(paths[0])
    if state == "decision_synthesis_required":
        return _findings_ready(paths[0])
    if state == "route_proof_required":
        try:
            validate_proof(
                run_dir / "run-manifest.json",
                run_dir / "scored-signals.json",
                paths[0],
            )
            return True
        except (OSError, ValueError):
            return False
    if state == "report_required":
        return _report_ready(paths)
    if state == "visual_qa_required":
        return _visual_qa_ready(paths[0], run_dir / "profile-report.html")
    return False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt_files(state: str, run_dir: Path) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    mapping = {
        "query_plan_required": (
            (run_dir / "research-context.json", run_dir / "subject.json"),
            (run_dir / "query-plan.json",),
        ),
        "collection_required": (
            (run_dir / "query-plan.json", run_dir / "environment-doctor.json"),
            (run_dir / "collection-state.json",),
        ),
        "semantic_review_required": (
            (run_dir / "collection-state.json",),
            (run_dir / "reviewed-signals-final.json",),
        ),
        "normalization_required": (
            (run_dir / "reviewed-signals-final.json",),
            (run_dir / "normalized-signals.json",),
        ),
        "cluster_plan_required": (
            (run_dir / "normalized-signals.json", run_dir / "cluster-config.json"),
            (run_dir / "cluster-plan.json",),
        ),
        "clustering_required": (
            (run_dir / "normalized-signals.json", run_dir / "cluster-plan.json", run_dir / "research-context.json"),
            (run_dir / "clustered-signals.json",),
        ),
        "scoring_required": (
            (run_dir / "clustered-signals.json",),
            (run_dir / "scored-signals.json",),
        ),
        "decision_synthesis_required": (
            (run_dir / "scored-signals.json", run_dir / "research-context.json"),
            (run_dir / "profile-findings.json",),
        ),
        "route_proof_required": (
            (run_dir / "scored-signals.json", run_dir / "environment-doctor.json"),
            (run_dir / "route-execution-proof.json",),
        ),
        "report_required": (
            (
                run_dir / "research-context.json",
                run_dir / "scored-signals.json",
                run_dir / "profile-findings.json",
                run_dir / "route-execution-proof.json",
            ),
            (run_dir / "profile-report.json", run_dir / "profile-report.md", run_dir / "profile-report.html"),
        ),
        "visual_qa_required": (
            (run_dir / "profile-report.html",),
            (run_dir / "html-visual-qa.json",),
        ),
    }
    inputs, outputs = mapping[state]
    return tuple(path for path in inputs if path.is_file()), tuple(path for path in outputs if path.is_file())


def _hash_map(paths: tuple[Path, ...]) -> dict[str, str]:
    return {path.name: _sha256(path) for path in paths}


def _ensure_stage_receipt(state: str, run_dir: Path) -> None:
    index = next(index for index, (name, _) in enumerate(RESUME_STAGES, start=1) if name == state)
    receipt_dir = run_dir / ".trend-radar-receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / f"{index:02d}-{state.removesuffix('_required')}.json"
    inputs, outputs = _receipt_files(state, run_dir)
    if not outputs:
        raise ValueError(f"Cannot record {state}: its required output is missing.")
    expected = {
        "schema_version": "trend-radar-stage-receipt-v0.1",
        "stage": state,
        "status": "passed",
        "inputs": _hash_map(inputs),
        "outputs": _hash_map(outputs),
    }
    if receipt_path.is_file():
        current = _load_json_object(receipt_path)
        comparable = {key: current.get(key) for key in expected} if current else None
        if comparable != expected:
            raise ValueError(f"The immutable receipt for {state} no longer matches its artifacts.")
        return
    write_json(receipt_path, {**expected, "recorded_at": now_iso()})


def _resume_state(run_dir: Path, manifest: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    for state, names in RESUME_STAGES:
        paths = tuple(run_dir / name for name in names)
        if not _stage_is_ready(state, paths, run_dir, manifest):
            return state, names
        _ensure_stage_receipt(state, run_dir)
    return "complete", ()


def _run_script(script: str, arguments: list[str]) -> None:
    command = [sys.executable, str(Path(__file__).resolve().parent / script), *arguments]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "deterministic stage failed").strip().splitlines()
        raise ValueError(f"{script} failed: {message[-1] if message else 'unknown error'}")


def _execute_stage(state: str, run_dir: Path, receipt_args: list[str]) -> bool:
    if state == "normalization_required":
        _run_script("normalize_signals.py", [
            "--input", str(run_dir / "reviewed-signals-final.json"),
            "--output", str(run_dir / "normalized-signals.json"),
        ])
        return True
    if state == "cluster_plan_required":
        config = run_dir / "cluster-config.json"
        if not config.is_file():
            return False
        _run_script("build_cluster_plan.py", [
            "--input", str(run_dir / "normalized-signals.json"),
            "--config", str(config),
            "--output", str(run_dir / "cluster-plan.json"),
        ])
        return True
    if state == "clustering_required":
        _run_script("audit_clusters.py", [
            "--input", str(run_dir / "normalized-signals.json"),
            "--plan", str(run_dir / "cluster-plan.json"),
            "--output", str(run_dir / "clustered-signals.json"),
            "--research-context", str(run_dir / "research-context.json"),
        ])
        return True
    if state == "scoring_required":
        _run_script("calculate_evidence_index.py", [
            "--input", str(run_dir / "clustered-signals.json"),
            "--output", str(run_dir / "scored-signals.json"),
        ])
        return True
    if state == "route_proof_required":
        arguments = [
            "--manifest", str(run_dir / "run-manifest.json"),
            "--signals", str(run_dir / "scored-signals.json"),
        ]
        for receipt in receipt_args:
            arguments.extend(("--receipt", receipt))
        arguments.extend(("--output", str(run_dir / "route-execution-proof.json"), "--require-passed"))
        _run_script("prove_collection_route.py", arguments)
        return True
    if state == "report_required":
        _run_script("generate_profile_report.py", [
            "--research-context", str(run_dir / "research-context.json"),
            "--signals", str(run_dir / "scored-signals.json"),
            "--findings", str(run_dir / "profile-findings.json"),
            "--json-output", str(run_dir / "profile-report.json"),
            "--markdown-output", str(run_dir / "profile-report.md"),
            "--html-output", str(run_dir / "profile-report.html"),
        ])
        return True
    return False


def resume_run(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "run-manifest.json"
    manifest = _load_json_object(manifest_path)
    if not manifest or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("A valid run-manifest.json created by trend_radar.py start is required.")
    frozen_states = {
        "clarification_required",
        "preflight_required",
        "pilot_opt_in_required",
        "live_unavailable_import_ready",
        "import_required",
    }
    current = str(manifest.get("state") or "")
    if current in frozen_states:
        return manifest
    required = (run_dir / "research-context.json", run_dir / "subject.json", run_dir / "environment-doctor.json")
    if not all(path.is_file() for path in required):
        raise ValueError("The frozen context, subject, and environment diagnosis must remain in the run directory.")

    receipt_args = list(getattr(args, "receipt", []) or [])
    execute = not bool(getattr(args, "no_execute", False))
    for _ in range(len(RESUME_STAGES) + 1):
        state, required_artifacts = _resume_state(run_dir, manifest)
        if state == "complete" or not execute or state not in AUTOMATIC_STAGES:
            break
        if not _execute_stage(state, run_dir, receipt_args):
            break
    else:
        raise ValueError("Resume exceeded the deterministic stage limit without reaching a stable state.")
    language = str((_load_json_object(run_dir / "research-context.json") or {}).get("language") or "en")
    zh, en = STAGE_ACTIONS[state]
    manifest["state"] = state
    manifest["next_action"] = _language_text(language, zh, en)
    manifest["required_artifacts"] = list(required_artifacts)
    manifest["updated_at"] = now_iso()
    if state == "complete":
        manifest["completed_at"] = manifest.get("completed_at") or now_iso()
    else:
        manifest.pop("completed_at", None)
    write_json(manifest_path, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Start, resume, diagnose, and monitor a Trend Opportunity Radar research run.")
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

    resume = subparsers.add_parser("resume", help="Continue from the first missing or stale required artifact.")
    resume.add_argument("--run-dir", required=True)
    resume.add_argument("--receipt", action="append", default=[], help="Split route receipt in role=PATH form; repeat as needed.")
    resume.add_argument("--no-execute", action="store_true", help="Inspect the next state without running safe deterministic stages.")

    monitor = subparsers.add_parser("monitor", help="Create, append, or compare compatible completed research snapshots.")
    monitor_commands = monitor.add_subparsers(dest="monitor_command", required=True)

    monitor_create = monitor_commands.add_parser("create", help="Freeze a completed run as the baseline of a monitoring cycle.")
    monitor_create.add_argument("--run-dir", required=True)
    monitor_create.add_argument("--monitor-dir", required=True)
    monitor_create.add_argument("--cadence-days", type=int)
    monitor_create.add_argument("--max-snapshots", type=int, default=4)

    monitor_append = monitor_commands.add_parser("append", help="Append one newer compatible completed run.")
    monitor_append.add_argument("--monitor-dir", required=True)
    monitor_append.add_argument("--run-dir", required=True)

    monitor_compare = monitor_commands.add_parser("compare", help="Compare the latest two compatible snapshots.")
    monitor_compare.add_argument("--monitor-dir", required=True)
    monitor_compare.add_argument("--json-output")
    monitor_compare.add_argument("--markdown-output")
    monitor_compare.add_argument("--html-output")

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

    if args.command == "monitor":
        if args.monitor_command == "create":
            result = create_monitor(
                Path(args.run_dir),
                Path(args.monitor_dir),
                cadence_days=args.cadence_days,
                max_snapshots=args.max_snapshots,
            )
        elif args.monitor_command == "append":
            result = append_snapshot(Path(args.monitor_dir), Path(args.run_dir))
        else:
            result = compare_monitor(
                Path(args.monitor_dir),
                json_output=Path(args.json_output) if args.json_output else None,
                markdown_output=Path(args.markdown_output) if args.markdown_output else None,
                html_output=Path(args.html_output) if args.html_output else None,
            )
    else:
        result = resume_run(args) if args.command == "resume" else start_run(args)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
