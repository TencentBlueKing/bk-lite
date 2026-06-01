"""Kubernetes工具模块

这个模块包含了所有Kubernetes相关的工具函数，按功能分类到不同的子模块中：
- resources: 基础资源查询工具
- diagnostics: 故障诊断和监控工具
- analysis: 配置分析和策略检查工具
- utils: 通用辅助函数
"""

from apps.opspilot.metis.llm.tools.kubernetes.analysis import (
    analyze_deployment_configurations,
    check_kubernetes_daemonsets,
    check_kubernetes_endpoints,
    check_kubernetes_hpa_status,
    check_kubernetes_ingress,
    check_kubernetes_jobs,
    check_kubernetes_network_policies,
    check_kubernetes_persistent_volumes,
    check_kubernetes_resource_quotas,
    check_kubernetes_statefulsets,
)
from apps.opspilot.metis.llm.tools.kubernetes.batch_operations import batch_restart_pods, cleanup_failed_pods, find_configmap_consumers
from apps.opspilot.metis.llm.tools.kubernetes.cluster import (
    describe_kubernetes_resource,
    explain_kubernetes_resource,
    get_kubernetes_contexts,
    kubernetes_troubleshooting_guide,
    list_kubernetes_api_resources,
    verify_kubernetes_connection,
)
from apps.opspilot.metis.llm.tools.kubernetes.data_collection import (
    build_incident_evidence_package,
    collect_k8s_context_by_target_type,
    normalize_alert_event,
    resolve_k8s_target_from_alert,
)
from apps.opspilot.metis.llm.tools.kubernetes.diagnostics import (
    diagnose_kubernetes_pod_issues,
    get_failed_kubernetes_pods,
    get_high_restart_kubernetes_pods,
    get_kubernetes_node_capacity,
    get_kubernetes_orphaned_resources,
    get_pending_kubernetes_pods,
)
from apps.opspilot.metis.llm.tools.kubernetes.diagnostics_advanced import (
    check_network_policies_blocking,
    check_pvc_capacity,
    diagnose_pending_pod_issues,
)
from apps.opspilot.metis.llm.tools.kubernetes.node_diagnostics import diagnose_node_issues
from apps.opspilot.metis.llm.tools.kubernetes.optimization import (
    check_pod_distribution,
    check_scaling_capacity,
    compare_deployment_revisions,
    validate_probe_configuration,
)
from apps.opspilot.metis.llm.tools.kubernetes.query import kubectl_get_all_resources, kubectl_get_resources
from apps.opspilot.metis.llm.tools.kubernetes.remediation import (
    delete_kubernetes_resource,
    get_deployment_revision_history,
    restart_pod,
    rollback_deployment,
    scale_deployment,
    wait_for_pod_ready,
)
from apps.opspilot.metis.llm.tools.kubernetes.resources import (
    get_kubernetes_namespaces,
    get_kubernetes_pod_logs,
    get_kubernetes_previous_pod_logs,
    get_kubernetes_resource_yaml,
    list_kubernetes_deployments,
    list_kubernetes_events,
    list_kubernetes_nodes,
    list_kubernetes_pods,
    list_kubernetes_services,
    search_workload_across_namespaces,
)
from apps.opspilot.metis.llm.tools.kubernetes.tracing import (
    analyze_pod_restart_pattern,
    check_oom_events,
    get_resource_events_timeline,
    trace_service_chain,
)

# 工具集构造参数元数据
from apps.opspilot.metis.llm.tools.kubernetes.utils import format_bytes, parse_resource_quantity, prepare_context, get_current_cluster_name

CONSTRUCTOR_PARAMS = [
    {
        "name": "kubernetes_instances",
        "type": "array",
        "required": False,
        "description": "Kubernetes 实例列表，每个实例包含 id、name、kubeconfig_data",
    },
]


# 导入所有工具函数，保持向后兼容性

