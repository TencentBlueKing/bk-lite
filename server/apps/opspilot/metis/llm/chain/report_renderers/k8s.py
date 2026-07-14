"""K8s report renderers + 配置分析 payload builders。

历史背景(F039):
- risk / fix / benefit 三段中文文案原本在 node.py 三处复制粘贴,各按相同关键词
  字符串匹配,改了 A 忘了 B 是常态。
- 统一抽到 _CONFIG_ANALYSIS_ISSUE_RULES + _lookup_config_analysis_description,
  三个 render 共享 match 谓词;risk render 单独保留"健康探针"补充匹配(历史上
  只有 risk 这条会同时匹配"存活探针"和"健康探针")。
- 输出字符串与原实现 byte-for-byte 一致,per-renderer 匹配顺序保留。

render_config_analysis_report / render_repair_diff_report 在模块加载时通过
包级 register_renderer() 注册,既有的 dispatch_custom_event 路径不变。
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, SystemMessage

# 用相对导入拿 registry / register_*,不依赖 k8s_report_tools shim
from . import (
    register_renderer,
    register_tool_result_capability,
)


# ---------------------------------------------------------------------------
# 工具结果 → 报告卡片 引导 system message
# ---------------------------------------------------------------------------
def build_post_tool_directives(
    result_messages: List[BaseMessage],
    enable_config_analysis_report: bool = True,
    enable_repair_diff_report: bool = True,
) -> List[SystemMessage]:
    directives: List[SystemMessage] = []

    for message in result_messages:
        message_name = getattr(message, "name", "")
        message_content = getattr(message, "content", "")

        if enable_config_analysis_report and message_name == "analyze_deployment_configurations":
            try:
                parsed = json.loads(message_content) if isinstance(message_content, str) else message_content
            except Exception:
                parsed = None

            if isinstance(parsed, dict) and (parsed.get("issues_detail") or _should_emit_parsed(parsed)):
                directives.append(
                    SystemMessage(
                        content=(
                            "【配置检查输出规则】结构化配置检查报告已经通过 AG-UI 的 config_analysis_report 事件展示给用户。"
                            "不要再用 Markdown、标题、列表或表格重复输出“配置检查报告”“问题分组”“修复建议”等完整报告内容。"
                            "最终文本最多只允许一句简短说明，例如“配置检查报告已展示，请查看上方卡片”。"
                            "如果检查结果存在问题项，必须主动调用 request_user_choice，"
                            "通过 AG-UI 交互卡片让用户选择修复展示方式（按问题类别聚合 / 按工作负载聚合 / 全部一次性展示）。"
                            "不要主动调用 generate_repair_report，必须等待用户完成选择后再生成修复对比。"
                            "如果检查结果没有问题，则直接用一句话结束，不要追加修复交互。"
                        )
                    )
                )

        if enable_repair_diff_report and message_name == "generate_repair_report" and ("修复命令" in message_content or "```" in message_content):
            directives.append(
                SystemMessage(
                    content=(
                        "【强制输出规则】用户无法看到工具返回的内容（ToolMessage 对用户不可见）。"
                        "你必须在你的回复中完整列出工具结果中的所有修复命令。"
                        "格式要求：按工作负载分组，每条命令用 ```bash 代码块包裹。"
                        "严禁省略任何命令，严禁说'见上方'或'复制以上命令'。"
                        "用户只能看到你的文字回复，所以命令必须出现在你的回复中。"
                    )
                )
            )

    return directives


def _should_emit_parsed(parsed: Any) -> bool:
    """包内 alias,避免循环 import 把 should_emit 拖到 k8s 顶部。"""
    return should_emit_config_analysis_report(parsed) if isinstance(parsed, dict) else False


def build_config_analysis_report_markdown(parsed: Dict[str, Any]) -> str:
    cluster_name = parsed.get("cluster_name") or "Kubernetes"
    problematic = parsed.get("problematic", 0)
    healthy = parsed.get("healthy")
    total = _build_config_analysis_report_total(parsed)
    issues_detail = parsed.get("issues_detail") or []

    lines = [f"# 配置检查报告 - {cluster_name}"]
    summary_parts = []
    if total is not None:
        summary_parts.append(f"总计 {total} 个工作负载")
    if problematic is not None:
        summary_parts.append(f"存在问题 {problematic} 个")
    if healthy is not None:
        summary_parts.append(f"健康 {healthy} 个")
    if summary_parts:
        lines.append("；".join(summary_parts))

    if not issues_detail:
        lines.append("未发现明显配置问题")

    severity_titles = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "warning": "Warning",
        "info": "Info",
    }
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in issues_detail:
        grouped.setdefault(item.get("severity", "info"), []).append(item)

    severity_order = ["critical", "high", "medium", "low", "warning", "info"]
    for severity in severity_order:
        items = grouped.get(severity)
        if not items:
            continue
        lines.append(f"## {severity_titles.get(severity, severity.title())}")
        for item in items:
            issue = item.get("issue", "未知问题")
            count = item.get("count", 0)
            workloads = item.get("workloads") or []
            workload_preview = "、".join(workloads[:5])
            if len(workloads) > 5:
                workload_preview += f" 等 {len(workloads)} 个工作负载"
            elif workload_preview:
                workload_preview = f"：{workload_preview}"
            lines.append(f"- {issue}（{count} 个工作负载{workload_preview}）")

    return "\n\n".join(lines)


def downgrade_config_analysis_next_step_hint(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Remove expert repair workflow hints when no skill package enables them."""
    if not isinstance(parsed, dict):
        return parsed
    hint = parsed.get("_next_step_hint")
    if not isinstance(hint, str) or "修复展示方式" not in hint:
        return parsed

    result = dict(parsed)
    problematic = result.get("problematic")
    if isinstance(problematic, int) and problematic > 0:
        result["_next_step_hint"] = (
            f"分析完成，共 {problematic} 个工作负载存在问题。"
            "本轮输出基础检查结果和关键风险摘要即可。"
            "不要调用 request_user_choice，也不要调用 generate_repair_report。"
        )
    else:
        result["_next_step_hint"] = (
            "分析完成。请输出基础检查结果即可。"
            "不要调用 request_user_choice，也不要调用 generate_repair_report。"
        )
    return result


