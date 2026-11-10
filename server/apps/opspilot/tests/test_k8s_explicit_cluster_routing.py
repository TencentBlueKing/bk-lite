"""Kubernetes 公开工具必须把明确选择的集群传到连接层。"""

import importlib

import pytest

CASES = [
    ("analysis", name, {})
    for name in (
        "check_kubernetes_resource_quotas",
        "check_kubernetes_network_policies",
        "check_kubernetes_persistent_volumes",
        "check_kubernetes_ingress",
        "check_kubernetes_jobs",
        "check_kubernetes_endpoints",
        "check_kubernetes_hpa_status",
    )
] + [
    ("query", "kubectl_get_resources", {"resource_type": "pods"}),
    ("query", "kubectl_get_all_resources", {}),
    ("node_diagnostics", "diagnose_node_issues", {"node_name": "node"}),
    ("diagnostics", "get_kubernetes_node_capacity", {}),
    ("diagnostics", "get_kubernetes_orphaned_resources", {}),
    ("optimization", "check_pod_distribution", {"deployment_name": "app", "namespace": "default"}),
    ("diagnostics_advanced", "check_network_policies_blocking", {"source_namespace": "default"}),
    ("cluster", "verify_kubernetes_connection", {}),
    ("cluster", "list_kubernetes_api_resources", {}),
    ("resources", "get_kubernetes_namespaces", {}),
    ("resources", "list_kubernetes_nodes", {}),
    ("resources", "list_kubernetes_services", {}),
    ("remediation", "get_deployment_revision_history", {"deployment_name": "app", "namespace": "default"}),
    ("batch_operations", "find_configmap_consumers", {"configmap_name": "config", "namespace": "default"}),
]


@pytest.mark.parametrize(("module_name", "tool_name", "arguments"), CASES)
def test_tool_selects_second_cluster(module_name, tool_name, arguments, mocker):
    module = importlib.import_module(f"apps.opspilot.metis.llm.tools.kubernetes.{module_name}")

    class ConnectionReached(BaseException):
        pass

    prepare = mocker.patch.object(module, "prepare_context", side_effect=ConnectionReached)
    config = {
        "configurable": {
            "kubernetes_instances": [
                {"id": "one", "name": "first", "kubeconfig_data": "first-config"},
                {"id": "two", "name": "second", "kubeconfig_data": "second-config"},
            ]
        }
    }
    with pytest.raises(ConnectionReached):
        getattr(module, tool_name).invoke({**arguments, "instance_name": "second"}, config=config)
    bound = prepare.call_args.args[0]["configurable"]
    assert bound["instance_id"] == "two"
    assert bound["kubeconfig_data"] == "second-config"


def test_workload_search_only_scans_explicit_cluster(mocker):
    from types import SimpleNamespace

    from apps.opspilot.metis.llm.tools.kubernetes.resources import search_workload_across_namespaces

    loaded = []
    mocker.patch("kubernetes.config.load_kube_config", side_effect=lambda config_file: loaded.append(config_file.read()))
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.utils._preprocess_kubeconfig", side_effect=lambda value: value)
    api = mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.resources.client.AppsV1Api").return_value
    for method in ("list_deployment_for_all_namespaces", "list_stateful_set_for_all_namespaces", "list_daemon_set_for_all_namespaces"):
        getattr(api, method).return_value = SimpleNamespace(items=[])
    config = {
        "configurable": {
            "kubernetes_instances": [
                {"id": "one", "name": "first", "kubeconfig_data": "first-config"},
                {"id": "two", "name": "second", "kubeconfig_data": "second-config"},
            ]
        }
    }
    search_workload_across_namespaces.invoke({"workload_name": "app", "instance_name": "second"}, config=config)
    assert loaded == ["second-config"]