__all__ = [
    # 基础资源查询工具
    "get_kubernetes_namespaces",
    "list_kubernetes_pods",
    "list_kubernetes_nodes",
    "list_kubernetes_deployments",
    "list_kubernetes_services",
    "list_kubernetes_events",
    "get_kubernetes_resource_yaml",
    "get_kubernetes_pod_logs",
    "get_kubernetes_previous_pod_logs",
    "search_workload_across_namespaces",
    # 故障诊断和监控工具    "get_failed_kubernetes_pods",
    "get_pending_kubernetes_pods",
    "get_high_restart_kubernetes_pods",
    "get_kubernetes_node_capacity",
    "get_kubernetes_orphaned_resources",
    "diagnose_kubernetes_pod_issues",
    "diagnose_node_issues",
    # 配置分析和策略检查工具
    "check_kubernetes_resource_quotas",
    "check_kubernetes_network_policies",
    "check_kubernetes_persistent_volumes",
    "check_kubernetes_ingress",
    "check_kubernetes_daemonsets",
    "check_kubernetes_statefulsets",
    "check_kubernetes_jobs",
    "check_kubernetes_endpoints",
    "analyze_deployment_configurations",
    "check_kubernetes_hpa_status",
    # 集群检查和连接工具
    "verify_kubernetes_connection",
    "get_kubernetes_contexts",
    "list_kubernetes_api_resources",
    "explain_kubernetes_resource",
    "describe_kubernetes_resource",
    "kubernetes_troubleshooting_guide",
    # 高级查询工具
    "kubectl_get_resources",
    "kubectl_get_all_resources",
    # 链路追踪和关联分析工具 (P0)
    "trace_service_chain",
    "get_resource_events_timeline",
    "analyze_pod_restart_pattern",
    "check_oom_events",
    # 故障自愈工具 (P1)
    "restart_pod",
    "scale_deployment",
    "get_deployment_revision_history",
    "rollback_deployment",
    "delete_kubernetes_resource",
    "wait_for_pod_ready",
    # 配置优化工具 (P2)
    "check_scaling_capacity",
    "check_pod_distribution",
    "validate_probe_configuration",
    "compare_deployment_revisions",
    # 高级诊断工具 (P0-新增)
    "diagnose_pending_pod_issues",
    "check_network_policies_blocking",
    "check_pvc_capacity",
    # 批量操作工具 (P1-新增)
    "batch_restart_pods",
    "find_configmap_consumers",
    "cleanup_failed_pods",
    # 告警驱动采集编排工具
    "normalize_alert_event",
    "resolve_k8s_target_from_alert",
    "collect_k8s_context_by_target_type",
    "build_incident_evidence_package",
    # 通用工具函数
    "prepare_context",
    "format_bytes",
    "parse_resource_quantity",
    "get_current_cluster_name",
]


# ---------------------------------------------------------------------------
# 执行后验证元数据（附加到操作类工具）
# ---------------------------------------------------------------------------

_VERIFICATION_TOOLS = [
    (
        restart_pod,
        {
            "verify_tool": "list_kubernetes_pods",
            "args_mapping": {"namespace": "namespace"},
            "delay_seconds": 5.0,
            "description": "验证 Pod 重启后状态是否恢复为 Running",
        },
    ),
    (
        scale_deployment,
        {
            "verify_tool": "list_kubernetes_deployments",
            "args_mapping": {"namespace": "namespace"},
            "delay_seconds": 5.0,
            "description": "验证 Deployment 副本数是否已调整到目标值",
        },
    ),
    (
        delete_kubernetes_resource,
        {
            "verify_tool": "kubectl_get_resources",
            "args_mapping": {"namespace": "namespace"},
            "delay_seconds": 3.0,
            "description": "验证资源是否已被成功删除",
        },
    ),
    (
        rollback_deployment,
        {
            "verify_tool": "list_kubernetes_deployments",
            "args_mapping": {"namespace": "namespace"},
            "delay_seconds": 5.0,
            "description": "验证 Deployment 是否已成功回滚到指定版本",
        },
    ),
]

for _tool_obj, _verify_spec in _VERIFICATION_TOOLS:
    if not hasattr(_tool_obj, "metadata") or _tool_obj.metadata is None:
        _tool_obj.metadata = {}
    _tool_obj.metadata["verification"] = _verify_spec


# ---------------------------------------------------------------------------
# 操作回滚元数据（附加到操作类工具）
# ---------------------------------------------------------------------------

_ROLLBACK_TOOLS = [
    (
        scale_deployment,
        {
            "snapshot_tool": "list_kubernetes_deployments",
            "snapshot_args_mapping": {"namespace": "namespace"},
            "rollback_tool": "scale_deployment",
            "rollback_args_mapping": {"deployment_name": "deployment_name", "namespace": "namespace"},
            "rollback_snapshot_args": {},
            "strategy": "prompt",
            "description": "回滚 Deployment 副本数到操作前的值",
        },
    ),
    (
        rollback_deployment,
        {
            "snapshot_tool": "get_deployment_revision_history",
            "snapshot_args_mapping": {"deployment_name": "deployment_name", "namespace": "namespace"},
            "rollback_tool": "rollback_deployment",
            "rollback_args_mapping": {"deployment_name": "deployment_name", "namespace": "namespace"},
            "rollback_snapshot_args": {},
            "strategy": "prompt",
            "description": "回滚操作可通过再次回滚到之前的 revision 来撤销",
        },
    ),
    (
        restart_pod,
        {
            "strategy": "none",
            "description": "Pod 重启由控制器重建，不可回滚",
        },
    ),
    (
        delete_kubernetes_resource,
        {
            "strategy": "none",
            "description": "资源删除不可自动回滚，需手动重新创建",
        },
    ),
]

for _tool_obj, _rb_spec in _ROLLBACK_TOOLS:
    if not hasattr(_tool_obj, "metadata") or _tool_obj.metadata is None:
        _tool_obj.metadata = {}
    _tool_obj.metadata["rollback"] = _rb_spec