# ---------------------------------------------------------------------------
# F039: single issue-type knowledge registry
# ---------------------------------------------------------------------------
#
# Each rule is an ordered match against the (possibly empty) ``issue_type``
# string. ``match`` is the predicate shared by all three renderers;
# ``risk_match`` is an OPTIONAL extra predicate used ONLY by the risk renderer
# (this preserves the historical behavior where the risk renderer also matched
# the "健康探针" keyword on the liveness rule while fix/benefit did not).
#
# The output strings below are copied verbatim from the previous three inline
# functions; nothing about the produced text changes.


def _has(*keywords):
    def predicate(issue_type: str) -> bool:
        lowered = issue_type.lower()
        for kw in keywords:
            if kw.endswith("@lower"):
                if kw[:-6] in lowered:
                    return True
            elif kw in issue_type:
                return True
        return False

    return predicate


_CONFIG_ANALYSIS_ISSUE_RULES = [
    {
        "match": _has("资源限制", "资源请求"),
        "risk": "无资源限制的容器可消耗节点所有资源，导致其他 Pod OOM 或 CPU 饥饿，影响集群稳定性。",
        "fix": "为所有容器设置 resources.requests 和 resources.limits，建议 CPU 100m-500m，内存 128Mi-256Mi。",
        "benefit": "避免单个容器争抢过多节点资源，提升集群稳定性并减少相互干扰。",
    },
    {
        # risk renderer additionally matches "健康探针" on this liveness rule.
        "match": _has("存活探针", "liveness@lower"),
        "risk_match": _has("存活探针", "健康探针", "liveness@lower"),
        "risk": "无存活探针时 Kubernetes 无法自动检测和重启不健康的容器，故障容器将持续运行。",
        "fix": "添加 livenessProbe 配置（建议 httpGet 方式），设置合理的 initialDelaySeconds 和 periodSeconds。",
        "benefit": "让 Kubernetes 能自动发现并重启异常容器，缩短故障持续时间。",
    },
    {
        "match": _has("就绪探针", "readiness@lower"),
        "risk": "无就绪探针时 Service 可能将流量路由到未准备好的 Pod，导致请求失败。",
        "fix": "添加 readinessProbe 配置，确保 Pod 准备好接收流量后才加入 Service 端点。",
        "benefit": "仅在 Pod 真正可用时接收流量，减少发布抖动和瞬时请求失败。",
    },
    {
        "match": _has("探针"),
        "risk": "缺少健康检查探针，Kubernetes 无法自动检测容器故障并执行自愈操作。",
        "fix": "为容器添加 livenessProbe 和 readinessProbe，建议使用 httpGet 或 tcpSocket 检测方式。",
        "benefit": "补齐健康检查后，工作负载更容易被平台自动发现异常并恢复。",
    },
    {
        "match": _has("root", "安全上下文", "非 root@lower"),
        "risk": "容器以 root 用户运行，容器逃逸后攻击者将获得宿主机 root 权限，安全风险极高。",
        "fix": "配置 securityContext.runAsNonRoot: true 和 runAsUser: 1000，禁止容器以 root 运行。",
        "benefit": "降低容器逃逸后直接获得宿主机 root 权限的风险，收紧运行时权限边界。",
    },
    {
        "match": _has("latest", "镜像标签"),
        "risk": "latest 标签不可溯源，每次拉取可能获得不同版本，导致不可预测行为和回滚困难。",
        "fix": "将所有 :latest 标签替换为固定版本号（如 :1.25.3），确保镜像版本可追溯。",
        "benefit": "让镜像版本可追溯、可回滚，减少因隐式升级带来的变更风险。",
    },
    {
        "match": _has("单副本", "副本"),
        "risk": "单副本部署存在单点故障风险，节点异常时服务将完全中断，无法保障高可用。",
        "fix": "将生产环境工作负载副本数增加至 2 或以上，配合 PodDisruptionBudget 保障高可用。",
        "benefit": "提升服务可用性，在节点故障或滚动发布时降低中断风险。",
    },
    {
        "match": _has("特权", "privileged@lower"),
        "risk": "特权容器拥有宿主机全部 Linux capabilities，容器逃逸后等同于 root 访问整个节点。",
        "fix": "移除 privileged 权限，仅授予容器完成业务所需的最小能力集。",
        "benefit": "缩小容器可用能力范围，降低被利用后进一步突破宿主机的风险。",
    },
    {
        "match": _has("hostNetwork", "主机命名空间", "hostPID"),
        "risk": "共享宿主机网络/进程/IPC 命名空间会绕过网络和进程隔离，增大攻击面。",
        "fix": "尽量避免使用 hostNetwork、hostPID 和 hostIPC，保持默认隔离边界。",
        "benefit": "保留容器默认隔离边界，减少跨容器和宿主机暴露面。",
    },
    {
        "match": _has("密码", "明文", "Secret"),
        "risk": "密码暴露在 Git 历史、kubectl describe 输出中，任何有 namespace 读权限的用户均可看到。",
        "fix": "将敏感信息迁移到 Secret，并通过环境变量或挂载文件按需注入。",
        "benefit": "集中管理敏感信息，减少凭据泄露面并简化后续轮换。",
    },
    {
        "match": _has("NetworkPolicy", "网络隔离"),
        "risk": "所有 Pod 之间可自由通信，一旦某个容器被入侵，攻击者可横向移动到所有命名空间。",
        "fix": "为命名空间补充 NetworkPolicy，只允许必要的入站和出站流量。",
        "benefit": "限制横向通信范围，降低单点失陷后在集群内扩散的风险。",
    },
    {
        "match": _has("ServiceAccount"),
        "risk": "使用默认 ServiceAccount 违反最小权限原则，可能被利用进行集群内横向攻击。",
        "fix": "为工作负载创建专用 ServiceAccount，并按最小权限绑定 RBAC。",
        "benefit": "落实最小权限访问，减少工作负载凭证被滥用的风险。",
    },
]

