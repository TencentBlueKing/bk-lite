"""Kubernetes 资源查询 @tool 扩展单元测试 (kubernetes/resources, 未覆盖工具)。

mock kubernetes.client 各 Api(CoreV1Api/AppsV1Api/BatchV1Api) 与 prepare_context
(kubeconfig 加载边界),断言 nodes/deployments/services/events/resource_yaml/
previous_pod_logs/search_workload 的结构化输出、分页、Ready 判定、YAML 字段过滤、
ApiException 翻译与 previous 日志缺失分支。不连真实集群。
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.metis.llm.tools.kubernetes import resources as res
from apps.opspilot.metis.llm.tools.kubernetes.resources import ApiException


@pytest.fixture
def apis():
    """patch prepare_context + 三个 Api 工厂,返回 (core, apps, batch) mock。"""
    core, apps, batch = MagicMock(), MagicMock(), MagicMock()
    with patch.object(res, "prepare_context", return_value=None), \
         patch.object(res.client, "CoreV1Api", return_value=core), \
         patch.object(res.client, "AppsV1Api", return_value=apps), \
         patch.object(res.client, "BatchV1Api", return_value=batch):
        yield core, apps, batch


def _meta(name, namespace=None, ts=None, labels=None):
    return SimpleNamespace(name=name, namespace=namespace, creation_timestamp=ts, labels=labels)


# ---------------- list_kubernetes_nodes ----------------
class TestListNodes:
    def test_ready_and_addresses(self, apis):
        core, _, _ = apis
        cond_ready = SimpleNamespace(type="Ready", status="True", reason="KubeletReady", message="ok")
        node = SimpleNamespace(
            metadata=_meta("node-1", labels={"role": "master"}),
            status=SimpleNamespace(
                conditions=[cond_ready],
                allocatable={"cpu": "4", "memory": "8Gi", "pods": "110"},
                node_info=SimpleNamespace(kubelet_version="v1.28.0"),
                addresses=[SimpleNamespace(type="InternalIP", address="10.0.0.1")],
            ),
        )
        core.list_node.return_value = SimpleNamespace(items=[node])
        out = json.loads(res.list_kubernetes_nodes.invoke({"config": {}}))
        assert out[0]["name"] == "node-1"
        assert out[0]["status"] == "Ready"
        assert out[0]["version"] == "v1.28.0"
        assert out[0]["allocatable"]["cpu"] == "4"
        assert out[0]["addresses"] == [{"type": "InternalIP", "address": "10.0.0.1"}]
        assert out[0]["roles"] == ["role"]

    def test_notready_when_no_ready_condition(self, apis):
        core, _, _ = apis
        cond = SimpleNamespace(type="DiskPressure", status="False", reason="", message="")
        node = SimpleNamespace(
            metadata=_meta("node-2", labels=None),
            status=SimpleNamespace(conditions=[cond], allocatable=None,
                                   node_info=None, addresses=None),
        )
        core.list_node.return_value = SimpleNamespace(items=[node])
        out = json.loads(res.list_kubernetes_nodes.invoke({"config": {}}))
        assert out[0]["status"] == "NotReady"
        assert out[0]["version"] == ""
        assert out[0]["roles"] == []

    def test_api_exception(self, apis):
        core, _, _ = apis
        core.list_node.side_effect = ApiException(status=500, reason="boom")
        out = json.loads(res.list_kubernetes_nodes.invoke({"config": {}}))
        assert "获取节点列表失败" in out["error"]


# ---------------- list_kubernetes_deployments ----------------
class TestListDeployments:
    def _dep(self, name, replicas=3, ready=3):
        return SimpleNamespace(
            metadata=_meta(name, namespace="default", labels={"app": name}),
            spec=SimpleNamespace(replicas=replicas, selector=SimpleNamespace(match_labels={"app": name})),
            status=SimpleNamespace(ready_replicas=ready, available_replicas=ready, updated_replicas=ready),
        )

    def test_pagination_and_has_more(self, apis):
        _, apps, _ = apis
        deps = [self._dep(f"d{i}") for i in range(5)]
        apps.list_deployment_for_all_namespaces.return_value = SimpleNamespace(items=deps)
        out = json.loads(res.list_kubernetes_deployments.invoke({"limit": 2, "offset": 1, "config": {}}))
        assert out["total"] == 5
        assert out["returned"] == 2
        assert out["offset"] == 1
        assert out["has_more"] is True
        assert out["items"][0]["name"] == "d1"
        assert out["items"][0]["ready_replicas"] == 3

    def test_namespaced_and_limit_clamped(self, apis):
        _, apps, _ = apis
        apps.list_namespaced_deployment.return_value = SimpleNamespace(items=[self._dep("d", ready=None)])
        out = json.loads(res.list_kubernetes_deployments.invoke(
            {"namespace": "prod", "limit": 999, "config": {}}))
        apps.list_namespaced_deployment.assert_called_once_with("prod")
        # ready_replicas None -> 0
        assert out["items"][0]["ready_replicas"] == 0
        assert out["has_more"] is False

    def test_api_exception(self, apis):
        _, apps, _ = apis
        apps.list_deployment_for_all_namespaces.side_effect = ApiException(status=403, reason="forbidden")
        out = json.loads(res.list_kubernetes_deployments.invoke({"config": {}}))
        assert "获取Deployment列表失败" in out["error"]


# ---------------- list_kubernetes_services ----------------
class TestListServices:
    def test_ports_and_external_ip(self, apis):
        core, _, _ = apis
        port = SimpleNamespace(name="http", port=80, target_port=8080, protocol="TCP", node_port=30080)
        ingress = SimpleNamespace(ip="1.2.3.4", hostname=None)
        svc = SimpleNamespace(
            metadata=_meta("web", namespace="default"),
            spec=SimpleNamespace(type="LoadBalancer", cluster_ip="10.96.0.1", ports=[port], selector={"app": "web"}),
            status=SimpleNamespace(load_balancer=SimpleNamespace(ingress=[ingress])),
        )
        core.list_service_for_all_namespaces.return_value = SimpleNamespace(items=[svc])
        out = json.loads(res.list_kubernetes_services.invoke({"config": {}}))
        assert out[0]["type"] == "LoadBalancer"
        assert out[0]["external_ips"] == ["1.2.3.4"]
        assert out[0]["ports"][0] == {"name": "http", "port": 80, "target_port": "8080",
                                      "protocol": "TCP", "node_port": 30080}

    def test_hostname_external_ip(self, apis):
        core, _, _ = apis
        ingress = SimpleNamespace(ip=None, hostname="lb.example.com")
        svc = SimpleNamespace(
            metadata=_meta("web", namespace="default"),
            spec=SimpleNamespace(type="ClusterIP", cluster_ip="10.0.0.1", ports=None, selector=None),
            status=SimpleNamespace(load_balancer=SimpleNamespace(ingress=[ingress])),
        )
        core.list_namespaced_service.return_value = SimpleNamespace(items=[svc])
        out = json.loads(res.list_kubernetes_services.invoke({"namespace": "default", "config": {}}))
        assert out[0]["external_ips"] == ["lb.example.com"]
        assert out[0]["ports"] == []
        assert out[0]["selector"] == {}


# ---------------- list_kubernetes_events ----------------
class TestListEvents:
    def test_event_object_formatting(self, apis):
        core, _, _ = apis
        ev = SimpleNamespace(
            type="Warning", reason="BackOff", message="Back-off restarting",
            involved_object=SimpleNamespace(kind="Pod", name="p1"),
            metadata=SimpleNamespace(namespace="default"),
            count=5, first_timestamp=None, last_timestamp=None,
        )
        core.list_event_for_all_namespaces.return_value = SimpleNamespace(items=[ev])
        out = json.loads(res.list_kubernetes_events.invoke({"config": {}}))
        assert out[0]["object"] == "Pod/p1"
        assert out[0]["type"] == "Warning"
        assert out[0]["count"] == 5

    def test_api_exception(self, apis):
        core, _, _ = apis
        core.list_event_for_all_namespaces.side_effect = ApiException(status=500, reason="x")
        out = json.loads(res.list_kubernetes_events.invoke({"config": {}}))
        assert "获取事件列表失败" in out["error"]


# ---------------- get_kubernetes_resource_yaml ----------------
class TestResourceYaml:
    def test_unsupported_type(self, apis):
        out = res.get_kubernetes_resource_yaml.invoke(
            {"namespace": "default", "resource_type": "ingress", "resource_name": "x", "config": {}})
        assert "不支持的资源类型" in out

    def test_pod_yaml_strips_status_and_managed_fields(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.return_value = MagicMock()
        sanitized = {
            "metadata": {"name": "p1", "managedFields": [{"x": 1}],
                         "annotations": {"kubectl.kubernetes.io/last-applied-configuration": "{}", "keep": "v"}},
            "status": {"phase": "Running"},
            "spec": {"containers": []},
        }
        api_client = MagicMock()
        api_client.sanitize_for_serialization.return_value = sanitized
        with patch.object(res.client, "ApiClient", return_value=api_client):
            out = res.get_kubernetes_resource_yaml.invoke(
                {"namespace": "default", "resource_type": "pod", "resource_name": "p1", "config": {}})
        assert "managedFields" not in out
        assert "last-applied-configuration" not in out
        assert "status" not in out
        assert "keep: v" in out
        core.read_namespaced_pod.assert_called_once_with("p1", "default")

    def test_api_exception(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.side_effect = ApiException(status=404, reason="not found")
        out = res.get_kubernetes_resource_yaml.invoke(
            {"namespace": "default", "resource_type": "pod", "resource_name": "p1", "config": {}})
        assert "获取资源YAML失败" in out


# ---------------- get_kubernetes_previous_pod_logs ----------------
class TestPreviousPodLogs:
    def _pod(self, containers):
        return SimpleNamespace(spec=SimpleNamespace(containers=containers))

    def test_pod_not_found_404(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.side_effect = ApiException(status=404, reason="not found")
        out = res.get_kubernetes_previous_pod_logs.invoke(
            {"namespace": "ns", "pod_name": "p1", "config": {}})
        assert "不存在" in out

    def test_multi_container_requires_name(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.return_value = self._pod(
            [SimpleNamespace(name="a"), SimpleNamespace(name="b")])
        out = res.get_kubernetes_previous_pod_logs.invoke(
            {"namespace": "ns", "pod_name": "p1", "config": {}})
        assert "请指定容器名称" in out

    def test_single_container_auto_selected_returns_logs(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.return_value = self._pod([SimpleNamespace(name="app")])
        core.read_namespaced_pod_log.return_value = "panic: boom\nstack trace"
        out = res.get_kubernetes_previous_pod_logs.invoke(
            {"namespace": "ns", "pod_name": "p1", "config": {}})
        assert "panic: boom" in out
        # previous=True 必须传入
        _, kwargs = core.read_namespaced_pod_log.call_args
        assert kwargs["previous"] is True
        assert kwargs["container"] == "app"

    def test_empty_previous_logs(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.return_value = self._pod([SimpleNamespace(name="app")])
        core.read_namespaced_pod_log.return_value = ""
        out = res.get_kubernetes_previous_pod_logs.invoke(
            {"namespace": "ns", "pod_name": "p1", "config": {}})
        assert "没有上一次实例的日志" in out

    def test_no_previous_terminated_container(self, apis):
        core, _, _ = apis
        core.read_namespaced_pod.return_value = self._pod([SimpleNamespace(name="app")])
        core.read_namespaced_pod_log.side_effect = ApiException(
            status=400, reason="previous terminated container not found")
        out = res.get_kubernetes_previous_pod_logs.invoke(
            {"namespace": "ns", "pod_name": "p1", "config": {}})
        assert "没有可用的 previous 日志" in out


# ---------------- search_workload_across_namespaces ----------------
class TestSearchWorkload:
    def _patch_instances(self, instances):
        from apps.opspilot.metis.llm.tools.kubernetes import connection as conn
        return patch.object(conn, "get_kubernetes_instances_from_configurable", return_value=instances)

    def test_unique_default_cluster(self, apis):
        _, apps, _ = apis
        dep = SimpleNamespace(
            metadata=_meta("scheduler", namespace="prod"),
            spec=SimpleNamespace(replicas=2),
            status=SimpleNamespace(ready_replicas=2),
        )
        apps.list_deployment_for_all_namespaces.return_value = SimpleNamespace(items=[dep])
        apps.list_stateful_set_for_all_namespaces.return_value = SimpleNamespace(items=[])
        apps.list_daemon_set_for_all_namespaces.return_value = SimpleNamespace(items=[])
        with self._patch_instances([]):
            out = json.loads(res.search_workload_across_namespaces.invoke(
                {"workload_name": "scheduler", "config": {}}))
        assert out["found"] is True
        assert out["unique"] is True
        assert out["total_count"] == 1
        assert out["locations"][0]["cluster"] == "default"
        assert out["locations"][0]["kind"] == "Deployment"
        assert "全局唯一" in out["_next_step_hint"]

    def test_not_found(self, apis):
        _, apps, _ = apis
        empty = SimpleNamespace(items=[])
        apps.list_deployment_for_all_namespaces.return_value = empty
        apps.list_stateful_set_for_all_namespaces.return_value = empty
        apps.list_daemon_set_for_all_namespaces.return_value = empty
        with self._patch_instances([]):
            out = json.loads(res.search_workload_across_namespaces.invoke(
                {"workload_name": "ghost", "config": {}}))
        assert out["found"] is False
        assert out["total_count"] == 0
        assert "未找到" in out["_next_step_hint"]
