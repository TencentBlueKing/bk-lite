"""Kubernetes 资源查询 @tool 单元测试 (kubernetes/resources)。

mock kubernetes.client 的 CoreV1Api 与 prepare_context(kube 配置加载边界),
断言工具产出的结构化 JSON、错误分支与日志选择逻辑。不连接真实集群。
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.kubernetes import resources as res
from apps.opspilot.metis.llm.tools.kubernetes.resources import ApiException


@pytest.fixture
def fake_core():
    """patch prepare_context (跳过 kubeconfig 加载) 与 CoreV1Api,返回可编排的 mock。"""
    core = MagicMock()
    with patch.object(res, "prepare_context", return_value=None), patch.object(res.client, "CoreV1Api", return_value=core):
        yield core


def _meta(name, namespace=None, ts=None, labels=None, annotations=None):
    return SimpleNamespace(
        name=name,
        namespace=namespace,
        creation_timestamp=ts,
        labels=labels,
        annotations=annotations,
    )


class TestGetKubernetesNamespaces:
    def test_returns_structured_list(self, fake_core):
        ns = SimpleNamespace(
            metadata=_meta("default", labels={"k": "v"}, annotations=None),
            status=SimpleNamespace(phase="Active"),
        )
        fake_core.list_namespace.return_value = SimpleNamespace(items=[ns])

        out = json.loads(res.get_kubernetes_namespaces.invoke({"config": {}}))
        assert out == [
            {"name": "default", "status": "Active", "creation_time": None, "labels": {"k": "v"}, "annotations": {}}
        ]

    def test_exception_returns_error_json(self, fake_core):
        fake_core.list_namespace.side_effect = RuntimeError("boom")
        out = json.loads(res.get_kubernetes_namespaces.invoke({"config": {}}))
        assert "error" in out
        assert "获取命名空间列表失败" in out["error"]


class TestListKubernetesPods:
    def _pod(self, name, phase="Running", containers=None, statuses=None):
        return SimpleNamespace(
            metadata=_meta(name, namespace="default", labels=None),
            status=SimpleNamespace(phase=phase, pod_ip="1.2.3.4", container_statuses=statuses),
            spec=SimpleNamespace(node_name="node-1", restart_policy="Always", containers=containers or []),
        )

    def test_namespaced_pods_with_container_status(self, fake_core):
        cstatus = SimpleNamespace(name="app", ready=True, restart_count=2, image="img:1", state="running")
        fake_core.list_namespaced_pod.return_value = SimpleNamespace(items=[self._pod("p1", statuses=[cstatus])])

        out = json.loads(res.list_kubernetes_pods.invoke({"namespace": "default", "config": {}}))
        assert out[0]["name"] == "p1"
        assert out[0]["phase"] == "Running"
        assert out[0]["ip"] == "1.2.3.4"
        assert out[0]["node"] == "node-1"
        assert out[0]["containers"][0] == {
            "name": "app", "ready": True, "restart_count": 2, "image": "img:1", "state": "running"
        }
        fake_core.list_namespaced_pod.assert_called_once_with("default")

    def test_all_namespaces_when_none(self, fake_core):
        fake_core.list_pod_for_all_namespaces.return_value = SimpleNamespace(items=[])
        out = json.loads(res.list_kubernetes_pods.invoke({"config": {}}))
        assert out == []
        fake_core.list_pod_for_all_namespaces.assert_called_once()

    def test_api_exception_returns_error(self, fake_core):
        fake_core.list_pod_for_all_namespaces.side_effect = ApiException(status=500, reason="x")
        out = json.loads(res.list_kubernetes_pods.invoke({"config": {}}))
        assert "获取Pod列表失败" in out["error"]


class TestGetKubernetesPodLogs:
    def _pod_with_containers(self, names):
        return SimpleNamespace(spec=SimpleNamespace(containers=[SimpleNamespace(name=n) for n in names]))

    def test_pod_not_found_404(self, fake_core):
        fake_core.read_namespaced_pod.side_effect = ApiException(status=404, reason="nf")
        out = res.get_kubernetes_pod_logs.invoke({"namespace": "ns", "pod_name": "p", "config": {}})
        assert out == "Pod p 在命名空间 ns 中不存在"

    def test_multi_container_requires_name(self, fake_core):
        fake_core.read_namespaced_pod.return_value = self._pod_with_containers(["a", "b"])
        out = res.get_kubernetes_pod_logs.invoke({"namespace": "ns", "pod_name": "p", "config": {}})
        assert "包含多个容器" in out
        assert "请指定容器名称" in out

    def test_single_container_auto_selected_and_logs_returned(self, fake_core):
        fake_core.read_namespaced_pod.return_value = self._pod_with_containers(["only"])
        fake_core.read_namespaced_pod_log.return_value = "line1\nline2"
        out = res.get_kubernetes_pod_logs.invoke({"namespace": "ns", "pod_name": "p", "config": {}})
        assert out == "line1\nline2"
        # 自动选用唯一容器名
        _, kwargs = fake_core.read_namespaced_pod_log.call_args
        assert kwargs["container"] == "only"
        assert kwargs["tail_lines"] == 100

    def test_empty_logs_message(self, fake_core):
        fake_core.read_namespaced_pod.return_value = self._pod_with_containers(["only"])
        fake_core.read_namespaced_pod_log.return_value = ""
        out = res.get_kubernetes_pod_logs.invoke({"namespace": "ns", "pod_name": "p", "config": {}})
        assert "没有日志输出" in out

    def test_head_mode_truncates(self, fake_core):
        fake_core.read_namespaced_pod.return_value = self._pod_with_containers(["only"])
        fake_core.read_namespaced_pod_log.return_value = "l1\nl2\nl3\nl4"
        out = res.get_kubernetes_pod_logs.invoke(
            {"namespace": "ns", "pod_name": "p", "lines": 2, "tail": False, "config": {}}
        )
        assert out == "l1\nl2"

    def test_container_creating_message(self, fake_core):
        fake_core.read_namespaced_pod.return_value = self._pod_with_containers(["only"])
        fake_core.read_namespaced_pod_log.side_effect = ApiException(status=400, reason="ContainerCreating")
        out = res.get_kubernetes_pod_logs.invoke(
            {"namespace": "ns", "pod_name": "p", "container": "only", "config": {}}
        )
        assert "正在创建中" in out