_CONFIG_ANALYSIS_DEFAULTS = {
    "risk": "当前配置不符合 Kubernetes 最佳实践，可能影响集群安全性和稳定性。",
    "fix": "根据实际业务场景补充对应的 Kubernetes 最佳实践配置。",
    "benefit": "提升 Kubernetes 配置治理水平，降低常见稳定性与安全风险。",
}


def _lookup_config_analysis_description(issue_type: str, field: str) -> str:
    issue_type = issue_type or ""
    for rule in _CONFIG_ANALYSIS_ISSUE_RULES:
        if field == "risk" and "risk_match" in rule:
            matched = rule["risk_match"](issue_type)
        else:
            matched = rule["match"](issue_type)
        if matched:
            return rule[field]
    return _CONFIG_ANALYSIS_DEFAULTS[field]


def _config_analysis_risk_description(issue_type: str) -> str:
    return _lookup_config_analysis_description(issue_type, "risk")


def _config_analysis_fix_description(issue_type: str) -> str:
    return _lookup_config_analysis_description(issue_type, "fix")


def _config_analysis_benefit_description(issue_type: str) -> str:
    return _lookup_config_analysis_description(issue_type, "benefit")


def should_emit_config_analysis_report(parsed: Dict[str, Any]) -> bool:
    if not isinstance(parsed, dict) or parsed.get("error"):
        return False
    if parsed.get("issues_detail"):
        return True
    return any(parsed.get(key) is not None for key in ("total", "problematic", "healthy"))


