from src.tools.jenkins_tools import list_jenkins_jobs, trigger_jenkins_build
from src.tools.search_tools import duckduckgo_search
from src.tools.time_tools import get_current_time
from src.tools.kubernetes_tools import (
    get_kubernetes_namespaces, list_kubernetes_pods, list_kubernetes_nodes,
    list_kubernetes_deployments, list_kubernetes_services, list_kubernetes_events,
    get_failed_kubernetes_pods, get_pending_kubernetes_pods, get_high_restart_kubernetes_pods,
    get_kubernetes_node_capacity, get_kubernetes_orphaned_resources,
    get_kubernetes_resource_yaml, get_kubernetes_pod_logs
)

ToolsMap = {
    'current_time': [get_current_time],
    'duckduckgo': [duckduckgo_search],
    'jenkins': [
        list_jenkins_jobs,
        trigger_jenkins_build
    ],
    'kubernetes': [
        get_kubernetes_namespaces,
        list_kubernetes_pods,
        list_kubernetes_nodes,
        list_kubernetes_deployments,
        list_kubernetes_services,
        list_kubernetes_events,
        get_failed_kubernetes_pods,
        get_pending_kubernetes_pods,
        get_high_restart_kubernetes_pods,
        get_kubernetes_node_capacity,
        get_kubernetes_orphaned_resources,
        get_kubernetes_resource_yaml,
        get_kubernetes_pod_logs
    ]
}


class ToolsLoader:

    @staticmethod
    def load_tools(tools_protocol: str):
        tools_name = tools_protocol.split(":")[1]
        return ToolsMap[tools_name]
