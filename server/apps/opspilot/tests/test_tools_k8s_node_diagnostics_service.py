"""Kubernetes Node 深度诊断 @tool 单元测试 (kubernetes/node_diagnostics)。

mock prepare_context 与 client.CoreV1Api,用 SimpleNamespace 构造 V1Node + 节点上
的 Pod 列表,覆盖 healthy / warning / critical 三态判定、压力 Condition、Taint /
Cordon、资源利用率与碎片化、Pod 容量预警、节点角色解析、404 与异常包装。
不连真实集群。
"""

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pydantic.root_model  # noqa
import pytest
from kubernetes.client import ApiException

from apps.opspilot.metis.llm.tools.kubernetes import node_diagnostics as nd


@pytest.fixture
def core():
    c = MagicMock()
    with patch.object(nd, "prepare_context", return_value=None), \
         patch.object(nd.client, "CoreV1Api", return_value=c):
        yield c


def _cond(type_, status="True", reason="r", message="m"):
    return SimpleNamespace(type=type_, status=status, reason=reason, message=message,
                           last_transition_time=datetime(2024, 1, 1, tzinfo=timezone.utc))


def _node(conditions=None, taints=None, unschedulable=False, allocatable=None,
          node_info=None, labels=None):
    return SimpleNamespace(
        metadata=SimpleNamespace(name="n1", labels=labels),
        spec=SimpleNamespace(unschedulable=unschedulable, taints=taints),
        status=SimpleNamespace(
            conditions=conditions,
            allocatable=allocatable if allocatable is not None
            else {"cpu": "8", "memory": "16Gi", "pods": "110"},
            node_info=node_info,
        ),
    )


def _pod(name="p", ns="default", phase="Running", cpu=None, mem=None, node="n1"):
    container = SimpleNamespace(resources=SimpleNamespace(
        requests={"cpu": cpu, "memory": mem} if cpu or mem else None))
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name, namespace=ns),
        status=SimpleNamespace(phase=phase),
        spec=SimpleNamespace(node_name=node, containers=[container]),
    )


def _items(lst):
    return SimpleNamespace(items=lst)


def _run(core, node, pods=None):
    core.read_node.return_value = node
    core.list_pod_for_all_namespaces.return_value = _items(pods or [])
    return json.loads(nd.diagnose_node_issues.invoke(
        {"node_name": "n1", "config": {}}))


class TestNodeDiagnostics:
    def test_healthy_node(self, core):
        node = _node(conditions=[_cond("Ready", "True")],
                     node_info=SimpleNamespace(
                         os_image="ubuntu", kernel_version="5.x",
                         container_runtime_version="containerd://1",
                         kubelet_version="v1.28", kube_proxy_version="v1.28",
                         architecture="amd64"),
                     labels={"node-role.kubernetes.io/control-plane": ""})
        out = _run(core, node, [_pod(cpu="1", mem="1Gi")])
        assert out["health_status"] == "healthy"
        assert out["node_info"]["roles"] == ["control-plane"]
        assert out["resource_analysis"]["allocated"]["cpu"] == 1.0
        assert out["pod_summary"]["total_pods"] == 1

    def test_not_ready_is_critical(self, core):
        node = _node(conditions=[_cond("Ready", "False", reason="KubeletDown")])
        out = _run(core, node)
        assert out["health_status"] == "critical"
        assert any(i["category"] == "node_health" for i in out["issues"])

    def test_disk_pressure_recommendation(self, core):
        node = _node(conditions=[_cond("Ready", "True"),
                                 _cond("DiskPressure", "True")])
        out = _run(core, node)
        assert out["health_status"] == "critical"
        assert any("磁盘" in r for r in out["recommendations"])

    def test_memory_and_pid_pressure(self, core):
        node = _node(conditions=[_cond("Ready", "True"),
                                 _cond("MemoryPressure", "True"),
                                 _cond("PIDPressure", "True")])
        out = _run(core, node)
        cats = [i["category"] for i in out["issues"]]
        assert cats.count("resource_pressure") == 2

    def test_network_unavailable(self, core):
        node = _node(conditions=[_cond("Ready", "True"),
                                 _cond("NetworkUnavailable", "True")])
        out = _run(core, node)
        assert any(i["category"] == "network" for i in out["issues"])

    def test_taints_and_cordon(self, core):
        taint = SimpleNamespace(key="dedicated", value="gpu", effect="NoSchedule")
        node = _node(conditions=[_cond("Ready", "True")], taints=[taint],
                     unschedulable=True)
        out = _run(core, node)
        assert out["is_cordoned"] is True
        assert out["taints"][0]["description"] == "dedicated=gpu:NoSchedule"
        cats = [i["category"] for i in out["issues"]]
        assert "scheduling" in cats  # taint + cordon both add scheduling issues

    def test_high_cpu_utilization_warning(self, core):
        # allocatable 1 cpu, pod requests 0.95 -> 95% utilization
        node = _node(conditions=[_cond("Ready", "True")],
                     allocatable={"cpu": "1", "memory": "1Gi", "pods": "110"})
        out = _run(core, node, [_pod(cpu="950m", mem="100Mi")])
        assert out["resource_analysis"]["utilization_percent"]["cpu"] > 90
        assert out["health_status"] == "warning"
        assert any(i["category"] == "capacity" for i in out["issues"])

    def test_pod_capacity_nearly_exhausted(self, core):
        node = _node(conditions=[_cond("Ready", "True")],
                     allocatable={"cpu": "100", "memory": "100Gi", "pods": "5"})
        pods = [_pod(name=f"p{i}", cpu="10m", mem="10Mi") for i in range(3)]
        out = _run(core, node, pods)
        # available pods = 5 - 3 = 2 < 10 -> warning issue
        assert any("Pod容量" in i["message"] for i in out["issues"])

    def test_succeeded_pods_not_counted(self, core):
        node = _node(conditions=[_cond("Ready", "True")])
        pods = [_pod(name="done", phase="Succeeded", cpu="1", mem="1Gi"),
                _pod(name="live", phase="Running", cpu="1", mem="1Gi")]
        out = _run(core, node, pods)
        assert out["pod_summary"]["total_pods"] == 1

    def test_node_not_found_404(self, core):
        core.read_node.side_effect = ApiException(status=404)
        out = json.loads(nd.diagnose_node_issues.invoke(
            {"node_name": "ghost", "config": {}}))
        assert "Node不存在" in out["error"]

    def test_generic_exception_wrapped(self, core):
        core.read_node.side_effect = RuntimeError("boom")
        out = json.loads(nd.diagnose_node_issues.invoke(
            {"node_name": "n1", "config": {}}))
        assert "诊断Node失败" in out["error"]
        assert out["node_name"] == "n1"