def _build_config_analysis_scope(parsed: Dict[str, Any]) -> Dict[str, Any]:
    scope = parsed.get("scope") if isinstance(parsed.get("scope"), dict) else {}
    result = {}

    cluster_name = parsed.get("cluster_name")
    if cluster_name:
        result["cluster_name"] = cluster_name

    for key in ("namespace", "instance_name", "name", "target_name"):
        value = scope.get(key) or parsed.get(key)
        if value not in (None, ""):
            result[key] = value

    fallback_target = scope.get("target_name") or scope.get("name") or parsed.get("target_name") or parsed.get("name")
    if fallback_target:
        result.setdefault("name", fallback_target)
        result.setdefault("target_name", fallback_target)

    return result


def _build_config_analysis_scan_range(parsed: Dict[str, Any]) -> Dict[str, Any]:
    scan_range = {}
    for key in ("offset", "limit", "has_more"):
        if key in parsed:
            scan_range[key] = parsed.get(key)
    return scan_range


def _build_config_analysis_report_total(parsed: Dict[str, Any]) -> Optional[int]:
    healthy = parsed.get("healthy")
    problematic = parsed.get("problematic")
    if isinstance(healthy, int) and isinstance(problematic, int):
        return healthy + problematic

    deployments_full = parsed.get("_deployments_full")
    if isinstance(deployments_full, list):
        return len(deployments_full)

    total = parsed.get("total")
    return total if isinstance(total, int) else None


