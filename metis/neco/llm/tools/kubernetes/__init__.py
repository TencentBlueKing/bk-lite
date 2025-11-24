"""Kubernetes工具模块

这个模块包含了所有Kubernetes相关的工具函数，按功能分类到不同的子模块中：
- resources: 基础资源查询工具
- diagnostics: 故障诊断和监控工具
- analysis: 配置分析和策略检查工具
- utils: 通用辅助函数
"""

# 导入所有工具函数，保持向后兼容性
from neco.llm.tools.kubernetes.resources import (
    get_kubernetes_namespaces,
    list_kubernetes_pods,
    list_kubernetes_nodes,
    list_kubernetes_deployments,
    list_kubernetes_services,
    list_kubernetes_events,
    get_kubernetes_resource_yaml,
    get_kubernetes_pod_logs,
)

from neco.llm.tools.kubernetes.diagnostics import (
    get_failed_kubernetes_pods,
    get_pending_kubernetes_pods,
    get_high_restart_kubernetes_pods,
    get_kubernetes_node_capacity,
    get_kubernetes_orphaned_resources,
    diagnose_kubernetes_pod_issues,
)

from neco.llm.tools.kubernetes.analysis import (
    check_kubernetes_resource_quotas,
    check_kubernetes_network_policies,
    check_kubernetes_persistent_volumes,
    check_kubernetes_ingress,
    check_kubernetes_daemonsets,
    check_kubernetes_statefulsets,
    check_kubernetes_jobs,
    check_kubernetes_endpoints,
    analyze_deployment_configurations,
    check_kubernetes_hpa_status,
)

from neco.llm.tools.kubernetes.utils import (
    prepare_context,
    format_bytes,
    parse_resource_quantity,
)

from neco.llm.tools.kubernetes.cluster import (
    verify_kubernetes_connection,
    get_kubernetes_contexts,
    list_kubernetes_api_resources,
    explain_kubernetes_resource,
    describe_kubernetes_resource,
    kubernetes_troubleshooting_guide,
)

from neco.llm.tools.kubernetes.query import (
    kubectl_get_resources,
    kubectl_get_all_resources,
)

from neco.llm.tools.kubernetes.tracing import (
    trace_service_chain,
    get_resource_events_timeline,
    analyze_pod_restart_pattern,
    check_oom_events,
)

from neco.llm.tools.kubernetes.remediation import (
    restart_pod,
    scale_deployment,
    get_deployment_revision_history,
    rollback_deployment,
    delete_kubernetes_resource,
    wait_for_pod_ready,
)

from neco.llm.tools.kubernetes.optimization import (
    check_scaling_capacity,
    check_pod_distribution,
    validate_probe_configuration,
    compare_deployment_revisions,
)

from neco.llm.tools.kubernetes.diagnostics_advanced import (
    diagnose_pending_pod_issues,
    check_network_policies_blocking,
    check_pvc_capacity,
)

from neco.llm.tools.kubernetes.batch_operations import (
    batch_restart_pods,
    find_configmap_consumers,
    cleanup_failed_pods,
)

__all__ = [
    # 基础资源查询工具
    'get_kubernetes_namespaces',
    'list_kubernetes_pods',
    'list_kubernetes_nodes',
    'list_kubernetes_deployments',
    'list_kubernetes_services',
    'list_kubernetes_events',
    'get_kubernetes_resource_yaml',
    'get_kubernetes_pod_logs',

    # 故障诊断和监控工具
    'get_failed_kubernetes_pods',
    'get_pending_kubernetes_pods',
    'get_high_restart_kubernetes_pods',
    'get_kubernetes_node_capacity',
    'get_kubernetes_orphaned_resources',
    'diagnose_kubernetes_pod_issues',

    # 配置分析和策略检查工具
    'check_kubernetes_resource_quotas',
    'check_kubernetes_network_policies',
    'check_kubernetes_persistent_volumes',
    'check_kubernetes_ingress',
    'check_kubernetes_daemonsets',
    'check_kubernetes_statefulsets',
    'check_kubernetes_jobs',
    'check_kubernetes_endpoints',
    'analyze_deployment_configurations',
    'check_kubernetes_hpa_status',

    # 集群检查和连接工具
    'verify_kubernetes_connection',
    'get_kubernetes_contexts',
    'list_kubernetes_api_resources',
    'explain_kubernetes_resource',
    'describe_kubernetes_resource',
    'kubernetes_troubleshooting_guide',

    # 高级查询工具
    'kubectl_get_resources',
    'kubectl_get_all_resources',

    # 链路追踪和关联分析工具 (P0)
    'trace_service_chain',
    'get_resource_events_timeline',
    'analyze_pod_restart_pattern',
    'check_oom_events',

    # 故障自愈工具 (P1)
    'restart_pod',
    'scale_deployment',
    'get_deployment_revision_history',
    'rollback_deployment',
    'delete_kubernetes_resource',
    'wait_for_pod_ready',

    # 配置优化工具 (P2)
    'check_scaling_capacity',
    'check_pod_distribution',
    'validate_probe_configuration',
    'compare_deployment_revisions',

    # 高级诊断工具 (P0-新增)
    'diagnose_pending_pod_issues',
    'check_network_policies_blocking',
    'check_pvc_capacity',

    # 批量操作工具 (P1-新增)
    'batch_restart_pods',
    'find_configmap_consumers',
    'cleanup_failed_pods',

    # 通用工具函数
    'prepare_context',
    'format_bytes',
    'parse_resource_quantity',
]
