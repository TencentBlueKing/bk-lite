"""Kubernetes 高级查询 @tool 单元测试 (kubernetes/query)。

mock prepare_context(kubeconfig 边界)与 client.*Api,驱动 kubectl_get_resources
分派到各资源 helper;断言别名解析、label/field selector 转发、json/table 输出、
就绪/重启统计、age 计算、外部IP/节点IP 推导、不支持类型与异常包装。
另直接测纯函数 helper(_get_pod_ready_status 等)。不连真实集群。
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.metis.llm.tools.kubernetes import query as q


@pytest.fixture
def apis():
    core, apps = MagicMock(), MagicMock()
    with patch.object(q, "prepare_context", return_value=None), patch.object(q.client, "CoreV1Api", return_value=core), patch.object(
        q.client, "AppsV1Api", return_value=apps
    ):
        yield core, apps


def _pod(name, phase="Running", statuses=None, ip="1.2.3.4", node="n1", ts=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace="default", creation_timestamp=ts),
        status=SimpleNamespace(phase=phase, container_statuses=statuses, pod_ip=ip),
        spec=SimpleNamespace(node_name=node),
    )


# ---------------- pure helpers ----------------
class TestPureHelpers:
    def test_ready_status(self):
        pod = _pod("p", statuses=[SimpleNamespace(ready=True, restart_count=0), SimpleNamespace(ready=False, restart_count=0)])
        assert q._get_pod_ready_status(pod) == "1/2"

    def test_ready_status_no_containers(self):
        assert q._get_pod_ready_status(_pod("p", statuses=None)) == "0/0"

    def test_restart_count_sum(self):
        pod = _pod("p", statuses=[SimpleNamespace(ready=True, restart_count=2), SimpleNamespace(ready=True, restart_count=3)])
        assert q._get_pod_restart_count(pod) == 5

    def test_restart_count_none(self):
        assert q._get_pod_restart_count(_pod("p", statuses=None)) == 0

    def test_calculate_age_days_hours_minutes(self):
        now = datetime.now(timezone.utc)
        assert q._calculate_age(now - timedelta(days=3)) == "3d"
        assert q._calculate_age(now - timedelta(hours=5)) == "5h"
        assert q._calculate_age(now - timedelta(minutes=10)).endswith("m")
        assert q._calculate_age(None) == "unknown"

    def test_external_ip_nodeport(self):
        svc = SimpleNamespace(spec=SimpleNamespace(type="NodePort", external_i_ps=None), status=SimpleNamespace(load_balancer=None))
        assert q._get_external_ip(svc) == "<nodes>"

    def test_external_ip_loadbalancer(self):
        ing = SimpleNamespace(ip="9.9.9.9", hostname=None)
        svc = SimpleNamespace(
            spec=SimpleNamespace(type="LoadBalancer", external_i_ps=None),
            status=SimpleNamespace(load_balancer=SimpleNamespace(ingress=[ing])),
        )
        assert q._get_external_ip(svc) == "9.9.9.9"

    def test_node_internal_ip(self):
        node = SimpleNamespace(status=SimpleNamespace(addresses=[SimpleNamespace(type="InternalIP", address="10.0.0.5")]))
        assert q._get_node_internal_ip(node) == "10.0.0.5"
        assert q._get_node_external_ip(node) == "<none>"


# ---------------- kubectl_get_resources: pods ----------------
class TestGetPods:
    def test_json_output_with_selectors(self, apis):
        core, _ = apis
        cstat = [SimpleNamespace(ready=True, restart_count=1)]
        core.list_namespaced_pod.return_value = SimpleNamespace(items=[_pod("p1", statuses=cstat)])
        out = json.loads(
            q.kubectl_get_resources.invoke(
                {"resource_type": "po", "namespace": "default", "label_selector": "app=nginx", "field_selector": "status.phase=Running", "config": {}}
            )
        )
        assert out["total"] == 1
        assert out["items"][0]["ready"] == "1/1"
        assert out["items"][0]["restarts"] == 1
        assert out["items"][0]["status"] == "Running"
        core.list_namespaced_pod.assert_called_once_with(namespace="default", label_selector="app=nginx", field_selector="status.phase=Running")

    def test_all_namespaces(self, apis):
        core, _ = apis
        core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[])
        out = json.loads(q.kubectl_get_resources.invoke({"resource_type": "pods", "config": {}}))
        assert out == {"items": [], "total": 0}
        core.list_pod_for_all_namespaces.assert_called_once()

    def test_table_output(self, apis):
        core, _ = apis
        cstat = [SimpleNamespace(ready=True, restart_count=0)]
        core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[_pod("webpod", statuses=cstat)])
        out = q.kubectl_get_resources.invoke({"resource_type": "pods", "output_format": "table", "config": {}})
        assert "NAME" in out
        assert "webpod" in out


# ---------------- kubectl_get_resources: deployments / nodes / namespaces ----------------
class TestOtherResources:
    def test_deployments_alias(self, apis):
        _, apps = apis
        dep = SimpleNamespace(
            metadata=SimpleNamespace(name="d", namespace="default", creation_timestamp=None),
            spec=SimpleNamespace(replicas=2),
            status=SimpleNamespace(ready_replicas=2, updated_replicas=2, available_replicas=2),
        )
        apps.list_deployment_for_all_namespaces.return_value = SimpleNamespace(items=[dep])
        out = json.loads(q.kubectl_get_resources.invoke({"resource_type": "deploy", "config": {}}))
        assert out["total"] == 1
        assert out["items"][0]["ready"] == "2/2"

    def test_nodes(self, apis):
        core, _ = apis
        node = SimpleNamespace(
            metadata=SimpleNamespace(name="n1", creation_timestamp=None, labels={}),
            status=SimpleNamespace(
                conditions=[SimpleNamespace(type="Ready", status="True")],
                addresses=[SimpleNamespace(type="InternalIP", address="10.0.0.1")],
                node_info=SimpleNamespace(kubelet_version="v1.28"),
            ),
        )
        core.list_node.return_value = SimpleNamespace(items=[node])
        out = json.loads(q.kubectl_get_resources.invoke({"resource_type": "no", "config": {}}))
        assert out["total"] == 1

    def test_namespaces(self, apis):
        core, _ = apis
        ns = SimpleNamespace(
            metadata=SimpleNamespace(name="default", creation_timestamp=None),
            status=SimpleNamespace(phase="Active"),
        )
        core.list_namespace.return_value = SimpleNamespace(items=[ns])
        out = json.loads(q.kubectl_get_resources.invoke({"resource_type": "ns", "config": {}}))
        assert out["total"] == 1


# ---------------- dispatcher edges ----------------
class TestDispatcherEdges:
    def test_unsupported_type(self, apis):
        out = json.loads(q.kubectl_get_resources.invoke({"resource_type": "widgets", "config": {}}))
        assert "暂不支持的资源类型" in out["error"]
        assert "pods" in out["supported_types"]

    def test_exception_wrapped(self, apis):
        core, _ = apis
        core.list_pod_for_all_namespaces.side_effect = RuntimeError("api down")
        out = json.loads(q.kubectl_get_resources.invoke({"resource_type": "pods", "config": {}}))
        assert "查询资源失败" in out["error"]
        assert out["resource_type"] == "pods"


def test_kubectl_get_resources_routes_explicit_second_cluster(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.query import kubectl_get_resources

    loaded = []
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.utils.config.load_kube_config",
        side_effect=lambda config_file: loaded.append(config_file.read()),
    )
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.utils.validate_kubeconfig_api_servers")
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.utils._preprocess_kubeconfig", side_effect=lambda value: value)
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.query._get_pods", side_effect=lambda *args: loaded[-1])
    config = {
        "configurable": {
            "kubernetes_instances": [
                {"id": "one", "name": "first", "kubeconfig_data": "cluster-first"},
                {"id": "two", "name": "second", "kubeconfig_data": "cluster-second"},
            ]
        }
    }

    result = kubectl_get_resources.invoke({"resource_type": "pods", "instance_name": "second"}, config=config)

    assert result == "cluster-second"
    assert loaded == ["cluster-second"]


def test_kubectl_get_resources_refuses_ambiguous_cluster(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.query import kubectl_get_resources

    prepare = mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.query.prepare_context")
    config = {
        "configurable": {
            "kubernetes_instances": [
                {"id": "one", "name": "first", "kubeconfig_data": "cluster-first"},
                {"id": "two", "name": "second", "kubeconfig_data": "cluster-second"},
            ]
        }
    }
    result = json.loads(kubectl_get_resources.invoke({"resource_type": "pods"}, config=config))
    assert result["instance_names"] == ["first", "second"]
    prepare.assert_not_called()


def test_explicit_analysis_cluster_overrides_previously_bound_id(mocker):
    from apps.opspilot.metis.llm.tools.kubernetes.analysis import check_kubernetes_daemonsets

    loaded = []
    mocker.patch(
        "apps.opspilot.metis.llm.tools.kubernetes.utils.config.load_kube_config", side_effect=lambda config_file: loaded.append(config_file.read())
    )
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.utils.validate_kubeconfig_api_servers")
    mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.utils._preprocess_kubeconfig", side_effect=lambda value: value)
    api = mocker.patch("apps.opspilot.metis.llm.tools.kubernetes.analysis.client.AppsV1Api").return_value
    api.list_daemon_set_for_all_namespaces.return_value.items = []
    config = {
        "configurable": {
            "instance_id": "one",
            "instance_name": "first",
            "kubernetes_instances": [
                {"id": "one", "name": "first", "kubeconfig_data": "cluster-first"},
                {"id": "two", "name": "second", "kubeconfig_data": "cluster-second"},
            ],
        }
    }
    result = json.loads(check_kubernetes_daemonsets.invoke({"instance_name": "second"}, config=config))
    assert result["cluster_name"] == "second"
    assert loaded == ["cluster-second"]
    assert config["configurable"]["instance_id"] == "one"