def build_config_analysis_report_payload(parsed: Dict[str, Any]) -> Dict[str, Any]:
    cluster_name = parsed.get("cluster_name") or "Kubernetes"
    issues_detail = parsed.get("issues_detail") or []
    report_total = _build_config_analysis_report_total(parsed)

    severity_titles = {
        "critical": "Critical",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "warning": "Warning",
        "info": "Info",
    }
    severity_priority = {
        "critical": "P0",
        "high": "P1",
        "medium": "P2",
        "low": "P3",
        "warning": "P2",
        "info": "P3",
    }
    severity_order = ["critical", "high", "medium", "low", "warning", "info"]
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in issues_detail:
        grouped.setdefault(item.get("severity", "info"), []).append(item)

    severity_sections = []
    recommendations = []
    for severity in severity_order:
        items = grouped.get(severity)
        if not items:
            continue

        section_issues = []
        for item in items:
            issue = item.get("issue", "未知问题")
            workloads = item.get("workloads") or []
            issue_payload = {
                "issue": issue,
                "count": item.get("count", 0),
                "workloads": workloads,
                "risk": _config_analysis_risk_description(issue),
            }
            section_issues.append(issue_payload)
            recommendations.append(
                {
                    "priority": severity_priority.get(severity, "P3"),
                    "action": _config_analysis_fix_description(issue),
                    "target": workloads[0] if workloads else "",
                    "benefit": _config_analysis_benefit_description(issue),
                }
            )

        severity_sections.append(
            {
                "severity": severity,
                "title": severity_titles.get(severity, severity.title()),
                "issues": section_issues,
            }
        )

    markdown = build_config_analysis_report_markdown(parsed)

    return {
        "report_id": str(uuid.uuid4())[:8],
        "title": f"配置检查报告 - {cluster_name}",
        "cluster_name": cluster_name,
        "a2ui": build_a2ui_report_contract(
            component="config-analysis-report",
            event_name="config_analysis_report",
            actions=[
                {"key": "expand_issue", "label": "展开问题"},
                {"key": "request_repair_mode", "label": "选择修复展示方式"},
            ],
        ),
        "scope": _build_config_analysis_scope(parsed),
        "scan_range": _build_config_analysis_scan_range(parsed),
        "summary": {
            "total": report_total,
            "problematic": parsed.get("problematic"),
            "healthy": parsed.get("healthy"),
        },
        "severity_sections": severity_sections,
        "recommendations": recommendations,
        "markdown": markdown,
        "fallback_markdown": markdown,
    }


