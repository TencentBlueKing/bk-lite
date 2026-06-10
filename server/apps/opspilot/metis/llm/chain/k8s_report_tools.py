"""K8s config-analysis report rendering helpers (relocated from node.py).

F039: the "fix command" / config-analysis knowledge used to be triplicated
across ``_config_analysis_risk_description`` / ``_config_analysis_fix_description``
/ ``_config_analysis_benefit_description`` which each string-matched the same
Chinese issue keywords. The matching rules are now expressed once in
``_CONFIG_ANALYSIS_ISSUE_RULES`` and the three renderers read from it.

Output strings are byte-for-byte identical to the previous inline
implementations, and the per-renderer matching order is preserved (the risk
renderer additionally matches "健康探针" on the liveness rule, exactly as before).
"""

import json
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import BaseMessage, SystemMessage


def build_post_tool_directives(result_messages: List[BaseMessage]) -> List[SystemMessage]:
    directives: List[SystemMessage] = []

    for message in result_messages:
        message_name = getattr(message, "name", "")
        message_content = getattr(message, "content", "")

        if message_name == "analyze_deployment_configurations":
            try:
                parsed = json.loads(message_content) if isinstance(message_content, str) else message_content
            except Exception:
                parsed = None

            if isinstance(parsed, dict) and (parsed.get("issues_detail") or should_emit_config_analysis_report(parsed)):
                directives.append(
                    SystemMessage(
                        content=(
                            "【配置检查输出规则】不要同时输出“问题摘要”和“配置问题报告”两个重复板块。"
                            "如果已经输出按严重级别或问题类别展开的详细问题报告，就不要再单独重复一段摘要。"
                            "优先保留详细问题报告，并把总数、集群名、影响范围合并到报告标题或开头一句。"
                            "本轮先输出一次完整配置检查结果。"
                            "如果检查结果存在问题项，输出完整配置检查报告后，必须主动调用 request_user_choice，"
                            "让用户选择修复展示方式（按问题类别聚合 / 按工作负载聚合 / 全部一次性展示）。"
                            "不要主动调用 generate_repair_report，必须等待用户完成选择后再生成修复对比。"
                            "如果检查结果没有问题，则直接结束，不要追加修复交互。"
                        )
                    )
                )

        if message_name == "generate_repair_report" and ("修复命令" in message_content or "```" in message_content):
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