def build_a2ui_report_contract(component: str, event_name: str, actions: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    return {
        "version": "1.0",
        "component": component,
        "event_name": event_name,
        "render_mode": "card",
        "actions": actions or [],
    }


def build_config_diff_report_payload(
    title: str,
    cluster_name: str,
    items: List[Dict[str, Any]],
    event_name: str = "repair_diff_report",
) -> Dict[str, Any]:
    normalized_items = []
    for item in items:
        normalized_items.append(
            {
                "workload_name": item.get("workload_name", "") if isinstance(item, dict) else getattr(item, "workload_name", ""),
                "workload_type": item.get("workload_type", "") if isinstance(item, dict) else getattr(item, "workload_type", ""),
                "namespace": item.get("namespace", "") if isinstance(item, dict) else getattr(item, "namespace", ""),
                "severity": item.get("severity", "info") if isinstance(item, dict) else getattr(item, "severity", "info"),
                "summary": item.get("summary", "") if isinstance(item, dict) else getattr(item, "summary", ""),
                "before_yaml": item.get("before_yaml", "") if isinstance(item, dict) else getattr(item, "before_yaml", ""),
                "after_yaml": item.get("after_yaml", "") if isinstance(item, dict) else getattr(item, "after_yaml", ""),
            }
        )

    return {
        "report_id": str(uuid.uuid4())[:8],
        "title": title,
        "cluster_name": cluster_name,
        "a2ui": build_a2ui_report_contract(
            component="config-diff-report",
            event_name=event_name,
            actions=[
                {"key": "open_diff", "label": "查看差异"},
                {"key": "copy_after_yaml", "label": "复制修复配置"},
            ],
        ),
        "items": normalized_items,
    }


def build_repair_mode_choice_args(parsed: Dict[str, Any]) -> Dict[str, Any]:
    issues_detail = parsed.get("issues_detail") if isinstance(parsed, dict) else None
    issues = [item for item in issues_detail if isinstance(item, dict)] if isinstance(issues_detail, list) else []
    problematic = parsed.get("problematic") if isinstance(parsed, dict) else None
    problematic_count = problematic if isinstance(problematic, int) else 0

    issue_types = {str(item.get("issue", "")).strip() for item in issues if str(item.get("issue", "")).strip()}
    workloads = {
        str(workload).strip()
        for item in issues
        for workload in (item.get("workloads") or [])
        if str(workload).strip()
    }
    high_impact_count = sum(
        int(item.get("count", 0))
        for item in issues
        if item.get("severity") in {"critical", "high"} and isinstance(item.get("count", 0), int)
    )

    options: List[str] = []
    if len(issue_types) >= 2 and problematic_count >= 8:
        if high_impact_count >= 10 or len(issue_types) >= 3:
            options.append("按问题类别聚合（推荐：多类问题覆盖面广）")
        else:
            options.append("按问题类别聚合")

    if len(workloads) >= 2:
        if problematic_count <= 10:
            options.append("按工作负载聚合（推荐：目标数量较少）")
        else:
            options.append("按工作负载聚合")

    if problematic_count <= 10 or len(issues) <= 2:
        options.append("全部一次性展示" if problematic_count > 1 else "直接展示单个修复对比（推荐）")

    # issues_detail/workloads may be summarized or truncated. For large scans,
    # keep the grouped display modes available even when the summary only lists
    # one issue/workload exemplar.
    if problematic_count > 10:
        existing_prefixes = {option.split("（", 1)[0] for option in options}
        if "按问题类别聚合" not in existing_prefixes:
            options.insert(0, "按问题类别聚合")
        if "按工作负载聚合" not in existing_prefixes:
            insert_at = 1 if options and options[0].startswith("按问题类别聚合") else len(options)
            options.insert(insert_at, "按工作负载聚合")

    if not options:
        options.append("按问题类别聚合（推荐：先处理共性问题）")
        options.append("按工作负载聚合")

    deduped_options = list(dict.fromkeys(options))[:4]
    return {
        "question": "请选择修复展示方式",
        "question_type": "single_select",
        "options": deduped_options,
    }


def find_pending_k8s_analysis_choice(messages: List[BaseMessage]) -> Optional[Dict[str, Any]]:
    latest_index = -1
    latest_payload: Optional[Dict[str, Any]] = None

    for index, message in enumerate(messages):
        if getattr(message, "type", "") != "tool" or getattr(message, "name", "") != "analyze_deployment_configurations":
            continue
        content = getattr(message, "content", "")
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
        except Exception:
            continue
        if isinstance(parsed, dict) and parsed.get("issues_detail"):
            latest_index = index
            latest_payload = parsed

    if latest_index < 0 or latest_payload is None:
        return None

    for message in messages[latest_index + 1 :]:
        if getattr(message, "type", "") == "tool" and getattr(message, "name", "") in {"request_user_choice", "generate_repair_report"}:
            return None
        if getattr(message, "type", "") == "ai":
            tool_calls = getattr(message, "tool_calls", []) or []
            if any(tool_call.get("name") == "request_user_choice" for tool_call in tool_calls):
                return None

    return latest_payload


# ---------------------------------------------------------------------------
# Built-in renderers(模块加载时注册)
# ---------------------------------------------------------------------------


def render_config_analysis_report(
    parsed: Any,
    package: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """把 analyze_deployment_configurations 的结果包装成 config_analysis_report 卡片。

    parsed: 工具直接返回的 dict(由 LangChain ToolMessage.content 解出)
    package: 命中的技能包字典(供 a2ui/标题扩展用,当前未使用)
    """
    if not should_emit_config_analysis_report(parsed):
        return None
    return build_config_analysis_report_payload(parsed)


def render_repair_diff_report(
    parsed: Any,
    package: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """把 generate_repair_report 的结果包装成 repair_diff_report 卡片(before/after 对比)。

    接受两种入参 shape,调用方按场景选:
    - 直接传 items 列表(常见:从状态里抽出来)
    - 传 {"items": [...], "cluster_name": "...", "title": "..."} (常见:整段 Pydantic 工具输出)
    """
    if isinstance(parsed, dict):
        items = parsed.get("items") or []
        cluster_name = parsed.get("cluster_name") or package.get("name", "Kubernetes")
        title = parsed.get("title") or f"修复对比 - {cluster_name}"
    elif isinstance(parsed, list):
        items = parsed
        cluster_name = package.get("name", "Kubernetes")
        title = f"修复对比 - {cluster_name}"
    else:
        return None

    if not items:
        return None

    return build_config_diff_report_payload(
        title=title,
        cluster_name=cluster_name,
        items=items,
    )


def _config_analysis_yaml_diff(issue_type: str, workload_name: str = "app") -> Dict[str, str]:
    """根据 issue 类型生成 spec 的 before/after YAML 片段(只列问题字段,便于前端行 diff 高亮)。

    返回 dict 含 before / after 两个字符串,前端的 DiffReportCard 拿来并排渲染并
    按行算 diff(新增行绿、删除行红)。YAML 严格用 2 空格缩进,与 kubectl 输出一致。
    """
    name = (workload_name or "app").strip() or "app"

    if _has("资源限制", "资源请求")(issue_type):
        before = (
            "spec:\n"
            "  containers:\n"
            f"  - name: {name}\n"
            "    # 缺少资源 requests/limits\n"
            "    resources: {}\n"
        )
        after = (
            "spec:\n"
            "  containers:\n"
            f"  - name: {name}\n"
            "    resources:\n"
            "      requests:\n"
            "        cpu: 100m\n"
            "        memory: 128Mi\n"
            "      limits:\n"
            "        cpu: 500m\n"
            "        memory: 256Mi\n"
        )
    elif _has("存活探针", "liveness@lower")(issue_type):
        before = (
            "spec:\n"
            "  containers:\n"
            f"  - name: {name}\n"
            "    # 缺少 livenessProbe,故障容器无法被自动重启\n"
        )
        after = (
            "spec:\n"
            "  containers:\n"
            f"  - name: {name}\n"
            "    livenessProbe:\n"
            "      httpGet:\n"
            "        path: /healthz\n"
            "        port: 8080\n"
            "      initialDelaySeconds: 30\n"
            "      periodSeconds: 10\n"
        )
    elif _has("就绪探针", "readiness@lower")(issue_type):
        before = (
            "spec:\n"
            "  containers:\n"
            f"  - name: {name}\n"
            "    # 缺少 readinessProbe,未就绪 Pod 可能接收流量\n"
        )
        after = (
            "spec:\n"
            "  containers:\n"
            f"  - name: {name}\n"
            "    readinessProbe:\n"
            "      httpGet:\n"
            "        path: /ready\n"
            "        port: 8080\n"
            "      initialDelaySeconds: 5\n"
            "      periodSeconds: 5\n"
        )
    elif _has("探针")(issue_type):
        before = (
            "spec:\n"
            "  containers:\n"
            f"  - name: {name}\n"
            "    # 同时缺少 livenessProbe / readinessProbe\n"
        )
        after = (
            "spec:\n"
            "  containers:\n"
            f"  - name: {name}\n"
            "    livenessProbe:\n"
            "      httpGet: { path: /healthz, port: 8080 }\n"
            "      initialDelaySeconds: 30\n"
            "      periodSeconds: 10\n"
            "    readinessProbe:\n"
            "      httpGet: { path: /ready, port: 8080 }\n"
            "      initialDelaySeconds: 5\n"
            "      periodSeconds: 5\n"
        )
    elif _has("root", "安全上下文", "非 root@lower")(issue_type):
        before = (
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            f"      - name: {name}\n"
            "        # 容器以 root 运行\n"
        )
        after = (
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            f"      - name: {name}\n"
            "        securityContext:\n"
            "          runAsNonRoot: true\n"
            "          runAsUser: 1000\n"
            "          allowPrivilegeEscalation: false\n"
        )
    elif _has("latest", "镜像标签")(issue_type):
        before = (
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            f"      - name: {name}\n"
            "        image: nginx:latest\n"
        )
        after = (
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            f"      - name: {name}\n"
            "        image: nginx:1.27.3\n"
        )
    elif _has("单副本", "副本")(issue_type):
        before = (
            "spec:\n"
            "  replicas: 1\n"
        )
        after = (
            "spec:\n"
            "  replicas: 3\n"
        )
    elif _has("特权", "privileged@lower")(issue_type):
        before = (
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            f"      - name: {name}\n"
            "        securityContext:\n"
            "          privileged: true\n"
        )
        after = (
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            f"      - name: {name}\n"
            "        securityContext:\n"
            "          privileged: false\n"
            "          capabilities:\n"
            "            drop: [\"ALL\"]\n"
        )
    elif _has("hostNetwork", "主机命名空间", "hostPID")(issue_type):
        before = (
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      hostNetwork: true\n"
            "      hostPID: true\n"
        )
        after = (
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      # 保持默认隔离边界\n"
            "      hostNetwork: false\n"
            "      hostPID: false\n"
        )
    else:
        # 兜底:走原来的文字描述,前端能正常显示但没有行 diff
        return {
            "before": f"# 当前状态\n# {issue_type}\n",
            "after": f"# 修复建议\n# {_config_analysis_fix_description(issue_type)}\n",
        }

    return {"before": before, "after": after}


def build_summary_diff_from_analysis(
    analysis: Dict[str, Any],
    skill_id: int = None,
) -> Optional[Dict[str, Any]]:
    """从 analyze_deployment_configurations 的 issues 构造"summary diff"payload。

    后端按 issue 类型生成 spec 的 before/after YAML 片段,前端 DiffReportCard
    拿来并排渲染并按行高亮(新增行绿、删除行红)。LLM 不参与,后端直接组装,
    绕过 LLM 服从度问题。YAML 只是近似的 spec 片段,只覆盖问题字段,不调 k8s API。
    """
    issues = analysis.get("issues_detail") or []
    if not isinstance(issues, list) or not issues:
        return None
    cluster_name = analysis.get("cluster_name") or "Kubernetes"
    items: List[Dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        issue_text = str(issue.get("issue") or "").strip()
        if not issue_text:
            continue
        severity = str(issue.get("severity") or "info")
        workloads = issue.get("workloads") or []
        # 列表太长的截断显示,避免单行超宽
        workload_label = ", ".join(str(w) for w in workloads[:8])
        if len(workloads) > 8:
            workload_label += f" 等 {len(workloads)} 个"
        # YAML 片段里的容器名取第一个 workload(其他同类,模板一致)
        first_workload = str(workloads[0]) if workloads else "app"
        yaml_diff = _config_analysis_yaml_diff(issue_text, first_workload)
        items.append({
            "workload_name": workload_label or f"({len(workloads)} 个工作负载)",
            "workload_type": "Deployment",
            "namespace": str(analysis.get("scope", {}).get("namespace") or "all"),
            "severity": severity,
            "summary": issue_text,
            # before_yaml / after_yaml 现在是真正的 YAML 片段,前端行 diff 高亮
            "before_yaml": yaml_diff["before"],
            "after_yaml": yaml_diff["after"],
            "fix_description": _config_analysis_fix_description(issue_text),
        })
    if not items:
        return None
    payload = build_config_diff_report_payload(
        title=f"修复建议 - {cluster_name}",
        cluster_name=cluster_name,
        items=items,
    )
    # 前端 modal "查看实际 deployment" 按钮需要这个 skill_id 查 kubeconfig
    if skill_id is not None:
        payload["skill_id"] = skill_id
    return payload


# 模块加载时注册内置渲染器。新增能力只需在这里加一行 + 写一个 renderer。
register_renderer("config_analysis_report", render_config_analysis_report)
register_renderer("repair_diff_report", render_repair_diff_report)

# 工具结果 → capability 的隐式 dispatch 映射。
# analyze_deployment_configurations 跑完后,deepagent 把 JSON 放进 ToolMessage,
# 后处理器扫到这个 tool name 就调 config_analysis_report 渲染器。
register_tool_result_capability("analyze_deployment_configurations", "config_analysis_report")
